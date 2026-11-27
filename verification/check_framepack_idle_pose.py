"""Measure the visible Spine attachments in the supplied Mod Spec v2 battle models."""
import argparse
import json
import math
from pathlib import Path
import sys


def value(keys, field, default, time, component):
    previous = None
    for current in keys:
        t1 = current.get('time', 0)
        if t1 > time:
            if previous is None:
                return default
            t0 = previous.get('time', 0)
            a, b = previous.get(field, default), current.get(field, default)
            curve = previous.get('curve')
            if curve == 'stepped':
                return a
            if not isinstance(curve, list):
                return a + (b - a) * (time - t0) / (t1 - t0)
            x1, y1, x2, y2 = curve[4*component:4*component+4]
            lo, hi = 0., 1.
            for _ in range(24):
                u = (lo + hi) / 2
                v = 1 - u
                if v**3*t0 + 3*v*v*u*x1 + 3*v*u*u*x2 + u**3*t1 < time:
                    lo = u
                else:
                    hi = u
            return v**3*a + 3*v*v*u*y1 + 3*v*u*u*y2 + u**3*b
        previous = current
    return previous.get(field, default) if previous is not None else default


def bone_matrices(doc, anim, time):
    world = {}
    for bone in doc['bones']:
        assert bone.get('transform', 'normal') == 'normal'
        curves = anim.get('bones', {}).get(bone['name'], {})
        assert set(curves) <= {'translate', 'scale', 'rotate'}
        x, y = [bone.get(k, 0) + value(curves.get('translate', []), k, 0, time, i)
                for i, k in enumerate('xy')]
        sx, sy = [bone.get('scale' + k.upper(), 1) * value(curves.get('scale', []), k, 1, time, i)
                  for i, k in enumerate('xy')]
        rot = bone.get('rotation', 0) + value(curves.get('rotate', []), 'value', 0, time, 0)
        ax = math.radians(rot + bone.get('shearX', 0))
        ay = math.radians(rot + 90 + bone.get('shearY', 0))
        xx, xy = math.cos(ax)*sx, math.cos(ay)*sy
        yx, yy = math.sin(ax)*sx, math.sin(ay)*sy
        parent = world.get(bone.get('parent'), ((1, 0, 0), (0, 1, 0)))
        world[bone['name']] = tuple((a*xx+b*yx, a*xy+b*yy, a*x+b*y+c) for a,b,c in parent)
    return world


def transform_y(matrix, x, y):
    a, b, c = matrix[1]
    return a*x + b*y + c


def visible_y(doc, skin, anim, time):
    assert set(anim) <= {'bones', 'slots'}
    bones = bone_matrices(doc, anim, time)
    matrices = list(bones.values())
    attachments = {s['name']: s.get('attachments', {}) for s in doc['skins']}
    ys = []
    for slot in doc['slots']:
        selected = slot.get('attachment')
        track = anim.get('slots', {}).get(slot['name'], {})
        assert set(track) <= {'attachment'}
        for key in track.get('attachment', []):
            if key.get('time', 0) <= time:
                selected = key.get('name')
        att = attachments[skin].get(slot['name'], {}).get(selected)
        if att is None:
            att = attachments.get('default', {}).get(slot['name'], {}).get(selected)
        if not att:
            continue
        mat = bones[slot['bone']]
        if att.get('type', 'region') == 'region':
            r = math.radians(att.get('rotation', 0))
            for i, j in ((-1,-1), (-1,1), (1,-1), (1,1)):
                x = i * att['width'] * att.get('scaleX', 1) / 2
                y = j * att['height'] * att.get('scaleY', 1) / 2
                ys.append(transform_y(mat, x*math.cos(r)-y*math.sin(r)+att.get('x',0),
                                      x*math.sin(r)+y*math.cos(r)+att.get('y',0)))
            continue
        assert att['type'] == 'mesh'
        pts = iter(att['vertices'])
        weighted = len(att['uvs']) != len(att['vertices'])
        for _ in range(len(att['uvs'])//2):
            if weighted:
                height = 0
                for _ in range(int(next(pts))):
                    joint = matrices[int(next(pts))]
                    height += transform_y(joint, next(pts), next(pts)) * next(pts)
                ys.append(height)
            else:
                ys.append(transform_y(mat, next(pts), next(pts)))
        assert next(pts, None) is None
    return (min(ys), max(ys)) if ys else None


def report_bundle(model):
    import UnityPy
    from private_server_art import _components, _local
    from roland_merge import Prefab
    from skin_assets import _roots

    env = UnityPy.load(model.read_bytes())
    [(address, root, _)] = _roots(env)
    prefab = Prefab.from_asset(env, root)
    obs = prefab.objects

    def height_scale(go):
        scale = 1
        while go:
            [tr] = _components(obs, go, 'Transform')
            tree = tr.read_typetree()
            q = tree['m_LocalRotation']
            assert abs(q['x']) + abs(q['z']) < 1e-5, 'rig is tilted; needs 3D projection'
            scale *= abs(tree['m_LocalScale']['y'])
            parent = tree['m_Father']['m_PathID']
            go = obs[obs[parent].read_typetree()['m_GameObject']['m_PathID']] if parent else None
        return scale

    sr = _local(obs,prefab.app['sprenderer_charactermotion'],'SpriteRenderer').read_typetree()
    sprite = _local(obs, sr['m_Sprite'], 'Sprite').read_typetree()
    factor = height_scale(_local(obs, sr['m_GameObject'], 'GameObject'))
    still = sprite['m_Rect']['height'] / sprite['m_PixelsToUnits'] * factor
    for ref in prefab.app['_spineSkins']:
        ctrl = _local(obs, ref, 'MonoBehaviour').read_typetree()
        go = _local(obs, ctrl['m_GameObject'], 'GameObject')
        for component in _components(obs, go, 'MonoBehaviour'):
            rig = component.read_typetree()
            if not rig.get('skeletonDataAsset'):
                continue
            data = _local(obs,rig['skeletonDataAsset'],'MonoBehaviour').read_typetree()
            doc = json.loads(_local(obs,data['skeletonJSON'],'TextAsset').read_typetree()['m_Script'])
            mesh_scale = height_scale(go) * data['scale']
            for name, anim in doc['animations'].items():
                for skin in doc['skins']:
                    poses = [visible_y(doc, skin['name'], anim, t) for t in (0., .25, .5, 1.)]
                    heights = [round((hi-lo)*mesh_scale,3) for pose in poses if pose for lo,hi in [pose]]
                    if heights:
                        print(Path(address).stem, skin['name'], name, 'idle mesh heights', heights,
                              'default sprite height', round(still,3), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models', nargs='+', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / 'MirrorOfSkin' / 'Workbench'))
    import _module_paths
    import UnityPy
    UnityPy.config.FALLBACK_UNITY_VERSION = '6000.3.0f1'
    for model in args.models:
        report_bundle(model)
