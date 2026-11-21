"""Inspect motions on the selected Unity prefab and build its native attack contract."""
import math
import re
from functools import lru_cache

import boss_importer


_DEFENSE = {2: 'Evade', 3: 'Guard', 4: 'Damaged'}
_DUEL = re.compile(
    r'(?:^|_)(?:duel|parrying|clash)(?:_?(ready|prepare|win|lose|loss))?'
    r'(?:_timeline)?(?:[_ ]\d+)*$', re.I)
_SCOPED = re.compile(r'(?:^|_)(?:summon|actor|target|link|special)(?:_|$)', re.I)
_DEFENSE_NAME = re.compile(r'(?:^|_)(evade|guard|damaged)(?:_timeline)?(?:[_ ]\d+)*$', re.I)


def _object_id(ref):
    return ref.get('m_PathID', 0) if isinstance(ref, dict) and not ref.get('m_FileID') else 0


def _role(name, detail):
    lower = name.lower()
    duel_name = re.search(r'(?:^|_)(?:duel|parrying|clash)', lower)
    if detail in (41, 42, 43):
        return 6 if duel_name and re.search(r'(?:^|_)(?:actor|target|link)(?:_|$)', lower) else 0
    if detail == 19 and duel_name and re.search(r'(?:^|_)special(?:_|$)', lower):
        return 5
    if _SCOPED.search(name):
        return 0
    match = _DUEL.search(name)
    if match:
        return {None: 4, 'ready': 1, 'prepare': 1, 'win': 2,
                'lose': 3, 'loss': 3}[(match[1] or '').lower() or None]
    match = _DEFENSE_NAME.search(name)
    if match and match[1].lower() == _DEFENSE.get(detail, '').lower():
        return 7
    return 0


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _timeline(tree, read, kind):
    """Follow only owned tracks/markers. A clip's parent or prefab is not another track."""
    if not tree or 'm_Tracks' not in tree:
        return None
    pending = [(ref, True) for ref in tree['m_Tracks']]
    marker_track = tree.get('m_MarkerTrack') or {}
    if marker_track.get('m_PathID'):
        pending.append((marker_track, True))
    seen = set()
    active_hits, end_points, end_markers = [], [], []
    damage_count = 0
    visual = False
    while pending:
        ref, parent_enabled = pending.pop()
        pid = _object_id(ref)
        if not pid or pid in seen:
            return None
        seen.add(pid)
        track = read(pid)
        if not track or 'm_Clips' not in track:
            return None
        enabled = parent_enabled and not track.get('m_Muted')
        pending.extend((child, enabled) for child in track.get('m_Children', []))
        for ref in track.get('m_Markers', {}).get('m_Objects', []):
            marker = read(_object_id(ref))
            if not marker or not _number(marker.get('m_Time')):
                return None
            time = marker['m_Time']
            if enabled:
                end_points.append(time)
                if re.search(r'(?:^|_)End (?:Cheaker|Checker)(?:\(Clone\))*$', marker.get('m_Name', ''), re.I):
                    end_markers.append(time)
            if 'ratios' in marker and 'sturnInfo' in marker:
                damage_count += 1
                if enabled:
                    active_hits.append((time, (marker.get('info') or {}).get('afterDelay')))
        if not enabled:
            continue
        for clip in track.get('m_Clips', []):
            start, length = clip.get('m_Start'), clip.get('m_Duration')
            if not _number(start) or not _number(length) or length <= 0:
                continue
            end_points.append(start + length)
            if 'm_InfiniteClip' in track:
                playable = read(_object_id(clip.get('m_Asset'))) or {}
                if kind(_object_id(playable.get('m_Clip'))) == 'AnimationClip':
                    visual = True
        if kind(_object_id(track.get('m_InfiniteClip'))) == 'AnimationClip':
            visual = True
    duration = tree.get('m_FixedDuration') if tree.get('m_DurationMode') == 1 else max(end_points, default=0)
    if not _number(duration) or not 0 < duration <= 600:
        return None
    active_hits.sort(key=lambda item: item[0])
    return dict(name=tree.get('m_Name', ''), duration=duration, hits=active_hits,
                end=min(end_markers, default=-1), damage_count=damage_count, visual=visual)


def _animator_states(app, read, kind):
    anim = read(_object_id(app.get('_anim'))) or {}
    controller = read(_object_id(anim.get('m_Controller'))) or {}
    clips = controller.get('m_AnimationClips', [])
    names = dict(controller.get('m_TOS', []))
    states = set()
    for machine in controller.get('m_Controller', {}).get('m_StateMachineArray', []):
        for item in machine['data'].get('m_StateConstantArray', []):
            state = item['data']
            name = names.get(state.get('m_NameID'))
            if name not in _DEFENSE.values():
                continue
            for blend in state.get('m_BlendTreeConstantArray', []):
                for node in blend['data'].get('m_NodeArray', []):
                    index = node['data'].get('m_ClipID', -1)
                    if 0 <= index < len(clips) and kind(_object_id(clips[index])) == 'AnimationClip':
                        states.add(name)
    return states


