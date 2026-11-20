"""Offline draft compiler for workbench plans. Does not modify game files."""
import argparse
import json
import math
import pathlib
import resource_identity


class PlanError(ValueError):
    pass


def populated(value):
    return value is not None and value != ''


def number(value, label):
    if isinstance(value, bool):
        raise PlanError(label + '必须是有限的非负数字')
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise PlanError(label + '必须是有限的非负数字')
    if not math.isfinite(result) or result < 0:
        raise PlanError(label + '必须是有限的非负数字')
    return result


def records(resource):
    # Supports both native_timeline_extract output and effect-live-status output.
    if 'records' in resource:
        yield from resource['records']
    else:
        for variant in resource.get('variants', []):
            for motion in variant.get('motions', []):
                for part in motion.get('parts', []):
                    yield dict(part, detail=motion.get('detail'),
                               path_id=str((part.get('ref') or {}).get('path_id') or ''))


def compile_plan(plan, resource, appearance_id):
    if not isinstance(plan, dict) or plan.get('schema') != 1 or not isinstance(plan.get('effects'), list):
        raise PlanError('特效方案格式无效')
    if not isinstance(resource, dict) or not resource.get('appearance'):
        raise PlanError('资源缺少外观名称')
    if not isinstance(appearance_id, str) or not appearance_id:
        raise PlanError('请选择外观')
    result = []
    for index, effect in enumerate(plan['effects']):
        try:
            if not isinstance(effect, dict): raise PlanError('条目格式无效')
            allowed = {'identity', 'appearance', 'skill', 'coin', 'motion', 'bundle_sha256', 'event', 'event_locator', 'time', 'duration', 'parameters'}
            if any(populated(v) for k, v in effect.items() if k not in allowed):
                raise PlanError('存在不认识的字段')
            if str(effect.get('appearance', '')) != str(appearance_id):
                raise PlanError('外观与读取的资源不匹配')
            identity = str(effect.get('identity') or '')
            if not identity.isdigit(): raise PlanError('请选择人格')
            if populated(effect.get('duration')): raise PlanError('暂不支持设置持续时间')
            params = effect.get('parameters') or {}
            if not isinstance(params, dict) or any(populated(x) for x in params.values()):
                raise PlanError('位置、缩放、颜色和锚点尚未接入')
            if populated(effect.get('skill')) or populated(effect.get('coin')):
                raise PlanError('技能组和硬币条件尚未接入，请暂时留空')
            target_time = number(effect.get('time'), '时间')
            key = effect.get('motion')
            matches = [r for r in records(resource) if resource_identity.motion_key(r) == key]
            if len(matches) != 1: raise PlanError('动作不存在或存在重复')
            motion = matches[0]
            expected = effect.get('bundle_sha256')
            if not isinstance(expected, str) or len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected) or not motion.get('bundle_path') or len(str(motion.get('bundle_key') or ''))!=64 or expected != motion.get('bundle_sha256'):
                raise PlanError('资源包已变化或缺少版本信息，请重新选择动作')
            event = effect.get('event')
            if not isinstance(event, str) or not event.strip(): raise PlanError('请选择特效片段')
            candidates = [(ti, ci, track, clip) for ti, track in enumerate(motion.get('tracks', []))
                          for ci, clip in enumerate(track.get('clips', []))
                          if clip.get('name') == event and track.get('script', {}).get('status') == 'resolved' and track.get('script', {}).get('class') == 'EffectActivateTimelineTrack']
            locator = effect.get('event_locator')
            if locator is not None:
                if not isinstance(locator, dict) or set(locator) != {'track_path', 'clip_index'}:
                    raise PlanError('特效片段位置格式无效')
                path = locator['track_path']; selected_index = locator['clip_index']
                if not isinstance(path, list) or not path or any(type(n) is not int or n < 0 for n in path) or type(selected_index) is not int or selected_index < 0:
                    raise PlanError('特效片段位置格式无效')
                candidates = [(ti, ci, t, c) for ti, ci, t, c in candidates if t.get('track_path') == path and ci == selected_index]
            if len(candidates) != 1: raise PlanError('片段不存在或存在重名，请核对资源')
            ti, ci, track, clip = candidates[0]
            path = track.get('track_path')
            if not isinstance(path, list) or not path or any(type(n) is not int or n < 0 for n in path): raise PlanError('资源缺少轨道层级路径，请重新读取')
            track_type = track.get('script') or {}
            source = track_type.get('source') or {}
            if any(not isinstance(track_type.get(k), str) for k in ('assembly', 'namespace', 'class', 'cab', 'path_id')) or any(not isinstance(source.get(k), str) or not source[k] for k in ('bundle_path', 'bundle_key', 'bundle_sha256')):
                raise PlanError('轨道脚本来源未完整解析，请重新读取本机资源')
            original = number(clip.get('start'), '原始时间')
            result.append({'identity_id': identity, 'appearance_id': str(appearance_id),
                           'appearance_name': resource['appearance'], 'detail': motion['detail'],
                           'part_index': motion['index'], 'timeline_name': motion.get('name'),
                           'timeline_path_id': str(motion.get('path_id') or ''),
                           'bundle_path': motion.get('bundle_path'), 'bundle_key': motion.get('bundle_key'), 'bundle_sha256': expected,
                           'track_index': ti, 'track_path': path, 'track_name': track.get('name'), 'track_type': {k: track_type[k] for k in ('assembly','namespace','class','cab','path_id','source')}, 'clip_index': ci,
                           'clip_name': event, 'original_start': original, 'new_start': target_time})
        except (PlanError, KeyError, TypeError) as exc:
            raise PlanError('effect {}: {}'.format(index + 1, exc))
    keys = [(x['identity_id'], x['appearance_id'], x['bundle_key'], x['bundle_sha256'], x['timeline_path_id'], tuple(x['track_path']), x['clip_index']) for x in result]
    if len(set(keys)) != len(keys): raise PlanError('同一片段被重复修改')
    return {'format': 'personality-workbench.effect-plan', 'version': 4,
            'status': 'offline-draft-not-applied', 'operations': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scheme'); parser.add_argument('resource'); parser.add_argument('appearance_id'); parser.add_argument('output')
    a = parser.parse_args()
    try:
        plan = json.loads(pathlib.Path(a.scheme).read_text(encoding='utf-8-sig'))
        resource = json.loads(pathlib.Path(a.resource).read_text(encoding='utf-8-sig'))
        compiled = compile_plan(plan, resource, a.appearance_id)
        pathlib.Path(a.output).write_text(json.dumps(compiled, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    except (PlanError, OSError, ValueError) as exc:
        parser.exit(2, 'Cannot compile: {}\n'.format(exc))


if __name__ == '__main__': main()


def preview_workbench(plan, live_state):
    """Compile against server-owned readings, never a client supplied resource."""
    if not isinstance(plan, dict) or plan.get('schema') != 1 or not isinstance(plan.get('effects'), list):
        raise PlanError('方案格式无效')
    if not plan['effects']:
        raise PlanError('请先新增特效条目')
    operations = []
    for index, item in enumerate(plan['effects']):
        if not isinstance(item, dict):
            raise PlanError('第 %d 条格式无效' % (index + 1))
        appearance = item.get('appearance')
        if not isinstance(appearance, str) or not appearance:
            raise PlanError('第 %d 条请选择外观' % (index + 1))
        resource = live_state(appearance)
        if resource.get('status') != 'done':
            raise PlanError('第 %d 条请先读取该外观的本机资源' % (index + 1))
        try:
            operations.extend(compile_plan({'schema': 1, 'effects': [item]}, resource, appearance)['operations'])
        except PlanError as exc:
            raise PlanError('第 %d 条：%s' % (index + 1, exc))
    keys = [(x['identity_id'], x['appearance_id'], x['bundle_key'], x['bundle_sha256'], x['timeline_path_id'], tuple(x['track_path']), x['clip_index']) for x in operations]
    if len(set(keys)) != len(keys):
        raise PlanError('同一片段被重复修改')
    return {'format': 'personality-workbench.effect-plan', 'version': 4, 'status': 'offline-draft-not-applied', 'operations': operations}

def verify_before_handoff(plan, live_state, cache_root):
    """Rebuild every operation from server-owned live records, then rehash sources.

    The caller must retain control of live_state and repeat this immediately at
    the future handoff; this function does not write or apply anything.
    """
    if not isinstance(plan, dict) or plan.get('format') != 'personality-workbench.effect-plan' or plan.get('version') != 4 or plan.get('status') != 'offline-draft-not-applied' or not isinstance(plan.get('operations'), list) or not plan['operations']:
        raise PlanError('离线方案版本或格式无效')
    effects = []
    for op in plan['operations']:
        if not isinstance(op, dict):
            raise PlanError('离线操作格式无效')
        try:
            look = op['appearance_id']
            state = live_state(look)
            if state.get('status') != 'done':
                raise PlanError('请重新读取当前外观的本机资源')
            candidates = [r for r in records(state) if r.get('detail') == op['detail'] and r.get('index') == op['part_index'] and str(r.get('path_id') or '') == op['timeline_path_id'] and r.get('bundle_key') == op['bundle_key']]
            if len(candidates) != 1:
                raise PlanError('动作来源已变化或不唯一，请重新读取资源')
            effects.append({'identity': op['identity_id'], 'appearance': look,
                            'motion': resource_identity.motion_key(candidates[0]),
                            'bundle_sha256': op['bundle_sha256'], 'event': op['clip_name'],
                            'event_locator': {'track_path': op['track_path'], 'clip_index': op['clip_index']},
                            'time': op['new_start'], 'parameters': {}})
        except (KeyError, TypeError) as exc:
            raise PlanError('离线操作缺少定位信息') from exc
    rebuilt = preview_workbench({'schema': 1, 'effects': effects}, live_state)
    if rebuilt != plan:
        raise PlanError('离线方案与当前资源的轨道、脚本或时间不一致，请重新核对')
    try:
        return resource_identity.verify_plan(cache_root, rebuilt)
    except (OSError, ValueError) as exc:
        raise PlanError('资源指纹复核失败，请重新读取') from exc
