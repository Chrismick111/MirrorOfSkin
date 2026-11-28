import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))
import _module_paths  # noqa: F401
import rulesets


class RulesetHardeningTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        pools = {
            '101': {'entries': [
                {'identity_id': '10101', 'name': 'Default one', 'weight': 1},
                {'identity_id': '10117', 'name': 'Zero weight', 'weight': 0},
            ]},
            '102': {'entries': [
                {'identity_id': '10201', 'name': 'Zero only', 'weight': 0},
            ]},
        }
        catalog = self.root / 'Assets/runtime/all_sinners_pools.json'
        catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps(pools), encoding='utf8')
        rules = self.root / '规则集'
        rules.mkdir()
        self.identity = rules / '人格-10117.json'
        self.identity.write_text(json.dumps({
            'schema': 1, 'scope': 'identity', 'sinner': 101, 'identity': '10117',
            'name': 'Zero weight', 'entries': [],
        }), encoding='utf8')
        rulesets.save_state(self.root, {
            'schema': 1, 'global': False,
            'active': {'101': 'identity:10117'},
            'selected': {'id': 'identity:10117', 'kind': 'identity', 'sinner': '101', 'identity': '10117'},
        })

    def rule(self, kind='identity', sinner='101', identity='10117'):
        return {
            'id': ('identity:' + identity) if kind == 'identity' else (kind + ':' + sinner),
            'kind': kind, 'sinner': sinner, 'identity': identity,
        }

    def test_empty_identity_ruleset_can_be_activated(self):
        rulesets.activate(self.root, self.rule())
        self.assertEqual(rulesets.state(self.root)['active']['101'], 'identity:10117')

    def test_fill_default_rejects_empty_pool(self):
        with self.assertRaisesRegex(ValueError, '没有可填入的默认外观候选'):
            rulesets.fill_default(self.root, {'kind': 'sinner', 'sinner': '102'})

    def test_create_identity_starts_with_empty_entries(self):
        known = {'10201': {'source': '102', 'name': 'Zero only'}}
        data = rulesets.create_identity(self.root, '102', '10201', known)
        self.assertEqual(data['entries'], [])
        self.assertEqual(rulesets.entries(self.root, self.rule('identity', '102', '10201')), [])
        rulesets.activate(self.root, self.rule('identity', '102', '10201'))
        self.assertEqual(rulesets.state(self.root)['active']['102'], 'identity:10201')

    def test_sinner_mode_without_custom_pool_still_activates(self):
        rulesets.activate(self.root, self.rule('sinner'))
        self.assertEqual(rulesets.state(self.root)['active']['101'], 'sinner')

    def test_only_keeps_existing_identity_even_when_empty(self):
        rulesets.only(self.root, self.rule())
        self.assertEqual(rulesets.state(self.root)['active']['101'], 'identity:10117')

    def test_fill_default_populates_positive_candidates(self):
        entries = rulesets.fill_default(self.root, self.rule())
        self.assertEqual([item['identity_id'] for item in entries], ['10101'])


if __name__ == '__main__':
    unittest.main()
