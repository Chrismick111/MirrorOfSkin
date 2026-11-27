from contextlib import ExitStack
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))
import _module_paths
from frame_pack_model import FrameArt


class FramePackPixels(unittest.TestCase):
    def test_frame_names_are_scoped_and_honor_grouped_frames_and_forms(self):
        path = PurePosixPath('skins/test/frames')
        names = ('skill2_4,5', 'skill2_6~8', 'idle', 'idle_r', 'idle_p2', 'idle_p2_r')
        members = {str(path / (name + '.png')): None for name in names}
        members['skins/other/frames/skill2_1.png'] = None
        art = FrameArt(None, SimpleNamespace(frames_dir=path, members=members, visual={}))
        self.assertEqual(art.resolve('skill2_5', 'Actor_S2'), 'skill2_4,5')
        self.assertEqual(art.resolve('skill2_7', 'Actor_S2'), 'skill2_6~8')
        self.assertEqual(art.resolve('Default', 'Actor_Phase2_Default_Right'), 'idle_p2_r')
        self.assertEqual(art.resolve('Default', 'Actor_Default_Right'), 'idle_r')
        self.assertIsNone(art.resolve('skill2_1', 'Actor_S2'))

    def test_declared_controls_retain_visible_alpha_and_reject_nonfinite_offsets(self):
        from PIL import Image

        path = PurePosixPath('frames')
        raw = BytesIO()
        image = Image.new('RGBA', (8, 8))
        image.paste((100, 120, 140, 255), (2, 2, 6, 6))
        image.save(raw, format='PNG')
        with ZipFile(BytesIO(), 'w') as archive:
            archive.writestr('frames/Default.png', raw.getvalue())
            visual = {'frame_params': {'Default': {'offset_x': -50, 'scale': 1.25, 'brightness': 2}}}
            art = FrameArt(archive, SimpleNamespace(frames_dir=path, members={'frames/default.png':
                           archive.getinfo('frames/Default.png')}, visual=visual))
            pixels, bounds = art.pixels('default', (6, 6), (-3, -3))
            self.assertEqual(pixels.size, (4, 4))
            self.assertEqual(pixels.getpixel((pixels.width // 2, pixels.height // 2)), (200, 240, 255, 255))
            self.assertEqual(bounds, (-52, -2, -48, 2))
            art.params['default']['offset_x'] = float('nan')
            with self.assertRaises(ValueError):
                art.pixels('default', (6, 6), (-3, -3))

    def test_transparent_padding_preserves_the_authors_scale_and_anchor(self):
        from PIL import Image

        canvas = Image.new('RGBA', (20, 20))
        canvas.paste((100, 120, 140, 255), (8, 12, 12, 16))
        raw = BytesIO()
        canvas.save(raw, format='PNG')
        with ZipFile(BytesIO(), 'w') as archive:
            archive.writestr('frames/idle.png', raw.getvalue())
            art = FrameArt(archive, SimpleNamespace(
                frames_dir=PurePosixPath('frames'), members={'frames/idle.png': archive.getinfo('frames/idle.png')},
                visual={'frame_params': {'idle': {'scale': 2, 'offset_x': 1, 'offset_y': 2}}}))
            pixels, bounds = art.pixels('idle', (10, 10), (-5, -1))
            self.assertEqual(pixels.size, (4, 4))
            self.assertEqual(bounds, (-1, -4, 3, 0))


@unittest.skipUnless(os.environ.get('MOS_FRAMEPACK_ARCHIVES'), 'optional author frame packs and game cache')
class AuthorFramePacks(unittest.TestCase):
    def test_models_round_trip_body_curves_and_battle_only_spine(self):
        import UnityPy
        from framepack_manifest import read_framepacks
        from frame_pack_model import build_frame_pack_record
        from private_server_art import _components, _local
        from skin_assets import _roots
        from stock_coin_import import _locate

        UnityPy.config.FALLBACK_UNITY_VERSION = '6000.3.0f1'
        with ExitStack() as stack:
            paths = os.environ['MOS_FRAMEPACK_ARCHIVES'].split(os.pathsep)
            archives = [stack.enter_context(ZipFile(path)) for path in paths]
            pairs = [(archive, skin) for archive in archives for skin in read_framepacks(archive)]
            self.assertTrue(pairs)
            base = {skin: skin.manifest['private_server']['vanilla_appearance_id'] for _, skin in pairs}
            files = _locate(set(base.values()), UnityPy)
            work = Path(stack.enter_context(TemporaryDirectory()))
            for archive, skin in pairs:
                with self.subTest(skin=skin.skin_id):
                    partners = [(z, other, files[base[other]]) for z, other in pairs if other is not skin]
                    record = build_frame_pack_record(archive, skin, files[base[skin]], work, UnityPy,
                                                     'test_' + skin.personality, skin.label, partners=partners)
                    self.assertTrue(record['actions']['attack'])
                    self.assertTrue(record['actions']['clash'])
                    self.assertTrue({2, 3, 4} <= set(record['actions']['runtime_animator']))
                    env = UnityPy.load(record['bundle'].read_bytes())
                    _, pid, _ = _roots(env)[0]
                    objects = env.assets[0].objects
                    app, = [obj.read_typetree() for obj in _components(objects, objects[pid], 'MonoBehaviour')
                            if 'motionList' in obj.read_typetree()]
                    renderer = _local(objects, app['sprenderer_charactermotion'], 'SpriteRenderer').read_typetree()
                    sprite = _local(objects, renderer['m_Sprite'], 'Sprite')
                    self.assertIn(sprite.peek_name(), ['mos_frame_' + skin.personality + '_' + pose
                                                       for pose in ('default', 'idle')])
                    self.assertIsNotNone(sprite.read().image.getbbox())
                    for ref in app['_spineSkins']:
                        body = _local(objects, ref, 'MonoBehaviour').read_typetree()
                        go = _local(objects, body['m_GameObject'], 'GameObject')
                        for obj in _components(objects, go, 'MonoBehaviour'):
                            rig = obj.read_typetree()
                            if 'skeletonDataAsset' not in rig:
                                continue
                            skeleton = _local(objects, rig['skeletonDataAsset'], 'MonoBehaviour').read_typetree()
                            text = _local(objects, skeleton['skeletonJSON'], 'TextAsset')
                            key = str(skin.spine_dir / (text.peek_name() + '.json')).casefold()
                            if key in skin.members:
                                self.assertEqual(json.loads(text.read_typetree()['m_Script']),
                                                 json.loads(archive.read(skin.members[key])))


if __name__ == '__main__':
    unittest.main()
