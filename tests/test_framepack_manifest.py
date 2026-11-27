from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import sys
import unittest
from zipfile import ZipFile, ZipInfo

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))

from framepack_manifest import portrait_png, read_framepacks
from mod_archive import normalized


def png(color):
    stream = BytesIO()
    Image.new('RGBA', (256, 256), color).save(stream, 'PNG')
    return stream.getvalue()


def write_pack(archive, *, root='wrapped/', skins=('hero_a', 'hero_b'), visual=None):
    archive.writestr(root + 'pack.json', json.dumps(dict(schema_version=2,
                     pack_id='authors_pack', skins=list(skins), preview='preview.png')))
    archive.writestr(root + 'preview.png', png('white'))
    for index, skin_id in enumerate(skins, 1):
        if '/' in skin_id:
            continue
        folder = root + 'skins/' + skin_id + '/'
        archive.writestr(folder + 'manifest.json', json.dumps(dict(
            schema_version=2, meta=dict(skin_id=skin_id, display_name=f'作者外观{index}',
                                        preview='portrait.png'),
            target=dict(kind='personality', personality_id=10000 + index),
            visual=visual or dict(sd_frames_dir='custom/frames', illust_dir='custom/art'),
            voice=dict(dir='voice'), locale=dict(exclusive_dir='locale/exclusive'),
            combo=dict(mirror_into_hosts=[12001]))))
        archive.writestr(folder + 'portrait.png', png(('blue', 'green')[index - 1]))
        archive.writestr(folder + 'custom/frames/Default.png', png('red'))
        archive.writestr(folder + 'voice/line.wav', b'RIFF')


class FramePackManifestTests(unittest.TestCase):
    def test_stock_model_fallback_needs_one_matching_personality(self):
        from types import SimpleNamespace
        from skin_assets import _framepack_base

        skin = SimpleNamespace(manifest={}, personality='11116', label='Author skin')
        roster = [dict(identity_id='11116', appearance_name='BaseA'),
                  dict(identity_id='11017', appearance_name='BaseB')]
        self.assertEqual(_framepack_base(skin, roster), 'BaseA')
        with self.assertRaises(ValueError):
            _framepack_base(skin, roster + [dict(identity_id='11116', appearance_name='BaseC')])
        skin.manifest['private_server'] = dict(vanilla_appearance_id='DeclaredBase')
        self.assertEqual(_framepack_base(skin, roster), 'DeclaredBase')

    def test_each_declared_skin_has_its_own_resources_and_appearance(self):
        with ZipFile(BytesIO(), 'w') as archive:
            write_pack(archive)
            a, b = read_framepacks(archive)
            self.assertEqual((a.label, b.label), ('作者外观1', '作者外观2'))
            self.assertEqual((a.personality, b.personality), ('10001', '10002'))
            self.assertEqual(a.frames_dir, a.package_root / 'custom/frames')
            self.assertEqual(a.voice_dir, a.package_root / 'voice')
            self.assertEqual(a.manifest['combo']['mirror_into_hosts'], [12001])
            self.assertTrue(all(name.startswith(str(a.package_root) + '/') for name in a.members))
            for skin, color in ((a, (0, 0, 255, 255)), (b, (0, 128, 0, 255))):
                with Image.open(BytesIO(portrait_png(archive, skin))) as image:
                    self.assertEqual(image.getpixel((0, 0)), color)

    def test_unrelated_pack_json_does_not_claim_import(self):
        with ZipFile(BytesIO(), 'w') as archive:
            archive.writestr('pack.json', '{"name": "another type", "schema_version": 2}')
            self.assertEqual(read_framepacks(archive), [])

    def test_rejects_escape_in_skin_id_and_in_declared_directory(self):
        for options in (dict(skins=('../outside',)), dict(visual=dict(sd_frames_dir='../outside')),
                        dict(visual=dict(sd_frames_dir='D:\\outside'))):
            with self.subTest(options=options), ZipFile(BytesIO(), 'w') as archive:
                write_pack(archive, **options)
                with self.assertRaises(ValueError):
                    read_framepacks(archive)

    def test_rejects_case_insensitive_member_collisions(self):
        with ZipFile(BytesIO(), 'w') as archive:
            write_pack(archive)
            archive.writestr('WRAPPED/SKINS/HERO_A/PORTRAIT.PNG', png('red'))
            with self.assertRaises(ValueError):
                read_framepacks(archive)

    def test_rejects_symlink_member(self):
        with ZipFile(BytesIO(), 'w') as archive:
            write_pack(archive)
            member = ZipInfo('wrapped/skins/hero_a/custom/frames/other.png')
            member.external_attr = 0o120777 << 16
            archive.writestr(member, b'../../outside.png')
            with self.assertRaises(ValueError):
                read_framepacks(archive)

    def test_rejects_relative_escape_and_windows_reserved_resource_name(self):
        for name in ('wrapped/skins/hero_a/../outside.png', 'wrapped/skins/hero_a/CON.png'):
            with self.subTest(name=name), ZipFile(BytesIO(), 'w') as archive:
                write_pack(archive)
                archive.writestr(name, b'bad')
                with self.assertRaises(ValueError):
                    read_framepacks(archive)

    def test_recognizes_a_wrapper_directory_named_skins(self):
        with ZipFile(BytesIO(), 'w') as archive:
            write_pack(archive, root='skins/author_pack/', skins=('hero_a',))
            skin, = read_framepacks(archive)
            self.assertIn(str(skin.package_root / 'custom/frames/default.png'), skin.members)

    def test_selected_folder_preserves_custom_frame_and_voice_paths(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            stream = BytesIO()
            with ZipFile(stream, 'w') as archive:
                write_pack(archive, root='', skins=('hero_a',))
            with ZipFile(stream) as archive:
                archive.extractall(directory)
            with normalized(Path(directory)) as path, ZipFile(path) as archive:
                skin, = read_framepacks(archive)
                expected = (PurePosixPath('skins/hero_a/custom/frames/Default.png'),
                            PurePosixPath('skins/hero_a/voice/line.wav'))
                for member in expected:
                    self.assertIn(str(member).casefold(), skin.members)


if __name__ == '__main__':
    unittest.main()
