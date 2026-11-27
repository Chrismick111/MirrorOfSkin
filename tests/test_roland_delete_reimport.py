import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1] / 'MirrorOfSkin'
sys.path.insert(0, str(BASE / 'Workbench'))
import _module_paths
import delete_imported
import skin_import
import skin_assets
import mod_archive
from file_lock import FileLock

class RolandLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'data'
        self.addon = Path(self.tmp.name) / 'addon'
        for rel in ('compatibility.json', skin_import.CATALOG, 'Assets/Roland/import-actions.json'):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(BASE / rel, target)
        for folder in (self.root, self.addon):
            path = folder / 'Assets/Roland/BRoland.bundle'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'previous-model')
        self.archive = Path(self.tmp.name) / 'RolandBundle.zip'
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr('custom_appearance/model.bundle', b'fixture')

    def rows(self):
        data = json.loads((self.root / skin_import.CATALOG).read_bytes())
        return [e for g in data.values() for e in g['entries'] if e.get('identity_id') == skin_import.BUILTIN]

    def run_import(self):
        def install(_archive, root):
            (root / 'Assets/Roland/BRoland.bundle').write_bytes(b'new-model')
        with patch.object(skin_assets, 'build_assets', return_value=iter([{'builtin':'roland'}])), patch.object(skin_import, 'install_roland_bundles', side_effect=install):
            return skin_import._import_normalized(self.archive, self.root, unity=object())

    def test_delete_then_reimport_restores_catalog_and_assets(self):
        delete_imported.delete(self.root, skin_import.BUILTIN, lock_factory=FileLock, addon=self.addon)
        self.assertFalse(self.rows())
        self.assertFalse((self.root / 'Assets/Roland/BRoland.bundle').exists())
        self.assertFalse((self.addon / 'Assets/Roland/BRoland.bundle').exists())
        self.assertIn(skin_import.BUILTIN, json.loads((self.root/'imported-skin-deletions.json').read_bytes()))
        self.assertEqual(self.run_import()[0]['status'], 'added')
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual((self.root/'Assets/Roland/BRoland.bundle').read_bytes(), b'new-model')
        self.assertNotIn(skin_import.BUILTIN, json.loads((self.root/'imported-skin-deletions.json').read_bytes()))

    def test_missing_bundle_reports_reinstalled(self):
        (self.root/'Assets/Roland/BRoland.bundle').unlink()
        self.assertEqual(self.run_import()[0]['status'], 'updated')

    def test_loose_roland_bundles_are_imported_as_one_set(self):
        folder = Path(self.tmp.name)/'original'
        folder.mkdir()
        for name in ('BRoland.bundle','BRolandGun.bundle','BRolandUltraSword.bundle'):
            (folder/name).write_bytes(name.encode())
        with mod_archive.normalized(folder/'BRoland.bundle') as archive:
            with zipfile.ZipFile(archive) as z:
                self.assertEqual({Path(i.filename).name for i in z.infolist()},
                                 {'BRoland.bundle','BRolandGun.bundle','BRolandUltraSword.bundle'})
        (folder/'BRolandGun.bundle').unlink()
        with self.assertRaisesRegex(ValueError, '三个'):
            with mod_archive.normalized(folder/'BRoland.bundle'): pass

if __name__ == '__main__': unittest.main()
