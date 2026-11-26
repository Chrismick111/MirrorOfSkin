"""Remove inherited body artwork from an otherwise authored stock-layout prefab."""
from pathlib import PurePosixPath
import zlib

from motion_bundle_model import primary_idle_clip_roles
from private_server_art import _body_path, _components, _local, _role, _save
from sprite_facing import body_mapping_indices


_NULL = {'m_FileID': 0, 'm_PathID': 0}

def _sprite_renderers(objects, root):
    """Walk the Animator's own hierarchy, excluding separately referenced assets."""
    transform, = _components(objects, objects[root], 'Transform')
    seen, pending = set(), [(transform, ())]
    while pending:
        node, names = pending.pop()
        if node.path_id in seen:
            continue
        seen.add(node.path_id)
        tree = node.read_typetree()
        game_object = _local(objects, tree['m_GameObject'], 'GameObject')
        path = zlib.crc32('/'.join(names).encode())
        for renderer in _components(objects, game_object, 'SpriteRenderer'):
            yield path, renderer, renderer.read_typetree()
        for ref in tree['m_Children']:
            child = _local(objects, ref, 'Transform')
            child_game_object = _local(objects, child.read_typetree()['m_GameObject'], 'GameObject')
            pending.append((child, (*names, child_game_object.peek_name())))


def _animation_clips(objects, root, state, controller, animator, animator_root):
    """Find Animator clips and animation tracks routed to the same character."""
    directors = list(_components(objects, objects[root], 'PlayableDirector'))
    director_ref = state.get('_playableDirector') or _NULL
    if director_ref['m_PathID']:
        directors.append(_local(objects, director_ref, 'PlayableDirector'))
    bindings, timelines = {}, []
    for director in directors:
        tree = director.read_typetree()
        bindings.update((row['key']['m_PathID'], row['value'])
                        for row in tree['m_SceneBindings'] if not row['key']['m_FileID']
                        and row['key']['m_PathID'])
        timelines.append(tree['m_PlayableAsset'])
    timelines.extend(ref for motion in state['motionList'] for ref in motion['timelineAssets'])
    clips = list(controller['m_AnimationClips'])
    tracks = []
    for ref in timelines:
        if ref['m_PathID']:
            timeline = _local(objects, ref, 'MonoBehaviour').read_typetree()
            tracks.extend((track, _NULL) for track in timeline['m_Tracks'])
    seen_tracks = set()
    while tracks:
        ref, inherited = tracks.pop()
        pid = ref['m_PathID']
        if pid in seen_tracks or not pid:
            continue
        seen_tracks.add(pid)
        track = _local(objects, ref, 'MonoBehaviour').read_typetree()
        target = bindings.get(pid, inherited)
        tracks.extend((child, target) for child in track.get('m_Children', []))
        if ('m_InfiniteClip' not in track or target['m_FileID']
                or target['m_PathID'] not in (0, animator, animator_root)):
            continue
        clips.append(track['m_InfiniteClip'])
        for section in track.get('m_Clips', []):
            payload = section['m_Asset']
            if not payload['m_PathID']:
                continue
            playable = _local(objects, payload, 'MonoBehaviour').read_typetree()
            if 'm_Clip' in playable:
                clips.append(playable['m_Clip'])
    for pid, file_id in dict.fromkeys((ref['m_PathID'], ref['m_FileID']) for ref in clips if ref['m_PathID']):
        obj = _local(objects, {'m_FileID': file_id, 'm_PathID': pid}, 'AnimationClip')
        yield obj, obj.read_typetree()


def _same_stock_sprite(obj, sprite, baseline, stock):
    if not sprite['m_PathID'] or sprite['m_PathID'] != stock['m_PathID']:
        return False
    file_id, stock_id = sprite['m_FileID'], stock['m_FileID']
    if file_id and stock_id:
        source_path = PurePosixPath(obj.assets_file.externals[file_id - 1].path).name
        stock_path = PurePosixPath(baseline.assets_file.externals[stock_id - 1].path).name
        return source_path.casefold() == stock_path.casefold()
    if file_id or stock_id:
        return False
    art = _local(obj.assets_file.objects, sprite, 'Sprite').read().image.convert('RGBA')
    stock_art = _local(baseline.assets_file.objects, stock, 'Sprite').read().image.convert('RGBA')
    return art.size == stock_art.size and art.tobytes() == stock_art.tobytes()


def _sprite_curves(clip, paths):
    """Return the runtime and serialized editor PPtrs for each controlled renderer."""
    binding = clip['m_ClipBindingConstant']
    pointers = [b for b in binding['genericBindings'] if b['isPPtrCurve']]
    result = {}
    for lane in pointers:
        path = lane['path']
        if lane['typeID'] == 212 and path in paths:
            mapping = binding['pptrCurveMapping']
            indices = range(len(mapping)) if len(pointers) == 1 else body_mapping_indices(
                dict(clip, m_PPtrCurves=[]), path, ())
            result.setdefault(path, []).extend(mapping[i] for i in indices)
    for curve in clip.get('m_PPtrCurves', []):
        if curve.get('classID') != 212 or curve.get('attribute') != 'm_Sprite':
            continue
        path = zlib.crc32(curve['path'].encode())
        if path in paths:
            result.setdefault(path, []).extend(key['value'] for key in curve['curve'])
    return result


