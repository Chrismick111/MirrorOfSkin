"""Read inert, bounded recipes for combining published appearance bundles."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import stat
import struct


MANIFEST = 'mirrorofskin-migration.json'
MAX_RECIPE = 64 * 1024
MAX_BUNDLE = 384 * 1024**2
MAX_TOTAL = 768 * 1024**2
_SLOTS = set(range(7, 17)) | set(range(24, 35))
_TOKEN = r'[A-Za-z0-9_, -]{1,128}'


def _fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() <= set(required) | set(optional):
        raise ValueError('模型合并配方字段不受支持')


def _string(value, pattern):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError('模型合并配方含无效文字或路径')


def _numbers(values, allowed, *, empty=False):
    if (not isinstance(values, list) or (not values and not empty) or len(values) > len(allowed)
            or any(type(value) is not int or value not in allowed for value in values)
            or len(set(values)) != len(values)):
        raise ValueError('模型合并配方含无效或重复的动作组')


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('模型合并配方含重复字段：' + key)
        result[key] = value
    return result


def _replacements(value):
    _fields(value, (), ('exact', 'ranges', 'prefixes', 'keep_sprite_substring'))
    for key in ('exact', 'prefixes'):
        rows = value.get(key, {})
        if not isinstance(rows, dict) or len(rows) > 128:
            raise ValueError('模型合并配方的精灵替换数量无效')
        for old, new in rows.items():
            _string(old, _TOKEN)
            _string(new, _TOKEN)
    ranges = value.get('ranges', [])
    if not isinstance(ranges, list) or len(ranges) > 16:
        raise ValueError('模型合并配方的精灵编号区间无效')
    intervals = {}
    for row in ranges:
        _fields(row, ('prefix', 'first', 'last', 'target'))
        _string(row['prefix'], _TOKEN)
        _string(row['target'], _TOKEN)
        first, last = row['first'], row['last']
        if type(first) is not int or type(last) is not int or not 0 <= first <= last <= 999:
            raise ValueError('模型合并配方的精灵编号区间无效')
        for low, high in intervals.setdefault(row['prefix'], []):
            if low <= last and first <= high:
                raise ValueError('模型合并配方的精灵编号区间重复')
        intervals[row['prefix']].append((first, last))
    if 'keep_sprite_substring' in value:
        _string(value['keep_sprite_substring'], _TOKEN)


def _asset(value, *, base=False, builtin=False):
    required = ['member', 'sha256', 'prefab']
    optional = ['sprites']
    if base:
        required.append('bind_groups')
        optional.append('replace_clips')
    else:
        required.extend(('groups', 'detail', 'segments'))
    if builtin:
        required.extend(('root', 'address'))
    _fields(value, required, optional)
    _string(value['member'], r'[A-Za-z0-9_-]{1,100}\.bundle')
    _string(value['sha256'], r'[a-f0-9]{64}')
    _string(value['prefab'], r'[A-Za-z0-9_-]{1,100}')
    if builtin:
        _string(value['root'], r'[A-Za-z0-9_-]{1,120}')
        _string(value['address'], r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+\.prefab')
    if base:
        _numbers(value['bind_groups'], range(1, 128), empty=True)
        clips = value.get('replace_clips', [])
        if not isinstance(clips, list) or len(clips) > 32:
            raise ValueError('模型合并配方的替换动画过多')
        for clip in clips:
            _string(clip, _TOKEN)
        if bool(clips) != bool(value.get('sprites')):
            raise ValueError('基础模型的精灵替换需要同时声明目标动画')
    else:
        _numbers(value['groups'], _SLOTS)
        _numbers([value['detail']], _SLOTS)
        _numbers([value['segments']], range(1, 33))
    if 'sprites' in value:
        _replacements(value['sprites'])


def _parse(raw, *, builtin=False):
    if len(raw) > MAX_RECIPE:
        raise ValueError('模型合并配方文件过大')
    try:
        data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique_pairs)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('无法读取模型合并配方') from exc
    common = ('schema', 'id', 'name', 'base', 'donors', 'verified_attack_details')
    _fields(data, common + (('source_archive', 'cab_namespace') if builtin else ('dependency',)))
    if type(data['schema']) is not int or data['schema'] != 1:
        raise ValueError('模型合并配方版本不受支持')
    _string(data['id'], r'[a-z0-9][a-z0-9_.-]{0,79}')
    _string(data['name'], r'[^\x00-\x1f\x7f]{1,100}')
    if not builtin and data['id'].startswith('builtin.'):
        raise ValueError('外部模型合并配方不能使用内置标识')
    if builtin:
        _string(data['source_archive'], r'[A-Za-z0-9_-]+\.zip')
        _string(data['cab_namespace'], r'[a-z0-9_.]+')
    else:
        _string(data['dependency'], r'(?:SD_Personality|SD_Enemy)/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.prefab')
    _asset(data['base'], base=True, builtin=builtin)
    if not isinstance(data['donors'], list) or not 1 <= len(data['donors']) <= 4:
        raise ValueError('模型合并配方需要一至四个供体模型')
    for donor in data['donors']:
        _asset(donor, builtin=builtin)
    names = [asset['member'].casefold() for asset in assets(data)]
    details = [donor['detail'] for donor in data['donors']]
    verified = data['verified_attack_details']
    _numbers(details, _SLOTS)
    _numbers(verified, _SLOTS)
    if (len(names) != len(set(names)) or not set(details) <= set(verified)
            or set(details).intersection(data['base']['bind_groups'])):
        raise ValueError('模型合并配方含冲突的模型或动作组')
    return data


@lru_cache(maxsize=1)
def builtin_recipe():
    path = Path(__file__).resolve().parents[1] / 'Assets/Migrations/roland-v1.json'
    return _parse(path.read_bytes(), builtin=True)


def _regular_info(info):
    mode = stat.S_IFMT(info.external_attr >> 16)
    if info.flag_bits & 1 or mode not in (0, stat.S_IFREG):
        raise ValueError('模型合并配方只支持未加密的普通文件')


def read_recipe(archive):
    matches = [info for info in archive.infolist() if info.filename.casefold() == MANIFEST]
    if not matches:
        return None
    if len(matches) != 1 or matches[0].file_size > MAX_RECIPE:
        raise ValueError('模型合并配方重复或文件过大')
    _regular_info(matches[0])
    return _parse(archive.read(matches[0]))


def assets(recipe):
    return [recipe['base'], *recipe['donors']]


def archive_members(archive, recipe):
    available = {}
    for info in archive.infolist():
        path = info.filename.replace('\\', '/').split('/')
        if info.is_dir() or not path[-1].casefold().endswith('.bundle'):
            continue
        if any(not part or part in ('.', '..') or ':' in part for part in path):
            raise ValueError('模型合并包含无效压缩路径')
        if 'custom_appearance' not in (part.casefold() for part in path[:-1]):
            continue
        _regular_info(info)
        name = path[-1].casefold()
        if name in available or not 0 < info.file_size <= MAX_BUNDLE:
            raise ValueError('模型合并包的模型重复或文件过大')
        available[name] = info
    wanted = [asset['member'].casefold() for asset in assets(recipe)]
    if set(available) != set(wanted) or sum(info.file_size for info in available.values()) > MAX_TOTAL:
        raise ValueError('模型合并包的模型与配方不符或超出读取上限')
    return [available[name] for name in wanted]


def verify_members(archive, recipe, members):
    for asset, info in zip(assets(recipe), members):
        digest = hashlib.sha256()
        with archive.open(info) as stream:
            for chunk in iter(lambda: stream.read(1024**2), b''):
                digest.update(chunk)
        if digest.hexdigest() != asset['sha256']:
            raise ValueError('模型合并 SHA-256 校验失败：' + asset['member'])


def validated_unpacked_size(content):
    """Bound external UnityFS reads before UnityPy expands their block data."""
    import lz4.block

    invalid = '外部合并模型须为未加密的 UnityFS 文件（未压缩或 LZ4）'
    if not content.startswith(b'UnityFS\0') or content[8:12] not in (b'\0\0\0\x07', b'\0\0\0\x08'):
        raise ValueError(invalid)
    try:
        engine_at = content.index(b'\0', 12, 80) + 1
        header_at = content.index(b'\0', engine_at, 100) + 1
        total_size, packed, plain, flags = struct.unpack_from('>QIII', content, header_at)
    except (ValueError, struct.error) as exc:
        raise ValueError(invalid) from exc
    start = (header_at + 20 + 15) & ~15
    compression = flags & 63
    if (flags & ~0x2ff or compression not in (0, 2, 3) or total_size != len(content)
            or not 0 < packed <= 4 * 1024**2 or not 20 <= plain <= 4 * 1024**2
            or start + packed > len(content)):
        raise ValueError(invalid)
    table_at = len(content) - packed if flags & 128 else start
    table = content[table_at:table_at + packed]
    try:
        if compression:
            table = lz4.block.decompress(table, uncompressed_size=plain)
    except lz4.block.LZ4BlockError as exc:
        raise ValueError(invalid) from exc
    if len(table) != plain:
        raise ValueError(invalid)
    count = struct.unpack_from('>i', table, 16)[0]
    if not 0 < count <= 32768 or 20 + count * 10 > plain:
        raise ValueError(invalid)
    expanded = stored = 0
    for size, compressed, codec in struct.iter_unpack('>IIH', memoryview(table)[20:20 + count * 10]):
        codec &= 63
        if (codec not in (0, 2, 3) or not 0 < compressed <= MAX_BUNDLE
                or not 0 < size <= MAX_BUNDLE or (codec == 0 and size != compressed)):
            raise ValueError('外部合并模型的解包块超出读取上限或格式无效')
        expanded += size
        stored += compressed
    block_at = start if flags & 128 else start + packed
    if flags & 512:
        block_at = (block_at + 15) & ~15
    limit = table_at if flags & 128 else len(content)
    if expanded > 1024**3 or block_at + stored > limit:
        raise ValueError('外部合并模型的解包数据超出读取上限')
    try:
        read_at = 20 + count * 10
        nodes = struct.unpack_from('>i', table, read_at)[0]
        read_at += 4
        names = set()
        if not 1 <= nodes <= 16:
            raise ValueError(invalid)
        for _ in range(nodes):
            offset, size, _ = struct.unpack_from('>qqI', table, read_at)
            name_at = read_at + 20
            read_at = table.index(b'\0', name_at, name_at + 256) + 1
            name = table[name_at:read_at - 1].lower()
            if (not name or name in names or b'/' in name or b'\\' in name or b':' in name
                    or offset < 0 or size < 0 or offset + size > expanded):
                raise ValueError(invalid)
            names.add(name)
    except (ValueError, struct.error) as exc:
        raise ValueError(invalid) from exc
    return expanded
