"""Read authored Timeline body tracks for conversion into native appearances."""
from dataclasses import dataclass
from collections import defaultdict
from pathlib import PurePosixPath
from motion_bundle_timelines import timeline_slot


@dataclass
class BodyTrack:
    timeline: object
    track: object
    clip: object
    sprite_ids: list


def find_body_tracks(env, *, empty_tracks=None):
    if len(env.assets) != 1:
        raise ValueError('作者动作包必须包含一个资源文件')
    objects = env.assets[0].objects
    result = {}
    for address, timeline in env.container.items():
        path = PurePosixPath(address.replace('\\', '/').casefold())
        if path.suffix != '.playable':
            continue
        if path.stem not in ('idle', 'default', 'move', 'dead') and timeline_slot(path.stem) is None:
            continue
        tree = timeline.read_typetree()
        if 'm_Tracks' not in tree:
            continue
        found = []
        has_empty_curve = False
        for pointer in tree['m_Tracks']:
            if pointer.get('m_FileID') or pointer.get('m_PathID') not in objects:
                raise ValueError('作者动作轨道引用无法解析')
            track = objects[pointer['m_PathID']]
            track_tree = track.read_typetree()
            pointer = track_tree.get('m_InfiniteClip') or {}
            if track_tree.get('m_Muted') or not pointer.get('m_PathID'):
                continue
            if pointer.get('m_FileID') or pointer['m_PathID'] not in objects:
                raise ValueError('作者动画引用无法解析')
            clip = objects[pointer['m_PathID']]
            if clip.type.name != 'AnimationClip':
                continue
            binding = clip.read_typetree()['m_ClipBindingConstant']
            curves = [row for row in binding['genericBindings'] if row['isPPtrCurve']]
            if len(curves) != 1 or curves[0]['typeID'] != 212 or curves[0]['path'] != 0:
                continue
            ids = []
            for item in binding['pptrCurveMapping']:
                if not item['m_PathID']:
                    if item['m_FileID']:
                        raise ValueError('作者动画的身体精灵引用无法解析')
                    continue
                obj = objects.get(item['m_PathID'])
                if item['m_FileID'] or obj is None or obj.type.name != 'Sprite':
                    raise ValueError('作者动画的身体精灵引用无法解析')
                ids.append(obj.path_id)
            if ids:
                found.append(BodyTrack(timeline, track, clip, ids))
            elif binding['pptrCurveMapping']:
                has_empty_curve = True
        if not found and has_empty_curve:
            if empty_tracks is not None:
                empty_tracks.add(path.stem)
            continue
        if len(found) != 1 or path.stem in result:
            raise ValueError('无法唯一确认作者时间轴的身体轨道：' + address)
        result[path.stem] = found[0]
    return result


def select_stock_override_tracks(tracks, motion_data):
    """Do not play unconfigured stock-name templates as the author's attacks."""
    attack_roles = {role for role in motion_data if (slot := timeline_slot(role)) and slot[1].startswith('s')}
    playable = {}
    for name, track in tracks.items():
        slot = timeline_slot(name)
        if slot:
            _, role, index = slot
            if role.startswith('s') and role not in attack_roles:
                continue
            if index and role not in motion_data and any(
                    (role if prior == 0 else f'{role}_{prior}') not in tracks for prior in range(index)):
                continue
        playable[name] = track
    for role in attack_roles:
        if role not in playable:
            raise ValueError('作者动作声明没有可读取的身体轨道：' + role)
    return playable


def animator_body_role(role, controller_roles):
    if role == 'default' and 'idle' not in controller_roles:
        return 'idle'
    return role


def primary_idle_clip_roles(controller):
    """Identify clips owned by a single Default or Idle state on the primary layer."""
    data = controller['m_Controller']
    layers = data.get('m_LayerArray', [])
    if not layers:
        return {}
    primary = layers[0]['data']['m_StateMachineIndex']
    names = dict(controller['m_TOS'])
    refs = controller['m_AnimationClips']
    owners = defaultdict(set)
    roles = {}
    for machine_index, machine in enumerate(data['m_StateMachineArray']):
        machine = machine['data']
        for state_index, state in enumerate(machine.get('m_StateConstantArray', [])):
            state = state['data']
            role = names.get(state.get('m_NameID'), '').casefold()
            for blend in state.get('m_BlendTreeConstantArray', []):
                for node in blend['data'].get('m_NodeArray', []):
                    index = node['data'].get('m_ClipID', -1)
                    if not 0 <= index < len(refs):
                        continue
                    pointer = refs[index]
                    if pointer['m_FileID'] or not pointer['m_PathID']:
                        continue
                    pid = pointer['m_PathID']
                    owners[pid].add((machine_index, state_index))
                    if machine_index == primary and (role == 'idle' or
                            role == 'default' and state_index == machine.get('m_DefaultState')):
                        roles[pid] = role
    return {pid: role for pid, role in roles.items() if len(owners[pid]) == 1}


