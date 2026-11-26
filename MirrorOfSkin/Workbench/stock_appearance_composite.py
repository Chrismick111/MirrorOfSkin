"""Build one appearance from the exact locally installed timelines chosen by the mod."""
from collections import defaultdict
from copy import deepcopy
import hashlib
from pathlib import Path

from skin_assets import _convert, _roots, _Streams


ATTACK_DETAILS = set(range(7, 17)) | set(range(24, 35))


def _validate_groups(groups, sources):
    if not groups:
        raise ValueError('合成外观没有指定任何攻击动作')
    for detail, segments in groups.items():
        if type(detail) is not int or detail not in ATTACK_DETAILS or not segments or len(segments) > 128:
            raise ValueError('合成外观的攻击槽或段数无效')
        for source, motion, index in segments:
            if (source not in sources or type(motion) is not int or motion not in ATTACK_DETAILS
                    or type(index) is not int or index < 0):
                raise ValueError(f'合成外观引用了无效的供体动作：{source} {motion}:{index}')
    return groups


def _open(appearance_assets, source, unity, prefab_type):
    path, address = appearance_assets[source]
    env = unity.load(str(path))
    matches = [row for row in _roots(env) if row[0] == address]
    if len(env.assets) != 1 or len(matches) != 1:
        raise ValueError('找不到合成外观所需的唯一预制体：' + source)
    _, root, _ = matches[0]
    try:
        return prefab_type.from_asset(env, root)
    except (KeyError, StopIteration) as error:
        raise ValueError('预制体没有受支持的战斗模型或资源流：' + source) from error


def _selected(prefab, source, keys):
    by_detail = defaultdict(list)
    for motion in prefab.app['motionList']:
        by_detail[motion['_motiondetail']].append(motion)
    template = None
    timelines = []
    for detail, part in keys:
        variants = by_detail[detail]
        if len(variants) != 1:
            raise ValueError(f'供体没有唯一的攻击动作：{source} {detail}')
        motion = variants[0]
        if motion['motionObjects'] or motion['damageObj'] or motion['isSpineAnim']:
            raise ValueError(f'供体动作包含不支持的非时间轴动画：{source} {detail}')
        if part >= len(motion['timelineAssets']):
            raise ValueError(f'供体没有指定的时间轴段：{source} {detail}:{part}')
        item = motion['timelineAssets'][part]
        if item['m_FileID'] or item['m_PathID'] not in prefab.objects:
            raise ValueError(f'无法读取供体时间轴段：{source} {detail}:{part}')
        if template is None:
            template = deepcopy(motion)
        timelines.append(item)
    template['timelineAssets'] = timelines
    return template


def build(appearance_assets, base, groups, look, unity, *, progress=None):
    """Combine ordered (source appearance, motion detail, zero-based part) references."""
    _validate_groups(groups, appearance_assets)
    from roland_merge import Prefab, bind_attack_bodies, merge
    from sprite_facing import body_rig
    from import_progress import progress_range
    from UnityPy.streams import EndianBinaryReader

    report = progress_range(progress)
    target = _open(appearance_assets, base, unity, Prefab)
    layout = look
    address = appearance_assets[base][1]
    if groups.keys() & {m['_motiondetail'] for m in target.app['motionList']}:
        raise ValueError('合成攻击槽已被基础外观占用')

    by_source = defaultdict(dict)
    for segments in groups.values():
        for source, detail, part in segments:
            by_source[source][detail, part] = None
    next_id = (pid for pid in range(10000000000, 10010000000) if pid not in target.objects)
    stream_file = target.env.file.files[target.stream_name]
    stream = bytearray(stream_file.bytes)
    preloads = []
    timelines = {}
    template = None
    for i, (source, keys) in enumerate(by_source.items()):
        report(i * 75 // len(by_source), f'正在合并逐币动作（{i + 1}/{len(by_source)}）：{source}')
        donor = target if source == base else _open(appearance_assets, source, unity, Prefab)
        selection = _selected(donor, source, keys)
        if source == base:
            body = body_rig(target)[0]
            for timeline in selection['timelineAssets']:
                if not bind_attack_bodies(target, (), body, timelines=(timeline,)):
                    raise ValueError('基础外观片段没有可验证的主体精灵轨道')
        else:
            selection = merge(target, donor, {}, next_id, stream, preloads,
                              legacy=False, selected_motion=selection)
        if template is None:
            template = {k: v for k, v in selection.items() if k != 'timelineAssets'}
        timelines.update(((source, *key), item) for key, item in zip(keys, selection['timelineAssets']))

    report(75, '正在绑定攻击动作与身体图像')
    for detail, segments in groups.items():
        motion = deepcopy(template)
        motion.update(_motiondetail=detail, timelineAssets=[deepcopy(timelines[key]) for key in segments])
        target.app['motionList'].append(motion)
    target.objects[target.app_id].save_typetree(target.app)
    target.objects[target.director_id].save_typetree(target.director)
    target.index['m_PreloadTable'].extend({'m_FileID': f, 'm_PathID': p} for f, p in preloads)
    target.objects[target.index_id].save_typetree(target.index)
    merged_stream = EndianBinaryReader(bytes(stream))
    merged_stream.flags = stream_file.flags
    target.env.file.files[target.stream_name] = merged_stream

    revision = hashlib.sha256(repr((base, groups)).encode('utf8'))
    for source in dict.fromkeys([base, *by_source]):
        with Path(appearance_assets[source][0]).open('rb') as file:
            while block := file.read(2**20):
                revision.update(block)
    # UnityPy stages writes separately from its typetree readers. Reopen the
    # edited file so the converter walks the grafted references and bindings.
    report(87, '正在生成外观模型文件')
    edited = unity.load(target.env.file.save(packer='lz4'))
    encoded, _ = _convert(edited, revision.hexdigest(), look, address, target.root,
                          target.index_id, _Streams(unity))
    return encoded, address, layout
