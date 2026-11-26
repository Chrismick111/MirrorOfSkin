from io import BytesIO
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))
import private_server_art as art


class PoseMatching(unittest.TestCase):
    def pixels(self, entries, other=(), scope=True):
        from PIL import Image
        original = Image.new('RGBA', (8, 8), 'black')
        stream = BytesIO()
        with ZipFile(stream, 'w') as archive:
            for name, size, colour in entries:
                data = BytesIO()
                Image.new('RGBA', size, colour).save(data, format='PNG')
                archive.writestr(name, data.getvalue())
        with ZipFile(stream) as archive:
            result = art._matching_pixels(archive, archive.infolist(), original, lambda:set(other), lambda:scope)
        return result.getpixel((4, 4))

    def test_unique_scoped_png_overrides_an_entirely_different_atlas_frame(self):
        self.assertEqual(self.pixels([('idle.png',(8,8),'white')]), (255,255,255,255))

    def test_different_art_with_ambiguous_form_or_personality_is_rejected(self):
        for sizes,scope in [([(8,8)],True),([],False)]:
            with self.subTest(sizes=sizes,scope=scope), self.assertRaisesRegex(ValueError,'唯一匹配'):
                self.pixels([('idle.png',(8,8),'white')], sizes, scope)
        with self.assertRaisesRegex(ValueError,'唯一匹配'):
            self.pixels([('a/idle.png',(8,8),'white'),('b/idle.png',(8,8),'red')])

    def test_pixel_evidence_selects_a_matching_export_among_duplicate_names(self):
        value=self.pixels([('a/idle.png',(8,8),'white'),('b/idle.png',(8,8),(2,3,4,255))],[(8,8)],False)
        self.assertEqual(value,(2,3,4,255))

    def test_alternate_form_dimensions_do_not_replace_the_selected_pose(self):
        self.assertEqual(self.pixels([('idle.png',(16,8),'white')],[(16,8)]), (0,0,0,255))
        with self.assertRaisesRegex(ValueError,'唯一匹配'):
            self.pixels([('idle.png',(16,8),'white')])

    def test_skill_order_uses_numeric_coin_suffix_and_skips_repeated_frames(self):
        sequences = {'s1':[1,1], 's1_10':[4], 's1_2':[2,3], 's2':[7]}
        self.assertEqual(art._frames('s1',sequences),[1,2,3,4])


@unittest.skipUnless(os.environ.get('MOS_MYO_RAR'), 'optional author archive')
class AuthorArchive(unittest.TestCase):
    def test_packed_model_uses_author_idle_and_actual_loose_evade_pixels(self):
        import UnityPy
        from PIL import Image
        from skin_assets import _convert, _roots, _Streams
        UnityPy.config.FALLBACK_UNITY_VERSION='6000.3.0f1'
        rar = os.environ['MOS_MYO_RAR']
        names = subprocess.check_output(['tar','-tf',rar]).decode('ascii',errors='replace').splitlines()
        stream = BytesIO()
        with ZipFile(stream,'w') as z:
            for name in names:
                lower=name.casefold()
                if lower.endswith('/motion.bundle') or lower.endswith('/myo.bundle') or (
                        '/custom_sprites/sprite/' in lower and lower.endswith('.png')):
                    z.writestr(name,subprocess.check_output(['tar','-xOf',rar,name]))
        with ZipFile(stream) as z:
            prefab = next(n for n in z.namelist() if n.endswith('/myo.bundle'))
            motion = next(n for n in z.namelist() if n.endswith('/motion.bundle'))
            env = UnityPy.load(z.read(prefab))
            address,pid,index = next(row for row in _roots(env) if '10703_' in row[0])
            source = UnityPy.load(z.read(motion))
            idle_id = art._sequences(source)['idle'][0]
            author_idle = source.assets[0].objects[idle_id].read().image.convert('RGBA')
            archive_root = PurePosixPath(prefab).parents[1]
            revision = art.adapt_private_appearance(z,archive_root,PurePosixPath(motion).parent.name,env,pid,UnityPy)
            raw,_ = _convert(env,revision,'TestBody',address,pid,index,_Streams(UnityPy))
            expected = Image.open(BytesIO(z.read(str(archive_root/'custom_sprites/Sprite/miss.png')))).convert('RGBA')
        result = UnityPy.load(raw)
        objects = result.assets[0].objects
        app, = [o for o in art._components(objects,objects[pid],'MonoBehaviour') if 'motionList' in o.read_typetree()]
        renderer = art._local(objects,app.read_typetree()['sprenderer_charactermotion'],'SpriteRenderer').read_typetree()
        idle = art._local(objects,renderer['m_Sprite'],'Sprite').read().image.convert('RGBA')
        self.assertEqual((idle.size,idle.tobytes()),(author_idle.size,author_idle.tobytes()))
        roles = set()
        for _,clip in art._body_clips(objects,app,art._body_path(objects,pid,renderer)):
            role = art._role(clip['m_Name'])
            roles.add(role)
            for p in clip['m_ClipBindingConstant']['pptrCurveMapping']:
                sprite = art._local(objects,p,'Sprite').read()
                self.assertFalse(sprite.m_SpriteAtlas)
                if role == 'evade':
                    self.assertEqual(sprite.image.convert('RGBA').tobytes(),expected.tobytes())
        self.assertTrue({'default','move','evade','guard','damaged','s1','s2','s3'} <= roles)
        self.assertFalse(any(m['isSpineAnim'] for m in app.read_typetree()['motionList']))


if __name__ == '__main__':
    unittest.main()

