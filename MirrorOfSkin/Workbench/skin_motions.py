"""Inspect motions on the selected Unity prefab and build its native attack contract."""
import math
import re
from functools import lru_cache

import boss_importer


_DEFENSE = {2: 'Evade', 3: 'Guard', 4: 'Damaged'}
_STANDARD_VISUAL_ROLES = {2: 7, 3: 7, 4: 7, 17: 4, 23: 3, 36: 1, 37: 2, 38: 3}
_DUEL = re.compile(
    r'(?:^|_)(?:duel|parrying|clash)(?:_?(ready|prepare|win|lose|loss))?'
    r'(?:_timeline)?(?:[_ ]\d+)*$', re.I)
_NUMBERED_DUEL = re.compile(
    r'(?:^|_)(?:duel|parry|parrying|clash)(?:_(ready|prepare|win|lose|loss))?'
    r'(?:_timeline)?_?\d+$', re.I)
_DUEL_ROLES = {None: 4, 'ready': 1, 'prepare': 1, 'win': 2, 'lose': 3, 'loss': 3}
_SCOPED = re.compile(r'(?:^|_)(?:summon|actor|target|link|special)(?:_|$)', re.I)
_DEFENSE_NAME = re.compile(r'(?:^|_)(evade|guard|damaged)(?:_timeline)?(?:[_ ]\d+)*$', re.I)
_OTHER_TIMELINE = re.compile(r'(?:^|[_ ])(?:attack|skill|voice|sound|audio|fmod|sfx|vfx)(?:[_ ]|$)', re.I)
_VOICE_TRACK = 'fmodcustomtrack_voice'
_FMOD_TRACKS = {'fmodcustomtrack', _VOICE_TRACK, 'fmodeventtrack'}
_VOICE_PATH = re.compile(r'(?:^|[/_ :])(?:voice|voices|vo)(?=[/_ :]|$)', re.I)
_NON_VOICE_PATH = re.compile(r'(?:^|[/_ :])(?:sfx|bgm|music|ambience)(?=[/_ :]|$)', re.I)


def _object_id(ref):
    return ref.get('m_PathID', 0) if isinstance(ref, dict) and not ref.get('m_FileID') else 0


def _role(name, detail):
    if _OTHER_TIMELINE.search(name):
        return 0
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
        return _DUEL_ROLES[(match[1] or '').lower() or None]
    # Independently authored timelines can prefix a numbered action with the
    # character name. Only the corresponding standard clash slot can claim it.
    if detail in (17, 36, 37, 38):
        words = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', name).lower()
        match = _NUMBERED_DUEL.search(words)
        if (match and not _SCOPED.search(words) and not _OTHER_TIMELINE.search(words)
                and _DUEL_ROLES[match[1]] == _STANDARD_VISUAL_ROLES[detail]):
            return _DUEL_ROLES[match[1]]
    match = _DEFENSE_NAME.search(name)
    if match and match[1].lower() == _DEFENSE.get(detail, '').lower():
        return 7
    return 0


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _voice_event(asset, voice_track):
    """FMOD playables store either a path or a GUID, sometimes under a template."""
    fields = {name.casefold(): value for name, value in asset.items()}
    sources = [fields]
    template = fields.get('template')
    if isinstance(template, dict):
        sources.append({name.casefold(): value for name, value in template.items()})
    for source in sources:
        reference = source.get('eventreference')
        if not isinstance(reference, dict):
            reference = {}
        path = reference.get('Path') or reference.get('path') or source.get('eventname') or ''
        if isinstance(path, str) and _NON_VOICE_PATH.search(path):
            return None
        voice_path = isinstance(path, str) and _VOICE_PATH.search(path)
        guid = reference.get('Guid') or reference.get('guid') or {}
        if (voice_track or voice_path) and isinstance(guid, dict):
            parts = tuple(guid.get('Data' + str(i)) for i in range(1, 5))
            if all(type(part) is int for part in parts) and any(parts):
                return ('guid', parts)
        if voice_path:
            return ('path', path.casefold())
    return None


