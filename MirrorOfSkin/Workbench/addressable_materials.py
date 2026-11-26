"""Resolve and embed verified game Addressables material dependencies."""

from collections import defaultdict
from copy import copy
from hashlib import sha256
from pathlib import PurePosixPath
import re
import struct


_ARCHIVE = re.compile(r'archive:/CAB-[0-9a-f]{32}/(CAB-[0-9a-f]{32})', re.I)
_RESOURCE_TYPES = {'Material', 'Shader', 'Texture2D'}


def _cab(path):
    match = _ARCHIVE.fullmatch(path)
    return match[1].casefold() if match else None


def _pointers(tree):
    from skin_assets import _dicts
    return ((item['m_FileID'], item['m_PathID']) for item in _dicts(tree)
            if 'm_FileID' in item and item.get('m_PathID'))


def _reachable(file, root):
    pending, seen = [root], set()
    while pending:
        pid = pending.pop()
        if pid in seen or pid not in file.objects:
            continue
        seen.add(pid)
        obj = file.objects[pid]
        tree = obj.read_typetree()
        yield obj, tree
        pending.extend(p for f, p in _pointers(tree) if not f)


def _materials(tree):
    return [(item['m_FileID'], item['m_PathID']) for item in tree.get('m_Materials', ())]


def verified_replacements(witnesses):
    """Require independent stock prefabs to agree on one current CAB."""
    options = defaultdict(list)
    for (file_id, cab), rows in witnesses.items():
        options[file_id].append((cab, {address for address, _ in rows}))
    return {file_id: matches[0][0] for file_id, matches in options.items()
            if len(matches) == 1 and len(matches[0][1]) >= 2}


def material_closure(file, roots):
    for pid in roots:
        obj = file.objects.get(pid)
        if obj is None or obj.type.name != 'Material':
            raise ValueError(f'找不到已验证的游戏材质 {pid}')
    pending, seen = list(roots), set()
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        obj = file.objects.get(pid)
        if obj is None or obj.type.name not in _RESOURCE_TYPES:
            raise ValueError(f'游戏材质引用了无法验证的资源 {pid}')
        seen.add(pid)
        for file_id, child in _pointers(obj.read_typetree()):
            if file_id:
                raise ValueError(f'游戏材质引用了外部资源 {child}')
            pending.append(child)
    return seen


def _directory_names(path):
    """Read only the UnityFS metadata instead of inflating every game bundle."""
    from UnityPy.helpers.CompressionHelper import decompress_lzma
    import lz4.block

    with path.open('rb') as stream:
        header = stream.read(256)
        if not header.startswith(b'UnityFS\0'):
            return []
        version, = struct.unpack_from('>I', header, 8)
        pos = header.index(b'\0', header.index(b'\0', 12) + 1) + 1
        length, packed, size, flags = struct.unpack_from('>QIII', header, pos)
        pos += 20
        if version >= 7:
            pos = (pos + 15) & ~15
        if not 0 < packed <= size + 65536 or size > 32 * 1024**2:
            return []
        stream.seek(length - packed if flags & 128 else pos)
        data = stream.read(packed)
    codec = flags & 63
    if codec in (2, 3):
        data = lz4.block.decompress(data, uncompressed_size=size)
    elif codec == 1:
        data = decompress_lzma(data)
    elif codec:
        return []
    if len(data) != size:
        return []
    blocks, = struct.unpack_from('>I', data, 16)
    pos = 20 + blocks * 10
    count, = struct.unpack_from('>I', data, pos)
    pos += 4
    names = []
    for _ in range(count):
        pos += 20
        end = data.index(b'\0', pos)
        names.append(data[pos:end].decode('utf-8').casefold())
        pos = end + 1
    return names


def _cab_files(paths, names):
    matches = defaultdict(list)
    for path in paths:
        try:
            found = names.intersection(_directory_names(path))
        except (OSError, struct.error, ValueError, RuntimeError):
            continue
        for name in found:
            matches[name].append(path)
    return {name: paths[0] for name, paths in matches.items() if len(paths) == 1}


def _stock_witnesses(source_env, root, index, requested, unity):
    from skin_assets import _roots

    source, = source_env.assets
    sources = defaultdict(list)
    for rel, item in index['entries'].items():
        path = (root / rel).resolve()
        if path.is_relative_to(root):
            for address in item.get('prefabs', {}).values():
                sources[address.replace('\\', '/').casefold()].append(path)
    witnesses = defaultdict(set)
    contradicted = set()
    for address, pid, _ in _roots(source_env):
        matches = sources[address.casefold()]
        if len(matches) != 1 or not matches[0].is_file():
            continue
        current_env = unity.load(matches[0].read_bytes())
        if len(current_env.assets) != 1 or not any(a.casefold() == address.casefold() and p == pid
                                                  for a, p, _ in _roots(current_env)):
            continue
        current, = current_env.assets
        current_objects = {obj.path_id: (obj, tree) for obj, tree in _reachable(current, pid)
                           if 'm_Materials' in tree}
        for old, old_tree in _reachable(source, pid):
            materials = _materials(old_tree)
            if not materials or old.path_id not in current_objects:
                continue
            new, new_tree = current_objects[old.path_id]
            if old.type.name != new.type.name or old.peek_name() != new.peek_name():
                continue
            current_slots = _materials(new_tree)
            if len(materials) != len(current_slots):
                contradicted.update(f for f, p in materials if p in requested.get(f, ()))
                continue
            for (f, p), (nf, np) in zip(materials, current_slots):
                if f not in requested or not p:
                    continue
                cab = _cab(current.externals[nf - 1].path) if 0 < nf <= len(current.externals) else None
                if cab and p == np:
                    witnesses[f, cab].add((address.casefold(), p))
                elif p in requested[f]:
                    # A current Material with the old ID can still be unrelated.
                    # Direct evidence about the requested slot overrides inference.
                    contradicted.add(f)
    return {f: cab for f, cab in verified_replacements(witnesses).items() if f not in contradicted}


