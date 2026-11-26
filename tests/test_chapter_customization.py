import base64
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))
import workbench
from github_update import _protected


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B', 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b'\x00\x01\x02\x03')) + chunk(b'IEND', b''))


class ChapterCustomization(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.pools = self.root / 'Assets/runtime/all_sinners_pools.json'
        self.pools.parent.mkdir(parents=True)
        self.pools.write_text(json.dumps({'101': {'entries': [
            {'identity_id': 'one', 'name': 'First'}, {'identity_id': 'two', 'name': 'Second'},
        ]}}), encoding='utf8')
        (self.root / 'boss_chapters.json').write_text(json.dumps({'one': {
            'chapter': 'chapter_1', 'label': '原章', 'memberships': [
                {'chapter': 'chapter_1', 'label': '原章'}, {'chapter': 'chapter_2', 'label': '另一章'},
            ],
        }}), encoding='utf8')
        self.store = self.reopen()

    def reopen(self):
        store = object.__new__(workbench.Store)
        store.root = self.root
        store.lock = workbench.FileLock(self.root / 'workbench-save.lock')
        store.portraits = {}
        store.local_portraits = {}
        return store

    def snapshot(self):
        return self.store.catalog_snapshot()

    def test_exclusive_move_survives_rescan_and_rename_then_restores_automatic_memberships(self):
        _, _, revision = self.snapshot()
        saved = self.store.save_chapter({'label': '自建', 'revision': revision})
        ident = saved['id']
        self.assertEqual(self.snapshot()[1][ident]['title'], '自建')
        self.store.move_chapter({'ids': ['one', 'two'], 'chapter': ident, 'revision': saved['revision']})
        chapters = self.root / 'boss_chapters.json'
        scanned = json.loads(chapters.read_bytes())
        scanned['one']['memberships'][1]['label'] = '扫描更新'
        chapters.write_text(json.dumps(scanned), encoding='utf8')
        self.store = self.reopen()
        catalog, _, revision = self.snapshot()
        for entry in catalog.values():
            self.assertEqual(entry['user_chapter'], ident)
            self.assertEqual(entry['chapter_memberships'], [{'chapter': ident, 'label': '自建'}])
        self.assertNotIn('user_chapter', json.loads(self.pools.read_bytes())['101']['entries'][0])
        renamed = self.store.save_chapter({'id': 'chapter_1', 'label': '新章名', 'revision': revision})
        self.store.move_chapter({'ids': ['one', 'two'], 'chapter': None, 'revision': renamed['revision']})
        catalog, art, _ = self.snapshot()
        self.assertEqual(art['chapter_1']['title'], '新章名')
        self.assertEqual(catalog['one']['chapter_memberships'], [
            {'chapter': 'chapter_1', 'label': '新章名'}, {'chapter': 'chapter_2', 'label': '扫描更新'},
        ])
        self.assertNotIn('user_chapter', catalog['two'])

    def test_cover_restores_bundled_art_and_rejects_stale_writes(self):
        folder = self.root / 'Workbench/chapter_art'
        folder.mkdir(parents=True)
        (folder / 'chapters.json').write_text(json.dumps({'chapter_1': {'image': 'default.png'}}), encoding='utf8')
        (folder / 'default.png').write_bytes(b'default-image')
        _, _, revision = self.snapshot()
        saved = self.store.save_chapter({'id': 'chapter_1', 'label': '新章名', 'revision': revision,
                                         'image': 'data:image/png;base64,' + base64.b64encode(png()).decode()})
        self.assertTrue(self.snapshot()[1]['chapter_1']['custom_image'])
        self.assertEqual(workbench.chapter_cards.image(self.root, 'chapter_1'), png())
        with self.assertRaises(ValueError):
            self.store.move_chapter({'ids': ['one'], 'chapter': 'chapter_1', 'revision': revision})
        self.store.save_chapter({'id': 'chapter_1', 'label': '新章名', 'revision': saved['revision'], 'image': None})
        self.assertEqual(workbench.chapter_cards.image(self.root, 'chapter_1'), b'default-image')

    def test_invalid_batch_leaves_every_appearance_unchanged(self):
        _, _, revision = self.snapshot()
        with self.assertRaises(ValueError):
            self.store.move_chapter({'ids': ['one', 'unknown'], 'chapter': 'chapter_1', 'revision': revision})
        with self.assertRaises(ValueError):
            self.store.move_chapter({'ids': ['one'], 'chapter': '__personality__', 'revision': revision})
        self.assertEqual(self.snapshot()[2], revision)
        self.assertNotIn('user_chapter', self.snapshot()[0]['one'])

    def test_chapter_settings_and_uploaded_art_are_protected_from_plugin_updates(self):
        self.assertTrue(_protected('Workbench/appearance_chapters.json'))
        self.assertTrue(_protected('Workbench/user_chapter_art/example.png'))
        self.assertFalse(_protected('Workbench/data/chapter_cards.json'))
