import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))
import skin_import
import workbench
import imported_portraits
from delete_imported import delete
from file_lock import FileLock


IDENTITY = 'story_WBImp_' + '1' * 24
OTHER = 'story_WBImp_' + '2' * 24
LOOK = IDENTITY.removeprefix('story_')
MEMBER = 'mos_portraits/' + IDENTITY + '.png'


def png(colour):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>II5B', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0' + colour)) + chunk(b'IEND', b''))


class ImportedPortraitTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.archive = self.root / 'mod.zip'
        self.catalog = self.root / skin_import.CATALOG
        self.catalog.parent.mkdir(parents=True)
        self.catalog.write_text('{"101":{"entries":[]}}')
        (self.root / 'compatibility.json').write_text('{"local_skin_import":1}')
        self.image = png(b'\xff\xff\xff')
        self.image_path = self.root / 'Workbench/imported_portraits' / (IDENTITY + '.png')
        self.record = {
            'look': LOOK, 'entry': {'appearance_name': LOOK, 'identity_id': IDENTITY, 'sinner': '101', 'name': 'Model'},
            'bundle': b'bundle', 'timing': b'timing', 'dependency': 'SD_Personality/A.prefab',
            'asset': 'assets/A.prefab', 'layout': 'Standard', 'actions': {'runtime_roles': {}, 'runtime_animator': []},
        }

    def make_zip(self, mapping=None, image=None):
        with ZipFile(self.archive, 'w') as archive:
            archive.writestr('mos-portraits.json', json.dumps({
                'schema': 1, 'portraits': mapping if mapping is not None else {IDENTITY: MEMBER}
            }))
            archive.writestr(MEMBER, self.image if image is None else image)

    def load(self):
        with patch('skin_assets.build_assets', return_value=[self.record]):
            return skin_import._import_normalized(self.archive, self.root, unity=object(),
                                                portraits=imported_portraits.read_archive(self.archive))

    def store(self):
        store = workbench.Store.__new__(workbench.Store)
        store.root = self.root
        store.portraits = {}
        return store

    def test_import_lookup_user_precedence_and_delete(self):
        self.make_zip()
        self.load()
        store = self.store()
        self.assertTrue(store.portrait_lookup()(IDENTITY))
        self.assertEqual(store.portrait(IDENTITY), self.image)
        self.assertIsNone(store.portrait(OTHER))
        custom = workbench.custom_portraits.path_for(self.root, IDENTITY)
        custom.parent.mkdir()
        custom.write_bytes(png(b'\0\0\0'))
        self.assertEqual(store.portrait(IDENTITY), custom.read_bytes())
        delete(self.root, IDENTITY, lock_factory=FileLock)
        self.assertFalse(self.image_path.exists())

    def test_reject_invalid_png_and_cross_identity_declaration(self):
        for mapping, image in ((None, b'invalid'), ({OTHER: 'mos_portraits/' + OTHER + '.png'}, None),
                               ({OTHER: MEMBER}, None), ({IDENTITY: '../portrait.png'}, None)):
            with self.subTest(mapping=mapping, image=image):
                self.make_zip(mapping, image)
                with self.assertRaises(ValueError):
                    self.load()
                self.assertFalse(self.image_path.exists())
                self.assertEqual(json.loads(self.catalog.read_bytes())['101']['entries'], [])

    def test_catalog_write_failure_restores_previous_portrait(self):
        self.make_zip()
        self.load()
        self.make_zip(image=png(b'\0\0\0'))
        writer = skin_import.write_atomic

        def fail_catalog(path, data):
            if path == self.catalog:
                raise OSError('catalog write failed')
            writer(path, data)

        self.record['actions'] = dict(self.record['actions'], attack=[{'test': 1}])
        with patch('skin_import.write_atomic', side_effect=fail_catalog):
            with self.assertRaisesRegex(OSError, 'catalog write failed'):
                self.load()
        self.assertEqual(self.image_path.read_bytes(), self.image)