def _empty_animator_clip(tree):
    bindings = tree['m_ClipBindingConstant']
    muscle = tree['m_MuscleClip']['m_Clip']['data']
    streamed = muscle['m_StreamedClip']
    return (not bindings['genericBindings'] and not bindings['pptrCurveMapping']
            and not streamed['curveCount'] and not streamed.get('discreteCurveCount')
            and not muscle['m_DenseClip']['m_CurveCount'] and not muscle['m_ConstantClip']['data']
            and not any(tree.get(key) for key in ('m_RotationCurves', 'm_CompressedRotationCurves',
                                                  'm_EulerCurves', 'm_PositionCurves', 'm_ScaleCurves',
                                                  'm_FloatCurves', 'm_PPtrCurves', 'm_Events')))


def animator_replacement(role, controller_roles, tracks):
    selected = animator_body_role(role, controller_roles)
    if selected not in tracks:
        selected = 'idle'
    return selected, selected == 'idle' and role in ('default', 'idle')


def set_idle_loop(tree):
    tree['m_MuscleClip']['m_LoopTime'] = True


def copy_body_clips(source, target_env, target_root, *, tracks=None, progress=None):
    """Copy authored clips and sprites into a native prefab, retaining curve keyframes.

    Returns role-to-clip IDs. The caller owns timeline construction and final save.
    """
    from copy import copy, deepcopy
    from private_server_art import (_refs, _body_path, _components, _local,
                                    _pose_sprite, _pose_texture, _role, _save)
    if tracks is None:
        tracks = find_body_tracks(source)
    if 'idle' not in tracks or 's1' not in tracks:
        raise ValueError('作者动作缺少待机或第一技能')
    if len(target_env.assets) != 1:
        raise ValueError('基础外观必须包含一个资源文件')
    source_objects = source.assets[0].objects
    objects = target_env.assets[0].objects
    apps = [obj for obj in _components(objects, objects[target_root], 'MonoBehaviour')
            if 'motionList' in obj.read_typetree()]
    if len(apps) != 1:
        raise ValueError('基础外观没有唯一的动作组件')
    app = apps[0]
    app_tree = app.read_typetree()
    renderer = _local(objects, app_tree['sprenderer_charactermotion'], 'SpriteRenderer')
    renderer_tree = renderer.read_typetree()
    body_path = _body_path(objects, target_root, renderer_tree)
    animator = _local(objects, app_tree['_anim'], 'Animator').read_typetree()
    controller = _local(objects, animator['m_Controller'], 'AnimatorController').read_typetree()
    primary_roles = primary_idle_clip_roles(controller)
    # A Motions sidecar starts at positive unit scale relative to the appearance.
    # The source clip then writes its own local transform. Remove the template's
    # renderer reflection for the first frame and compensate for mirrored parents.
    from roland_merge import Prefab
    from sprite_facing import body_rig
    _, parity, _ = body_rig(Prefab.from_asset(target_env, target_root))
    body_go = _local(objects, renderer_tree['m_GameObject'], 'GameObject')
    transform, = _components(objects, body_go, 'Transform')
    transform_tree = transform.read_typetree()
    local_x = transform_tree['m_LocalScale']['x']
    parent_parity = parity * (-1 if renderer_tree['m_FlipX'] else 1) * (-1 if local_x < 0 else 1)
    renderer_tree['m_FlipX'] = parent_parity < 0
    transform_tree['m_LocalScale']['x'] = abs(local_x)
    _save(transform, transform_tree)
    old_clips = []
    pending, seen = [app], set()
    while pending:
        obj = pending.pop()
        if obj.path_id in seen:
            continue
        seen.add(obj.path_id)
        tree = obj.read_typetree()
        if obj.type.name == 'AnimationClip':
            if any(b['isPPtrCurve'] and b['path'] == body_path and b['typeID'] == 212
                   for b in tree['m_ClipBindingConstant']['genericBindings']):
                old_clips.append((obj, tree, _role(tree['m_Name'])))
            elif obj.path_id in primary_roles and _empty_animator_clip(tree):
                old_clips.append((obj, tree, primary_roles[obj.path_id]))
        else:
            for pointer in _refs(tree):
                child = objects.get(pointer['m_PathID'])
                if not pointer['m_FileID'] and child and child.type.name in ('MonoBehaviour', 'AnimationClip', 'AnimatorController', 'Animator'):
                    pending.append(child)
    old_idle = next((tree for _, tree, role in old_clips if role in ('idle', 'default')
                     and tree['m_ClipBindingConstant']['pptrCurveMapping']), None)
    if not old_idle:
        raise ValueError('基础外观缺少默认身体动画')
    old_sprite = _local(objects, old_idle['m_ClipBindingConstant']['pptrCurveMapping'][0], 'Sprite').read_typetree()
    authored_sprite = source_objects[tracks['idle'].sprite_ids[0]].read_typetree()
    scale = (old_sprite['m_Rect']['height'] / old_sprite['m_PixelsToUnits']) / (authored_sprite['m_Rect']['height'] / authored_sprite['m_PixelsToUnits'])
    templates = {kind: next((o for o in objects.values() if o.type.name == kind), None)
                 for kind in ('Sprite', 'Texture2D', 'AnimationClip')}
    if not all(templates.values()):
        raise ValueError('基础外观缺少可写入的动画或图像类型')
    next_id = 1
    def clone(kind, tree):
        nonlocal next_id
        while next_id in objects:
            next_id += 1
        obj = copy(templates[kind])
        obj.path_id = next_id
        _save(obj, tree)
        objects[next_id] = obj
        next_id += 1
        return obj.path_id
    sprites = {}
    def sprite_id(pid):
        if pid not in sprites:
            obj = source_objects[pid]
            image = obj.read().image.convert('RGBA')
            texture = clone('Texture2D', _pose_texture(templates['Texture2D'], obj.peek_name(), image))
            sprites[pid] = clone('Sprite', _pose_sprite(obj, texture, image, scale))
        return sprites[pid]
    def converted(track, name=None):
        tree = deepcopy(track.clip.read_typetree())
        if name is not None:
            tree['m_Name'] = name
        bindings = tree['m_ClipBindingConstant']
        for binding in bindings['genericBindings']:
            if binding['path'] != 0:
                raise ValueError('作者身体动画包含不支持的子节点曲线')
            binding['path'] = body_path
        for pointer in bindings['pptrCurveMapping']:
            if pointer['m_PathID']:
                pointer['m_PathID'] = sprite_id(pointer['m_PathID'])
        return tree
    result = {}
    for i, (role, track) in enumerate(sorted(tracks.items())):
        if progress:
            progress(int(i * 100 / len(tracks)), '正在转换作者身体动作：' + role)
        result[role] = clone('AnimationClip', converted(track))
    # Distinguish a single Default state from controllers with both states.
    controller_ids = {ref['m_PathID'] for ref in controller.get('m_AnimationClips', []) if not ref['m_FileID']}
    controller_roles = {role for obj, _, role in old_clips if obj.path_id in controller_ids}
    for obj, tree, role in old_clips:
        selected, loop = (animator_replacement(role, controller_roles, tracks)
                          if obj.path_id in controller_ids else (role, False))
        authored = tracks.get(selected) or tracks['idle']
        replacement = converted(authored, tree['m_Name'])
        if loop:
            set_idle_loop(replacement)
        _save(obj, replacement)
    initial = tracks.get('default') or tracks['idle']
    renderer_tree['m_Sprite'] = {'m_FileID': 0, 'm_PathID': sprite_id(initial.sprite_ids[0])}
    _save(renderer, renderer_tree)
    for pointer in app_tree.get('_spineSkins', []):
        spine = _local(objects, pointer, 'MonoBehaviour')
        skin = spine.read_typetree()
        if '_isDisableSpine' not in skin:
            raise ValueError('无法关闭基础外观的骨骼身体')
        skin['_isDisableSpine'] = 1
        _save(spine, skin)
        pointer = skin.get('_spine_renderer') or {}
        if pointer.get('m_PathID'):
            mesh = objects.get(pointer['m_PathID'])
            if pointer.get('m_FileID') or not mesh or mesh.type.name not in ('MeshRenderer', 'SkinnedMeshRenderer'):
                raise ValueError('无法确认基础外观的骨骼渲染器')
            tree = mesh.read_typetree()
            tree['m_Enabled'] = False
            _save(mesh, tree)
    for motion in app_tree['motionList']:
        motion['isSpineAnim'] = 0
    _save(app, app_tree)
    return result


