"""Read the prepared local resource index without launching an external app.

Nothing here needs a developer machine layout or Limbus Archive: the timeline
snapshot, the resource index cache, and the user's game install are each
resolved by resource_catalog, and every one of them can be pointed elsewhere.
An appearance that the snapshot never recorded is reported as unknown instead of
looking like an appearance with no animation.
"""
import json
import pathlib
import re
import sys
import hashlib
import os
import tempfile
import zlib
from functools import lru_cache
import threading

import resource_catalog
import mos_data
import resource_identity
import timeline_store

HERE = pathlib.Path(__file__).resolve().parents[1]
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


@lru_cache(maxsize=1)
def _bundle_families():
    with (HERE/'native_bundle_families.json').open(encoding='utf8') as stream:
        return json.load(stream)


def _candidate_bundles(appearance, roots, index):
    root = roots.get('resource_root')
    if not root:
        return []
    root = pathlib.Path(root).resolve()
    families = set(_bundle_families().get(appearance, []))
    for relative, row in (index or {}).get('entries', {}).items():
        if appearance in (row.get('prefabs') or {}):
            families.add(pathlib.PurePosixPath(relative.replace(chr(92), '/')).parts[0])
    if not families:
        try:
            discovered=json.loads((mos_data.data_dir()/'Workbench/scan_state.json').read_bytes())
        except (OSError,ValueError):
            discovered={}
        for relative,row in discovered.items():
            if isinstance(row,dict) and appearance in (row.get('entries') or {}):
                families.add(pathlib.PurePosixPath(relative.replace(chr(92), '/')).parts[0])
    paths = []
    for family in sorted(families):
        if pathlib.Path(family).name != family or family in ('', '.', '..'):
            continue
        candidates = [p for p in (root/family).glob('*/__data') if p.is_file() and root in p.resolve().parents]
        if candidates:
            # A cache may retain older Unity content hashes after a game update.
            path = max(candidates, key=lambda p:(p.stat().st_mtime_ns, p.name, str(p)))
            paths.append(path.relative_to(root).as_posix())
    return paths


def _signature(roots, paths):
    root = pathlib.Path(roots['resource_root']).resolve()
    scripts = [p for folder in root.glob('*_monoscripts') for p in folder.rglob('__data')]
    files = sorted({root/item for item in paths} | set(scripts))
    return [str(root), [[p.relative_to(root).as_posix(),*resource_catalog.fingerprint(p)] for p in files]]


def _cache_path(roots, appearance):
    key=hashlib.sha256(appearance.encode()).hexdigest()
    return pathlib.Path(roots['index_dir'])/'live-timelines-v1'/(key+'.json.z')


def _cached(roots, appearance, paths):
    if not paths:
        return None
    try:
        obj=timeline_store._load_compressed(_cache_path(roots,appearance), limit=128*1024*1024)
        if obj['appearance']==appearance and obj.pop('signature')==_signature(roots,paths):
            return obj
    except (OSError, ValueError, KeyError, TypeError, zlib.error):
        pass
    return None


def _save_local(path, result, signature):
    path.parent.mkdir(parents=True, exist_ok=True)
    data=zlib.compress(json.dumps(dict(result,signature=signature),ensure_ascii=False,separators=(',',':')).encode('utf8'))
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
        temp=pathlib.Path(f.name)
        try:
            f.write(data)
            f.close()
            os.replace(temp,path)
        finally:
            temp.unlink(missing_ok=True)


def lookup(identity, roots=None):
    roots = roots or resource_catalog.resolve_roots()
    if not isinstance(identity,str) or not identity.strip():
        raise ValueError('请选择外观')
    aliases = resource_catalog.alias_map(roots['timeline_dir'])
    index, source = resource_catalog.load_index(roots['index_dir'], roots.get('resource_root'), auto_build=False)
    appearance,how=resource_catalog.resolve_appearance(identity,index,aliases)
    if not appearance:
        for pool in _pool_entries().values():
            for entry in pool.get('entries',[]):
                if identity in (entry.get('identity_id'),entry.get('appearance_name')):
                    appearance,how=entry['appearance_name'],'pool'
                    break
            if appearance: break
    if not appearance and identity in _bundle_families():
        appearance,how=identity,'resource-family'
    base={'identity':identity,'appearance':appearance,'records':[],'available':False,'resolved_by':how,
          'index_source':source,'roots':{k:str(roots.get(k)) for k in ('resource_root','index_dir','timeline_dir','game_dir')}}
    if not appearance:
        return dict(base,status='unknown',notice='未找到此外观',reason=how)
    paths=_candidate_bundles(appearance,roots,index)
    cached=_cached(roots,appearance,paths)
    if cached:
        with _lock:
            if _state.get(identity,{}).get('status')!='running':
                _state[identity]=cached
        return {**base,**cached,'status':'ok'}
    # Explicit old snapshots still work offline; online data always comes from game files.
    if not roots.get('resource_root'):
        legacy=_load(roots,appearance)
        if legacy and 'records' in legacy:
            return dict(base,status='ok',available=True,records=legacy['records'],notice='离线历史时间线')
        return dict(base,status='no_index',reason='缺少游戏资源缓存',notice='请先启动游戏并下载资源，再重新选择外观。')
    return dict(base,status='local_pending',notice='准备读取本机游戏资源',reason='待从本机游戏提取')


