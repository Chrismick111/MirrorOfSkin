"""Offline checks for Roland installation and local resource publication."""
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

WORKBENCH = pathlib.Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'
sys.path.insert(0, str(WORKBENCH))
import skin_import


class RolandImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name) / 'data'
        self.addon = pathlib.Path(self.tmp.name) / 'addon'
        metadata = self.root / 'Assets/runtime/story_native/story_BRolandBaseAppearance.bin'
        metadata.parent.mkdir(parents=True)
        metadata.write_bytes(b'valid-metadata')
        self.target = self.root / 'Assets/Roland/BRoland.bundle'
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b'old-bundle')

    def build(self, model, metadata):
        def build_fixture(archive, *, with_voice=False):
            return (model, metadata, {'state': 'found', 'count': 3}) if with_voice else (model, metadata)

        return patch.dict(sys.modules, {'roland_merge': types.SimpleNamespace(
            build_roland_bundle=build_fixture)})

    def test_mismatch_preserves_existing_model(self):
        with self.build(b'new-bundle', b'bad-metadata'):
            with self.assertRaises(ValueError):
                skin_import.install_roland_bundles('unused', self.root)
        self.assertEqual(self.target.read_bytes(), b'old-bundle')

    def test_matching_model_replaces_only_after_validation(self):
        with self.build(b'new-bundle', b'valid-metadata'):
            evidence = skin_import.install_roland_bundles('unused', self.root)
        self.assertEqual(evidence, {'state': 'found', 'count': 3})
        self.assertEqual(self.target.read_bytes(), b'new-bundle')

    def test_mirror_same_size_and_identical_root(self):
        target = self.addon / 'Assets/Roland/BRoland.bundle'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'new-bundle')
        skin_import.mirror_import_assets(self.root, self.addon)
        self.assertEqual(target.read_bytes(), b'old-bundle')
        skin_import.mirror_import_assets(self.root, self.root)
        self.assertEqual(self.target.read_bytes(), b'old-bundle')


if __name__ == '__main__':
    unittest.main()
