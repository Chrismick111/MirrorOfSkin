from pathlib import Path, PurePosixPath
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))
from private_server_appearance import Declaration
from private_identity import PrivateIdentities


def personality(root, value):
    return Declaration(PurePosixPath(root), str(value), '!custom_Actual', 'Example', False, 8)


class PrivateIdentityTest(unittest.TestCase):
    def test_separates_independent_declarations_with_identical_legacy_keys(self):
        a, b = personality('Collection/A', 811), personality('Collection/B', 812)
        choices = [(a, 'WBImp_old'), (b, 'WBImp_old')]
        identities = PrivateIdentities(choices, [], 'joined.zip')
        self.assertNotEqual(identities.look(a, 'WBImp_old'), identities.look(b, 'WBImp_old'))

    def test_legacy_entry_stays_with_recorded_source_when_reimported(self):
        a = personality('Collection/A', 811)
        old = dict(identity_id='story_WBImp_old', import_source='original', weight=9, name='Custom')
        theirs = PrivateIdentities([(a, 'WBImp_old')], [old], 'other.zip')
        self.assertNotEqual(theirs.look(a, 'WBImp_old'), 'WBImp_old')
        original = PrivateIdentities([(a, 'WBImp_old')], [old], 'original.zip')
        self.assertEqual(original.look(a, 'WBImp_old'), 'WBImp_old')
        linked = dict(old, private_declaration=original.owner(a))
        renamed_bundle = PrivateIdentities([(a, 'WBImp_new_basename')], [linked], 'original.zip')
        self.assertEqual(renamed_bundle.look(a, 'WBImp_new_basename'), 'WBImp_old')

    def test_ambiguous_legacy_entries_are_not_claimed_by_one_of_two_declarations(self):
        a, b = personality('Collection/A', 811), personality('Collection/B', 812)
        old = dict(identity_id='story_WBImp_old', import_source='joined')
        plans = PrivateIdentities([(a, 'WBImp_old'), (b, 'WBImp_old')], [old], 'joined.zip')
        self.assertNotIn('WBImp_old', [plans.look(a, 'WBImp_old'), plans.look(b, 'WBImp_old')])