class MaterialSegment:
    def __init__(self, env, source, roots):
        self.env = env
        self.source = source
        self.ids = material_closure(source, roots)

    def revision(self, digest):
        for pid in sorted(self.ids):
            obj = self.source.objects[pid]
            digest.update(str(pid).encode('ascii') + b'\0')
            digest.update(obj.serialized_type.old_type_hash)
            digest.update(sha256(obj.get_raw_data()).digest())
        for name, member in self.env.file.files.items():
            if name.casefold().endswith(('.ress', '.resource')):
                digest.update(sha256(member.bytes).digest())

    def pack(self, model, model_cab, mount):
        from skin_assets import _dicts
        from UnityPy.streams import EndianBinaryReader

        source = self.source
        segment = copy(source)
        segment.name = mount
        segment.parent = model.parent
        segment.flags = model.flags
        segment.objects, segment.types = {}, []
        segment.externals, segment.script_types, segment.ref_types = [], [], []
        packed = bytearray()
        offsets = {}
        for pid in sorted(self.ids):
            obj = source.objects[pid]
            serialized = obj.serialized_type
            if serialized.script_type_index != -1 or serialized.type_dependencies:
                raise ValueError('游戏材质资源包含无法验证的脚本类型')
            if serialized not in segment.types:
                segment.types.append(serialized)
            tree = obj.read_typetree()
            for item in _dicts(tree):
                if not (item.get('path') and item.get('size') and 'offset' in item):
                    continue
                name = PurePosixPath(item['path']).name
                offset, size = item['offset'], item['size']
                key = name, offset, size
                if key not in offsets:
                    member = self.env.file.files.get(name)
                    if member is None or offset < 0 or size < 0 or offset + size > member.Length:
                        raise ValueError('游戏材质纹理流超出可验证范围：' + name)
                    packed.extend(b'\0' * (-len(packed) % 16))
                    offsets[key] = len(packed)
                    packed.extend(memoryview(member.bytes)[offset:offset + size])
                item.update(path=f'archive:/{model_cab}/{mount}.resS', offset=offsets[key])
            clone = copy(obj)
            clone.assets_file = segment
            clone.type_id = segment.types.index(serialized)
            clone.save_typetree(tree)
            segment.objects[pid] = clone
        result = {mount: segment}
        if packed:
            stream = EndianBinaryReader(bytes(packed))
            stream.flags = 0
            result[mount + '.resS'] = stream
        return result


def resolve_materials(env, root_pid, unity, builtin_ids, *, progress=None):
    from import_progress import progress_range
    from scan.resource_catalog import build_index, bundle_files, load_index, resolve_roots

    file, = env.assets
    wanted = defaultdict(set)
    for _, tree in _reachable(file, root_pid):
        for f, p in _materials(tree):
            if p and 0 < f <= len(file.externals) and f not in builtin_ids and _cab(file.externals[f - 1].path):
                wanted[f].add(p)
    if not wanted:
        return {}

    report = progress_range(progress)
    report(0, '正在查找外观使用的游戏材质')
    roots = resolve_roots()
    root, index_dir = roots['resource_root'], roots['index_dir']
    if root is None:
        return {}
    paths = bundle_files(root)
    if not paths:
        paths = sorted(root.rglob('*.bundle'))
    direct = {f: _cab(file.externals[f - 1].path) for f in wanted}
    matches = _cab_files(paths, set(direct.values()))
    unresolved = {f for f, cab in direct.items() if cab not in matches}
    if unresolved:
        index, _ = load_index(index_dir, root, auto_build=False)
        if index is None:
            last = -1

            def scanned(done, total, _changed):
                nonlocal last
                percent = 5 + 75 * done // max(1, total)
                if last != percent or done == total:
                    report(percent, f'正在索引游戏资源（{done}/{total}）')
                    last = percent

            index = build_index(root, index_dir, unity_py=unity, progress=scanned)
        report(83, '正在校对游戏预制体的材质引用')
        alternates = _stock_witnesses(env, root, index, {f: wanted[f] for f in unresolved}, unity)
        if alternates:
            matches.update(_cab_files(paths, set(alternates.values())))
        direct.update(alternates)

    report(94, '正在保留游戏材质、着色器和纹理')
    result = {}
    for f, cab in direct.items():
        if cab not in matches:
            continue
        donor = unity.load(matches[cab].read_bytes())
        candidates = [asset for asset in donor.assets if asset.name.casefold() == cab
                      and asset._m_target_platform == file._m_target_platform]
        if len(candidates) == 1:
            result[f] = MaterialSegment(donor, candidates[0], wanted[f])
    return result
