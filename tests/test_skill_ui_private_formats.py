from io import BytesIO
import json
import os
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))

from skill_ui import collect


def image_file(format):
    output = BytesIO()
    Image.new('RGB', (4, 4), (100, 20, 30)).save(output, format=format)
    return output.getvalue()


def collect_files(files, record):
    output = BytesIO()
    with ZipFile(output, 'w') as archive:
        for path, value in files.items():
            archive.writestr(path, value if isinstance(value, bytes) else json.dumps(value))
    with ZipFile(output) as archive:
        [(data, images)] = collect(archive, [record])
    return [line.split('\t') for line in data.decode().splitlines()], images


class PrivateSkillUiFormatsTest(unittest.TestCase):
    def test_enemy_declaration_matches_prefab_and_reads_only_its_part_and_skills(self):
        record = {'entry': {'private_declaration': {'root': 'Mod', 'personality': '81000'}},
                  '_source_address': 'Assets/SD_Enemy/Boss.prefab'}
        files = {
            'Mod/custom_limbus_data/abnormality-unit/boss.json': {'list': [
                {'id': 92000, 'appearance': '!custom_Boss', 'viewid': 93000,
                 'abnormalityPartList': [92001],
                 'patternList': [{'slotList': [{'skillParentList': [
                     {'skillChildList': [{'skillID': 93201}]}]}]}]},
                {'id': 81000, 'appearance': 'Unrelated', 'abnormalityPartList': [92002]},
            ]},
            'Mod/custom_limbus_data/abnormality-part/parts.json': {'list': [
                {'id': 92001, 'attributeList': [{'skillId': 93101, 'number': 1}],
                 'passiveSet': {'passiveIdList': [93010]}},
                {'id': 92002, 'attributeList': [{'skillId': 93301, 'number': 1}]},
            ]},
            'Mod/custom_limbus_data/passive/boss.json': {'list': [
                {'id': 93010, 'scriptName': 'Modular/TIMING:BeforeUse/buff(Self,Armor,2,0,0)'},
            ]},
            'Mod/custom_limbus_data/buff/boss.json': {'list': [{'id': 'Armor'}]},
            'Mod/custom_limbus_data/skill/boss.json': {'list': [
                {'id': 93101, 'skillTier': 2, 'skillData': [{'defType': 'ATTACK'}]},
                {'id': 93201, 'skillTier': 1, 'skillData': [{'defType': 'GUARD'}]},
            ]},
            'Mod/custom_limbus_locale/JP/skillList/boss.json': {'dataList': [
                {'id': 93101, 'name': '攻撃'}, {'id': 93201, 'name': '防御'},
                {'id': 93301, 'name': 'Unrelated'},
            ]},
            'Mod/custom_sprites/profile_93000.jpg': image_file('JPEG'),
            'Mod/custom_sprites/skill_93101.webp': image_file('WEBP'),
            'Mod/custom_sprites/buffIcon_Armor.png': image_file('PNG'),
        }
        rows, images = collect_files(files, record)
        self.assertEqual([row[:5] for row in rows if row[0] == 'S'], [
            ['S', '93101', 'attack2', '0', '攻撃'], ['S', '93201', 'defense', '0', '防御'],
        ])
        self.assertEqual([row[0] for row in rows], ['MOSUI1', 'T', 'P', 'S', 'S', 'B', 'D'])
        self.assertEqual(rows[-1], ['D', '93201', 'GUARD'])
        for row in (rows[2], rows[3], rows[5]):
            self.assertTrue(images[row[-1]].startswith(b'\x89PNG'))

    def test_missing_preferred_names_fall_back_per_level(self):
        record = {'entry': {'private_declaration': {'root': 'Mod', 'personality': '81000'}}}
        files = {
            'Mod/custom_limbus_data/personality/a.json': {
                'list': [{'id': 81000, 'attributeList': [{'skillId': 81101, 'number': 1}]}]},
            'Mod/custom_limbus_data/skill/a.json': {'list': [{'id': 81101, 'skillTier': 1}]},
            'Mod/custom_limbus_locale/CN/skillList/a.json': {'list': [
                {'id': 81101, 'levelList': [{'level': 1, 'name': '开始'}, {'level': 3, 'desc': '说明'}]},
            ]},
            'Mod/custom_limbus_locale/EN/skillList/a.json': {'list': [
                {'id': 81101, 'levelList': [{'level': 1, 'name': 'Start'}, {'level': 3, 'name': 'Finisher'}]},
            ]},
        }
        rows, _ = collect_files(files, record)
        self.assertEqual([row[3:5] for row in rows if row[0] == 'S'], [['0', '开始'], ['3', 'Finisher']])

    def test_enemy_only_import_uses_the_actual_model_package(self):
        record = {'entry': {'identity_id': 'enemy'}, '_source_address': 'SD_Enemy/Boss.prefab',
                  '_source_member': 'Mod/custom_appearance/body.bundle'}
        files = {
            record['_source_member']: b'bundle',
            'Mod/custom_limbus_data/enemy-unit/boss.json': {
                'id': 92000, 'appearance': 'Boss', 'attributeList': [{'skillId': 92001, 'number': 1}]},
            'Mod/custom_limbus_locale/KR/skillList/boss.json':
                json.dumps({'dataList': [{'id': 92001, 'name': '공격'}]}).encode('utf-16'),
            'Neighbor/custom_limbus_data/enemy-unit/boss.json': {
                'id': 93000, 'appearance': 'Boss', 'attributeList': [{'skillId': 93001, 'number': 1}]},
            'Neighbor/custom_sprites/skill_92001.png': image_file('PNG'),
        }
        rows, images = collect_files(files, record)
        self.assertEqual(rows, [['MOSUI1'], ['T', '92000'], ['S', '92001', 'unknown', '0', '공격', '']])
        self.assertEqual(images, {})

    @unittest.skipUnless(os.environ.get('MOS_SKILL_UI_PURPLE_TEAR'), 'optional original Purple Tear package')
    def test_real_purple_tear_uses_unit_ids_to_disambiguate_shared_prefab(self):
        root = 'Reception of the Purple Tear'
        ids = (689043, 689044, 1048118, 99999)
        records = [{'entry': {'private_declaration': {'root': root, 'personality': str(ident)}},
                    '_source_address': 'SD_Enemy/iori.prefab'} for ident in ids]
        with ZipFile(os.environ['MOS_SKILL_UI_PURPLE_TEAR']) as archive:
            results = collect(archive, records)
        one, two, persona, unknown = [[line.split('\t') for line in content.decode().splitlines()]
                                      for content, _ in results]
        self.assertIn(['S', '68904301', 'conditional', '0', 'Serpent Sword Technique'],
                      [row[:5] for row in one])
        self.assertIn('ThePurpleTearBoss', {row[1] for row in two if row[0] == 'B'})
        self.assertNotIn('ThePurpleTearBoss', {row[1] for row in one if row[0] == 'B'})
        self.assertIn('ThePurpleTearPersonality', {row[1] for row in persona if row[0] == 'B'})
        self.assertIn(['D', '104811831', 'CONDITIONAL_EVADE'], persona)
        self.assertIn(['D', '104811833', 'CONDITIONAL_GUARD'], persona)
        self.assertIn(['D', '104811804', 'COUNTER'], persona)
        self.assertEqual(unknown, [['MOSUI1'], ['T', '99999']])


if __name__ == '__main__':
    unittest.main()
