"""Exercise package folders and stable identifiers through the production importer."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
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

    def convert(self, filename, *records, framepack_dialogue=False):
        with patch('skin_assets.build_assets', return_value=iter(records)):
            return skin_import._import_normalized(self.archive, self.data, unity=object(),
                                                   package_addon=self.addon, package_source=filename,
                                                   framepack_dialogue=framepack_dialogue)

    def test_reimport_updates_and_clears_author_without_resetting_personal_settings(self):
        from pathlib import PurePosixPath

        candidate = dict(record('a'), _source_member=PurePosixPath('Pack/custom_appearance/model.bundle'))
        manifest = 'Pack/README.md'
        catalog_path = self.data / skin_import.CATALOG

        def catalog():
            return json.loads(catalog_path.read_bytes())

        def update_document(content):
            with ZipFile(self.archive, 'w') as package:
                package.writestr(manifest, content)
            return self.convert('Pack.zip', candidate)[0]

        self.assertEqual(update_document('Description only')['status'], 'added')
        data = catalog()
        data['101']['entries'][0].update(name='我的外观名', weight=31, enabled=False)
        catalog_path.write_bytes(skin_import.encode(data))
        for author in ('First', 'Second'):
            imported = update_document('Author: ' + author)
            self.assertEqual((imported['status'], imported['author'], imported['imported_author_source']),
                             ('updated', author, manifest))
            self.assertEqual(update_document('Author: ' + author)['status'], 'existing')
        self.assertEqual(update_document('Description only')['status'], 'updated')
        self.assertEqual(update_document('Description only')['status'], 'existing')
        [saved] = catalog()['101']['entries']
        self.assertNotIn('author', saved)
        self.assertNotIn('imported_author_source', saved)
        self.assertEqual((saved['name'], saved['weight'], saved['enabled']), ('我的外观名', 31, False))

    def test_reimport_updates_and_clears_links_without_an_author(self):
        candidate = dict(record('a'), _source_member='Pack/custom_appearance/model.bundle')
        catalog_path = self.data / skin_import.CATALOG

        def update(url=''):
            with ZipFile(self.archive, 'w') as package:
                package.writestr('Pack/README.md', '发布页：' + url if url else '说明')
            [result] = self.convert('Pack.zip', candidate)
            data = json.loads(catalog_path.read_bytes())
            [saved] = data['101']['entries']
            links = [{'url': url, 'label': '发布页'}] if url else None
            self.assertEqual(result.get('author_links'), links)
            self.assertEqual(saved.get('author_links'), links)
            self.assertNotIn('author', saved)
            return result['status']

        self.assertEqual(update(), 'added')
        for url in ('https://mod.example/old', 'https://mod.example/new?key=2'):
            self.assertEqual(update(url), 'updated')
            self.assertEqual(update(url), 'existing')
        self.assertEqual(update(), 'updated')
        self.assertEqual(update(), 'existing')

    def test_skill_ui_reimport_and_uninstall_keep_shared_art_until_last_reference(self):
        from imported_package_uninstall import delete_identity
        from skill_ui import icon_names
        from test_skill_ui import png

        source = 'Family.zip'
        first, second = record('a'), record('b')
        for candidate, personality in [(first, '12345'), (second, '12346')]:
            candidate['entry']['private_declaration'] = {
                'root': 'family', 'source': 'family.zip', 'personality': personality,
            }

        def prepare(first_name, *, include_first=True):
            with ZipFile(self.archive, 'w') as archive:
                archive.writestr('Family/custom_limbus_data/personality/units.json', json.dumps({'list': [
                    {'id': 12345, 'defenseSkillIDList': [1234504]},
                    {'id': 12346, 'defenseSkillIDList': [1234604]},
                ]}))
                archive.writestr('Family/custom_limbus_locale/EN/skillList/names.json',
                                 json.dumps({'1234504': {'name': first_name},
                                             '1234604': {'name': 'Second guard'}}))
                for skill_id in ([1234504] if include_first else []) + [1234604]:
                    archive.writestr(f'Family/custom_sprites/skill_{skill_id}.png', png())

        prepare('First guard')
        rows = self.convert(source, first, second)
        folder = Path(rows[0]['package_directory'])
        sidecars = [folder / (candidate['look'] + '.skill-ui.tsv') for candidate in (first, second)]
        [shared] = icon_names(sidecars[0])
        self.assertEqual(icon_names(sidecars[1]), {shared})
        self.assertTrue((folder / shared).is_file())
        self.assertEqual([row['status'] for row in self.convert(source, first, second)], ['existing'] * 2)

        prepare('Updated', include_first=False)
        self.assertEqual([row['status'] for row in self.convert(source, first, second)], ['updated', 'existing'])
        self.assertIn('Updated', sidecars[0].read_text(encoding='utf8'))
        self.assertEqual(icon_names(sidecars[0]), set())
        self.assertTrue((folder / shared).is_file())

        delete_identity(self.data, self.addon, second['entry']['identity_id'], lock_factory=skin_import.FileLock)
        self.assertFalse(sidecars[1].exists())
        self.assertFalse((folder / shared).exists())
        self.assertTrue(sidecars[0].is_file())

    def dialogue_record(self, digit, owner, sample):
        buffer = BytesIO()
        with wave.open(buffer, 'wb') as clip:
            clip.setparams((1, 2, 28000, 0, 'NONE', 'not compressed'))
            clip.writeframes(sample * 20)
        audio = buffer.getvalue()
        filename = hashlib.sha256(audio).hexdigest() + '.wav'
        source = self.base / filename
        source.write_bytes(audio)
        manifest = f'{owner}\tbattle_kill_{owner}_1\t{filename}\t台词\n'.encode('utf8')
        return dict(record(digit), framepack_dialogue=(manifest, {filename: source})), filename

    def test_framepack_dialogue_reload_reimport_and_delete(self):
        from imported_package_uninstall import delete_identity
        import imported_catalog

        native = self.addon / 'SinnersNative-v64.dll'
        native.write_bytes(b'fixture core')
        manifest = self.addon / 'compatibility.json'
        manifest.write_bytes(json.dumps({'framepack_dialogue': 1, 'import_package_folders': 1,
                                         'package_files':{native.name:hashlib.sha256(native.read_bytes()).hexdigest()}}).encode())
        first, old = self.dialogue_record('a', '11116', b'\0\1')
        second, same = self.dialogue_record('b', '10316', b'\0\1')
        self.assertEqual(old, same)
        rows = self.convert('duo.zip', first, second, framepack_dialogue=True)
        folder = Path(rows[0]['package_directory'])
        first_id, second_id = (row['identity_id'] for row in rows)
        identities = (first_id, second_id)

        def reopen():
            rows = {identity: {'identity_id': identity, 'name': identity,
                               'dialogue_detection': {'voice': 'found', 'bubble': 'found'}}
                    for identity in identities}
            imported_catalog.apply(rows, self.data, self.addon)
            return [rows[identity]['dialogue_detection'] for identity in identities]

        both = {'voice': 'connected', 'bubble': 'connected'}
        self.assertEqual(reopen(), [both, both])
        (folder / old).unlink()
        self.assertEqual(reopen(), [{'voice': 'found', 'bubble': 'connected'}] * 2)
        self.convert('duo.zip', first, second, framepack_dialogue=True)
        self.assertEqual(reopen(), [both, both])
        native.write_bytes(b'older core')
        self.assertEqual(reopen(), [{'voice': 'found', 'bubble': 'found'}] * 2)
        native.write_bytes(b'fixture core')

        changed, new = self.dialogue_record('a', '11116', b'\0\2')
        [updated] = self.convert('duo.zip', changed, framepack_dialogue=True)
        self.assertEqual(updated['status'], 'updated')
        self.assertEqual({path.name for path in folder.glob('*.wav')}, {old, new})
        delete_identity(self.data, self.addon, second_id, lock_factory=skin_import.FileLock)
        self.assertFalse((folder / old).exists())
        self.assertFalse((folder / (second['look'] + '.voice.tsv')).exists())
        self.assertTrue((folder / new).is_file())

        [updated] = self.convert('duo.zip', first, framepack_dialogue=True)
        self.assertEqual(updated['status'], 'updated')
        self.assertEqual({path.name for path in folder.glob('*.wav')}, {old})
        delete_identity(self.data, self.addon, first_id, lock_factory=skin_import.FileLock)
        self.assertFalse(list(folder.glob('*.wav')))
        self.assertFalse(list(folder.glob('*.voice.tsv')))

    def test_framepack_dialogue_failure_restores_previous_manifest(self):
        old, wav_before = self.dialogue_record('a', '11116', b'\0\1')
        [row] = self.convert('reimport.zip', old, framepack_dialogue=True)
        folder = Path(row['package_directory'])
        sidecar = folder / (old['look'] + '.voice.tsv')
        before = sidecar.read_bytes()
        new, wav_after = self.dialogue_record('a', '11116', b'\0\2')
        write = skin_import.write_atomic

        def fail_sidecar(path, data):
            if path == sidecar:
                raise OSError('simulated sidecar failure')
            return write(path, data)

        with patch.object(skin_import, 'write_atomic', side_effect=fail_sidecar):
            with self.assertRaisesRegex(OSError, 'simulated sidecar failure'):
                self.convert('reimport.zip', new, framepack_dialogue=True)
        self.assertEqual(sidecar.read_bytes(), before)
        self.assertTrue((folder / wav_before).is_file())
        self.assertFalse((folder / wav_after).exists())

    def test_folder_keeps_real_models_and_multiple_stable_identities(self):
        rows = self.convert('test-archive.zip', record('a'), record('b'))
        expected = self.addon / 'imported-appearance' / 'test-archive'
        self.assertEqual([Path(row['package_directory']) for row in rows], [expected] * 2)
        self.assertEqual(len(list(expected.glob('*.bundle'))), 1)
        self.assertFalse(list((self.data / skin_import.LOCAL).glob('*.bundle')))
        for row in rows:
            locator = import_packages.locator_path(self.data, row['identity_id'])
            target = self.addon / locator.read_text('utf-8')
            self.assertEqual(target.read_bytes(), b'textured model')
        rows = self.convert('test-archive.zip', record('a'), record('b'))
        self.assertEqual([row['status'] for row in rows], ['existing', 'existing'])
        self.assertEqual(len(import_packages.read_index(self.data)['packages']), 1)

    def test_unrelated_same_name_and_known_asset_update(self):
        a, = self.convert('samename.zip', record('a', b'a'))
        b, = self.convert('samename.zip', record('b', b'b'))
        self.assertEqual(Path(a['package_directory']).name, 'samename')
        self.assertEqual(Path(b['package_directory']).name, 'samename (2)')
        updated, = self.convert('samename.zip', record('a', b'c'))
        self.assertEqual(updated['status'], 'updated')
        self.assertEqual(a['package_directory'], updated['package_directory'])
        locator = import_packages.locator_path(self.data, updated['identity_id'])
        self.assertTrue(locator.read_text('utf-8').endswith(hashlib.sha256(b'c').hexdigest() + '.bundle'))
        self.assertEqual(len(list(Path(a['package_directory']).glob('*.bundle'))), 1)

    def test_update_keeps_shared_revision_and_does_not_transfer_ownership(self):
        a, _ = self.convert('same-package.zip', record('a'), record('b'))
        self.convert('same-package.zip', record('a', b'revised'))
        self.assertEqual(len(list(Path(a['package_directory']).glob('*.bundle'))), 2)
        with self.assertRaisesRegex(ValueError, '已归属'):
            self.convert('accidental-rename.zip', record('b'))
        self.assertEqual(len(import_packages.read_index(self.data)['packages']), 1)

    def test_failed_new_import_leaves_no_registered_folder(self):
        with patch.object(skin_import, 'write_atomic', side_effect=OSError('simulated disk error')):
            with self.assertRaisesRegex(OSError, 'simulated disk error'):
                self.convert('failure.zip', record('a'))
        parent = import_packages.managed_root(self.addon)
        self.assertFalse((parent / 'failure').exists())
        self.assertEqual(import_packages.read_index(self.data)['packages'], [])

    def test_reinstall_preserves_catalog_and_can_restore_one_of_two_identities(self):
        first, second = self.convert('one-package.zip', record('a'), record('b'))
        catalog = self.data / skin_import.CATALOG
        snapshot = json.loads(catalog.read_bytes())
        snapshot['101']['entries'][0].update(enabled=False, weight=37)
        catalog.write_bytes(skin_import.encode(snapshot))
        rules = self.data / 'custom_pools.json'
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

        self.convert('new-package.zip', record('c'))
        restored, = self.convert('one-package.zip', record('a'))
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
                         [{'directory': 'one-package', 'identities': [first['identity_id']]}])
        package = import_packages.read_index(self.data)['packages'][0]
        self.assertEqual(package['identities'], [second['identity_id']])
        self.assertTrue(import_packages.locator_path(self.data, second['identity_id']).exists())
        self.assertEqual(json.loads(rules.read_bytes())['entries'], [{'identity_id': second['identity_id']}])

    def test_reinstall_retry_and_returning_old_library(self):
        old, = self.convert('old-package.zip', record('a'))
        old_library = import_packages.read_library(self.addon)
        managed = import_packages.managed_root(self.addon)
        backup = managed.rename(self.addon / 'old-library')
        with patch.object(skin_import, 'write_atomic', side_effect=OSError('simulated disk error')):
            with self.assertRaisesRegex(OSError, 'simulated disk error'):
                self.convert('old-package.zip', record('a'))
        packages = import_packages.read_index(self.data)['packages']
        self.assertEqual(packages[0]['missing_identities'], [old['identity_id']])
        self.assertFalse((managed / packages[0]['directory']).exists())
        self.convert('new-package.zip', record('b'))
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
        imported, = self.convert('one-package.zip', record('a'))
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

        self.convert('one-package.zip', record('a'))
        old_library = import_packages.read_library(self.addon)
        managed.rename(self.addon / 'second-library')
        self.assertFalse(synchronize(self.data, self.addon)['removed'])
        self.assertNotEqual(import_packages.read_library(self.addon), old_library)
        package = import_packages.read_index(self.data)['packages'][0]
        self.assertEqual(package['missing_identities'], [imported['identity_id']])

    def test_restored_index_can_adopt_library_initialized_before_restore(self):
        imported, = self.convert('one-package.zip', record('a'))
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
        restored, = self.convert('one-package.zip', record('a'))
        self.assertEqual(restored['status'], 'updated')

    def test_fresh_profile_can_use_an_existing_marked_library(self):
        imported, = self.convert('installed-package.zip', record('a'))
        observed = import_packages.read_library(self.addon)
        model = Path(imported['package_directory'])
        fresh_profile = self.base / 'fresh-profile'
        fresh_profile.mkdir()

        self.assertEqual(import_packages.ensure_library(fresh_profile, self.addon), observed)
        self.assertEqual(import_packages.read_index(fresh_profile)['packages'], [])
        self.assertEqual(len(list(model.glob('*.bundle'))), 1)

    def test_nonempty_library_replacement_keeps_other_installation_identity(self):
        self.convert('one-package.zip', record('a'))
        managed = import_packages.managed_root(self.addon)
        self.assertEqual(import_packages.read_library(self.addon),
                         import_packages.read_index(self.data)['library'])
        managed.rename(self.addon / 'renamed')
        managed.mkdir()
        (managed / 'untouched.txt').write_bytes(b'unrelated')
        self.assertIsNone(import_packages.read_library(self.addon))
        with self.assertRaisesRegex(ValueError, '不匹配'):
            self.convert('new.zip', record('b'))
        self.assertEqual(list(managed.iterdir()), [managed / 'untouched.txt'])
        marker = managed / import_packages.LIBRARY_MARKER
        marker.write_bytes(import_packages.encode_index({'id': 'e' * 32}))
        self.assertTrue(synchronize(self.data, self.addon)['blocked'])
        self.assertEqual(import_packages.read_library(self.addon), 'e' * 32)
        self.assertEqual((managed / 'untouched.txt').read_bytes(), b'unrelated')

    def test_builtin_writes_into_named_package(self):
        from imported_package_uninstall import delete_identity
        from test_skill_ui import png
        from skill_ui import icon_names

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
            art = png()
            with patch('skill_ui_import.collect_external', return_value=[
                    (10115, [(1011501, 'attack1', 0, '作者的招式', b'')], {}, art)]):
                changed, = self.convert('RolandBundle.zip', {'builtin': 'roland'})
                same, = self.convert('RolandBundle.zip', {'builtin': 'roland'})
                self.assertEqual((changed['status'], same['status']), ('updated', 'existing'))
        folder = Path(row['package_directory'])
        self.assertEqual((folder / 'BRoland.bundle').read_bytes(), b'model')
        self.assertFalse((resources / 'BRoland.bundle').exists())
        self.assertEqual(import_packages.locator_path(self.data, import_packages.BUILTIN).read_text('utf8'),
                         'imported-appearance/RolandBundle/BRoland.bundle')
        sidecar = folder / 'BRolandBaseAppearance.skill-ui.tsv'
        self.assertIn('作者的招式', sidecar.read_text(encoding='utf8'))
        [portrait] = icon_names(sidecar)
        self.assertEqual((folder / portrait).read_bytes(), art)
        delete_identity(self.data, self.addon, import_packages.BUILTIN, lock_factory=skin_import.FileLock)
        self.assertFalse(sidecar.exists())
        self.assertFalse((folder / portrait).exists())


if __name__ == '__main__':
    unittest.main()
