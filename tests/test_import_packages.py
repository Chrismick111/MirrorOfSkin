"""Exercise package folders and stable identifiers through the production importer."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile


_HERE = Path(__file__).resolve().parent
for _folder in (_HERE.parent / 'MirrorOfSkin/Workbench', _HERE):
    if _folder.is_dir():
        sys.path.append(str(_folder))

import import_packages
import skin_import
from package_lifecycle import synchronize


def record(digit, content=b'textured model'):
    look = 'WBImp_' + digit * 24
    return {
        'look': look, 'bundle': content, 'timing': b'timing',
        'entry': {'identity_id': 'story_' + look, 'appearance_name': look,
                  'sinner': '101', 'name': '导入模型'},
        'actions': {'runtime_roles': {}, 'runtime_animator': []},
        'dependency': 'SD_Personality/test.prefab', 'asset': 'assets/test.prefab', 'layout': 'test',
    }


class ImportPackageTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.data = self.base / 'metadata'
        self.addon = self.base / 'addon'
        self.data.mkdir()
        self.addon.mkdir()
        catalog = self.data / skin_import.CATALOG
        catalog.parent.mkdir(parents=True)
        catalog.write_text('{"101":{"entries":[]}}', encoding='utf-8')
        (self.data / 'compatibility.json').write_text('{"local_skin_import":1}', encoding='utf-8')
        self.archive = self.base / 'ignored.zip'
        with ZipFile(self.archive, 'w') as container:
            container.writestr('model.bundle', b'dummy')

    def convert(self, filename, *records):
        with patch('skin_assets.build_assets', return_value=iter(records)):
            return skin_import._import_normalized(self.archive, self.data, unity=object(),
                                                   package_addon=self.addon, package_source=filename)

    def test_folder_keeps_real_models_and_multiple_stable_identities(self):
        rows = self.convert('测试压缩包.zip', record('a'), record('b'))
        expected = self.addon / '外来外观' / '测试压缩包'
        self.assertEqual([Path(row['package_directory']) for row in rows], [expected] * 2)
        self.assertEqual(len(list(expected.glob('*.bundle'))), 1)
        self.assertFalse(list((self.data / skin_import.LOCAL).glob('*.bundle')))
        for row in rows:
            locator = import_packages.locator_path(self.data, row['identity_id'])
            target = self.addon / locator.read_text('utf-8')
            self.assertEqual(target.read_bytes(), b'textured model')
        rows = self.convert('测试压缩包.zip', record('a'), record('b'))
        self.assertEqual([row['status'] for row in rows], ['existing', 'existing'])
        self.assertEqual(len(import_packages.read_index(self.data)['packages']), 1)

    def test_unrelated_same_name_and_known_asset_update(self):
        a, = self.convert('同名.zip', record('a', b'a'))
        b, = self.convert('同名.zip', record('b', b'b'))
        self.assertEqual(Path(a['package_directory']).name, '同名')
        self.assertEqual(Path(b['package_directory']).name, '同名 (2)')
        updated, = self.convert('同名.zip', record('a', b'c'))
        self.assertEqual(updated['status'], 'updated')
        self.assertEqual(a['package_directory'], updated['package_directory'])
        locator = import_packages.locator_path(self.data, updated['identity_id'])
        self.assertTrue(locator.read_text('utf-8').endswith(hashlib.sha256(b'c').hexdigest() + '.bundle'))
        self.assertEqual(len(list(Path(a['package_directory']).glob('*.bundle'))), 1)

    def test_update_keeps_shared_revision_and_does_not_transfer_ownership(self):
        a, _ = self.convert('同一包.zip', record('a'), record('b'))
        self.convert('同一包.zip', record('a', b'revised'))
        self.assertEqual(len(list(Path(a['package_directory']).glob('*.bundle'))), 2)
        with self.assertRaisesRegex(ValueError, '已归属'):
            self.convert('意外重名.zip', record('b'))
        self.assertEqual(len(import_packages.read_index(self.data)['packages']), 1)

    def test_failed_new_import_leaves_no_registered_folder(self):
        with patch.object(skin_import, 'write_atomic', side_effect=OSError('simulated disk error')):
            with self.assertRaisesRegex(OSError, 'simulated disk error'):
                self.convert('失败.zip', record('a'))
        parent = import_packages.managed_root(self.addon)
        self.assertFalse((parent / '失败').exists())
        self.assertEqual(import_packages.read_index(self.data)['packages'], [])

    def test_reinstall_preserves_catalog_and_can_restore_one_of_two_identities(self):
        first, second = self.convert('一个包.zip', record('a'), record('b'))
        catalog = self.data / skin_import.CATALOG
        snapshot = json.loads(catalog.read_bytes())
        snapshot['101']['entries'][0].update(enabled=False, weight=37)
        catalog.write_bytes(skin_import.encode(snapshot))
        rules = self.data / '自定义人格池.json'
        rules.write_bytes(skin_import.encode({'entries': [{'identity_id': second['identity_id']}]}))
        old_library = import_packages.read_library(self.addon)
        managed = import_packages.managed_root(self.addon)
        managed.rename(self.addon / 'old-library')
        managed.mkdir()

        result = synchronize(self.data, self.addon)
        self.assertEqual((result['removed'], result['blocked']), ([], []))
        self.assertEqual(json.loads(catalog.read_bytes()), snapshot)
        self.assertNotEqual(import_packages.read_library(self.addon), old_library)
        self.assertEqual(import_packages.read_index(self.data)['packages'][0]['missing_identities'],
                         sorted([first['identity_id'], second['identity_id']]))

        self.convert('新包.zip', record('c'))
        restored, = self.convert('一个包.zip', record('a'))
        self.assertEqual(restored['status'], 'updated')
        self.assertFalse(synchronize(self.data, self.addon)['removed'])
        package = import_packages.read_index(self.data)['packages'][0]
        self.assertEqual(package['missing_identities'], [second['identity_id']])
        self.assertEqual(package['identities'], sorted([first['identity_id'], second['identity_id']]))
        self.assertEqual(json.loads(rules.read_bytes())['entries'], [{'identity_id': second['identity_id']}])
        restored_entry = json.loads(catalog.read_bytes())['101']['entries'][0]
        self.assertEqual((restored_entry['enabled'], restored_entry['weight']), (False, 37))
        locator = import_packages.locator_path(self.data, first['identity_id'])
        model = self.addon / locator.read_text('utf-8')
        self.assertTrue(model.is_file())
        model.unlink()
        (model.parent / import_packages.MARKER).unlink()
        model.parent.rmdir()
        self.assertEqual(synchronize(self.data, self.addon)['removed'],
                         [{'directory': '一个包', 'identities': [first['identity_id']]}])
        package = import_packages.read_index(self.data)['packages'][0]
        self.assertEqual(package['identities'], [second['identity_id']])
        self.assertTrue(import_packages.locator_path(self.data, second['identity_id']).exists())
        self.assertEqual(json.loads(rules.read_bytes())['entries'], [{'identity_id': second['identity_id']}])

    def test_reinstall_retry_and_returning_old_library(self):
        old, = self.convert('旧包.zip', record('a'))
        old_library = import_packages.read_library(self.addon)
        managed = import_packages.managed_root(self.addon)
        backup = managed.rename(self.addon / 'old-library')
        with patch.object(skin_import, 'write_atomic', side_effect=OSError('simulated disk error')):
            with self.assertRaisesRegex(OSError, 'simulated disk error'):
                self.convert('旧包.zip', record('a'))
        packages = import_packages.read_index(self.data)['packages']
        self.assertEqual(packages[0]['missing_identities'], [old['identity_id']])
        self.assertFalse((managed / packages[0]['directory']).exists())
        self.convert('新包.zip', record('b'))
        current = managed.rename(self.addon / 'new-library')
        backup.rename(managed)
        result = synchronize(self.data, self.addon)
        self.assertEqual((result['removed'], result['blocked']), ([], []))
        self.assertEqual(import_packages.read_library(self.addon), old_library)
        packages = import_packages.read_index(self.data)['packages']
        self.assertNotIn('missing_identities', packages[0])
        self.assertEqual(packages[1]['missing_identities'], packages[1]['identities'])
        managed.rename(backup)
        current.rename(managed)
        self.assertFalse(synchronize(self.data, self.addon)['removed'])
        packages = import_packages.read_index(self.data)['packages']
        self.assertEqual(packages[0]['missing_identities'], packages[0]['identities'])
        self.assertNotIn('missing_identities', packages[1])

    def test_rebuild_retry_resumes_after_index_is_written(self):
        imported, = self.convert('一个包.zip', record('a'))
        managed = import_packages.managed_root(self.addon)
        managed.rename(self.addon / 'old-library')
        with patch.object(import_packages, '_write_marker', side_effect=OSError('simulated marker error')):
            result = synchronize(self.data, self.addon)
        self.assertIn('simulated marker error', result['blocked'][0]['error'])
        interrupted = import_packages.read_index(self.data)
        self.assertTrue(interrupted['creating_library'])
        self.assertIsNone(import_packages.read_library(self.addon))
        self.assertFalse(synchronize(self.data, self.addon)['blocked'])
        self.assertEqual(import_packages.read_library(self.addon), interrupted['library'])
        self.assertNotIn('creating_library', import_packages.read_index(self.data))

        self.convert('一个包.zip', record('a'))
        old_library = import_packages.read_library(self.addon)
        managed.rename(self.addon / 'second-library')
        self.assertFalse(synchronize(self.data, self.addon)['removed'])
        self.assertNotEqual(import_packages.read_library(self.addon), old_library)
        package = import_packages.read_index(self.data)['packages'][0]
        self.assertEqual(package['missing_identities'], [imported['identity_id']])

    def test_restored_index_can_adopt_library_initialized_before_restore(self):
        imported, = self.convert('一个包.zip', record('a'))
        managed = import_packages.managed_root(self.addon)
        managed.rename(self.addon / 'old-library')
        fresh_profile = self.base / 'fresh-profile'
        fresh_profile.mkdir()
        fresh_library = import_packages.ensure_library(fresh_profile, self.addon)
        marker = managed / import_packages.LIBRARY_MARKER
        before = marker.read_bytes()

        result = synchronize(self.data, self.addon)
        self.assertEqual((result['removed'], result['blocked']), ([], []))
        index = import_packages.read_index(self.data)
        self.assertEqual(index['library'], fresh_library)
        self.assertEqual(index['packages'][0]['missing_identities'], [imported['identity_id']])
        self.assertEqual(marker.read_bytes(), before)
        restored, = self.convert('一个包.zip', record('a'))
        self.assertEqual(restored['status'], 'updated')

    def test_fresh_profile_can_use_an_existing_marked_library(self):
        imported, = self.convert('已安装包.zip', record('a'))
        observed = import_packages.read_library(self.addon)
        model = Path(imported['package_directory'])
        fresh_profile = self.base / 'fresh-profile'
        fresh_profile.mkdir()

        self.assertEqual(import_packages.ensure_library(fresh_profile, self.addon), observed)
        self.assertEqual(import_packages.read_index(fresh_profile)['packages'], [])
        self.assertEqual(len(list(model.glob('*.bundle'))), 1)

    def test_nonempty_library_replacement_keeps_other_installation_identity(self):
        self.convert('一个包.zip', record('a'))
        managed = import_packages.managed_root(self.addon)
        self.assertEqual(import_packages.read_library(self.addon),
                         import_packages.read_index(self.data)['library'])
        managed.rename(self.addon / 'renamed')
        managed.mkdir()
        (managed / 'untouched.txt').write_bytes(b'unrelated')
        self.assertIsNone(import_packages.read_library(self.addon))
        with self.assertRaisesRegex(ValueError, '不匹配'):
            self.convert('新建.zip', record('b'))
        self.assertEqual(list(managed.iterdir()), [managed / 'untouched.txt'])
        marker = managed / import_packages.LIBRARY_MARKER
        marker.write_bytes(import_packages.encode_index({'id': 'e' * 32}))
        self.assertTrue(synchronize(self.data, self.addon)['blocked'])
        self.assertEqual(import_packages.read_library(self.addon), 'e' * 32)
        self.assertEqual((managed / 'untouched.txt').read_bytes(), b'unrelated')

    def test_builtin_writes_into_named_package(self):
        runtime = self.data / 'Assets/runtime/story_native/story_BRolandBaseAppearance.bin'
        runtime.parent.mkdir()
        runtime.write_bytes(b'compatible')
        resources = self.data / 'Assets/Roland'
        resources.mkdir()
        (resources / 'import-actions.json').write_text('{}', encoding='utf8')
        (self.data / skin_import.CATALOG).write_bytes(json.dumps({'101': {'entries': [{
            'identity_id': import_packages.BUILTIN, 'appearance_name': 'BRolandBaseAppearance', 'name': '罗兰'
        }]}}).encode())
        with patch.dict(sys.modules, {'roland_merge': type('Fake', (), {
            'build_roland_bundle': staticmethod(lambda archive, *, with_voice=False:
                (b'model', b'compatible', {'state': 'unknown', 'count': 0}) if with_voice else (b'model', b'compatible'))
        })}):
            row, = self.convert('RolandBundle.zip', {'builtin': 'roland'})
            managed = import_packages.managed_root(self.addon)
            managed.rename(self.addon / 'before-reinstall')
            self.assertFalse(synchronize(self.data, self.addon)['removed'])
            package = import_packages.read_index(self.data)['packages'][0]
            self.assertEqual(package['missing_identities'], [import_packages.BUILTIN])
            restored, = self.convert('RolandBundle.zip', {'builtin': 'roland'})
            self.assertEqual(restored['status'], 'updated')
        folder = Path(row['package_directory'])
        self.assertEqual((folder / 'BRoland.bundle').read_bytes(), b'model')
        self.assertFalse((resources / 'BRoland.bundle').exists())
        self.assertEqual(import_packages.locator_path(self.data, import_packages.BUILTIN).read_text('utf8'),
                         '外来外观/RolandBundle/BRoland.bundle')


if __name__ == '__main__':
    unittest.main()
