from io import BytesIO
import json
import os
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))


def png():
    from PIL import Image
    output = BytesIO()
    Image.new('RGBA', (4, 4), (100, 20, 30, 255)).save(output, format='PNG')
    return output.getvalue()


class SkillUiTest(unittest.TestCase):
    def test_defense_type_requires_consistent_author_data(self):
        from skill_ui import _defense_subtype
        for subtype in ('GUARD', 'EVADE', 'COUNTER'):
            self.assertEqual(_defense_subtype({'skillData': [{'defType': subtype}]}), subtype)
        for stages in ([], [{'defType': 'ATTACK'}], [{'defType': 'GUARD'}, {'defType': 'EVADE'}]):
            self.assertIsNone(_defense_subtype({'skillData': stages}))

    def test_higher_level_can_restore_name_independently_of_image(self):
        from skill_ui_merge import merge_external
        extras = (12345, [(1234501, 'attack1', 0, 'New', b''),
                          (1234501, 'attack1', 3, None, b'img')], {}, b'')
        merged = merge_external([], extras, lambda blob: blob.decode() if blob else '')
        self.assertIn(('R', '1234501', 'attack1', '3', '', 'img'), merged)
        primary = [('S', '1234501', 'attack1', '0', 'Explicit author text', '')]
        merged = merge_external(primary, extras, lambda blob: blob.decode() if blob else '')
        self.assertIn(('S', '1234501', 'attack1', '3', '', 'img'), merged)
        self.assertFalse(any(row[0] == 'R' for row in merged))

    def test_combines_fields_only_for_the_same_appearance_and_skill(self):
        from skill_ui_merge import merge_external
        rows = [('T', '12345'), ('S', '1234501', 'unknown', '0', '作者原名', ''),
                ('S', '1234501', 'unknown', '3', '条件之名', '')]
        extras = (12345, [(1234501, 'attack1', 0, '其他语言名', b'skill'),
                          (1234501, 'attack1', 4, '高阶招式', b''),
                          (1234501, 'defense', 1, '另一行为', b'other')], {}, b'')
        merged = merge_external(list(rows), extras, lambda blob: blob.decode() if blob else '')
        self.assertEqual(merged, [('T', '12345'), ('S', '1234501', 'attack1', '0', '作者原名', 'skill'),
                                  ('S', '1234501', 'attack1', '3', '条件之名', ''),
                                  ('S', '1234501', 'attack1', '4', '高阶招式', '')])
        self.assertEqual(merge_external(rows, (999, *extras[1:]), lambda _: 'incorrect'), rows)
        merged = merge_external([], (1288, [], {}, b'portrait'), lambda _: 'portrait.png',
                                address='Assets/Resources_moved/Prefab/SD/1288_LastKnight_Appearance.prefab')
        self.assertIn(('A', '1288_LastKnight_Appearance'), merged)
        mismatch = merge_external([], (1288, [], {}, b'portrait'), lambda _: 'portrait.png',
                                  address='Assets/Resources_moved/Prefab/SD/1289_Other.prefab')
        self.assertFalse(any(row[0] == 'A' for row in mismatch))

    def test_exact_scopes_roles_names_icons_and_status(self):
        from skill_ui import collect

        records = [{'entry': {'identity_id': 'skin-one',
                             'private_declaration': {'root': 'mod', 'personality': '12345'}}},
                   {'entry': {'identity_id': 'skin-two',
                             'private_declaration': {'root': 'mod', 'personality': '12346'}}}]
        files = {
            'Mod/custom_limbus_data/personality/a.json': {'list': [
                {'id': 12345, 'attributeList': [{'skillId': 1234501, 'number': 3},
                                                 {'skillId': 1234502, 'number': 0}],
                 'defenseSkillIDList': [1234504]},
                {'id': 12346, 'attributeList': [{'skillId': 1234601, 'number': 3}]},
            ]},
            'Mod/custom_limbus_data/skill/a.json': {'list': [
                {'id': 1234501, 'skillTier': 1, 'skillData': [
                    {'gaksungLevel': 1, 'abilityScriptList': [
                        {'scriptName': 'Modular/TIMING:BeforeUse/buff(Target,Marker,2,0,0)'}]}]},
                {'id': 1234502, 'skillTier': 1, 'skillData': [{'gaksungLevel': 1, 'iconID': 1234501}]},
                {'id': 1234504, 'skillTier': 1, 'skillData': [{'defType': 'GUARD'}]},
                {'id': 1234601, 'skillTier': 1, 'skillData': []},
            ]},
            'Mod/custom_limbus_data/buff/a.json': {'list': [{'id': 'Marker'}, {'id': 'Orphan'}]},
            'Mod/custom_limbus_locale/EN/skillList/a.json':
                '{"1234501":{"id":"1234501","levelList":[{"level":1,"name":"First"},]},'
                '"1234502":{"levelList":[{"level":1,"name":"Conditional"}]},'
                '"1234504":{"levelList":[{"level":1,"name":"Guard"}]},}',
            'Mod/custom_sprites/profile_12345.png': png(),
            'Mod/custom_sprites/skill_1234501.png': png(),
            'Mod/custom_sprites/buffIcon_Marker.png': png(),
            'Mod/custom_sprites/buffIcon_Orphan.png': png(),
            'Mod/Dependencies/custom_sprites/skill_1234504.png': png(),
        }
        output = BytesIO()
        with ZipFile(output, 'w') as archive:
            for path, value in files.items():
                archive.writestr(path, json.dumps(value) if isinstance(value, dict) else value)
        with ZipFile(output) as archive:
            (one, images), (two, _) = collect(archive, records)
        [filename] = images
        self.assertEqual(one.decode().splitlines(), [
            'MOSUI1', 'T\t12345', f'P\t{filename}',
            f'S\t1234501\tattack1\t0\tFirst\t{filename}',
            f'S\t1234502\tconditional\t0\tConditional\t{filename}',
            'S\t1234504\tdefense\t0\tGuard\t',
            f'B\tMarker\t{filename}',
            'D\t1234504\tGUARD',
        ])
        self.assertEqual(two, b'MOSUI1\nT\t12346\n')
        records[0]['coin_routes'] = [(1234504, 1, 1, 1, True)]
        with ZipFile(output) as archive:
            (one, _), _ = collect(archive, records)
        self.assertIn('D\t1234504\tCONDITIONAL_GUARD', one.decode().splitlines())

    def test_derived_defenses_use_owned_skill_declarations(self):
        from skill_ui import _conditional_defense_targets
        def definition(script):
            return {'skillData': [{'coinList': [{'abilityScriptList': [{'scriptName': script}]}]}]}
        definitions = {1: definition('Modular/TIMING:BeforeUse/IF(x):changeskill(4)'),
                       2: definition('ChangeSkillOnConditional_5'),
                       3: definition('Modular/TIMING:DefenseSwitch/changeskill(6)'),
                       7: definition('ChangeSkillOnConditional_8'), 9: definition('ChangeSkillOnConditional_10')}
        roles = {1: 'attack1', 2: 'conditional', 3: 'defense', 9: 'defense'}
        self.assertEqual(_conditional_defense_targets(roles, definitions), {4, 5, 10})

    @unittest.skipUnless(os.environ.get('MOS_SKILL_UI_ARCHIVES'), 'optional original appearance packages')
    def test_real_arisu_arbiter_and_kaltsit_packages(self):
        from framepack_manifest import portrait_png, read_framepacks
        from private_server_appearance import read_declarations
        from skill_ui import collect

        found = {}
        for path in os.environ['MOS_SKILL_UI_ARCHIVES'].split(os.pathsep):
            with ZipFile(path) as archive:
                skins = read_framepacks(archive)
                declarations = skins or read_declarations(archive)
                portraits = {skin.personality: portrait_png(archive, skin) for skin in skins}
                records = [{'entry': {'identity_id': declaration.personality, 'private_declaration': {
                    'root': str(declaration.package_root), 'personality': declaration.personality,
                }}} for declaration in declarations]
                for (payload, files), declaration in zip(collect(archive, records, portraits), declarations):
                    lines = [row.split('\t') for row in payload.decode().splitlines()[1:]]
                    self.assertIn(['T', declaration.personality], lines)
                    self.assertEqual(sum(row[0] == 'P' and row[1] in files for row in lines), 1)
                    found[declaration.personality] = lines

        self.assertEqual(set(found), {'11116', '10292199', '11633', '15433'})
        self.assertIn(['S', '1111601', 'unknown', '0', '光之剑：连击', ''], found['11116'])
        self.assertIn(['S', '1111608', 'unknown', '3', '世界的法则彻底崩坏！', ''], found['11116'])
        arbiter = {row[1]: row for row in found['10292199'] if row[0] == 'S'}
        self.assertEqual(len(arbiter), 10)
        self.assertEqual(arbiter['1029219904'][2], 'defense')
        self.assertIn(['D', '1029219904', 'GUARD'], found['10292199'])
        self.assertIn(['D', '1029219909', 'CONDITIONAL_GUARD'], found['10292199'])
        self.assertEqual(arbiter['1029219906'][2], 'conditional')
        self.assertEqual(arbiter['1029219901'][-1], arbiter['1029219906'][-1])
        self.assertFalse(any(row[0] == 'B' for row in found['10292199']))
        kaltsit = {row[1]: row for row in found['11633'] if row[0] == 'S'}
        mon3tr = {row[1]: row for row in found['15433'] if row[0] == 'S'}
        self.assertEqual(kaltsit['1163306'][-1], kaltsit['1163302'][-1])
        self.assertEqual(mon3tr['1543306'][-1], kaltsit['1163304'][-1])
        self.assertEqual({row[1] for row in found['11633'] if row[0] == 'B'},
                         {'Mon3trHP', 'Mon3trSPD', 'Mon3trTRUE'})
        self.assertEqual({row[1] for row in found['15433'] if row[0] == 'B'},
                         {'Mon3trUnit', 'Mon3trTRUE'})
