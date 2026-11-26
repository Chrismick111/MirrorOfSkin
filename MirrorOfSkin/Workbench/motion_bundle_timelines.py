"""Attach authored body clips and coin timings to a native appearance's director."""
from collections import defaultdict
from copy import copy, deepcopy
from itertools import count
import math
import re


def ref(pid):
    return {'m_FileID': 0, 'm_PathID': pid}


_VISUAL = {'evade': 2, 'guard': 3, 'damaged': 4, 'parrying': 17,
           'duel_ready': 36, 'duel_win': 37, 'duel_lose': 38}
_TRACKS = {'body': 'Animation Track', 'skill': 'Skill Give Timing Track',
           'view': 'Character Appearance Timeline Track'}
_MARKERS = {'damage': 'Skill Give Timing_Give Damage', 'move': 'Skill Give Timing_Tween Move_To Target_Wide',
            'handoff': 'Character Appearance Marker_Hit Cheaker', 'end': 'Character Appearance Marker_End Cheaker'}
_MARKER_FIELDS = {'damage': {'info', 'ratios', 'sturnInfo'}, 'move': {'moveInfo', 'moveInfo_wide'},
                  'handoff': {'hitCheakerInfo'}, 'end': set()}


def timeline_slot(name):
    match = re.fullmatch(r'(.+?)_([0-9]+)', name)
    role = match[1] if match else name
    detail = _VISUAL.get(role)
    if detail is None:
        if not re.fullmatch(r's(?:[1-9]|1[0-9]|2[01])', role):
            return None
        number = int(role[1:])
        detail = number + (6 if number <= 10 else 13)
    return detail, role, int(match[2]) if match else 0


def group_clips(clips):
    groups = defaultdict(dict)
    for name, pid in clips.items():
        slot = timeline_slot(name)
        if slot is None:
            continue
        detail, role, index = slot
        if index in groups[detail]:
            raise ValueError('作者动作重复：' + name)
        groups[detail][index] = (role, pid)
    result = {}
    for detail, segments in groups.items():
        if sorted(segments) != list(range(len(segments))) or len(segments) > 128:
            raise ValueError('作者动作的硬币片段不连续')
        result[detail] = segments[0][0], [segments[i][1] for i in range(len(segments))]
    return result


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('动作标记包含无效的时间或坐标')
    return value


def phase_times(phase, duration):
    steps = phase.get('steps', 1)
    if type(steps) is not int or not 0 <= steps <= 128:
        raise ValueError('动作标记的步数无效')
    start = _number(phase.get('start', 0))
    end = _number(phase.get('end', start))
    # Native fixed-length clips cannot fire a marker outside their playback window.
    return [duration * min(1, max(0, start + (end - start) * i / max(1, steps - 1))) for i in range(steps)]


def import_game_marker(prefab, source, path_id, kind):
    """Transfer the actual native marker and its type record into a compatible prefab file."""
    from private_server_art import _refs, _save

    target, donor = prefab.file, source.assets_file
    schema = lambda asset: (asset.header.version, asset.header.endian, asset.unity_version,
                            asset._m_target_platform, asset._enable_type_tree)
    serialized = source.serialized_type
    if (schema(target) != schema(donor) or not serialized or serialized.class_id != 114
            or serialized.is_stripped_type or serialized.type_dependencies
            or not 0 <= serialized.script_type_index < len(donor.script_types)):
        return False
    tree = source.read_typetree()
    if (set(tree) != {'m_GameObject', 'm_Enabled', 'm_Script', 'm_Name', 'm_Time'} | _MARKER_FIELDS[kind]
            or tree['m_GameObject'] != ref(0)
            or re.sub(r'(?:\(Clone\))+$', '', tree['m_Name']) != _MARKERS[kind]):
        return False
    script = tree['m_Script']
    if any(item is not script and item.get('m_PathID') for item in _refs(tree)):
        return False
    donor_type = donor.script_types[serialized.script_type_index]
    file_id = script['m_FileID']
    if (not 0 < file_id <= len(donor.externals) or not script['m_PathID']
            or (donor_type.local_serialized_file_index, donor_type.local_identifier_in_file)
               != (file_id, script['m_PathID'])):
        return False
    external = donor.externals[file_id - 1]
    matches = [index for index, item in enumerate(target.externals, 1)
               if (item.path.casefold(), item.guid, item.type) ==
                  (external.path.casefold(), external.guid, external.type)]
    if len(matches) != 1:
        return False
    file_id, = matches
    script_id = script['m_PathID']
    index = next((i for i, value in enumerate(target.script_types)
                  if (value.local_serialized_file_index, value.local_identifier_in_file)
                  == (file_id, script_id)), len(target.script_types))
    if index == len(target.script_types):
        imported_type = copy(donor_type)
        imported_type.local_serialized_file_index = file_id
        target.script_types.append(imported_type)
    imported = copy(serialized)
    imported.script_type_index = index
    target.types.append(imported)
    obj = copy(source)
    obj.path_id = path_id
    obj.assets_file = target
    obj.type_id = len(target.types) - 1
    obj.serialized_type = imported
    tree['m_Script']['m_FileID'] = file_id
    tree['m_Name'] = _MARKERS[kind]
    _save(obj, tree)
    prefab.objects[path_id] = obj
    return True


