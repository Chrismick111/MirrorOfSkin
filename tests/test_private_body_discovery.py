from io import BytesIO
from pathlib import Path, PurePosixPath
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))
import _module_paths
from private_body_discovery import borrowed_body_evidence, discover_private_bodies, scoped_bundles
from private_server_appearance import Declaration


class PrivateBodyDiscoveryTest(unittest.TestCase):
    def test_no_body_options_returns_the_missing_baseline_for_diagnostics(self):
        declaration = Declaration(PurePosixPath('Mods/A'), '1', '!custom_Artist', '', False)
        cab = 'CAB-' + 'a' * 32
        unity = SimpleNamespace(load=lambda data: SimpleNamespace(assets=[SimpleNamespace(name=cab)]))
        with ZipFile(BytesIO(), 'w') as archive:
            archive.writestr('Mods/A/Private/Unknown.bundle', b'UnityFS\0payload')
            with patch('private_body_discovery._published', return_value=[('Assets/Stock.prefab', 1, 2, 'Stock')]), \
                    patch('scan.resource_catalog.resolve_roots', return_value={'resource_root': None}):
                matches, files, proofs, missing = discover_private_bodies(archive, [declaration], [declaration], unity)
        self.assertFalse(matches or files or proofs)
        self.assertEqual(missing, [cab])

    def test_only_live_unconventional_members_in_the_exact_declaring_root_are_candidates(self):
        scope = Declaration(PurePosixPath('Mods/A'), '1', '!custom_Artist', '', False)
        child_scope = Declaration(PurePosixPath('Mods/A/Other'), '2', '!custom_Artist', '', False)
        names = ('Mods/A/Keywords/Live.bundle', 'Mods/A/Backup/Live.bundle', 'Mods/A/Uninstall/Live.bundle',
                 'Mods/A/Other/Contents/Live.bundle', 'Mods/B/Keywords/Live.bundle',
                 'Mods/A/custom_appearance/Normal.bundle', 'Mods/A/Keywords/NotUnity.bundle')
        with ZipFile(BytesIO(), 'w') as archive:
            for name in names:
                archive.writestr(name, b'other data' if 'NotUnity' in name else b'UnityFS\0payload')
            selected = scoped_bundles(archive, [scope], [scope, child_scope])
        self.assertEqual([(str(path), declarations) for _, path, declarations in selected],
                         [('Mods/A/Keywords/Live.bundle', (scope,))])

    def test_repacked_stock_pixels_do_not_prove_an_authored_body(self):
        self.assertEqual(self.compare_art(2, (11, 22, 33, 255)), [])

    def test_replaced_pixels_with_the_original_sprite_id_can_prove_an_authored_body(self):
        [(root, evidence)] = self.compare_art(1, (44, 55, 66, 255))
        self.assertEqual(root[1], 99)
        self.assertEqual(evidence.sprites, {1})
        self.assertEqual(evidence.clips, {42})

    def test_empty_body_curves_cannot_prove_an_authored_body(self):
        self.assertEqual(self.compare_art(0, (44, 55, 66, 255)), [])

    @staticmethod
    def compare_art(sprite_id, rgba):
        from PIL import Image

        def pointer(pid):
            return {'m_FileID': 0, 'm_PathID': pid}

        def file(pid, color, raw):
            sprite = SimpleNamespace(type=SimpleNamespace(name='Sprite'), get_raw_data=lambda: b'sprite',
                                     read=lambda: SimpleNamespace(image=Image.new('RGBA', (2, 2), color)),
                                     read_typetree=lambda: {'m_RD': {'texture': pointer(3)}})
            texture = SimpleNamespace(type=SimpleNamespace(name='Texture2D'), get_raw_data=lambda: raw)
            return SimpleNamespace(name='CAB-test', _m_target_platform=19, objects={pid: sprite, 3: texture})

        published = [('Assets/Original.prefab', 99, 100, 'Original')]
        stock = file(1, (11, 22, 33, 255), b'old pixel encoding')
        edited = file(sprite_id, rgba, b'edited or re-encoded texture')
        with patch('private_body_discovery._actor_clips', side_effect=[
                {42: [pointer(sprite_id)] if sprite_id else []}, {42: [pointer(1)]}]):
            return borrowed_body_evidence(edited, stock, published, published, Path('stock'))
