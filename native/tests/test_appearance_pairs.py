"""Verify the shipped registry offline. Optional arguments check it against source data."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_appearance_pairs import ROOT, build, expected_contracts


DATA = json.loads((ROOT.parent / 'addon/Workbench/data/appearance_pairs.json').read_bytes())
PAIRS = {(r['identity'], r['appearance']): r for r in DATA['pairs']}


class Counterparts(unittest.TestCase):
    def test_unique_exact_pairs_with_evidence(self):
        self.assertEqual(DATA['schema'], 1)
        self.assertEqual(len(PAIRS), len(DATA['pairs']))
        self.assertEqual(DATA['pairs'], sorted(DATA['pairs'], key=lambda row: (row['identity'], row['appearance'])))
        for row in DATA['pairs']:
            self.assertTrue(row['personality'].startswith(str(row['identity']) + '_'))
            self.assertTrue(row['appearance'].startswith('story_'))
            self.assertTrue(row['pool_id'].startswith('story_'))
            self.assertNotIn(row['personality'], row['aliases'])
            self.assertTrue(all(alias.startswith(str(row['identity']) + '_') for alias in row['aliases']))
            self.assertGreaterEqual(len(row['evidence']), 2)

    def test_specialized_routes_still_present(self):
        for ident, appearance, family, _ in expected_contracts():
            self.assertEqual(PAIRS[ident, 'story_' + appearance]['family'], family)

    def test_same_rank_or_shared_animation_is_not_ownership(self):
        # The Wedge twins share attacks. The Pequod heart shares Ahab's numeric ID.
        for ident, wrong in [(10316, '1584_PamelyAppearance'), (11017, '1585_PamelaAppearance'),
                             (10808, '8106_MobiDick_HeartAppearance'), (10315, '8380_SanchoAppearance'),
                             (10310, '8390_RealDon_1pAppearance'), (10215, '1325_Index_discipleAppearance'),
                             (11112, '1133_BlackHand_Mao_JaroAppearance')]:
            self.assertNotIn((ident, 'story_' + wrong), PAIRS)

    def test_legacy_pool_key_and_unusual_resource_names(self):
        self.assertEqual(PAIRS[10310, 'story_1079_Sancho_BerserkAppearance']['pool_id'], 'story_1079')
        self.assertIn((10312, 'story_400003_QueenOfHatred'), PAIRS)
        self.assertTrue(PAIRS[10814, 'story_1328_MiddleFinger_discipleAppearance']['personality'].endswith('Appearacne'))

    def test_native_source_and_target_orientation(self):
        groups = {row['identity']: row for row in DATA['native_forms']}
        self.assertEqual(set(groups), {10710, 10915, 11009, 11016})
        for ident, group in groups.items():
            self.assertEqual(len(set(group['appearances'])), 2)
            for pool_id in group['appearances']:
                row, = [r for (i, _), r in PAIRS.items() if i == ident and r['pool_id'] == pool_id]
                self.assertEqual(group['player'], [row['personality'], *row['aliases']])
        self.assertEqual(groups[10710]['appearances'][1], 'story_8173_MaouHeathclif_RideAppearance')
        self.assertEqual(groups[10915]['appearances'][1], 'story_1423_RingFinger_FauvismeDocent_Wolf2pAppearance')
        self.assertEqual(groups[11009]['appearances'][1], 'story_1587_Philip_AwakenAppearance')
        self.assertEqual(groups[11016]['appearances'][1], 'story_1517_Buffet_PerfectAppearance')


if __name__ == '__main__':
    if len(sys.argv) == 3:
        addon, archive = map(Path, sys.argv[1:])
        if build(addon, archive) != DATA:
            raise SystemExit('Source pool or databases no longer match the shipped registry')
        for row in DATA['pairs']:
            metadata = addon / 'Assets/runtime/story_native' / (row['pool_id'] + '.bin')
            if not metadata.is_file():
                raise SystemExit(f'Missing target motion metadata: {metadata}')
        del sys.argv[1:]
    unittest.main()