def _pool_entries():
    try:
        return json.loads(mos_data.path(HERE.parent,'Assets/runtime/all_sinners_pools.json').read_bytes())
    except (OSError,ValueError):
        return {}


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
        from resource_tools import unity
        unity()
    except Exception as exc:
        return '缺少 UnityPy 依赖：%s' % exc
    return None


def start(identity):
    snapshot = lookup(identity)
    if not snapshot['available'] and snapshot['status']!='local_pending':
        raise ValueError('本地索引状态为 %s：%s' % (snapshot['status'], snapshot.get('reason')))
    with _lock:
        if _state.get(identity, {}).get('status') == 'running':
            return {'status': 'running'}
        _state[identity] = {'status': 'running'}
    threading.Thread(target=_read_live, args=(identity, snapshot), kwargs={'allow_scan':True}, daemon=True).start()
    return {'status': 'running'}


def _locate_bundles(snapshot, roots, allow_scan):
    """Bundle paths from the snapshot, corrected through the rebuilt index.

    The snapshot stores paths relative to the Addressables cache root; a record
    written against another install still resolves, because the local index maps
    the appearance name to the path this machine actually has.
    """
    index, how = resource_catalog.load_index(roots['index_dir'], roots['resource_root'], auto_build=False)
    paths = _candidate_bundles(snapshot['appearance'],roots,index)
    if paths: return paths,index,how
    if snapshot['appearance'] in _bundle_families(): return [],index,how
    if allow_scan:
        with _index_lock:
            index=resource_catalog.build_index(roots['resource_root'],roots['index_dir'])
            how='built'
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


_index_lock = threading.Lock()


def _read_live(identity, snapshot, roots=None, allow_scan=False):
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
        bundles, index, index_source = _locate_bundles(snapshot, roots, allow_scan)
        if not bundles:
            raise RuntimeError('本机尚未下载此外观的资源包，请在游戏中下载资源后重试')
        signature=_signature(roots,bundles)
        if snapshot.get('status')=='ok' and 'resource_root' in snapshot:
            cached=_cached(roots,snapshot['appearance'],bundles)
            if cached:
                with _lock:
                    _state[identity]=cached
                return
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
                        script=(track.get('script') or {}).get('class') or ''
                        kind='effect' if script=='EffectActivateTimelineTrack' else 'sound' if 'sound' in script.lower() or 'audio' in script.lower() else '片段'
                        for clip in track.get('clips', []):
                            events.append({'t': clip.get('start'), 'kind': kind, 'label': clip.get('name'),
                                           'duration': clip.get('duration')})
                        for marker in track.get('markers', []):
                            events.append({'t': (marker.get('fields') or {}).get('m_Time'), 'kind': '标记',
                                           'label': marker.get('name') or marker.get('status')})
                    end_times=[event['t']+(event.get('duration') or 0) for event in events
                               if isinstance(event.get('t'), (int,float))]
                    fixed=part.get('fixed_duration')
                    duration = fixed if part.get('duration_mode')==1 and isinstance(fixed,(int,float)) else max(end_times,default=None)
                    group=re.sub(r'_Timeline(?:_\d+)?$','',part.get('name') or '',flags=re.I) or ('动作 %s' % motion.get('detail'))
                    records.append(dict(variant['_bundle_info'], **{
                        'detail': motion.get('detail'), 'index': part.get('index'), 'name': part.get('name'),
                        'bundle':variant['_bundle_info']['bundle_path'],'preferred_duration':duration,
                        'preferred_source':'unity_fixed_duration' if part.get('duration_mode')==1 else 'unity_track_end_estimate',
                        'path_id': pid, 'status': part.get('status'), 'tracks': part.get('tracks', []),
                        'matches': [{'group': g, 'events': events}
                                    for g in (list(dict.fromkeys(groups)) or [group])]}))
        records = _unique_live_records(records)
        missing = sum(1 for r in records if r.get('status') != 'resolved')
        missing += sum(1 for r in records for t in r.get('tracks', []) if t.get('status') == 'unresolved')
        result = {'status': 'done', 'available': True, 'appearance': snapshot['appearance'],
                  'records': records, 'failures': failures, 'unresolved': missing,
                  'resource_root': str(root), 'index_source': index_source,
                  'notice': '读取自当前游戏资源；未解析片段或轨道 %d 项，固定时长不一定等于播放时长。' % missing}
        if signature!=_signature(roots,bundles):
            raise RuntimeError('读取过程中游戏资源已变化，请重新选择外观')
        if not failures and not missing and records:
            try:
                _save_local(_cache_path(roots,snapshot['appearance']), result, signature)
            except OSError:
                result['notice'] += '；本机缓存不可写，下次将重新读取。'
    except Exception as exc:
        result = {'status': 'error', 'message': str(exc)}
    with _lock:
        _state[identity] = result
