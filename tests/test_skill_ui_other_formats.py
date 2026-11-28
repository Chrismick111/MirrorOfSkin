from io import BytesIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))


def image(color='red'):
    return Image.new('RGBA', (8, 8), color)


def png(color='red'):
    data = BytesIO()
    image(color).save(data, 'PNG')
    return data.getvalue()


def prefab(owner):
    return f'Assets/Resources_moved/Prefab/SD/{owner}_ExampleAppearance.prefab'


def sprite(color='red'):
    texture = SimpleNamespace(file_id=0, path_id=3, read=lambda: SimpleNamespace(m_Width=8, m_Height=8))
    content = SimpleNamespace(image=image(color), m_RD=SimpleNamespace(texture=texture))
    return SimpleNamespace(type=SimpleNamespace(name='Sprite'), path_id=2, read=lambda: content)


def asset(kind):
    return SimpleNamespace(type=SimpleNamespace(name=kind))


def text_asset(*rows):
    return SimpleNamespace(
        type=SimpleNamespace(name='TextAsset'), path_id=4,
        read=lambda: SimpleNamespace(m_Script=json.dumps({'list': rows})),
    )


class ExternalSkillUiTest(unittest.TestCase):
    def test_rollback_can_rejoin_author_name_at_an_inherited_level(self):
        from skill_ui_import import _embedded_name_changes
        installed = {'en': [{'id': 1011501, 'name': 'New'}]}
        original = {'en': [{'id': 1011501, 'name': 'Old',
                            'levelList': [{'level': 3, 'name': 'New'}]}]}
        changes = _embedded_name_changes(installed, original)[1011501]
        self.assertEqual(changes[0], 'New')
        self.assertIsNone(changes[3])

    def collect(self, files, records, environments):
        from skill_ui_import import collect_external

        data = BytesIO()
        with ZipFile(data, 'w') as archive:
            for name, content in files.items():
                archive.writestr(name, json.dumps(content) if isinstance(content, dict) else content)
        unity = SimpleNamespace(load=lambda raw: SimpleNamespace(container=environments[raw]))
        with ZipFile(data) as archive, patch('skill_ui_import.validated_unpacked_size', return_value=0):
            return collect_external(archive, records, unity=unity)

    def test_install_uses_only_assets_owned_by_selected_model(self):
        member = 'Example/Installation/abc/def/__data'
        refs = {
            prefab(10115): asset('GameObject'), prefab(10315): asset('GameObject'),
            'Assets/Resources_moved/Sprite/SkillIcon/1011501.png': sprite(),
            'Assets/Resources_moved/Sprite/SkillIcon/1011501_4.png': sprite('blue'),
            'Assets/Resources_moved/Sprite/SkillIcon/1031501.png': sprite(),
            'Assets/Resources_moved/Sprite/SkillIcon/10115099.png': sprite(),
            'Assets/Resources_moved/Sprite/Unit/Profile/Normal/10115_normal_profile.png': sprite(),
            'Assets/Resources_moved/Buf/Marker.png': sprite(),
            'Assets/Resources_moved/Buf/Unknown.png': sprite(),
        }
        files = {
            member: b'bundle',
            'Example/custom_limbus_data/personality/one.json': {'list': [
                {'id': 10115, 'appearance': '10115_ExampleAppearance', 'attributeList': [
                    {'skillId': 1011501, 'number': 3}]},
            ]},
            'Example/custom_limbus_data/skill/one.json': {'list': [
                {'id': 1011501, 'skillTier': 1, 'skillData': [
                    {'gaksungLevel': 1, 'abilityScriptList': [
                        {'scriptName': 'Modular/TIMING:BeforeUse/buff(Target,Marker,2,0,0)'}]}]},
            ]},
            'Example/custom_limbus_data/buff/one.json': {'list': [{'id': 'Marker'}, {'id': 'Unknown'}]},
            'Example/custom_limbus_locale/EN/skillList/one.json': {'list': [
                {'id': 1011501, 'name': 'Authored Slash'}, {'id': 1031501, 'name': 'Other Name'}]},
        }
        one, two = self.collect(files, [
            {'_source_member': member, '_source_address': prefab(10115)},
            {'_source_member': member, '_source_address': prefab(10315)},
        ], {b'bundle': refs})
        self.assertEqual(one, (10115, [(1011501, 'attack1', 0, 'Authored Slash', png()),
                                       (1011501, 'attack1', 4, 'Authored Slash', png('blue'))],
                               {'Marker': png()}, png()))
        self.assertEqual(two, (10315, [(1031501, 'unknown', 0, 'Other Name', png())], {}, b''))

    def test_chapter_manifest_binds_icons_to_published_model(self):
        prefix = 'Lethe/mods/Example/'
        member = prefix + 'archived_bundles/enemy.bundle'
        icon = 'Assets/Resources_moved/Sprite/SkillIcon/128801.png'
        portrait = 'Assets/Resources_moved/Sprite/Unit/Portrait/Example/1288_portrait.png'
        listing = '\n'.join([
            f'UnityEngine.GameObject\t{prefab(1288)}\tenemy.bundle\tSD/1288.prefab',
            f'UnityEngine.Sprite\t{icon}\tui.bundle\tSkillIcon/128801.png',
            f'UnityEngine.Sprite\t{portrait}\tui.bundle\tPortrait/1288_portrait.png',
        ])
        files = {prefix + 'archive_locations.tsv': listing, member: b'enemy',
                 prefix + 'archived_bundles/ui.bundle': b'ui'}
        one, two = self.collect(files, [
            {'_source_member': member, '_source_address': prefab(1288)},
            {'_source_member': member, '_source_address': prefab(1289)},
        ], {b'enemy': {prefab(1288): asset('GameObject'), prefab(1289): asset('GameObject')},
            b'ui': {icon: sprite(), portrait: sprite()}})
        self.assertEqual(one, (1288, [(128801, 'unknown', 0, '', png())], {}, png()))
        self.assertEqual(two, (None, [], {}, b''))

    def test_name_upgrade_keeps_the_current_authored_icon(self):
        member = 'Example/custom_appearance/hero.bundle'
        files = {
            member: b'bundle',
            'Example/TextData/EN/TextData_Skill.json': {'list': [{
                'id': 1011501, 'levelList': [{'level': 1, 'name': 'Slash'},
                                             {'level': 3, 'name': 'Finisher'}],
            }]},
            'Example/custom_limbus_data/personality/one.json': {'list': [{
                'id': 10115, 'attributeList': [{'skillId': 1011501, 'number': 1}],
            }]},
            'Example/custom_limbus_data/skill/one.json': {'list': [{
                'id': 1011501, 'skillData': [{'gaksungLevel': 4, 'iconID': 1011502}],
            }]},
        }
        icon = 'Assets/Resources_moved/Sprite/SkillIcon/'
        [result] = self.collect(files, [{'_source_member': member, '_source_address': prefab(10115)}], {
            b'bundle': {prefab(10115): asset('GameObject'),
                        icon + '1011501.png': sprite(), icon + '1011501_2.png': sprite('blue'),
                        icon + '1011502.png': sprite('green')},
        })
        self.assertEqual(result, (10115, [(1011501, 'unknown', 0, 'Slash', png()),
                                          (1011501, 'unknown', 2, 'Slash', png('blue')),
                                          (1011501, 'unknown', 3, 'Finisher', png('blue')),
                                          (1011501, 'unknown', 4, 'Finisher', png('green'))], {}, b''))

    def test_loose_and_embedded_skill_names_do_not_require_icons_or_coin_counts(self):
        member = 'Example/custom_appearance/hero.bundle'
        text = SimpleNamespace(type=SimpleNamespace(name='TextAsset'), path_id=4,
                               read=lambda: SimpleNamespace(m_Script=(
                                   '{"list":[{"id":1011599,"name":"Embedded"},'
                                   '{"id":1011699,"name":"Another Character"}]}')))
        files = {
            member: b'bundle',
            'Example/TextData/EN/TextData_Skill.json': {'list': [{'id': 1011501, 'name': 'Loose'}]},
            'Example/OtherMod/TextData_Skill.json': {'list': [{'id': 1011502, 'name': 'Foreign scope'}]},
        }
        [result] = self.collect(files, [{'_source_member': member, '_source_address': prefab(10115)}],
                                {b'bundle': {prefab(10115): asset('GameObject'),
                                            'Assets/TextData/EN/EN_TextData_Skill.json': text}})
        self.assertEqual(result, (10115, [(1011501, 'unknown', 0, 'Loose', b''),
                                         (1011599, 'unknown', 0, 'Embedded', b'')], {}, b''))

    def test_carra2_requires_authored_sprite_or_texture_object(self):
        from skill_ui_import import collect_external

        low, high = 'a' * 32, 'b' * 32
        member = f'Example/Installation/{low}/{high}/__data'
        data, model_data = BytesIO(), BytesIO()
        with ZipFile(data, 'w') as archive:
            archive.writestr(f'{low}/{high}/3.0', b'patched texture')
        with ZipFile(model_data, 'w') as archive:
            archive.writestr(member, b'materialized bundle')
        authored, stock = sprite(), sprite()
        stock.path_id = 12
        stock.read().m_RD.texture.path_id = 13
        unity = SimpleNamespace(load=lambda _: SimpleNamespace(container={
            prefab(10115): asset('GameObject'),
            'Assets/Resources_moved/Sprite/SkillIcon/1011501.png': authored,
            'Assets/Resources_moved/Sprite/SkillIcon/1011502.png': stock,
        }))
        with ZipFile(data) as archive, ZipFile(model_data) as model_archive, patch(
                'skill_ui_import.validated_unpacked_size', return_value=0):
            [result] = collect_external(archive, [{'_source_member': member, '_source_address': prefab(10115)}],
                                        model_archive=model_archive, unity=unity)
        self.assertEqual(result, (10115, [(1011501, 'unknown', 0, '', png())], {}, b''))

    def test_unchanged_installation_art_matches_rollback_and_is_omitted(self):
        member = 'Example/Installation/abc/def/__data'
        rollback = 'Example/Uninstallation/abc/def/__data'
        changed = 'Assets/Resources_moved/Sprite/SkillIcon/1011501.png'
        unchanged = 'Assets/Resources_moved/Sprite/SkillIcon/1011502.png'
        [result] = self.collect({member: b'bundle', rollback: b'rollback'},
                                [{'_source_member': member, '_source_address': prefab(10115)}],
                                {b'bundle': {prefab(10115): asset('GameObject'),
                                             changed: sprite('blue'), unchanged: sprite()},
                                 b'rollback': {changed: sprite(), unchanged: sprite()}})
        self.assertEqual(result, (10115, [(1011501, 'unknown', 0, '', png('blue'))], {}, b''))

    def test_installation_names_compare_fields_including_renamed_text_assets(self):
        member = 'Example/Installation/abc/def/__data'
        rollback = 'Example/Uninstallation/abc/def/__data'
        changed = {'id': 1011501, 'levelList': [{'level': 1, 'name': 'Author name'},
                                               {'level': 3, 'name': 'Stock upgrade'}]}
        stock = {'id': 1011501, 'levelList': [{'level': 1, 'name': 'Stock name'},
                                             {'level': 3, 'name': 'Stock upgrade'}]}
        unchanged = {'id': 1011502, 'name': 'Stock defense'}
        stock_loose = {'id': 1011503, 'name': 'Independent author text'}
        chinese = {'id': 1011502, 'name': '原防御'}
        loose_member = 'Example/TextData/EN/TextData_Skill.json'
        files = {member: b'bundle', rollback: b'rollback',
                 loose_member: {'list': [stock_loose]}}
        [result] = self.collect(files, [{'_source_member': member, '_source_address': prefab(10115)}], {
            b'bundle': {prefab(10115): asset('GameObject'),
                        'Assets/TextData/EN/TextData_Skill_changed.json': text_asset(changed, unchanged, stock_loose),
                        'Assets/TextData/CN/TextData_Skill.json': text_asset(chinese, {'id': 1011504, 'name': '改名'})},
            b'rollback': {
                'Assets/TextData/EN/TextData_Skill_stock.json': text_asset(stock, unchanged, stock_loose),
                'Assets/TextData/CN/TextData_Skill.json': text_asset(chinese, {'id': 1011504, 'name': '原名'}),
            },
        })
        self.assertEqual(result, (10115, [(1011501, 'unknown', 0, 'Author name', b''),
                                         (1011501, 'unknown', 3, None, b''),
                                         (1011503, 'unknown', 0, 'Independent author text', b''),
                                         (1011504, 'unknown', 0, '改名', b'')], {}, b''))
