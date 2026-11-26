"""Synthetic coverage for serialized rigs and body-only pointer selection."""
from types import SimpleNamespace
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))
try:
    from sprite_facing import body_mapping_indices, body_rig
except ModuleNotFoundError as error:
    if error.name not in ('UnityPy', 'PIL'):
        raise
    raise unittest.SkipTest('Sprite facing tests require Workbench UnityPy/Pillow dependencies')


def ref(pid):
    return {'m_FileID': 0, 'm_PathID': pid}


class SpriteFacingTest(unittest.TestCase):
    def test_full_animator_relative_path_and_parity(self):
        for scale, flip, expected in ((1, False, 1), (-1, False, -1), (-1, True, 1)):
            trees = {
                11: {'m_GameObject': ref(21), 'm_FlipX': flip},
                21: {'m_Name': 'Body', 'm_Component': [{'component': ref(31)}]},
                22: {'m_Name': 'Pivot', 'm_Component': [{'component': ref(32)}]},
                23: {'m_Name': 'Root', 'm_Component': [{'component': ref(33)}]},
                31: {'m_Father': ref(32), 'm_GameObject': ref(21), 'm_LocalScale': {'x':scale},
                     'm_LocalRotation': dict(x=0,y=0,z=0,w=1)},
                32: {'m_Father': ref(34), 'm_GameObject': ref(22), 'm_LocalScale': {'x':0.5},
                     'm_LocalRotation': dict(x=0,y=0,z=0,w=1)},
                34: {'m_GameObject': ref(23)},
            }
            pf = SimpleNamespace(app=dict(_anim=ref(33), sprenderer_charactermotion=ref(11)),
                                 tree=trees.__getitem__,
                                 objects={i:SimpleNamespace(type=SimpleNamespace(name='Transform')) for i in (31,32)})
            crc, parity, paths = body_rig(pf)
            self.assertEqual((crc, parity), (zlib.crc32(b'Pivot/Body'), expected))
            self.assertEqual(paths, (zlib.crc32(b'Pivot'), crc))

    def test_mixed_clip_only_selects_body_lane(self):
        bits = lambda v: struct.unpack('<I', struct.pack('<f', v))[0]
        ptr = lambda path: dict(typeID=212, path=path, isPPtrCurve=True)
        bindings = [dict(typeID=4,path=8,attribute=1,isPPtrCurve=False),ptr(12),ptr(20)]
        keys = [0,2,3,0,0,0,bits(2),4,0,0,0,bits(1)]
        stream = dict(curveCount=3, discreteCurveCount=2, data=keys)
        clip = {'m_Name':'Synthetic', 'm_PPtrCurves':[], 'm_ClipBindingConstant':
                dict(genericBindings=bindings,pptrCurveMapping=[ref(0),ref(3),ref(4)]),
                'm_MuscleClip':{'m_Clip':{'data':{'m_StreamedClip':stream}}}}
        self.assertEqual(body_mapping_indices(clip,12,(8,12)),[2])
        self.assertEqual(body_mapping_indices(clip,90,(8,90)),())
        stream['data'][-1] = bits(2)
        with self.assertRaisesRegex(ValueError,'共用'):
            body_mapping_indices(clip,12,(8,12))


if __name__ == '__main__':
    unittest.main()
