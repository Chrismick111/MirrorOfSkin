import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin'))
import release_compatibility as compat


class GameBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.names = ('GameAssembly.dll', 'UnityPlayer.dll',
                      'LimbusCompany_Data/il2cpp_data/Metadata/global-metadata.dat')
        self.old = self.write_build(b'old')
        self.new = self.write_build(b'new')
        self.manifest = {'game_files': self.old, 'additional_game_builds': {'26917622': self.new}}

    def write_build(self, marker):
        result = {}
        for name in self.names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            data = marker + name.encode()
            path.write_bytes(data)
            result[name] = hashlib.sha256(data).hexdigest()
        return result

    def test_current_build_reads_each_file_once(self):
        with patch.object(compat, 'digest', wraps=compat.digest) as hashed:
            self.assertEqual(compat.select_game_files(self.root, self.manifest), self.new)
            self.assertEqual(hashed.call_count, len(self.names))

    def test_old_build_and_original_manifest(self):
        self.write_build(b'old')
        for manifest in (self.manifest, {'game_files': self.old}):
            self.assertEqual(compat.select_game_files(self.root, manifest), self.old)

    def test_mixed_unknown_and_missing_files_are_rejected(self):
        file = self.root / self.names[1]
        for value in (b'old' + self.names[1].encode(), b'unknown', None):
            with self.subTest(value=value):
                if value is None:
                    file.unlink()
                else:
                    file.write_bytes(value)
                with self.assertRaisesRegex(compat.CompatibilityError, 'UnityPlayer'):
                    compat.select_game_files(self.root, self.manifest)

    def test_incomplete_profile_is_rejected(self):
        self.manifest['additional_game_builds']['26917622'] = {self.names[0]: self.new[self.names[0]]}
        with self.assertRaises(compat.CompatibilityError):
            compat.select_game_files(self.root, self.manifest)


if __name__ == '__main__':
    unittest.main()
