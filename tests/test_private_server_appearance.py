import json
from io import BytesIO
from pathlib import Path, PurePosixPath
import sys
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))


def package(definitions, locale, motions=()):
    source = BytesIO()
    with ZipFile(source, 'w') as archive:
        archive.writestr('Pack/custom_limbus_data/personality/people.json', json.dumps(definitions))
        archive.writestr('Pack/custom_limbus_locale/EN/personalityList/all.json', json.dumps(locale))
        for appearance in motions:
            archive.writestr('Pack/custom_motions/' + appearance + '/S1.json', '{}')
    return ZipFile(source)


class PrivateServerAppearanceTest(unittest.TestCase):
    def test_metadata_selects_multiple_published_models_without_using_archive_names(self):
        from private_server_appearance import read_declarations, select_models

        with package({'list': [{'id': 92304, 'appearance': '!custom_51102_Rook'},
                               {'id': 88200, 'appearance': '!custom_Dove'}]},
                     {'92304': {'title': 'Silver Rook'}, '88200': {'title': 'Ivory Dove'},
                      '51102': {'title': 'Old Identity'}}) as archive:
            declarations = read_declarations(archive)
        bundle = PurePosixPath('Pack/custom_appearance/many.bundle')
        rook = ('Assets/51102_Rook.prefab', 1, 20, '51102_Rook')
        dove = ('Assets/Dove.prefab', 2, 20, 'Dove')
        distraction = ('Assets/51102_Stock.prefab', 3, 20, '51102_Stock')
        selected = select_models(declarations, {bundle: [distraction, rook, dove]})
        self.assertEqual([(d.personality, d.label, root[1]) for d, root in selected[bundle]],
                         [('92304', 'Silver Rook', 1), ('88200', 'Ivory Dove', 2)])

    def test_missing_or_ambiguous_model_fails_instead_of_using_another_personality(self):
        from private_server_appearance import read_declarations, select_models

        with package({'list': [{'id': 92304, 'appearance': '!custom_51102_Rook'}]}, {}) as archive:
            declarations = read_declarations(archive)
        bundle = PurePosixPath('Pack/custom_appearance/a.bundle')
        rook = ('Assets/51102_Rook.prefab', 1, 20, '51102_Rook')
        other = ('Assets/51102_Stock.prefab', 2, 20, '51102_Stock')
        wrong_scope = PurePosixPath('Another/custom_appearance/a.bundle')
        with self.assertRaisesRegex(ValueError, '未找到'):
            select_models(declarations, {bundle: [other], wrong_scope: [rook]})
        with self.assertRaisesRegex(ValueError, '多个'):
            select_models(declarations, {bundle: [rook],
                                         PurePosixPath('Pack/custom_appearance/b.bundle'): [rook]})

    def test_conflicting_definitions_cannot_pick_the_first_file(self):
        from private_server_appearance import read_declarations

        with package({'list': [{'id': 92304, 'appearance': 'Rook'},
                               {'id': 92304, 'appearance': 'Dove'}]}, {}) as archive:
            with self.assertRaisesRegex(ValueError, '多个外观'):
                read_declarations(archive)

    def test_case_colliding_declarations_cannot_share_a_single_authored_body(self):
        from private_server_appearance import read_declarations, select_models

        source = BytesIO()
        with ZipFile(source, 'w') as archive:
            for root, identity in [('Outer/Custom', 92304), ('Outer/custom', 88200)]:
                archive.writestr(root + '/custom_limbus_data/personality/person.json',
                                 json.dumps({'list': [{'id': identity, 'appearance': '!custom_Rook'}]}))
        bundle = PurePosixPath('Outer/Custom/custom_appearance/a.bundle')
        rook = ('Assets/Rook.prefab', 1, 20, 'Rook')
        with ZipFile(source) as archive:
            with self.assertRaisesRegex(ValueError, 'Outer/Custom.*Outer/custom'):
                select_models(read_declarations(archive), {bundle: [rook]})

    def test_body_lookup_ignores_path_case_when_only_one_root_declares_a_personality(self):
        from private_server_appearance import read_declarations, select_models

        with package({'list': [{'id': 92304, 'appearance': '!CUSTOM_Rook'}]}, {}) as archive:
            declarations = read_declarations(archive)
        bundle = PurePosixPath('pACK/CUSTOM_APPEARANCE/unrelated-filename.BUNDLE')
        rook = ('Assets/ROOK.prefab', 1, 20, 'ROOK')
        self.assertEqual(select_models(declarations, {bundle: [rook]})[bundle][0][1], rook)

    def test_unicode_declaration_selects_the_matching_unity_layout(self):
        from private_server_appearance import read_declarations, select_models

        with package({'list': [{'id': 92304, 'appearance': '!custom_赤龙·试作'}]}, {}) as archive:
            declarations = read_declarations(archive)
        bundle = PurePosixPath('Pack/custom_appearance/other-name.bundle')
        body = ('Assets/Untitled.prefab', 1, 20, '赤龙·试作')
        other = ('Assets/Other.prefab', 2, 20, '苍鹰·试作')
        self.assertEqual(select_models(declarations, {bundle: [other, body]})[bundle][0][1], body)

    def test_custom_declaration_rejects_paths_reserved_names_and_invisible_marks(self):
        from private_server_appearance import read_declarations

        for shape in ('', 'PRN.prefab', 'LPT²', '甲:乙', '甲\n乙', '甲\u034f乙',
                      '甲\u2066乙', '甲\u3164乙', '甲[乙]', '名字.', '名字 '):
            with self.subTest(shape=shape):
                with package({'list': [{'id': 92304, 'appearance': '!custom_' + shape}]}, {}) as archive:
                    with self.assertRaisesRegex(ValueError, '无效'):
                        read_declarations(archive)

    def test_explicitly_authored_prefab_precedes_unprefixed_base(self):
        from private_server_appearance import read_declarations, select_models

        with package({'list': [{'id': 92304, 'appearance': '!custom_Rook'}]}, {}) as archive:
            declarations = read_declarations(archive)
        bundle = PurePosixPath('Pack/custom_appearance/a.bundle')
        stock = ('Assets/Rook.prefab', 1, 20, 'Rook')
        custom = ('Assets/!custom_Rook.prefab', 2, 20, 'Rook')
        self.assertEqual(select_models(declarations, {bundle: [stock, custom]})[bundle][0][1], custom)

    def test_unmodified_stock_personality_does_not_block_authored_neighbor(self):
        from private_server_appearance import read_declarations, select_models

        with package({'list': [{'id': 92304, 'appearance': '!custom_Rook'},
                               {'id': 33781, 'appearance': 'Unmodified'}]}, {}) as archive:
            declarations = read_declarations(archive)
        bundle = PurePosixPath('Pack/custom_appearance/a.bundle')
        rook = ('Assets/Rook.prefab', 1, 20, 'Rook')
        catalog = {'SD_Personality/Unmodified.prefab'}
        selected = select_models(declarations, {bundle: [rook]}, catalog)
        self.assertEqual([d.personality for d, _ in selected[bundle]], ['92304'])
        with package({'list': [{'id': 33781, 'appearance': '!custom_Unmodified'}]}, {}) as archive:
            declarations = read_declarations(archive)
        with self.assertRaisesRegex(ValueError, '未找到'):
            select_models(declarations, {bundle: [rook]}, catalog)
        with package({'list': [{'id': 33781, 'appearance': 'Unmodified'}]}, {},
                     motions=['Unmodified']) as archive:
            declarations = read_declarations(archive)
        with self.assertRaisesRegex(ValueError, '未找到'):
            select_models(declarations, {bundle: [rook]}, catalog)
