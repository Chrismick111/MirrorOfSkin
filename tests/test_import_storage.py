"""Regression for single-copy resources and conservative legacy fallback."""
import hashlib
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

workbench = Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'
if workbench.is_dir():
    sys.path.insert(0, str(workbench))
import skin_import


class ImportStorageTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.appdata = root / 'roaming'
        self.data = self.appdata / 'FaustLauncher/MOS_data'
        self.addon = root / 'launcher/addons/MirrorOfSkin'
        self.addon.mkdir(parents=True)
        self.dll = self.addon / 'SinnersNative-v64.dll'
        self.dll.write_bytes(b'known runtime')
        allowed = patch.object(skin_import, 'NATIVE_USER_ASSETS',
                               {hashlib.sha256(self.dll.read_bytes()).hexdigest()})
        allowed.start()
        self.addCleanup(allowed.stop)
        environment = patch.dict(os.environ, {'APPDATA': str(self.appdata)})
        environment.start()
        self.addCleanup(environment.stop)
        self.files = ('Assets/Roland/BRoland.bundle', 'Assets/ImportedSkins/example.bundle',
                      'Assets/ImportedVoices/example.bank')
        for rel in self.files:
            p = self.data / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(rel.encode())

    def test_known_native_needs_only_special_roland_in_addon(self):
        skin_import.mirror_import_assets(self.data, self.addon)
        self.assertEqual((self.addon / self.files[0]).read_bytes(), self.files[0].encode())
        for rel in self.files[1:]:
            self.assertFalse((self.addon / rel).exists())
            self.assertEqual((self.data / rel).read_bytes(), rel.encode())

    def test_unknown_core_uses_legacy_mirror(self):
        self.dll.write_bytes(b'unknown core')
        skin_import.mirror_import_assets(self.data, self.addon)
        for rel in self.files:
            self.assertEqual((self.addon / rel).read_bytes(), rel.encode())

    def test_non_native_data_root_preserves_compatibility_mirror(self):
        with patch.dict(os.environ, {'APPDATA': str(self.appdata / 'different')}):
            skin_import.mirror_import_assets(self.data, self.addon)
        for rel in self.files:
            self.assertEqual((self.addon / rel).read_bytes(), rel.encode())


if __name__ == '__main__':
    unittest.main()