def _find_game_markers(prefab, unity, needed):
    from scan.resource_catalog import fingerprint, load_index, resolve_roots

    roots = resolve_roots()
    root = roots['resource_root']
    if root is None:
        return {}
    index, _ = load_index(roots['index_dir'], root, auto_build=False)
    if index is None:
        return {}
    wanted = {_MARKERS[kind]: kind for kind in needed}
    found = {}
    for relative, item in sorted(index['entries'].items()):
        if not item.get('prefabs'):
            continue
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            continue
        try:
            if fingerprint(path) != item.get('fingerprint'):
                continue
            env = unity.load(path.read_bytes())
        except (OSError, ValueError):
            continue
        for asset in env.assets:
            for obj in asset.objects.values():
                if obj.type.name != 'MonoBehaviour':
                    continue
                name = re.sub(r'(?:\(Clone\))+$', '', obj.peek_name() or '')
                kind = wanted.get(name)
                if kind and import_game_marker(prefab, obj, needed[kind], kind):
                    found[kind] = needed[kind]
                    del wanted[name]
                    if not wanted:
                        return found
    return found


class _TimelineBuilder:
    def __init__(self, prefab, *, needs_skill_track=True):
        self.pf = prefab
        self.ids = count(1)
        names = {value: key for key, value in {**_TRACKS, **_MARKERS}.items()}
        self.templates = {}
        for pid, obj in prefab.objects.items():
            if obj.type.name != 'MonoBehaviour':
                continue
            key = names.get(re.sub(r'(?:\(Clone\)| \(\d+\))+$', '', obj.peek_name() or ''))
            if key:
                self.templates.setdefault(key, pid)
        self.templates['timeline'] = next(r['m_PathID'] for m in prefab.app['motionList'] for r in m['timelineAssets'])
        self.bindings = []
        receivers = defaultdict(set)
        for binding in prefab.director['m_SceneBindings']:
            track = prefab.objects.get(binding['key']['m_PathID'])
            target = binding['value']
            if track and not target['m_FileID'] and target['m_PathID']:
                name = re.sub(r' \(\d+\)$', '', track.peek_name() or '')
                receivers[name].add(target['m_PathID'])
        self.receivers = {'body': prefab.app['_anim']}
        self.implicit_bindings = (
            not prefab.director['m_SceneBindings'] and
            prefab.app.get('m_GameObject') == prefab.director.get('m_GameObject') == ref(prefab.root) and
            prefab.app.get('_playableDirector') in (ref(0), ref(prefab.director_id))
        )
        for key in (('view', 'skill') if needs_skill_track else ('view',)):
            ids = receivers[_TRACKS[key]]
            if self.implicit_bindings:
                # Some stock prefabs leave all bindings to the runtime.
                # These two native tracks target the root CharacterAppearance component.
                ids = {prefab.app_id}
            if len(ids) != 1:
                raise ValueError('无法唯一确认基础外观的动作接收器：' + _TRACKS[key])
            self.receivers[key] = ref(next(iter(ids)))

    def clone(self, key, **updates):
        from private_server_art import _save
        template = self.pf.objects.get(self.templates.get(key))
        if template is None:
            raise ValueError('基础外观缺少动作标记类型：' + key)
        obj = copy(template)
        obj.path_id = next(i for i in self.ids if i not in self.pf.objects)
        tree = template.read_typetree()
        tree.update(updates)
        _save(obj, tree)
        self.pf.objects[obj.path_id] = obj
        return obj

    def track(self, kind, timeline, markers=(), **fields):
        track = self.clone(kind, m_Parent=ref(timeline.path_id), m_Children=[], m_Clips=[],
                           m_Markers={'m_Objects': list(markers)}, m_Muted=0, m_Locked=0,
                           m_Curves=ref(0), m_AnimClip=ref(0), **fields)
        self.bindings.append({'key': ref(track.path_id), 'value': self.receivers[kind]})
        return ref(track.path_id)

    def timeline(self, role, index, clip, coin, attacking):
        from private_server_art import _save
        duration = _number(coin.get('totalDuration', 0))
        if duration <= 0:
            duration = self.pf.tree(clip)['m_MuscleClip']['m_StopTime']
        if not 0 < duration <= 600:
            raise ValueError('动作播放时长无效：' + role)
        timeline = self.clone('timeline', m_Name=f'{role}_{index + 1}', m_Tracks=[], m_MarkerTrack=ref(0),
                              m_DurationMode=1, m_FixedDuration=duration)
        tracks = [self.track('body', timeline, m_InfiniteClip=ref(clip), m_InfiniteClipTimeOffset=0,
                             m_ApplyAvatarMask=0, m_AvatarMask=ref(0))]
        view, skills = [], []
        hits = []
        for phase in coin.get('phases') or []:
            if not isinstance(phase, dict):
                raise ValueError('动作阶段格式无效：' + role)
            if phase.get('type') == 'GiveDamage' and attacking:
                hits.extend(phase_times(phase, duration))
            if phase.get('type') == 'ToTargetWide':
                point = {axis: _number((phase.get('move') or {}).get(axis, 0)) for axis in 'xyz'}
                for t in phase_times(phase, duration):
                    obj = self.clone('move', m_Time=t)
                    tree = obj.read_typetree()
                    tree['moveInfo_wide'].update(arriveRadius_Vector=point, overrideTarget=-1)
                    tree['moveInfo'].update(duration=phase.get('duration') or .066, arriveRadius=point['x'],
                                            ease=0, useAxisMoveAnimationCurve=0, isRefreshDir=bool(phase.get('isRefreshDir')),
                                            isInclude_targetRadius=bool(phase.get('targetRadius')),
                                            isInclude_attakcerRadius=bool(phase.get('attackerRadius')))
                    _save(obj, tree)
                    skills.append(ref(obj.path_id))
        if attacking:
            if not hits:
                raise ValueError('攻击动作没有声明伤害时点：' + role)
            for n, t in enumerate(sorted(hits)):
                obj = self.clone('damage', m_Time=t, ratios=1 / len(hits))
                tree = obj.read_typetree()
                tree['info'].update(isLastAttack=int(n == len(hits) - 1), multiHit=1, afterDelay=0,
                                    isNonDamageMotion=0, isUpAttack=0, multiHitDuration=-1)
                tree['sturnInfo'].update(forcePower=0, randomPower=0, isRotateTarget=0)
                _save(obj, tree)
                skills.append(ref(obj.path_id))
        for checker in coin.get('hitCheckers') or [{'time': .15}]:
            when = duration * min(1, max(0, _number(checker.get('time', 0))))
            obj = self.clone('handoff', m_Time=when)
            tree = obj.read_typetree()
            tree['hitCheakerInfo'].update(isCanNextMotion=0, nextEffectSpeed=1,
                                         isNextMotionCoinDelay=_number(checker.get('isNextMotionCoinDelay', 0)))
            _save(obj, tree)
            view.append(ref(obj.path_id))
        view.append(ref(self.clone('end', m_Time=duration).path_id))
        if skills:
            tracks.append(self.track('skill', timeline, skills))
        tracks.append(self.track('view', timeline, view))
        tree = timeline.read_typetree()
        tree['m_Tracks'] = tracks
        _save(timeline, tree)
        return ref(timeline.path_id)


