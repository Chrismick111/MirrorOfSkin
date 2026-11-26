import io
import json
from pathlib import Path, PurePosixPath
import sys
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))

from authored_frame_motion import read_frame_motions, match_frame_coins
from PIL import Image


def png():
    image = io.BytesIO()
    Image.new('RGBA', (2, 3), (18, 52, 86, 255)).save(image, format='PNG')
    return image.getvalue()


def motion(duration=1.0):
    return {'duration': duration, 'ppu': 120, 'filter': 'bilinear', 'frames': [
        {'t': 0, 'sprite': 'One.PNG', 'offset': [-0.25, 0.5], 'scale': 1.25},
        {'t': 0.43, 'sprite': 'two.png'}
    ]}


def write_motion(archive, base, role, data, images=None):
    directory = f'{base}/motions/{role}'
    archive.writestr(f'{directory}/animation.json', json.dumps(data))
    for name, contents in ({'one.png': png(), 'two.png': png()} if images is None else images).items():
        archive.writestr(f'{directory}/{name}', contents)


class AuthoredFrameMotionTests(unittest.TestCase):
    def test_reads_bound_rgba_images_and_preserves_irregular_times_and_geometry(self):
        base = 'Example/custom_motions/SomeAppearance'
        with ZipFile(io.BytesIO(), 'w') as archive:
            write_motion(archive, base, 'Special17', motion())
            write_motion(archive, base.replace('Example/', 'Other/'), 'Idle', motion())
            write_motion(archive, base + '/Props', 'Idle', motion())
            found = read_frame_motions(archive, PurePosixPath(base.lower()))
            self.assertEqual(set(found), {'special17'})
            imported = found['special17']
            self.assertEqual((imported.duration, imported.ppu, imported.filter_mode), (1.0, 120, 'bilinear'))
            first, second = imported.frames
            self.assertEqual((first.time, first.offset, first.scale), (0, (-0.25, 0.5), 1.25))
            self.assertEqual((second.time, second.offset, second.scale), (0.43, (0.0, 0.0), 1.0))
            self.assertEqual((first.width, first.height), (2, 3))
            self.assertEqual(first.read_image(archive).getpixel((0, 0)), (18, 52, 86, 255))

    def test_rejects_bad_references_timing_and_images(self):
        base = 'Mounted/motion_appearances/AnotherAppearance'
        for name, changes, images in [
            ('external reference', {'sprite': '../one.png'}, None),
            ('missing image', {'sprite': 'missing.png'}, None),
            ('duplicate time', {'t': 0}, None),
            ('negative scale', {'scale': -1}, None),
            ('unreadable image', {}, {'one.png': png(), 'two.png': b'not a PNG'}),
            ('ambiguous image', {}, {'one.png': png(), 'One.PNG': png(), 'two.png': png()}),
        ]:
            with self.subTest(name=name), ZipFile(io.BytesIO(), 'w') as archive:
                data = motion()
                data['frames'][1].update(changes)
                write_motion(archive, base, 'Idle', data, images)
                with self.assertRaises(ValueError):
                    read_frame_motions(archive, PurePosixPath(base))

    def test_matches_coins_only_to_exact_role_and_continuous_segments(self):
        base = 'Mounted/motion_appearances/AnotherAppearance'
        with ZipFile(io.BytesIO(), 'w') as archive:
            write_motion(archive, base, 'OtherRole', motion())
            write_motion(archive, base, 'Special17', motion())
            write_motion(archive, base, 'Special17_1', motion(2))
            found = read_frame_motions(archive, PurePosixPath(base))
            matching = {'coins': [{'totalDuration': 1}, {'totalDuration': 2}]}
            self.assertEqual([clip.role for clip in match_frame_coins(found, 'Special17', matching)],
                             ['Special17', 'Special17_1'])
            self.assertIsNone(match_frame_coins(found, 'S1', matching))
            self.assertIsNone(match_frame_coins(found, 'Special17', {'coins': [{'totalDuration': 1}]}))
            self.assertIsNone(match_frame_coins(found, 'Special17', {'coins': [
                {'totalDuration': 2}, {'totalDuration': 1}]}))
            found['special17_2'] = found.pop('special17_1')
            self.assertIsNone(match_frame_coins(found, 'Special17', matching))
