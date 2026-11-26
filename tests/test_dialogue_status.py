import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))
import imported_catalog


class DialogueStatusTests(unittest.TestCase):
    def test_live_bank_binding_is_scoped_and_does_not_replace_saved_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            library = root / 'Assets/ImportedVoices'
            revision = '1' * 64
            folder = library / revision
            folder.mkdir(parents=True)
            bank = folder / 'voices.bank'
            bank.touch()
            a, b = ('WBImp_' + c * 24 for c in 'ab')
            (library / 'bindings.tsv').write_text(
                f'{a}\t10101\t{revision}\tvoices.bank\n{b}\t10202\t{revision}\tvoices.bank\n',
                encoding='ascii')
            (folder / 'bubbles.tsv').write_text('10101\tbattle_kill_10101_1\t台词\n', encoding='utf8')
            raw = {'voice': 'found', 'bubble': 'none'}
            def view():
                rows = {'story_' + look: {'identity_id': 'story_' + look, 'name': look, 'dialogue_detection': raw}
                        for look in (a, b)}
                imported_catalog.apply(rows, root)
                return [row['dialogue_detection'] for row in rows.values()]
            self.assertEqual(view(), [{'voice': 'connected', 'bubble': 'connected'},
                                      {'voice': 'connected', 'bubble': 'none'}])
            bank.unlink()
            self.assertEqual(view(), [raw, raw])
            self.assertEqual(raw, {'voice': 'found', 'bubble': 'none'})
