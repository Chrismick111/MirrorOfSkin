import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))
import workbench
import mos_data


class DataPreservationTest(unittest.TestCase):
    def test_shared_copy_and_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'addon').mkdir()
            (root / 'addon/file').write_bytes(b'new')
            mos_data._copy_shared(root / 'addon', root / 'data', 'file')
            self.assertEqual((root / 'data/file').read_bytes(), b'new')
            with patch.object(mos_data, '_atomic_copy', side_effect=AssertionError('unexpected write')):
                mos_data._copy_shared(root / 'addon', root / 'data', 'file')

    def test_failed_copy_preserves_old_file_and_reports_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'addon').mkdir()
            (root / 'data').mkdir()
            (root / 'addon/file').write_bytes(b'new')
            dest = root / 'data/file'
            dest.write_bytes(b'old')
            with patch.object(mos_data.os, 'replace', side_effect=OSError('denied')):
                with self.assertRaisesRegex(OSError, '同步共享文件失败.*denied'):
                    mos_data._copy_shared(root / 'addon', root / 'data', 'file')
            self.assertEqual(dest.read_bytes(), b'old')
            self.assertEqual(list((root / 'data').iterdir()), [dest])

    def test_delete_images_preserves_user_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            wb = Path(tmp) / 'Workbench'
            for folder in ('portraits', 'local_portraits', 'chapter_art', 'user_portraits', 'user_chapter_art'):
                (wb / folder).mkdir(parents=True)
                (wb / folder / 'image.png').write_bytes(b'image')
            result = workbench._delete_images(tmp)
            self.assertEqual(result['count'], 3)
            for folder in ('user_portraits', 'user_chapter_art'):
                self.assertEqual((wb / folder / 'image.png').read_bytes(), b'image')


if __name__ == '__main__':
    unittest.main()