def required_markers(groups, motion_data):
    required = {'end', 'handoff'}
    if any(role.startswith('s') for role, _ in groups.values()):
        required.add('damage')
    if any(isinstance(phase, dict) and phase.get('type') == 'ToTargetWide' and phase.get('steps', 1) != 0
           for role, _ in groups.values() for coin in motion_data.get(role, {}).get('coins', [])
           for phase in coin.get('phases', [])):
        required.add('move')
    return required


def install_timelines(pf, clips, motion_data, unity=None):
    from private_server_art import _save
    groups = group_clips(clips)
    required = required_markers(groups, motion_data)
    builder = _TimelineBuilder(pf, needs_skill_track=bool(required & {'damage', 'move'}))
    missing = required - builder.templates.keys()
    if missing and unity is not None:
        needed = {kind: next(i for i in builder.ids if i not in pf.objects) for kind in sorted(missing)}
        builder.templates.update(_find_game_markers(pf, unity, needed))
        missing -= builder.templates.keys()
    if missing:
        raise ValueError('找不到与基础外观兼容的动作标记：' + '、'.join(sorted(missing)))
    keep = [m for m in pf.app['motionList'] if m['_motiondetail'] not in groups and not m['timelineAssets']]
    template = next(m for m in pf.app['motionList'] if m['timelineAssets'])
    for detail, (role, segments) in sorted(groups.items()):
        motion = deepcopy(template)
        motion.update(_motiondetail=detail, isSpineAnim=0, damageObj=[], motionObjects=[], timelineAssets=[])
        coins = motion_data[role]['coins'] if role in motion_data else [{} for _ in segments]
        if len(coins) != len(segments):
            raise ValueError('动作定义和实际硬币片段数量不一致：' + role)
        for index, (clip, coin) in enumerate(zip(segments, coins)):
            motion['timelineAssets'].append(builder.timeline(role, index, clip, coin, role.startswith('s')))
        keep.append(motion)
    pf.app['motionList'] = keep
    pf.director.update(m_SceneBindings=builder.bindings, m_PlayableAsset=ref(0))
    pf.director['m_ExposedReferences']['m_References'] = []
    if builder.implicit_bindings:
        pf.app['_playableDirector'] = ref(pf.director_id)
    _save(pf.objects[pf.director_id], pf.director)
    _save(pf.objects[pf.app_id], pf.app)