def build_motion_model(raw_bundle, base_asset, look, unity, motion_data, *, progress=None, stock_override=False):
    """Convert authored body animation into a standalone native appearance."""
    import hashlib
    import json
    from pathlib import Path
    from roland_merge import Prefab
    from skin_assets import _convert, _roots, _Streams
    from skin_motions import analyze_motion
    from motion_bundle_timelines import install_timelines, group_clips

    source = unity.load(raw_bundle)
    base_path, address = base_asset
    env = unity.load(str(base_path))
    roots = [row for row in _roots(env) if row[0] == address]
    if len(roots) != 1:
        raise ValueError('找不到唯一的基础外观')
    _, root, index = roots[0]
    normalized = {key.casefold(): value for key, value in motion_data.items()}
    if len(normalized) != len(motion_data):
        raise ValueError('动作名称大小写重复')
    empty_tracks = set()
    tracks = find_body_tracks(source, empty_tracks=empty_tracks)
    skipped = 0
    if stock_override:
        selected = select_stock_override_tracks(tracks, normalized)
        skipped = len(tracks) - len(selected)
        tracks = selected
    clips = copy_body_clips(source, env, root, tracks=tracks, progress=progress)
    prefab = Prefab.from_asset(env, root)
    install_timelines(prefab, clips, normalized, unity)
    digest = hashlib.sha256(raw_bundle)
    with Path(base_path).open('rb') as base_file:
        for block in iter(lambda: base_file.read(1024 * 1024), b''):
            digest.update(block)
    digest.update(json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf8'))
    serialized = env.file.save(packer='lz4')
    # Borrowed game templates can change independently of the author's bundle and base.
    digest.update(serialized)
    revision = digest.hexdigest()
    edited = unity.load(serialized)
    encoded, _ = _convert(edited, revision, look, address, root, index, _Streams(unity))
    parsed = unity.load(encoded)
    entry, timing, actions = analyze_motion(parsed, parsed.assets[0].objects[root], look,
                                             'Imported/' + look + '.prefab', look, declared_roles=True)
    groups = group_clips(clips)
    recognized = {row['detail']: row for section in ('attack', 'clash', 'defense') for row in actions[section]}
    for detail, (role, segments) in groups.items():
        row = recognized.get(detail)
        if row is None or len(row.get('parts', [])) != len(segments):
            raise ValueError('转换后的动作或片段数不一致：' + role)
    warnings = []
    if 'guard' in empty_tracks:
        idle_guard = any(row['detail'] == 3 and row['evidence'] == 'animator' for row in actions['defense'])
        warnings.append('原包守备轨道未引用身体图像，' +
                        ('守备使用作者待机画面' if idle_guard else '未生成独立守备动作'))
    omitted = sorted(set(normalized) - {role for role, _ in groups.values()})
    if omitted:
        warnings.append('当前无法绑定部分已声明动作：' + '、'.join(omitted))
    if skipped:
        warnings.append(f'另有 {skipped} 条轨道缺少对应技能时序或连续片段，未纳入')
    if stock_override:
        unsupported_phases = sorted({phase['type'] for role, _ in groups.values()
                                     for coin in normalized.get(role, {}).get('coins', ())
                                     for phase in coin.get('phases', ())
                                     if isinstance(phase.get('type'), str)
                                     and phase['type'] not in ('GiveDamage', 'ToTargetWide')})
        if unsupported_phases:
            warnings.append('部分附加阶段未绑定：' + '、'.join(unsupported_phases))
    if warnings:
        actions['presentation_warnings'] = warnings
    return encoded, address, look, entry, timing, actions

