import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))
import workbench

class AppearanceNamesTest(unittest.TestCase):
 def test_save_clear_and_validate(self):
  with tempfile.TemporaryDirectory() as d:
   store=object.__new__(workbench.Store); store.root=Path(d)
   store.lock=workbench.FileLock(store.root/'lock')
   (store.root/'identity_catalog.json').write_text('{"rows":[{"id":"one"}]}')
   store.save_appearance_name('one','Custom')
   self.assertEqual(workbench.read(store.root/'Workbench/appearance_names.json',{}), {'one':'Custom'})
   with self.assertRaises(ValueError): store.save_appearance_name('unknown','x')
   with self.assertRaises(ValueError): store.save_appearance_name('one','X\nY')
   store.save_appearance_name('one','')
   self.assertEqual(workbench.read(store.root/'Workbench/appearance_names.json',{}), {})
if __name__=='__main__': unittest.main()
