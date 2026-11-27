import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import wave
from zipfile import ZipFile

WORKBENCH = Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'
sys.path.insert(0, str(WORKBENCH))
import _module_paths  # noqa: F401


def wave_bytes():
    out = io.BytesIO()
    with wave.open(out, 'wb') as audio:
        audio.setparams((1, 1, 8000, 3, 'NONE', 'not compressed'))
        audio.writeframes(b'xyz')
    return out.getvalue()


def record(root, owner, label):
    return {'name': label, 'entry': {'private_declaration': {
        'root': root, 'personality': owner}}}


class AppearanceDialogueTests(unittest.TestCase):
    def detect(self, files, records, *, directory=False):
        from appearance_dialogue import for_record, scan_archive
        from mod_archive import normalized

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payloads = {name: data if isinstance(data, bytes) else json.dumps(data).encode()
                        for name, data in files.items()}
            if directory:
                for name, data in payloads.items():
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                with normalized(root) as archive:
                    scan = scan_archive(archive)
            else:
                path = root / 'sample.zip'
                with ZipFile(path, 'w') as archive:
                    for name, data in payloads.items():
                        archive.writestr(name, data)
                scan = scan_archive(path)
            return [for_record(scan, item, records) for item in records]

    def test_framepack_dialogue_is_limited_to_the_declared_skin_and_owner(self):
        first, second = 'pack/skins/first', 'pack/skins/second'
        files = {'pack/pack.json': {'schema_version': 2, 'pack_id': 'pack', 'skins': ['first', 'second']}}
        for root, owner in ((first, 10123), (second, 10987)):
            files[root + '/manifest.json'] = {
                'schema_version': 2,
                'meta': {'skin_id': root.rsplit('/', 1)[-1], 'display_name': root},
                'target': {'kind': 'personality', 'personality_id': owner},
                'visual': {'sd_frames_dir': 'assets/sd_frames'},
                'voice': {'dir': 'voice'},
                'locale': {'exclusive_dir': 'locale/exclusive'},
            }
            files[root + '/assets/sd_frames/Default.png'] = b'\x89PNG\r\n\x1a\n'
        files.update({
            first + '/voice/battle_special_10123_2_3-01.wav': wave_bytes(),
            first + '/voice/battle_break_10987_1.wav': wave_bytes(),
            second + '/voice/battle_break_10987_1.wav': b'not audio',
            second + '/other/battle_break_10987_1.wav': wave_bytes(),
            first + '/locale/exclusive/battleSpeechBubbleText/first.json': {
                'battle_s3_10123': {'id': 'battle_s3_10123', 'dlg': '  我来帮忙！  '},
            },
            second + '/locale/exclusive/battleSpeechBubbleText/second.json': {
                'battle_s3_10123': {'id': 'battle_s3_10123', 'dlg': '同包另一角色'},
                'battle_special_10987_1': {'id': 'battle_special_10987_2', 'dlg': '编号不一致'},
            },
            second + '/locale/shared_optional/battleSpeechBubbleText/second.json': {
                'dataList': [{'id': 'battle_s3_10987_1', 'dlg': '非专属台词'}],
            },
        })
        self.assertEqual(self.detect(files, [record(first, '10123', 'First'),
                                             record(second, '10987', 'Second'),
                                             record('another/skins/first', '10123', 'Unrelated')]),
                         [{'voice': 'found', 'bubble': 'found'},
                          {'voice': 'unknown', 'bubble': 'none'},
                          {'voice': 'none', 'bubble': 'none'}])

    def test_scoped_declared_audio_and_foreign_bubble(self):
        files = {
            'mod/custom_limbus_data/personality/Medic.json': {
                'list': [{'id': 10123, 'appearance': '!motions_Medic_Merged'}]},
            'mod/custom_limbus_data/personality/Summon.json': {
                'list': [{'id': 10987, 'appearance': '!motions_Summon'}]},
            'mod/custom_sounds/Audio.json': {'sounds': [
                {'name': 'MedicBattle1', 'file': 'Sounds/Battle_1.wav', 'soundType': 'Voice'},
                {'name': 'SummonHit', 'file': 'SFX/impact.wav', 'soundType': 'Voice'}]},
            'mod/custom_sounds/Sounds/Battle_1.wav': wave_bytes(),
            'mod/custom_sounds/SFX/impact.wav': wave_bytes(),
            'mod/custom_limbus_locale/ZH/battleSpeechBubbleText/ZH_BattleSpeechBubbleDlg.json':
                {'dataList': [{'id': 'battle_react_10987_1', 'dlg': '台词'}]},
            'mod/custom_limbus_locale/ZH/Story/Voice_Other_10123.json':
                {'dataList': [{'id': 'battle_react_10123_1', 'dlg': '剧情文件'}]},
        }
        for directory in (False, True):
            with self.subTest(directory=directory):
                self.assertEqual(self.detect(files, [record('mod', '10123', 'a'),
                                                     record('mod', '10987', 'b')], directory=directory),
                                 [{'voice': 'found', 'bubble': 'none'}, {'voice': 'none', 'bubble': 'found'}])

    def test_battle_voice_mapping_uses_real_audio_and_keeps_text_metadata_separate(self):
        files = {
            'custom_sounds/OperatorVoices.json': {'personalityId': 10123, 'lines': [
                {'voiceId': 'battleentry_10123_1', 'file': 'Voice/Operator/Voice_Operator_kr_023.wav',
                 'text': '战斗台词'},
                {'voiceId': 'lobby_10987_1', 'file': 'Voice/Operator/Voice_Operator_kr_019.wav'}]},
            'custom_sounds/Voice/Operator/Voice_Operator_kr_023.wav': wave_bytes(),
            'custom_sounds/Voice/Operator/Voice_Operator_kr_019.wav': wave_bytes(),
            'custom_limbus_locale/EN/battleSpeechBubbleText/empty.json': {'dataList': []},
        }
        records = [record('', '10123', 'operator'), record('', '10987', 'other')]
        self.assertEqual(self.detect(files, records),
                         [{'voice': 'found', 'bubble': 'text_only'}, {'voice': 'none', 'bubble': 'none'}])
        files['custom_sounds/Voice/Operator/Voice_Operator_kr_023.wav'] = b'broken'
        self.assertEqual(self.detect(files, records)[0]['voice'], 'unknown')

    def test_unnamed_battle_voice_is_unassigned_between_units(self):
        files = {'custom_sounds/Voice/Battle_1.wav': wave_bytes(),
                 'custom_sounds/Sounds/IoriBGM.wav': wave_bytes(),
                 'custom_limbus_locale/EN/PersonalityVoiceDlg/Voice_Operator_10123.json':
                     {'dataList': [{'id': 'get_10123_1', 'dlg': '入队'}]}}
        self.assertEqual(self.detect(files, [record('', '10123', 'unknown A'),
                                             record('', '10987', 'unknown B')]),
                         [{'voice': 'unassigned', 'bubble': 'none'}] * 2)

    def test_battle_skill_script_links_custom_sound_and_inline_bubble(self):
        files = {
            'mod/custom_limbus_data/personality/Medic.json': {'list': [
                {'id': 10123, 'appearance': '!motions_Medic', 'skillIdList': [{'skillId': 56001}]},
                {'id': 10987, 'appearance': '!motions_Other', 'defenseSkillIDList': [56002]}]},
            'mod/custom_limbus_data/skill/Combat.json': {'list': [
                {'id': 56001, 'skillData': [{'abilityScriptList': [
                    {'scriptName': 'Modular/TIMING:OnVisualUse/battledialogline(Self,Ready!):playcustomsound(TacticalLine)'}]}]},
                {'id': 56002, 'skillData': [{'abilityScriptList': [
                    {'scriptName': 'Modular/TIMING:OnVisualUse/playcustomsound(Impact)'},
                    {'scriptName': 'Modular/TIMING:StartVisualDuel/playcustomsound(TacticalLine)/battledialogline(id10123,Ready!)'}]}]}]},
            'mod/custom_sounds/Audio.json': {'sounds': [
                {'name': 'TacticalLine', 'file': 'Sounds/speech.wav', 'soundType': 'Voice'},
                {'name': 'Impact', 'file': 'Sounds/impact.wav', 'soundType': 'Effect'}]},
            'mod/custom_sounds/Sounds/speech.wav': wave_bytes(),
            'mod/custom_sounds/Sounds/impact.wav': wave_bytes(),
        }
        self.assertEqual(self.detect(files, [record('mod', '10123', 'Medic'),
                                             record('mod', '10987', 'Other')]),
                         [{'voice': 'found', 'bubble': 'found'}, {'voice': 'none', 'bubble': 'none'}])

    def test_conflicting_locale_copies_preserve_bank_and_canonical_personal_line(self):
        from bank_mod import import_banks
        from test_voice_universality import bank
        from voice_binding import sync_bubble_text

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'sample.zip'
            with ZipFile(source, 'w') as out:
                out.writestr('Unique.bank', bank([('battle_react_10123_1', 4000, 1)]))
                for language, line in (('CN', '甲'), ('JP', '乙')):
                    out.writestr(f'custom_limbus_locale/{language}/battleSpeechBubbleText/BattleSpeechBubbleDlg.json',
                                 json.dumps({'dataList': [{'id': 'battle_react_10123_1', 'dlg': line}]}))
                out.writestr('Voice_Example_10123.json',
                             json.dumps({'dataList': [{'id': 'battle_entry_10123_1', 'dlg': '个人台词'}]}))
            imported = import_banks(source, root)
            folder = root / 'Assets/ImportedVoices' / imported['revision']
            sync_bubble_text(folder, {'10123'})
            self.assertEqual((folder / 'bubbles.tsv').read_text(encoding='utf8'),
                             '10123\tbattle_entry_10123_1\t个人台词\n')


if __name__ == '__main__':
    unittest.main()
