"""Ensure personal imported assets and identities do not enter release archives."""
import hashlib
import json
import lzma
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

WORKBENCH = Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'
sys.path.insert(0, str(WORKBENCH))
import _module_paths
import package_release
import github_update


class ReleasePrivacyTest(unittest.TestCase):
    def test_packed_chapters_round_trip_in_release_scanner_and_user_data(self):
        import discovery_metadata
        import mos_data
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'addon'
            root.mkdir()
            seed = root / 'boss_chapters.json'
            chapters = {'story_one': {'chapter': 'chapter_1', 'battle_evidence': [{'label': '原始证据'}]}}
            raw = json.dumps(chapters, ensure_ascii=False, indent=2).encode()
            seed.write_bytes(raw)
            manifest = root / 'compatibility.json'
            manifest.write_text(json.dumps({'schema': 1, 'package_files': {
                seed.name: hashlib.sha256(raw).hexdigest()}}), encoding='utf8')
            catalog = root / github_update.CATALOG
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps({str(i): {'entries': []} for i in range(101, 113)}), encoding='utf8')
            packed = Path(folder) / 'release.zip'
            package_release.package(root, packed)
            addon = Path(folder) / 'installed'
            with zipfile.ZipFile(packed) as archive:
                self.assertNotIn(seed.name, archive.namelist())
                compressed = archive.read(seed.name + '.xz')
                self.assertEqual(lzma.decompress(compressed), raw)
                hashes = json.loads(archive.read('compatibility.json'))['package_files']
                self.assertEqual(hashes[seed.name + '.xz'], hashlib.sha256(compressed).hexdigest())
                archive.extractall(addon)
            # A previous copy can remain on an in-place launcher update.
            (addon / seed.name).write_bytes(b'{}')
            data = Path(folder) / 'data'
            data.mkdir()
            (data / seed.name).write_bytes(b'{}')
            mos_data._copy_shared(addon, data, seed.name)
            self.assertEqual((data / seed.name).read_bytes(), raw)
            self.assertEqual(discovery_metadata.load_metadata(root, addon / seed.name)['chapters'], chapters)
            repack = Path(folder) / 'repacked.zip'
            package_release.package(addon, repack)
            with zipfile.ZipFile(repack) as archive:
                self.assertEqual(archive.read(seed.name + '.xz'), compressed)
            self.assertEqual(seed.read_bytes(), raw)

    def test_personal_assets_are_protected(self):
        for name in ('Assets/ImportedSkins/x.cfg', 'Assets/ImportedVoices/x/voice.json',
                     'Assets/CarraBases/x/data', 'Assets/Roland/BRoland.bundle',
                     'Workbench/appearance_names.json'):
            self.assertTrue(github_update._protected(name), name)
        self.assertFalse(github_update._protected('Assets/Roland/appearance.json'))

    def test_release_excludes_imported_identities_without_modifying_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'addon'; root.mkdir()
            info = b'{"version":"1.3.1"}'
            (root / 'addon_info.json').write_bytes(info)
            (root / 'compatibility.json').write_text(json.dumps({'schema': 1, 'package_files': {
                'addon_info.json': hashlib.sha256(info).hexdigest()}}), encoding='utf8')
            catalog = {str(i): {'entries': []} for i in range(101, 113)}
            catalog['101']['entries'] = [
                {'identity_id':'story_WBImp_'+'a'*24, 'weight':3},
                {'identity_id':'story_BRolandBaseAppearance','weight':2}]
            path = root / github_update.CATALOG; path.parent.mkdir(parents=True)
            original = json.dumps(catalog).encode(); path.write_bytes(original)
            output = Path(folder) / 'candidate.zip'
            package_release.package(root, output)
            self.assertEqual(path.read_bytes(), original)
            with zipfile.ZipFile(output) as archive:
                entries = json.loads(archive.read(github_update.CATALOG))['101']['entries']
            self.assertEqual([x['identity_id'] for x in entries], ['story_BRolandBaseAppearance'])
            self.assertEqual(entries[0]['weight'], 1)


if __name__ == '__main__':
    unittest.main()
