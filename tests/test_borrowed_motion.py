from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))
from borrowed_motion import sanitize_borrowed_motion


def pointer(pid=0):
    return {'m_FileID': 0, 'm_PathID': pid}


class Asset:
    def __init__(self, file, pid, kind, **tree):
        self.assets_file = file
        self.path_id = pid
        self.type = SimpleNamespace(name=kind)
        self.tree = tree
        file.objects[pid] = self

    def peek_name(self):
        return self.tree['m_Name']

    def read_typetree(self):
        return deepcopy(self.tree)

    def read(self):
        image = Image.new('RGBA', (1, 1), self.tree['color'])
        return SimpleNamespace(image=image)


class BorrowedMotionTest(unittest.TestCase):
    def test_keeps_authored_overlay_keys_on_a_stock_renderer_that_starts_empty(self):
        file = SimpleNamespace(objects={})
        stock = SimpleNamespace(objects={})
        for container in (file, stock):
            Asset(container, 7, 'SpriteRenderer', m_Sprite=pointer())
            Asset(container, 20, 'Sprite', color='red')
        Asset(stock, 21, 'Sprite', color='green')
        Asset(file, 21, 'Sprite', color='blue')
        Asset(file, 22, 'Sprite', color='white')
        Asset(file, 1, 'GameObject', m_Name='Root',
              m_Component=[{'component': pointer(p)} for p in (2, 3, 4)])
        Asset(file, 2, 'Transform', m_GameObject=pointer(1), m_Father=pointer(),
              m_Children=[pointer(6), pointer(9)])
        Asset(file, 3, 'Animator', m_GameObject=pointer(1), m_Controller=pointer(12))
        Asset(file, 4, 'MonoBehaviour', motionList=[], _anim=pointer(3), sprenderer_charactermotion=pointer(10))
        Asset(file, 5, 'GameObject', m_Name='Overlay',
              m_Component=[{'component': pointer(p)} for p in (6, 7)])
        Asset(file, 6, 'Transform', m_GameObject=pointer(5), m_Father=pointer(2), m_Children=[])
        Asset(file, 8, 'GameObject', m_Name='Body',
              m_Component=[{'component': pointer(p)} for p in (9, 10)])
        Asset(file, 9, 'Transform', m_GameObject=pointer(8), m_Father=pointer(2), m_Children=[])
        Asset(file, 10, 'SpriteRenderer', m_GameObject=pointer(8), m_Sprite=pointer(22))
        Asset(file, 12, 'AnimatorController', m_Controller={}, m_AnimationClips=[pointer(13)])
        def overlay_keys(*pids):
            return [{'classID': 212, 'attribute': 'm_Sprite', 'path': 'Overlay',
                     'curve': [{'time': i, 'value': pointer(pid)} for i, pid in enumerate(pids)]}]
        body = [{'path': zlib.crc32(b'Body'), 'typeID': 212, 'isPPtrCurve': True}]
        clip = Asset(file, 13, 'AnimationClip', m_Name='Host_S3',
                     m_ClipBindingConstant={'genericBindings': body, 'pptrCurveMapping': [pointer(20)]},
                     m_PPtrCurves=overlay_keys(20, 21, 22))
        Asset(stock, 13, 'AnimationClip', m_ClipBindingConstant={'genericBindings': [], 'pptrCurveMapping': []},
              m_PPtrCurves=overlay_keys(20, 21))
        env = SimpleNamespace(assets=[file])
        unity = SimpleNamespace(load=lambda _: SimpleNamespace(assets=[stock]))
        proof = SimpleNamespace(baseline_path='baseline', sprites={22}, clips=set())
        with patch('borrowed_motion._save', side_effect=lambda asset, tree: setattr(asset, 'tree', tree)):
            warnings = sanitize_borrowed_motion(env, 1, proof, unity=unity)
        self.assertTrue(any('S3' in warning for warning in warnings))
        self.assertEqual(clip.tree['m_ClipBindingConstant']['pptrCurveMapping'], [pointer(22)])
        self.assertEqual(clip.tree['m_PPtrCurves'], overlay_keys(0, 21, 22))
