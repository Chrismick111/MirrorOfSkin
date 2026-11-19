"""Read the prepared local resource index without launching an external app.

Nothing here needs a developer machine layout or Limbus Archive: the timeline
snapshot, the resource index cache, and the user's game install are each
resolved by resource_catalog, and every one of them can be pointed elsewhere.
An appearance that the snapshot never recorded is reported as unknown instead of
looking like an appearance with no animation.
"""
import json
import pathlib
import sys
import threading

import resource_catalog
import resource_identity
import timeline_store

HERE = pathlib.Path(__file__).resolve().parent
AUDIT_NAME = 'audited-unknown.json'
_state = {}
_lock = threading.Lock()


def audited_unknown():
    """Appearances an earlier audit proved it could not index.

    Data, not logic: the file ships next to this module and deleting it only
    costs the hint, never the lookup.
    """
    try:
        value = json.loads((HERE / AUDIT_NAME).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return []
    rows = value.get('appearances') if isinstance(value, dict) else value
    return [row for row in (rows or []) if isinstance(row, (str, dict))]


def _audited_entry(identity, aliases):
    """Match an input id or its resolved prefab name against the audit list."""
    name = aliases.get(identity) or identity
    for row in audited_unknown():
        if isinstance(row, str):
            label, note = row, '审计记录缺少资源包索引'
        else:
            label, note = str(row.get('appearance') or ''), str(row.get('reason') or '审计记录缺少资源包索引')
        if label and label in (identity, name):
            return {'appearance': label, 'reason': note, 'audited': True}
    return None


def _timeline_dir(roots):
    return pathlib.Path(roots['timeline_dir'])


def _load(roots, appearance):
    try:
        return timeline_store.load(_timeline_dir(roots), appearance)
    except ValueError as exc:
        return {'__error__': str(exc)}


def lookup(identity, roots=None):
    """Resolve one appearance to its collected records, or say why not.

    status values:
      ok            records loaded from the local timeline snapshot
      no_index      the snapshot knows the appearance but ships no record
      unknown       neither the snapshot nor the local bundle index knows it
      corrupt       the snapshot record exists but does not match the appearance
    """
    roots = roots or resource_catalog.resolve_roots()
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError('请选择外观')
    aliases = resource_catalog.alias_map(roots['timeline_dir'])
    # A cached index is a plain file read; building one here would turn a lookup
    # into a multi-minute scan, so a missing index only costs name resolution.
    index, index_source = resource_catalog.load_index(roots['index_dir'], roots['resource_root'],
                                                      auto_build=False)
    appearance, how = resource_catalog.resolve_appearance(identity, index, aliases)
    base = {'identity': identity, 'appearance': appearance, 'records': [], 'available': False,
            'roots': {key: str(roots.get(key)) for key in ('game_dir', 'resource_root', 'index_dir', 'timeline_dir')},
            'resolved_by': how, 'index_source': index_source}
    if not appearance:
        audit = _audited_entry(identity, aliases)
        base.update({'status': 'unknown', 'reason': audit['reason'] if audit else how,
                     'audited': bool(audit)})
        base['notice'] = '未知：%s；未做任何动作假设。' % base['reason']
        return base
    obj = _load(roots, appearance)
    if isinstance(obj, dict) and '__error__' in obj:
        base.update({'status': 'corrupt', 'reason': obj['__error__'],
                     'notice': '时间线资料与外观不匹配：%s' % obj['__error__']})
        return base
    if obj is None:
        audit = _audited_entry(identity, aliases)
        base.update({'status': 'no_index', 'reason': audit['reason'] if audit else '时间线快照没有该外观的记录',
                     'audited': bool(audit)})
        base['notice'] = '无索引：%s；动作数量未知。' % base['reason']
        return base
    base.update({'status': 'ok', 'available': True, 'records': obj.get('records', []),
                 'notice': '资源引用与未渲染事件来自本地采集，时间可能是估算，游戏内效果尚未验证。'})
    return base


def unknown_report(roots=None):
    """Every audited appearance, with the state the lookup now reports for it."""
    roots = roots or resource_catalog.resolve_roots()
    rows = []
    for entry in audited_unknown():
        identity = entry if isinstance(entry, str) else str(entry.get('appearance') or '')
        if not identity:
            continue
        result = lookup(identity, roots)
        rows.append({'appearance': identity, 'status': result['status'],
                     'audited': result.get('audited', False), 'reason': result.get('reason')})
    return rows


def state(identity):
    with _lock:
        return _state.get(identity, {'status': 'idle'}).copy()


def _capability():
    """Why live bundle reading is unavailable, or None when it can run."""
    if sys.version_info < (3, 9):
        return '本机资源解析需要 Python 3.9 或更高版本，当前 %s' % sys.version.split()[0]
    try:
        import UnityPy  # noqa: F401
    except Exception as exc:
        return '缺少 UnityPy 依赖：%s' % exc
    return None


def start(identity):
    snapshot = lookup(identity)
    if not snapshot['available']:
        raise ValueError('本地索引状态为 %s：%s' % (snapshot['status'], snapshot.get('reason')))
    with _lock:
        if _state.get(identity, {}).get('status') == 'running':
            return {'status': 'running'}
        _state[identity] = {'status': 'running'}
    threading.Thread(target=_read_live, args=(identity, snapshot), daemon=True).start()
    return {'status': 'running'}


def _locate_bundles(snapshot, roots):
    """Bundle paths from the snapshot, corrected through the rebuilt index.

    The snapshot stores paths relative to the Addressables cache root; a record
    written against another install still resolves, because the local index maps
    the appearance name to the path this machine actually has.
    """
    index, how = resource_catalog.load_index(roots['index_dir'], roots['resource_root'], auto_build=True)
    table = resource_catalog.appearance_table(index)
    wanted = []
    for record in snapshot['records']:
        bundle = str(record.get('bundle') or '')
        if bundle:
            wanted.append(bundle)
    fallback = table.get(snapshot['appearance'])
    if fallback:
        wanted.append(fallback)
    return list(dict.fromkeys(wanted)), index, how


def _unique_live_records(records):
    """Drop byte-for-byte equivalent readings; preserve conflicting records."""
    by_key={};unique=[]
    for record in records:
        key=resource_identity.motion_key(record)
        bucket=by_key.setdefault(key,[])
        if record in bucket:continue
        bucket.append(record);unique.append(record)
    return unique


def _read_live(identity, snapshot, roots=None):
    try:
        blocked = _capability()
        if blocked:
            raise RuntimeError(blocked)
        roots = roots or resource_catalog.resolve_roots()
        root = roots.get('resource_root')
        if not root:
            raise RuntimeError('没有找到游戏资源目录：%s' % '；'.join(roots.get('problems') or ['请先启动一次游戏']))
        root = pathlib.Path(root).resolve()
        import native_timeline_extract
        import script_types
        script_resolver = script_types.shared(root)
        bundles, index, index_source = _locate_bundles(snapshot, roots)
        if not bundles:
            raise RuntimeError('索引中没有资源包引用')
        variants = []
        failures = []
        for relative in bundles:
            path = (root / relative).resolve()
            if root not in path.parents or not path.is_file():
                failures.append({'bundle': relative, 'error': '资源包未找到'})
                continue
            try:
                before = resource_identity.bundle_info(root, relative)
                result = native_timeline_extract.extract(str(path), snapshot['appearance'], script_resolver)
                after = resource_identity.bundle_info(root, relative)
                if before != after:
                    raise RuntimeError('读取时资源包发生变化，请重试')
                for variant in result['variants']:
                    variant['_bundle_info'] = after
                variants.extend(result['variants'])
                if not result['variants']:
                    failures.append({'bundle': relative, 'error': '没有找到外观'})
            except Exception as exc:
                failures.append({'bundle': relative, 'error': str(exc)})
        if not variants:
            raise RuntimeError('未读取到外观；' + '; '.join(x['error'] for x in failures))
        records = []
        for variant in variants:
            for motion in variant.get('motions', []):
                for part in motion.get('parts', []):
                    ref = part.get('ref') or {}
                    pid = str(ref.get('path_id') or '')
                    groups = [m.get('group') for r in snapshot['records']
                              if str(r.get('path_id')) == pid
                              and str(r.get('bundle') or '').replace('\\', '/').casefold() == variant['_bundle_info']['bundle_path'].casefold()
                              for m in r.get('matches', []) if m.get('group')]
                    events = []
                    for track in part.get('tracks', []):
                        for clip in track.get('clips', []):
                            events.append({'t': clip.get('start'), 'kind': '片段', 'label': clip.get('name'),
                                           'duration': clip.get('duration')})
                        for marker in track.get('markers', []):
                            events.append({'t': (marker.get('fields') or {}).get('m_Time'), 'kind': '标记',
                                           'label': marker.get('name') or marker.get('status')})
                    records.append(dict(variant['_bundle_info'], **{
                        'detail': motion.get('detail'), 'index': part.get('index'), 'name': part.get('name'),
                        'path_id': pid, 'status': part.get('status'), 'tracks': part.get('tracks', []),
                        'matches': [{'group': g, 'events': events}
                                    for g in (list(dict.fromkeys(groups)) or [''])]}))
        records = _unique_live_records(records)
        missing = sum(1 for r in records if r.get('status') != 'resolved')
        missing += sum(1 for r in records for t in r.get('tracks', []) if t.get('status') == 'unresolved')
        result = {'status': 'done', 'available': True, 'appearance': snapshot['appearance'],
                  'records': records, 'failures': failures, 'unresolved': missing,
                  'resource_root': str(root), 'index_source': index_source,
                  'notice': '读取自当前游戏资源；未解析片段或轨道 %d 项，固定时长不一定等于播放时长。' % missing}
    except Exception as exc:
        result = {'status': 'error', 'message': str(exc)}
    with _lock:
        _state[identity] = result
