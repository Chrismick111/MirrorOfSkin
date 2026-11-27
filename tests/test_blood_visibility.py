import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))
import workbench


class BloodVisibilityTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        pools = self.root / 'Assets/runtime/all_sinners_pools.json'
        pools.parent.mkdir(parents=True)
        pools.write_text(json.dumps({'101': {'entries': [{'identity_id': 'story_WBImp_example'}]}}))
        (self.root / 'identity_catalog.json').write_text('{"rows":[{"id":10101}]}')

    def store(self):
        store = object.__new__(workbench.Store)
        store.root = self.root
        store.lock = workbench.FileLock(self.root / 'workbench-save.lock')
        return store

    def test_independent_and_persistent(self):
        first = self.store()
        self.assertEqual(first.blood_visible_ids(), [])
        first.save_blood_visibility('10101', True)
        first.save_blood_visibility('story_WBImp_example', True)
        other = self.store()
        self.assertEqual(other.blood_visible_ids(), ['10101', 'story_WBImp_example'])
        self.assertEqual(other.save_blood_visibility('10101', False),
                         {'blood_visible_ids': ['story_WBImp_example']})
        self.assertEqual((self.root / 'appearance-blood-visibility.txt').read_bytes(),
                         b'story_WBImp_example\n')
        self.assertEqual(first.blood_visible_ids(), ['story_WBImp_example'])

    def test_invalid_input_keeps_settings(self):
        store = self.store()
        store.save_blood_visibility('10101', True)
        for identity, value in [('unknown', True), ('10101', 'false'), ('10101\nother', True)]:
            with self.subTest(identity=identity, value=value), self.assertRaises(ValueError):
                store.save_blood_visibility(identity, value)
        self.assertEqual(store.blood_visible_ids(), ['10101'])


if __name__ == '__main__':
    unittest.main()