def _spine_states(app, read):
    states = set()
    for ref in app.get('_spineSkins', []):
        spine = read(_object_id(ref)) or {}
        if spine.get('_isDisableSpine') or not read(_object_id(spine.get('_spine_Animation'))):
            continue
        for name in spine.get('_spineAnims', []):
            if isinstance(name, str):
                states.add(name.rsplit('/', 1)[-1].lower())
    return states


def analyze_motion(env, root, look, asset_key, name):
    """Return (pool entry, SST1 bytes, classified actions) for one root ObjectReader/PPtr."""
    if not hasattr(root, 'assets_file') or not hasattr(root, 'type'):
        root = root.deref()
    objects = root.assets_file.objects

    def kind(pid):
        obj = objects.get(pid)
        return obj.type.name if obj else None

    @lru_cache(maxsize=None)
    def read(pid):
        obj = objects.get(pid)
        return obj.read_typetree() if obj else None

    apps = [read(_object_id(c['component'])) for c in root.read_typetree()['m_Component']
            if kind(_object_id(c['component'])) == 'MonoBehaviour']
    apps = [app for app in apps if app and 'motionList' in app]
    if len(apps) != 1:
        raise ValueError('所选预制体根节点须有一个可识别的外观动作列表')
    app = apps[0]
    animator, spine = _animator_states(app, read, kind), _spine_states(app, read)
    actions = dict(attack=[], clash=[], defense=[], unclassified=[], runtime_roles={}, runtime_animator=[])
    groups = {}
    for motion in app['motionList']:
        detail = motion.get('_motiondetail')
        if type(detail) is int and 0 <= detail < 128:
            groups.setdefault(detail, []).append(motion)

    @lru_cache(maxsize=None)
    def inspect(pid):
        return _timeline(read(pid), read, kind)

    rows, contracts = [], []
    for detail, variants in groups.items():
        motion = variants[0]
        if any(motion != variant for variant in variants[1:]):
            actions['unclassified'].append(dict(detail=detail, reason='同槽存在不同动作'))
            continue
        refs = motion.get('timelineAssets') or []
        parts = [inspect(_object_id(ref)) for ref in refs]
        if parts and all(parts):
            names = [p['name'] for p in parts]
            attack_slot = 7 <= detail <= 16 or 24 <= detail <= 34
            if attack_slot and all(p['hits'] and p['visual'] and
                                   all(t >= 0 and _number(delay) and delay >= 0 for t, delay in p['hits']) for p in parts):
                items = [dict(motionIndex=i, duration=p['duration'], hitMarkerTime=p['hits'][0][0],
                              giveDamageDelay=p['hits'][0][1], endMarkerTime=p['end']) for i, p in enumerate(parts)]
                rows.append(dict(motionDetail=detail, motionTimelineDatas=items))
                contracts.append(dict(detail=detail, timelines=[dict(name=n, null=False) for n in names]))
                actions['attack'].append(dict(detail=detail, parts=names, evidence='timeline',
                                              hits=[[hit[0] for hit in p['hits']] for p in parts]))
                continue
            roles = {_role(n, detail) for n in names}
            if len(roles) == 1 and 0 not in roles and all(p['visual'] and not p['damage_count'] for p in parts):
                role = roles.pop()
                actions['runtime_roles'][str(detail)] = role
                actions['defense' if role == 7 else 'clash'].append(
                    dict(detail=detail, role=role, evidence='timeline', parts=names))
                continue
        pose = _DEFENSE.get(detail)
        if not refs and pose:
            evidence = None
            if motion.get('isSpineAnim') and pose.lower() in spine:
                evidence = 'spine'
            elif not motion.get('isSpineAnim') and pose in animator:
                actions['runtime_animator'].append(detail)
                evidence = 'animator'
            if evidence:
                actions['runtime_roles'][str(detail)] = 7
                actions['defense'].append(dict(detail=detail, role=7, evidence=evidence, state=pose))
                continue
        if refs or pose or detail in (17, 36, 37, 38):
            actions['unclassified'].append(dict(detail=detail, reason='缺少完整动作证据',
                                                 parts=[p['name'] if p else None for p in parts]))
    entry, timing = boss_importer.build_entry(
        dict(appearance=look, motions=contracts), dict(AppearanceName=look, motionList=rows),
        asset_key, display_name=name)
    entry.update(category='humanoid_boss', verified_attack_details=[r['motionDetail'] for r in rows],
                 metadata_evidence='serialized timelines')
    return entry, timing, actions
