from io import BytesIO
import json
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))
from private_server_appearance import gameplay_only_package


class GameplayOnlyTests(unittest.TestCase):
    def classified(self, entries):
        with ZipFile(BytesIO(), 'w') as z:
            for path, value in entries.items():
                z.writestr('Author/' + path, json.dumps(value) if isinstance(value, dict) else value)
            return gameplay_only_package(z)

    def test_skill_rules_without_art(self):
        rules = {'list': [{'id': 27, 'skillData': [{'skillMotion': 'S1'}]}]}
        self.assertTrue(self.classified({'custom_limbus_data/skill/renamed.json': rules,
                                         'custom_appearance/copied.json': {'list': [{'appearance': 'StockBody'}]}}))
        self.assertFalse(self.classified({'custom_limbus_data/skill/renamed.json': rules,
                                          'unused_location/body.bundle': b'UnityFS'}))

    def test_unsupported_models_and_empty_data_are_not_called_gameplay_only(self):
        self.assertFalse(self.classified({'custom_limbus_data/skill/data.json': {'list': []}}))
        self.assertFalse(self.classified({'custom_limbus_data/skill/data.json': {'list': [{'id': 5}]},
                                          'custom_limbus_data/personality/data.json': {'list': [{'id': 2, 'appearance': '!custom_NewBody'}]}}))