def _voice_events(app, read):
    """Inspect the selected appearance's motion timelines and their owned tracks."""
    complete = True

    def resolve(ref, field=None):
        nonlocal complete
        if not ref or not ref.get('m_PathID'):
            return None
        pid = _object_id(ref)
        try:
            tree = read(pid) if pid else None
        except Exception:
            tree = None
        if not isinstance(tree, dict) or (field and not isinstance(tree.get(field), list)):
            complete = False
            return None
        return tree

    @lru_cache(maxsize=None)
    def track_type(pid):
        track = read(pid)
        script_pid = _object_id(track.get('m_Script'))
        if script_pid:
            try:
                script = read(script_pid) or {}
            except Exception:
                script = {}
            if script.get('m_ClassName'):
                return script['m_ClassName'].casefold()
        # Native script references can point into the game rather than the bundle.
        name = re.sub(r'(?:\(Clone\)| \(\d+\))+$', '', track.get('m_Name') or '')
        return name.replace(' ', '').casefold()

    seen_timelines, seen_tracks = set(), set()
    events = []
    for motion in app['motionList']:
        for ref in motion.get('timelineAssets') or []:
            timeline = resolve(ref, 'm_Tracks')
            if timeline is None or _object_id(ref) in seen_timelines:
                continue
            seen_timelines.add(_object_id(ref))
            pending = [*timeline['m_Tracks'], timeline.get('m_MarkerTrack')]
            while pending:
                ref = pending.pop()
                track = resolve(ref, 'm_Clips')
                pid = _object_id(ref)
                if track is None or pid in seen_tracks or track.get('m_Muted'):
                    continue
                seen_tracks.add(pid)
                pending.extend(track.get('m_Children') or [])
                kind = track_type(pid)
                voice_track = kind == _VOICE_TRACK
                for ref in (track.get('m_Markers') or {}).get('m_Objects', []):
                    marker = resolve(ref)
                    if marker and _number(marker.get('m_Time')):
                        event = _voice_event(marker, voice_track)
                        if event:
                            events.append(event)
                if kind in _FMOD_TRACKS:
                    for clip in track['m_Clips']:
                        duration = clip.get('m_Duration')
                        if not _number(clip.get('m_Start')) or not _number(duration) or duration <= 0:
                            continue
                        asset = resolve(clip.get('m_Asset'))
                        if asset:
                            event = _voice_event(asset, voice_track)
                            if event:
                                events.append(event)
    return events, complete


def _model_voice_evidence(app, read, *, stock_voice=None, stock_only=False):
    events, complete = _voice_events(app, read)
    if not events:
        return dict(state='none' if complete else 'unknown', count=0)
    if stock_only:
        return dict(state='inherited', count=len(events))
    if stock_voice is None:
        return dict(state='found', count=len(events))
    inherited = stock_voice()
    if inherited is None:
        return dict(state='found_unattributed', count=len(events))
    authored_count = sum(event not in inherited for event in events)
    if authored_count:
        return dict(state='found', count=authored_count)
    if complete:
        return dict(state='inherited', count=len(events))
    return dict(state='unknown', count=0)


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


def _appearance_reader(root):
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
    return apps[0], read, kind


def stock_voice_events(root):
    """Get the event identities attached to a verified stock appearance root."""
    app, read, _ = _appearance_reader(root)
    events, _ = _voice_events(app, read)
    return frozenset(events)


def analyze_motion(env, root, look, asset_key, name, *, declared_roles=False, stock_voice=None, stock_only=False):
    """Return (pool entry, SST1 bytes, classified actions) for one root ObjectReader/PPtr."""
    app, read, kind = _appearance_reader(root)
    animator, spine = _animator_states(app, read, kind), _spine_states(app, read)
    actions = dict(attack=[], clash=[], defense=[], unclassified=[], runtime_roles={}, runtime_animator=[])
    actions['model_voice_evidence'] = _model_voice_evidence(app, read, stock_voice=stock_voice, stock_only=stock_only)
    if declared_roles:
        actions['declarable_timeline_roles'] = {}
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
            visual_only = all(p['visual'] and not p['damage_count'] for p in parts)
            if len(roles) == 1 and 0 not in roles and visual_only:
                role = roles.pop()
                actions['runtime_roles'][str(detail)] = role
                actions['defense' if role == 7 else 'clash'].append(
                    dict(detail=detail, role=role, evidence='timeline', parts=names))
                continue
            if (declared_roles and visual_only and roles == {0} and detail in _STANDARD_VISUAL_ROLES
                    and all(not (_SCOPED.search(n) or _OTHER_TIMELINE.search(n)
                                 or _DEFENSE_NAME.search(n) or _DUEL.search(n)) for n in names)):
                actions['declarable_timeline_roles'][str(detail)] = _STANDARD_VISUAL_ROLES[detail]
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
