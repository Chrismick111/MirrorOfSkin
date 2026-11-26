from io import BytesIO
import json
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))

from stock_coin_recipe import build_stock_coin_recipe, read_stock_coin_recipes


def script(name, **data):
    return {'scriptName': name, **({'buffData': data} if data else {})}


def coin(*scripts):
    return {'abilityScriptList': list(scripts)}


def skill(skill_id, tier, *levels):
    return {'id': skill_id, 'skillTier': tier, 'skillData': list(levels)}


class StockCoinRecipeTest(unittest.TestCase):
    def test_custom_form_references_follow_owned_skills_without_level_numbers(self):
        from private_server_appearance import read_declarations
        from stock_coin_recipe import referenced_custom_forms
        with ZipFile(BytesIO(), 'w') as archive:
            def rows(folder, entries):
                archive.writestr(folder + '/rows.json', json.dumps({'list': entries}))

            rows('A/custom_limbus_data/personality', [
                {'id': 12, 'appearance': '!custom_Body', 'attributeList': [{'skillId': 31}]}])
            rows('A/custom_limbus_data/skill', [
                skill(31, 1, {'abilityScriptList': [script('ChangeAppearance_!custom_Body'),
                                                    script('ChangeSkillOnConditional_32')]}),
                skill(32, 2, {'coinList': [coin(script('ChangeAppearance_!custom_第二形态'),
                                                 script('ChangeSkillOnConditional_31'))]}),
                skill(33, 3, {'abilityScriptList': [script('ChangeAppearance_!custom_Unrelated')]})])
            rows('B/custom_limbus_data/skill', [
                skill(32, 2, {'abilityScriptList': [script('ChangeAppearance_!custom_OtherPackage')]})])
            declaration, = read_declarations(archive)
            self.assertEqual(referenced_custom_forms(archive, declaration), ('!custom_第二形态',))

    def test_ownership_levels_fragments_and_branch(self):
        personality = {'id': 71, 'appearance': 'Base_Appearance', 'attributeList': [
            {'skillId': 12, 'number': 2}, {'skillId': 78, 'number': 0}],
            'defenseSkillIDList': [10]}
        condition = script('ChangeSkillOnConditional_78', buffKeyword='Example', stack=2, turn=0)
        skills = [
            skill(12, 2, {'gaksungLevel': 4, 'defaultValue': 9}, {
                'gaksungLevel': 3, 'skillMotion': 'S1', 'abilityScriptList': [condition],
                'coinList': [coin(script('ChangeAppearance_311_Name_Appearance'),
                                  script('ChangeSkillMotion_S2', turn=4)), coin()]}),
            skill(78, 2, {'gaksungLevel': 1, 'skillMotion': 'S5', 'coinList': [coin()]}),
            skill(10, 1, {'gaksungLevel': 1, 'skillMotion': 'Default', 'coinList': [coin()]}),
            skill(14, 2, {'gaksungLevel': 1, 'skillMotion': 'S6', 'coinList': [coin()]}),
        ]
        result = build_stock_coin_recipe(personality, skills)
        self.assertEqual(result, json.loads(json.dumps(result)))
        self.assertEqual(result['appearance'], 'Base_Appearance')
        self.assertEqual({s['skillId']: s['role'] for s in result['skills']},
                         {12: 'attack', 10: 'defense', 78: 'conditional'})
        root = next(s for s in result['skills'] if s['skillId'] == 12)
        self.assertEqual(root['skillTier'], 2)
        self.assertEqual([entry['gaksungLevel'] for entry in root['levels']], [3, 4])
        for entry in root['levels']:
            self.assertEqual(entry['conditionals'][0]['skillId'], 78)
            self.assertEqual(entry['conditionals'][0]['script'], condition)
            self.assertEqual(entry['conditionals'][0]['gaksungLevel'], 1)
            self.assertEqual([(c['coinIndex'], c['appearance'], c['motion'], c['fragment'])
                              for c in entry['coins']],
                             [(1, '311_Name_Appearance', 'S2', 4), (2, 'Base_Appearance', 'S1', 2)])
        self.assertEqual(result['issues'], [])

    def test_keeps_evidence_for_incomplete_and_conflicting_coins(self):
        personality = {'id': 71, 'appearance': 'Base', 'attributeList': [{'skillId': 12, 'number': 1}]}
        motion = script('ChangeSkillMotion_S2')
        result = build_stock_coin_recipe(personality, [skill(12, 3, {
            'gaksungLevel': 1, 'skillMotion': 'S3', 'coinList': [coin(motion), None,
                coin(script('ChangeAppearance_A'), script('ChangeAppearance_B'))],
            'abilityScriptList': [script('ChangeSkillOnConditional_99', buffKeyword='Gate')],
        })])
        coins = result['skills'][0]['levels'][0]['coins']
        self.assertEqual([c['coinIndex'] for c in coins], [1, 2, 3])
        self.assertIsNone(coins[0]['fragment'])
        self.assertEqual(coins[0]['changes'][0]['script'], motion)
        self.assertIsNone(coins[2]['appearance'])
        self.assertEqual({item['code'] for item in result['issues']},
                         {'missing_motion_fragment', 'invalid_coin', 'ambiguous_appearance', 'missing_skill'})

    def test_archive_scopes_ownership_and_combines_level_patches(self):
        def personality(personality_id, skill_id, appearance='StockAppearance'):
            return {'id': personality_id, 'appearance': appearance,
                    'attributeList': [{'skillId': skill_id, 'number': 1}]}

        def level(appearance=None):
            changes = [script('ChangeAppearance_' + appearance)] if appearance else []
            return {'gaksungLevel': 1, 'skillMotion': 'S2', 'coinList': [coin(*changes)]}

        with ZipFile(BytesIO(), 'w') as archive:
            def write(path, entries):
                archive.writestr(path + '/rows.json', json.dumps({'list': entries}))

            write('One/custom_limbus_data/personality',
                  [personality(1, 91), personality(2, 92), personality(3, 93, '!custom_MyPrefab')])
            write('One/custom_limbus_data/skill',
                  [skill(91, 2, level('DifferentAppearance')), skill(92, 2, level()),
                   skill(93, 2, level('YetAnotherAppearance'))])
            archive.writestr('One/custom_limbus_data/skill/levels.json', json.dumps(
                {'list': [{'id': 91, 'skillData': [{'gaksungLevel': 4, 'defaultValue': 18}]}]}))
            archive.writestr('One/custom_limbus_locale/EN/personalityList/rows.json', json.dumps(
                {'dataList': [{'id': 1, 'title': '<b>New Title</b>'}]}))
            write('Two/custom_limbus_data/personality', [personality(4, 91)])
            write('Two/custom_limbus_data/skill', [skill(91, 1, level())])
            recipes = read_stock_coin_recipes(archive)

        self.assertEqual(len(recipes), 1)
        declaration, recipe = recipes[0]
        self.assertEqual((declaration.personality, declaration.label), ('1', 'New Title'))
        self.assertEqual([(s['skillId'], s['skillTier']) for s in recipe['skills']], [(91, 2)])
        self.assertEqual([(l['gaksungLevel'], l['coins'][0]['appearance']) for l in recipe['skills'][0]['levels']],
                         [(1, 'DifferentAppearance'), (4, 'DifferentAppearance')])
        self.assertEqual(recipe['issues'], [])


if __name__ == '__main__':
    unittest.main()
