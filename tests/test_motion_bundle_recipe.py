import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))
from motion_bundle_recipe import contains_runtime_addon, read_motion_bundle_recipes


BUNDLE = b'UnityFS\0fixture'


class MotionBundleRecipeTest(unittest.TestCase):
    def archive(self, files):
        blob = io.BytesIO()
        with ZipFile(blob, 'w') as archive:
            for path, value in files.items():
                archive.writestr(path, value if isinstance(value, bytes) else json.dumps(value))
        archive = ZipFile(blob)
        self.addCleanup(archive.close)
        return archive

    def files(self, root='Outer/One', appearance='Author_One', personality=8123):
        folder = f'{root}/motion_appearances/{appearance}'
        return {
            f'{root}/custom_limbus_data/personality/rows.json':
                {'list': [{'id': personality, 'appearance': '!motions_' + appearance, 'characterId': 2}]},
            f'{root}/custom_limbus_locale/EN/personalityList/names.json':
                {str(personality): {'title': '<color=#123456>Author Look</color>'}},
            f'{folder}/appearance.json': {'base': '1234_NativeAppearance'},
            f'{folder}/arbitrary_name.bundle': BUNDLE,
            f'{folder}/S1.json': {'coins': [{'totalDuration': .4, 'hitCheckers': [{'time': 1.1}]}]},
        }

    def test_only_reads_declared_shapes_using_package_scope(self):
        files = self.files()
        files.update(self.files(root='Outer/Two', personality=8124))
        files['Outer/One/motion_appearances/Undeclared/broken.bundle'] = b'invalid, intentionally unused'
        files['Outer/One/custom_appearance/unrelated.bundle'] = b'not selected'
        one, two = read_motion_bundle_recipes(self.archive(files))
        self.assertEqual([r.declaration.personality for r in (one, two)], ['8123', '8124'])
        self.assertEqual(one.declaration.label, 'Author Look')
        self.assertTrue(one.declaration.has_motions)
        self.assertEqual(one.base, '1234_NativeAppearance')
        self.assertEqual(one.bundle.filename, 'Outer/One/motion_appearances/Author_One/arbitrary_name.bundle')
        self.assertEqual(one.actions['s1']['coins'][0]['hitCheckers'][0]['time'], 1.1)

    def test_asset_router_skips_undeclared_backup_next_to_motion_package(self):
        import _module_paths
        from skin_assets import build_assets
        files = self.files('Renamed/Independent')
        files['Renamed/Independent/custom_appearance/backup.bundle'] = b'not a selected model'
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'different-archive-name.zip'
            with ZipFile(source, 'w') as archive:
                for key, value in files.items():
                    archive.writestr(key, value if isinstance(value, bytes) else json.dumps(value))
            unity = Mock()
            with patch('motion_bundle_import.build_motion_records', return_value=[{'look': 'declared'}]):
                self.assertEqual(list(build_assets(source, Path(folder), unity)), [{'look': 'declared'}])
            unity.load.assert_not_called()

    def test_same_nested_declaration_in_different_source_packages_can_coexist(self):
        import _module_paths
        from skin_assets import build_assets

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            def imported(source, registered=()):
                with ZipFile(source, 'w') as archive:
                    for key, value in self.files().items():
                        archive.writestr(key, value if isinstance(value, bytes) else json.dumps(value))
                with patch('skin_assets._catalog_keys', return_value={}), \
                     patch('stock_coin_import._locate', return_value={'1234_NativeAppearance': ('file', 'address')}), \
                     patch('skin_assets._dependency', return_value='stock'), \
                     patch('motion_bundle_model.build_motion_model',
                           side_effect=lambda *a, **kw: (b'body', 'address', 'layout', {}, {}, {})):
                    record, = build_assets(source, folder, Mock(), registered=registered)
                return record

            one = imported(folder / 'A.zip')
            other = imported(folder / 'B.zip')
            self.assertNotEqual(one['look'], other['look'])
            import hashlib
            legacy = 'WBImp_' + hashlib.sha256(b'motion-bundle/outer/one/8123').hexdigest()[:24]
            old = dict(identity_id='story_' + legacy, import_source='A')
            migrated = imported(folder / 'A.zip', [old])
            self.assertEqual(migrated['look'], legacy)
            self.assertEqual(migrated['entry']['private_declaration']['personality'], '8123')

    def test_does_not_take_missing_body_from_another_package(self):
        files = self.files()
        del files['Outer/One/motion_appearances/Author_One/arbitrary_name.bundle']
        files.update(self.files(root='Outer/Two', personality=8124))
        with self.assertRaisesRegex(ValueError, 'Author_One'):
            read_motion_bundle_recipes(self.archive(files))

    def test_does_not_join_personalities_from_case_colliding_roots(self):
        files = self.files('Outer/One')
        files['Outer/one/custom_limbus_data/personality/second.json'] = {
            'list': [{'id': 8124, 'appearance': '!motions_Author_One'}],
        }
        with self.assertRaisesRegex(ValueError, 'Outer/One.*Outer/one'):
            read_motion_bundle_recipes(self.archive(files))

    def test_accepts_case_variations_in_assets_of_one_declared_root(self):
        files = self.files('Outer/One')
        renamed = {name.replace('Outer/One/motion_appearances/', 'outer/one/MOTION_APPEARANCES/'): value
                   for name, value in files.items()}
        recipe, = read_motion_bundle_recipes(self.archive(renamed))
        self.assertEqual(recipe.declaration.personality, '8123')
        self.assertIn('outer/one/MOTION_APPEARANCES/', recipe.bundle.filename)

    def test_unicode_motion_shape_uses_declared_directory_and_actual_body(self):
        for shape in ('凯尔希·合体', 'Δοκιμή_अशोक'):
            with self.subTest(shape=shape):
                recipe, = read_motion_bundle_recipes(self.archive(self.files(appearance=shape)))
                self.assertEqual(recipe.declaration.appearance, '!motions_' + shape)
                self.assertEqual(Path(recipe.bundle.filename).parent.name, shape)

    def test_motion_identifier_rejects_unsafe_name_even_if_resource_exists(self):
        for shape in ('../逃逸', '甲/乙', '甲\\乙', '甲\u202e影', '甲\u200d乙',
                      '甲\ufe0f', 'COM¹.asset', 'CON .foo', '名字.', '名字 '):
            with self.subTest(shape=shape):
                with self.assertRaisesRegex(ValueError, '无效'):
                    read_motion_bundle_recipes(self.archive(self.files(appearance=shape)))

    def test_rejects_mixed_or_case_colliding_bundles_in_a_selected_folder(self):
        for filename in ('ARBITRARY_NAME.BUNDLE', 'other.bundle'):
            with self.subTest(filename=filename):
                files = self.files()
                files['Outer/One/motion_appearances/Author_One/' + filename] = BUNDLE
                with self.assertRaisesRegex(ValueError, 'Author_One'):
                    read_motion_bundle_recipes(self.archive(files))

    def test_rejects_action_case_collisions_and_invalid_duration(self):
        path = 'Outer/One/motion_appearances/Author_One/'
        for name, data in [('s1.JSON', {'coins': [{'totalDuration': 1}]}),
                           ('S1.json', {'coins': [{'totalDuration': True}]})]:
            with self.subTest(name=name, data=data):
                files = self.files()
                files[path + name] = data
                with self.assertRaisesRegex(ValueError, 'Author_One'):
                    read_motion_bundle_recipes(self.archive(files))

    def test_runtime_only_archive_is_not_a_model_archive(self):
        plugin = {'wrapper/tool.dll': b'MZruntime', 'wrapper/main.cs': b'placeholder'}
        archive = self.archive(plugin)
        self.assertTrue(contains_runtime_addon(archive))
        self.assertEqual(read_motion_bundle_recipes(archive), [])
        plugin.update(self.files())
        self.assertFalse(contains_runtime_addon(self.archive(plugin)))

    def test_keeps_sdk_timing_sentinels_for_conversion(self):
        files = self.files()
        coins = [{'totalDuration': 0, 'hitCheckers': [{'time': -.1}]}, {'hitCheckers': None}]
        files['Outer/One/motion_appearances/Author_One/S1.json'] = {'coins': coins}
        recipe, = read_motion_bundle_recipes(self.archive(files))
        self.assertEqual(recipe.actions['s1']['coins'], coins)

    def test_stock_key_with_explicit_custom_motions_uses_only_its_body_bundle(self):
        root = 'Pack'
        key = '1234_ExampleAppearance'
        folder = f'{root}/custom_motions/{key}'
        files = {
            f'{root}/custom_limbus_data/personality/p.json':
                {'list': [{'id': 8123, 'appearance': key}]},
            f'{folder}/motion.bundle': BUNDLE,
            f'{folder}/effects.bundle': b'not the body',
            f'{folder}/CharacterVFX.json': {'allVFX': [], 'props': []},
            f'{folder}/S1.json': {'coins': [{'totalDuration': .4}]},
            f'{folder}/Special3.json': {'coins': [{'totalDuration': .4}]},
            f'{folder}/motions/Special3/animation.json': {'frames': []},
            'Another/custom_motions/1234_ExampleAppearance/motion.bundle': b'unrelated',
        }
        recipe, = read_motion_bundle_recipes(self.archive(files))
        self.assertTrue(recipe.stock_override)
        self.assertEqual(recipe.base, key)
        self.assertEqual(recipe.bundle.filename, f'{folder}/motion.bundle')
        self.assertEqual(set(recipe.actions), {'s1', 'special3'})
        del files[f'{folder}/motion.bundle']
        self.assertEqual(read_motion_bundle_recipes(self.archive(files)), [])

    def test_unbound_audio_and_assistant_warnings_are_scoped_to_the_declaring_package(self):
        from pathlib import PurePosixPath
        from motion_bundle_import import describe_unbound_package_resources

        files = {'Pack/Other/custom_sounds/voice.json': {}, 'Pack/MyMod/custom_sounds/readme.txt': b'notes',
                 'Pack/MyMod/custom_limbus_data/assistant/gear.json': {'list': [{'id': 9}]}}
        self.assertEqual(describe_unbound_package_resources(self.archive(files), PurePosixPath('Pack/MyMod')),
                         ['召唤物的私服运行时触发未接通'])
        files['Pack/MyMod/custom_sounds/voice.json'] = {}
        self.assertEqual(len(describe_unbound_package_resources(self.archive(files), PurePosixPath('Pack/MyMod'))), 2)

    def test_nonstandard_body_name_is_selected_by_published_body_tracks(self):
        root = 'Unseen/custom_motions/RandomBase/'
        files = {'Unseen/custom_limbus_data/personality/p.json': [{'id': 742, 'appearance': 'RandomBase'}],
                 root + 'scenery.bundle': BUNDLE + b'fx', root + 'author-body.bundle': BUNDLE + b'body',
                 root + 'S1.json': {'coins': [{}]}}
        body = Mock(container={'Artwork/idle.playable': 1, 'Artwork/s1.playable': 2})
        fx = Mock(container={'Assets/effect.prefab': 3})
        unity = Mock()
        unity.load.side_effect = lambda data: body if data.endswith(b'body') else fx
        with patch('motion_bundle_model.find_body_tracks', return_value={'idle': 1, 's1': 2}):
            recipe, = read_motion_bundle_recipes(self.archive(files), unity=unity)
            self.assertTrue(recipe.bundle.filename.endswith('/author-body.bundle'))
            files[root + 'also-valid.bundle'] = BUNDLE + b'body'
            with self.assertRaisesRegex(ValueError, '多个'):
                read_motion_bundle_recipes(self.archive(files), unity=unity)
