"""Exercise self-describing launcher mod packages end to end."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import zlib

_HERE = Path(__file__).resolve().parent
for _folder in (_HERE.parent / 'MirrorOfSkin/Workbench', _HERE.parent / 'MirrorOfSkin/Workbench/core'):
    if _folder.is_dir():
        sys.path.append(str(_folder))

import mod_packages
import skin_import


MAGIC = b'UnityFS\0' + b'\0\0'


def png(colour=b'\xff\x00\x00'):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>II5B', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0' + colour))
            + chunk(b'IEND', b''))


class ModPackageTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.addon = self.base / 'addons' / 'MOS'
        self.addon.mkdir(parents=True)
        self.mods = self.base / 'mods'
        self.mods.mkdir()

    def package(self, key='roland', *, info=None, manifest=None, bundle_names=('BRoland.bundle',),
                icon=True):
        folder = self.mods / key
        (folder / 'bundles').mkdir(parents=True)
        for name in bundle_names:
            target = folder / 'bundles' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(MAGIC + name.encode())
        if icon:
            (folder / 'icon.png').write_bytes(png())
        document = {
            'name': '罗兰', 'desc': '测试包', 'authors': {'作者': 'https://example.invalid'},
            'version': '1.0.0', 'settings': {'enable': True}, 'file_names': [], 'requires': ['MOS'],
        }
        document.update(info or {})
        (folder / mod_packages.INFO).write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
        contract = {
            'schema': 1, 'id': key, 'name': '罗兰', 'version': '1.0.0', 'strategy': 'bundles',
            'identity': 'story_BRolandBaseAppearance', 'icon': 'icon.png',
            'bundles': ['bundles/' + name for name in bundle_names],
        }
        contract.update(manifest or {})
        (folder / mod_packages.MANIFEST).write_text(json.dumps(contract, ensure_ascii=False), encoding='utf-8')
        return folder

    def test_scan_reports_ready_disabled_and_invalid_packages(self):
        self.package('roland')
        self.package('disabled', info={'name': '停用包', 'settings': {'enable': False}})
        self.package('broken', info={'requires': ['WarpHook']})
        self.package('traversal', manifest={'bundles': ['../escape.bundle']})

        items = {item['key']: item for item in mod_packages.scan(self.addon)}
        self.assertEqual(items['roland']['status'], 'ready')
        self.assertEqual(items['roland']['identity'], 'story_BRolandBaseAppearance')
        self.assertTrue(items['roland']['icon'])
        self.assertEqual(items['disabled']['status'], 'disabled')
        self.assertIn('启用', items['disabled']['error'])
        self.assertEqual(items['broken']['status'], 'invalid')
        self.assertIn('MOS', items['broken']['error'])
        self.assertEqual(items['traversal']['status'], 'invalid')

    def test_find_and_icon_are_confined_to_the_scanned_package(self):
        folder = self.package('roland')
        self.assertIsNotNone(mod_packages.find(self.addon, 'roland'))
        for key in ('../roland', 'roland/../roland', '', '.', '..', 'missing'):
            self.assertIsNone(mod_packages.find(self.addon, key), key)
        self.assertEqual(mod_packages.icon_bytes(self.addon, 'roland'), (folder / 'icon.png').read_bytes())
        self.assertIsNone(mod_packages.icon_bytes(self.addon, 'missing'))

    def test_find_rejects_a_duplicate_package_id(self):
        self.package('roland')
        duplicate = self.package('copy')
        contract = json.loads((duplicate / mod_packages.MANIFEST).read_text(encoding='utf-8'))
        contract['id'] = 'roland'
        (duplicate / mod_packages.MANIFEST).write_text(json.dumps(contract, ensure_ascii=False), encoding='utf-8')
        self.assertEqual(mod_packages.find(self.addon, 'roland')['status'], 'invalid')
        self.assertEqual(mod_packages.find(self.addon, 'copy')['status'], 'invalid')

    def test_manifest_rejects_unsafe_paths_and_non_unity_payloads(self):
        cases = {
            'absolute': {'bundles': ['C:/escape.bundle']},
            'nested': {'bundles': ['bundles/extra/model.bundle']},
            'duplicate': {'bundles': ['bundles/BRoland.bundle', 'bundles/BRoland.bundle']},
            'unknown': {'strategy': 'merge'},
            'bad_id': {'id': 'Roland'},
            'bad_identity': {'identity': 'story_Someone'},
        }
        for key, manifest in cases.items():
            with self.subTest(key=key):
                self.package(key, manifest=manifest,
                             bundle_names=('BRoland.bundle', 'extra/model.bundle')
                             if key == 'nested' else ('BRoland.bundle',))
                item = mod_packages.find(self.addon, key)
                self.assertEqual(item['status'], 'invalid', key)

        folder = self.package('badmagic')
        (folder / 'bundles' / 'BRoland.bundle').write_bytes(b'not a bundle')
        self.assertEqual(mod_packages.find(self.addon, 'badmagic')['status'], 'invalid')

        folder = self.package('badicon')
        (folder / 'icon.png').write_bytes(b'not a png')
        self.assertEqual(mod_packages.find(self.addon, 'badicon')['status'], 'invalid')

    def test_prepared_archive_uses_stable_name_and_carries_portrait(self):
        self.package('roland', bundle_names=('BRoland.bundle', 'BRolandGun.bundle'))
        with patch('mos_data.data_dir', return_value=self.base / 'empty-profile'):
            with mod_packages.prepared_archive(self.addon, 'roland') as prepared:
                self.assertEqual(prepared.archive.name, 'roland.zip')
                with ZipFile(prepared.archive) as archive:
                    names = set(archive.namelist())
                    self.assertEqual(names, {
                        'custom_appearance/BRoland.bundle', 'custom_appearance/BRolandGun.bundle',
                        'mos-portraits.json', 'mos_portraits/story_BRolandBaseAppearance.png',
                    })
                    self.assertEqual(json.loads(archive.read('mos-portraits.json'))['portraits'],
                                     {'story_BRolandBaseAppearance':
                                      'mos_portraits/story_BRolandBaseAppearance.png'})
                    self.assertTrue(archive.read(
                        'mos_portraits/story_BRolandBaseAppearance.png').startswith(b'\x89PNG'))
                self.assertIsNone(prepared.portrait)
                self.assertEqual(prepared.source, 'roland')
                self.assertEqual(prepared.version, '1.0.0')
                self.assertEqual(prepared.name, '罗兰')
        self.assertFalse(prepared.archive.exists())
        portrait = mod_packages._portrait(self.mods / 'roland' / 'icon.png')
        self.assertTrue(portrait.startswith(b'\x89PNG'))
        self.assertLessEqual(len(portrait), 1024 * 1024)

    def test_undeclared_identity_returns_default_portrait(self):
        self.package('plain', manifest={'identity': None})
        with mod_packages.prepared_archive(self.addon, 'plain') as prepared:
            self.assertEqual(prepared.portrait[1:4], b'PNG')
            self.assertEqual(prepared.source, 'plain')
            with ZipFile(prepared.archive) as archive:
                self.assertNotIn('mos-portraits.json', archive.namelist())

    def test_declared_identity_adopts_a_previously_imported_archive(self):
        import import_packages
        from uuid import uuid4

        self.package('roland')
        data = self.base / 'profile'
        library = uuid4().hex
        package_id = uuid4().hex
        folder = self.addon / import_packages.DIRECTORY / 'roland'
        folder.mkdir(parents=True)
        (folder / 'BRoland.bundle').write_bytes(b'bundle')
        import_packages._write_marker(folder / import_packages.MARKER, package_id)
        import_packages.write_index(data, {
            'schema': 1, 'library': library,
            'packages': [{'id': package_id, 'source': 'roland.7z', 'directory': 'roland',
                          'identities': ['story_BRolandBaseAppearance']}],
        })
        import_packages._write_marker(
            self.addon / import_packages.DIRECTORY / import_packages.LIBRARY_MARKER, library)
        package, reserved, encoded, created = import_packages.prepare_package(
            data, self.addon, 'roland', {'story_BRolandBaseAppearance'},
            source_kind='mod', source_name='罗兰', source_version='1.0.0')
        self.assertFalse(created)
        self.assertEqual(package['source'], 'roland')
        self.assertEqual(package['source_kind'], 'mod')
        self.assertEqual(package['source_name'], '罗兰')
        self.assertEqual(package['source_version'], '1.0.0')
        self.assertEqual(package['directory'], 'roland')
        self.assertEqual(json.loads(encoded)['packages'][0]['source'], 'roland')

    def test_unchanged_rows_skips_a_complete_package_at_the_same_version(self):
        import import_packages
        from uuid import uuid4

        self.package('roland')
        data = self.base / 'profile'
        folder = self.addon / import_packages.DIRECTORY / 'roland'
        folder.mkdir(parents=True)
        (folder / 'BRoland.bundle').write_bytes(b'bundle')
        import_packages.write_index(data, {
            'schema': 1, 'library': uuid4().hex,
            'packages': [{'id': uuid4().hex, 'source': 'roland', 'source_kind': 'mod',
                          'source_name': '罗兰', 'source_version': '1.0.0',
                          'directory': 'roland',
                          'identities': ['story_BRolandBaseAppearance']}],
        })
        locator = data / 'Assets/ImportedSkins/BRolandBaseAppearance.loc'
        locator.parent.mkdir(parents=True, exist_ok=True)
        locator.write_text('imported-appearance/roland/BRoland.bundle', encoding='utf-8')
        catalog = data / skin_import.CATALOG
        catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps({'101': {'entries': [
            {'identity_id': 'story_BRolandBaseAppearance', 'name': '罗兰·漆黑缄默'}]}}),
            encoding='utf-8')
        item = mod_packages.find(self.addon, 'roland')
        with patch('mos_data.data_dir', return_value=data):
            rows = mod_packages.unchanged_rows(self.addon, item)
        self.assertIsNotNone(rows)
        self.assertEqual(rows[0]['status'], 'existing')
        self.assertTrue(rows[0]['unchanged'])
        self.assertEqual(rows[0]['version'], '1.0.0')
        self.assertEqual(rows[0]['name'], '罗兰·漆黑缄默')

        item['version'] = '1.0.1'
        with patch('mos_data.data_dir', return_value=data):
            self.assertIsNone(mod_packages.unchanged_rows(self.addon, item))
        (folder / 'BRoland.bundle').unlink()
        item['version'] = '1.0.0'
        with patch('mos_data.data_dir', return_value=data):
            self.assertIsNone(mod_packages.unchanged_rows(self.addon, item))


class DefaultPortraitTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        catalog = self.root / skin_import.CATALOG
        catalog.parent.mkdir(parents=True)
        catalog.write_text('{"101":{"entries":[]}}')
        (self.root / 'compatibility.json').write_text('{"local_skin_import":1}')
        self.archive = self.root / 'mod.zip'
        with ZipFile(self.archive, 'w') as container:
            container.writestr('custom_appearance/model.bundle', b'dummy')
        self.look = 'WBImp_' + 'a' * 24
        self.identity = 'story_' + self.look
        self.image = png()
        self.record = {
            'look': self.look, 'bundle': b'bundle', 'timing': b'timing',
            'entry': {'identity_id': self.identity, 'appearance_name': self.look,
                      'sinner': '101', 'name': '导入模型'},
            'actions': {'runtime_roles': {}, 'runtime_animator': []},
            'dependency': 'SD_Personality/A.prefab', 'asset': 'assets/A.prefab', 'layout': 'Standard',
        }

    def test_default_portrait_is_bound_to_the_single_produced_identity(self):
        with patch('skin_assets.build_assets', return_value=[self.record]):
            rows = skin_import._import_normalized(self.archive, self.root, unity=object(),
                                                  default_portrait=self.image)
        self.assertEqual(rows[0]['identity_id'], self.identity)
        written = self.root / 'Workbench/imported_portraits' / (self.identity + '.png')
        self.assertEqual(written.read_bytes(), self.image)

    def test_default_portrait_rejects_ambiguous_imports(self):
        second = dict(self.record, look='WBImp_' + 'b' * 24,
                      entry=dict(self.record['entry'], identity_id='story_WBImp_' + 'b' * 24,
                                 appearance_name='WBImp_' + 'b' * 24))
        with patch('skin_assets.build_assets', return_value=[self.record, second]):
            with self.assertRaisesRegex(ValueError, 'identity'):
                skin_import._import_normalized(self.archive, self.root, unity=object(),
                                               default_portrait=self.image)


if __name__ == '__main__':
    unittest.main()