def _disable_spine(objects, app, state):
    for pointer in state.get('_spineSkins', []):
        skin = _local(objects, pointer, 'MonoBehaviour')
        tree = skin.read_typetree()
        if '_isDisableSpine' not in tree:
            raise ValueError('无法关闭借用外观的骨骼身体')
        tree['_isDisableSpine'] = 1
        _save(skin, tree)
        for field, kinds in (('_spine_renderer', ('MeshRenderer', 'SkinnedMeshRenderer')),
                             ('_spine_Animation', ('MonoBehaviour',))):
            ref = tree.get(field) or _NULL
            if not ref['m_PathID']:
                continue
            component = objects.get(ref['m_PathID'])
            if ref['m_FileID'] or not component or component.type.name not in kinds:
                raise ValueError('无法关闭借用外观的骨骼组件')
            data = component.read_typetree()
            data['m_Enabled'] = False
            _save(component, data)
    if any(motion['isSpineAnim'] for motion in state['motionList']):
        for motion in state['motionList']:
            motion['isSpineAnim'] = 0
        _save(app, state)


def sanitize_borrowed_motion(env, root, proof, *, unity=None):
    """Preserve authored keys and replace inherited body frames with an authored pose."""
    if unity is None:
        import UnityPy as unity
    root = root if isinstance(root, int) else root.path_id
    objects = env.assets[0].objects
    stock = unity.load(str(proof.baseline_path)).assets[0].objects
    app, = (obj for obj in _components(objects, objects[root], 'MonoBehaviour')
            if 'motionList' in obj.read_typetree())
    state = app.read_typetree()
    renderer = _local(objects, state['sprenderer_charactermotion'], 'SpriteRenderer')
    body = renderer.read_typetree()
    animator_object = _local(objects, state['_anim'], 'Animator')
    animator = animator_object.read_typetree()
    animator_root = _local(objects, animator['m_GameObject'], 'GameObject').path_id
    body_path = _body_path(objects, animator_root, body)
    controller = _local(objects, animator['m_Controller'], 'AnimatorController').read_typetree()
    idle_roles = primary_idle_clip_roles(controller)

    def is_authored(ref):
        return not ref['m_FileID'] and ref['m_PathID'] in proof.sprites

    overlays = {}
    for path, obj, tree in _sprite_renderers(objects, animator_root):
        if obj.path_id != renderer.path_id:
            original = stock.get(obj.path_id)
            if original and original.type.name == 'SpriteRenderer':
                overlays[path] = (obj, tree, original, original.read_typetree()['m_Sprite'])

    paths = {body_path, *overlays}
    clips = _animation_clips(objects, root, state, controller, animator_object.path_id, animator_root)
    curves = [(obj, clip, _sprite_curves(clip, paths)) for obj, clip in clips]
    defaults = [ref for obj, _, lanes in curves if obj.path_id in idle_roles
                for ref in lanes.get(body_path, []) if is_authored(ref)]
    initial = body['m_Sprite']
    fallback = next(iter(defaults), None)
    if is_authored(initial):
        fallback = initial
    if fallback is None:
        # A body proven by a referenced motion can still provide a pose if its
        # controller contains no authored default or idle animation.
        fallback = next((ref for obj, _, lanes in curves if obj.path_id in proof.clips
                         for ref in lanes.get(body_path, []) if is_authored(ref)), None)
    if fallback is None:
        raise ValueError('无法确定借用外观的作者备用身体画面')
    fallback = dict(fallback)

    fallbacks, other = set(), 0
    for obj, clip, lanes in curves:
        body_keys = lanes.pop(body_path, [])
        authored_frames = [ref for ref in body_keys if is_authored(ref)]
        needs_fallback = any(not is_authored(ref) and (ref['m_PathID'] or not authored_frames)
                             for ref in body_keys)
        if needs_fallback:
            role = _role(clip['m_Name'])
            if role:
                fallbacks.add(role.upper())
            else:
                other += 1
            replacement = authored_frames[0].copy() if authored_frames else fallback
            for ref in body_keys:
                if not is_authored(ref) and (ref['m_PathID'] or not authored_frames):
                    ref.update(replacement)
        edited_overlay = False
        stock_clip = stock.get(obj.path_id)
        stock_lanes = (_sprite_curves(stock_clip.read_typetree(), set(lanes))
                       if lanes and stock_clip and stock_clip.type.name == 'AnimationClip' else {})
        for path, keys in lanes.items():
            _, _, stock_renderer, stock_sprite = overlays[path]
            original_refs = [(stock_clip, ref) for ref in stock_lanes.get(path, [])]
            original_refs.append((stock_renderer, stock_sprite))
            for ref in keys:
                if not is_authored(ref) and any(
                        _same_stock_sprite(obj, ref, source, old) for source, old in original_refs):
                    ref.update(_NULL)
                    edited_overlay = True
        if needs_fallback or edited_overlay:
            _save(obj, clip)
    if not is_authored(initial):
        body['m_Sprite'] = fallback
        _save(renderer, body)
    for obj, tree, original, original_sprite in overlays.values():
        # Blanking the source image also covers visibility-only animation.
        # Keep the renderer so authored sprite keys can still be played.
        sprite = tree['m_Sprite']
        if not is_authored(sprite) and _same_stock_sprite(obj, sprite, original, original_sprite):
            tree['m_Sprite'] = _NULL.copy()
            _save(obj, tree)
    _disable_spine(objects, app, state)

    warnings = []
    if fallbacks:
        warnings.append('原包的 ' + '、'.join(sorted(fallbacks)) + ' 含原版身体画面，缺失处沿用作者已有画面。')
    if other:
        warnings.append(f'另有 {other} 条演出轨的原版身体画面已用作者已有画面补足。')
    return tuple(warnings)
