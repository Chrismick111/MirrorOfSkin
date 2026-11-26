from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / 'MirrorOfSkin/Workbench'))
import _module_paths
from stock_appearance_composite import _selected, _validate_groups


class StockAppearanceCompositeTests(unittest.TestCase):
    def test_keeps_exact_coin_order_and_distinct_sources_in_one_group(self):
        groups = {10: [('Soldier', 9, 2), ('Other', 13, 0), ('Soldier', 9, 0)]}
        self.assertEqual(_validate_groups(groups, {'Soldier', 'Other'}), groups)

    def test_rejects_unknown_sources_and_invalid_details(self):
        for groups in ({10: [('Absent', 9, 0)]}, {17: [('Soldier', 9, 0)]},
                       {10: [('Soldier', 9, -1)]}, {10: []}):
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                _validate_groups(groups, {'Soldier'})

    def test_selects_authored_parts_by_index_without_pulling_in_the_rest(self):
        parts = [{'m_FileID': 0, 'm_PathID': i} for i in (21, 22, 23)]
        original = dict(_motiondetail=9, timelineAssets=parts, motionObjects=[], damageObj=[], isSpineAnim=0)
        prefab = SimpleNamespace(app={'motionList': [original]}, objects={i: object() for i in (21, 22, 23)})
        selected = _selected(prefab, 'Soldier', [(9, 2), (9, 0)])
        self.assertEqual(selected['timelineAssets'], [parts[2], parts[0]])
        self.assertEqual(original['timelineAssets'], parts)
        with self.assertRaisesRegex(ValueError, '9:3'):
            _selected(prefab, 'Soldier', [(9, 3)])


if __name__ == '__main__':
    unittest.main()
