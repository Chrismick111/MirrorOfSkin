import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))
import _module_paths
from skin_assets import build_assets


class PrivateWorkflowTest(unittest.TestCase):
    def test_unrelated_model_in_same_root_does_not_hide_declared_coin_choreography(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / 'Collection.zip'
            with ZipFile(source, 'w') as package:
                person = {'id': 73, 'appearance': 'NativeBase', 'attributeList': [{'skillId': 12, 'number': 1}]}
                skill = {'id': 12, 'skillTier': 1, 'skillData': [{
                    'gaksungLevel': 1, 'skillMotion': 'S1', 'coinList': [{'abilityScriptList': [
                        {'scriptName': 'ChangeAppearance_OtherBody'}]}]}]}
                package.writestr('Nested/custom_limbus_data/personality/units.json', json.dumps([person]))
                package.writestr('Nested/custom_limbus_data/skill/skills.json', json.dumps([skill]))
                package.writestr('Nested/custom_appearance/unused.bundle', b'fixture')
            unity = Mock()
            unity.load.return_value.assets = [Mock(objects={1: Mock()})]
            with patch('skin_assets._catalog_keys', return_value={'SD_Personality/NativeBase.prefab'}), \
                 patch('skin_assets._roots', return_value=[('Assets/Unused.prefab', 1, 2)]), \
                 patch('stock_coin_import.build_coin_record', return_value={'look': 'coin-unit'}) as convert:
                self.assertEqual(list(build_assets(source, folder, unity)), [{'look': 'coin-unit'}])
                self.assertEqual(convert.call_args.args[0].personality, '73')

    def test_reports_unresolved_declaration_instead_of_generic_audio_error(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / 'Unknown.zip'
            with ZipFile(source, 'w') as package:
                package.writestr('Author/custom_limbus_data/personality/one.json',
                                 json.dumps([{'id': 73, 'appearance': '!custom_Unresolved'}]))
            with self.assertRaisesRegex(ValueError, r'73.*!custom_Unresolved'):
                list(build_assets(source, Path(tmp), Mock()))

    def test_archive_keeps_motion_frames_only_in_authored_motion_directories(self):
        from mod_archive import _supported_member
        from pathlib import PurePosixPath
        for marker in ('motion_appearances', 'custom_motions'):
            self.assertTrue(_supported_member(PurePosixPath(f'New/{marker}/Body/motions/S9/sprite.png')))
            self.assertFalse(_supported_member(PurePosixPath(f'New/{marker}/Body/unused_backup/sprite.png')))
