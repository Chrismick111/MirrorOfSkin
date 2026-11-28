"""Static guards for the single-file workbench UI."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'MirrorOfSkin' / 'Workbench' / 'ui' / 'index.html'


class WorkbenchUiTest(unittest.TestCase):
    def test_ruleset_cards_are_not_mapped_with_the_renderer_directly(self):
        text = INDEX.read_text(encoding='utf-8')
        # Array.map passes the index as the second argument, which would be
        # read as ``picker=True`` and hide the delete button on every card
        # after the first one.
        self.assertNotIn('.map(rulesetCard)', text)
        self.assertIn('.map((item) => rulesetCard(item))', text)

    def test_pool_add_opens_the_source_chooser_before_a_panel(self):
        text = INDEX.read_text(encoding='utf-8')
        self.assertIn('id="poolSourceModal"', text)
        self.assertIn('data-source="native"', text)
        self.assertIn('data-source="imported"', text)
        self.assertIn('function choosePoolSource(source)', text)


if __name__ == '__main__':
    unittest.main()