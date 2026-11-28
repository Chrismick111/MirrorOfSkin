import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))
import workbench
import resource_catalog
import scan_units


class ResourceCatalogTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.game = self.root / 'game'
        self.game.mkdir()
        self.index = self.root / 'index'

    def bundle(self, root, name):
        path = root / name / 'content' / '__data'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'initial')
        return path

    def unity(self):
        def open_bundle(path):
            prefab = Path(path).parents[1].name
            address = 'Assets/Resources_moved/Prefab/SD/Example/' + prefab + '.prefab'
            return SimpleNamespace(container={address: object()})

        return SimpleNamespace(load=Mock(side_effect=open_bundle))

    def test_scan_respects_config_environment_and_explicit_cache(self):
        configured, environmental, explicit, automatic = [self.root / name for name in
                                                            ('configured', 'environment', 'explicit', 'automatic')]
        for folder in (configured, environmental, explicit, automatic):
            folder.mkdir()
        with patch.object(resource_catalog, 'DATA', self.root), patch.dict(os.environ, {}, clear=True), \
                patch.object(resource_catalog, 'find_resource_root', return_value=automatic):
            resource_catalog.write_config({'resource_root': configured})
            self.assertEqual(scan_units.cache_root(self.game), configured)
            with patch.dict(os.environ, {resource_catalog.ENV_RESOURCE: str(environmental)}):
                self.assertEqual(scan_units.cache_root(self.game), environmental)
                self.assertEqual(scan_units.cache_root(self.game, explicit), explicit)
                self.assertIsNone(scan_units.cache_root(self.game, self.root / 'missing-explicit'))
            with patch.dict(os.environ, {resource_catalog.ENV_RESOURCE: str(self.root / 'missing-env')}):
                self.assertIsNone(scan_units.cache_root(self.game))
            resource_catalog.write_config({'resource_root': self.root / 'missing-config'})
            self.assertIsNone(scan_units.cache_root(self.game))
            resource_catalog.write_config({'resource_root': None})
            self.assertEqual(scan_units.cache_root(self.game), automatic)
            (self.root / resource_catalog.CONFIG_NAME).unlink()
            migrated = self.root / 'Workbench'
            migrated.mkdir()
            resource_catalog.write_config({'resource_root': configured}, root=migrated)
            self.assertEqual(scan_units.cache_root(self.game), configured)

    def test_rescan_only_reopens_changed_bundles(self):
        cache = self.root / 'cache'
        stable = self.bundle(cache, 'Stable')
        changed = self.bundle(cache, 'Changed')
        unity = self.unity()
        first = resource_catalog.build_index(cache, self.index, unity_py=unity)
        self.assertEqual(unity.load.call_count, 2)
        unity.load.reset_mock()
        changed.write_bytes(b'larger, new edition')
        second = resource_catalog.build_index(cache, self.index, unity_py=unity)
        unity.load.assert_called_once_with(str(changed))
        stable_rel = stable.relative_to(cache).as_posix()
        self.assertEqual(first['entries'][stable_rel], second['entries'][stable_rel])

    def test_migrates_unversioned_scan_state_from_matching_index(self):
        cache = self.root / 'cache'
        self.bundle(cache, 'Stable')
        unity = self.unity()
        old_index = resource_catalog.build_index(cache, self.index, unity_py=unity)
        _, state_file = resource_catalog.index_paths(self.index)
        state_file.write_text(json.dumps(old_index['entries']), encoding='utf-8')
        unity.load.reset_mock()
        self.assertEqual(old_index, resource_catalog.build_index(cache, self.index, unity_py=unity))
        unity.load.assert_not_called()
        self.assertEqual(json.loads(state_file.read_bytes()), old_index['entries'])

    def test_cache_from_a_different_root_cannot_supply_entries(self):
        cache = self.root / 'cache'
        self.bundle(cache, 'Same')
        other = self.root / 'other-cache'
        other_bundle = self.bundle(other, 'Same')
        unity = self.unity()
        with patch.object(resource_catalog, 'fingerprint', return_value=[7, 42]):
            resource_catalog.build_index(cache, self.index, unity_py=unity)
            unity.load.reset_mock()
            resource_catalog.build_index(other, self.index, unity_py=unity)
        unity.load.assert_called_once_with(str(other_bundle))

    def test_dropped_index_entry_and_failed_bundle_are_reopened(self):
        cache = self.root / 'cache'
        self.bundle(cache, 'Stable')
        dropped = self.bundle(cache, 'Dropped')
        failed = self.bundle(cache, 'Failed')
        unity = self.unity()
        normal_load = unity.load.side_effect

        def load(path):
            if path == str(failed):
                raise OSError('temporarily unreadable')
            return normal_load(path)

        unity.load.side_effect = load
        index = resource_catalog.build_index(cache, self.index, unity_py=unity)
        self.assertEqual(index['failure_count'], 1)
        index_file, _ = resource_catalog.index_paths(self.index)
        del index['entries'][dropped.relative_to(cache).as_posix()]
        index_file.write_text(json.dumps(index), encoding='utf-8')
        unity.load.reset_mock()
        unity.load.side_effect = normal_load
        result = resource_catalog.build_index(cache, self.index, unity_py=unity)
        self.assertEqual(result['failure_count'], 0)
        self.assertEqual([call.args[0] for call in unity.load.call_args_list], [str(dropped), str(failed)])

    def write_catalog(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        records = [b'\0' + name.encode('ascii') + b'.prefab' + struct.pack('<I', len(group))
                   + group.encode('ascii') + b'\0' for name, group in rows]
        path.write_bytes(b''.join(records))

    def test_discovery_uses_the_current_games_downloaded_catalog(self):
        install = self.game / 'LimbusCompany_Data'
        install.mkdir()
        (install / 'app.info').write_text('ProjectMoon\nLimbusCompany\n', encoding='utf-8')
        self.write_catalog(install / 'StreamingAssets/aa/catalog.bin', [
            ('SameAppearance', 'SD_Personality'), ('ConflictingAppearance', 'SD_Enemy'),
        ])
        profile = self.root / 'active-profile'
        downloaded = profile / 'AppData/LocalLow/ProjectMoon/LimbusCompany/com.unity.addressables'
        self.write_catalog(downloaded / 'catalog_S1.bin', [
            ('NewAppearance', 'SD_Abnormality'), ('SameAppearance', 'SD_Personality'),
            ('ConflictingAppearance', 'SD_Personality'),
        ])
        other = profile / 'AppData/LocalLow/ProjectMoon/OtherGame/com.unity.addressables'
        self.write_catalog(other / 'catalog_S1.bin', [('OtherGameAppearance', 'SD_Enemy')])
        with patch.dict(os.environ, {'USERPROFILE': str(profile)}, clear=True):
            groups = scan_units.catalog_groups(self.game)
        self.assertEqual(groups, {'SameAppearance': 'SD_Personality', 'NewAppearance': 'SD_Abnormality',
                                  'ConflictingAppearance': None})

    def test_configured_catalog_changes_discovery_and_scan_hash(self):
        install = self.game / 'LimbusCompany_Data/StreamingAssets/aa'
        self.write_catalog(install / 'catalog.bin', [('OriginalAppearance', 'SD_Personality')])
        (install / 'catalog.hash').write_text('base', encoding='ascii')
        custom = self.root / 'custom-catalog'
        self.write_catalog(custom / 'catalog_S1.bin', [('DownloadedAppearance', 'SD_Enemy')])
        downloaded_hash = custom / 'catalog_S1.hash'
        downloaded_hash.write_text('before', encoding='ascii')
        with patch.dict(os.environ, {'LIMBUS_ADDRESSABLE_CATALOG_DIR': str(custom)}, clear=True):
            self.assertEqual(scan_units.catalog_groups(self.game)['DownloadedAppearance'], 'SD_Enemy')
            before = scan_units.catalog_hash(self.game)
            downloaded_hash.write_text('after', encoding='ascii')
            self.assertNotEqual(scan_units.catalog_hash(self.game), before)
        with patch.dict(os.environ, {'LIMBUS_ADDRESSABLE_CATALOG_DIR': str(self.root / 'missing')}, clear=True):
            self.assertEqual(scan_units.catalog_groups(self.game), {'OriginalAppearance': 'SD_Personality'})
            self.assertEqual(scan_units.catalog_hash(self.game), 'base')


if __name__ == '__main__':
    unittest.main()
