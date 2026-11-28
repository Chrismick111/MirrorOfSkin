"""Materialize Carra2 object replacements in private Unity bundle copies."""
from collections import defaultdict
from contextlib import contextmanager
from copy import copy
from io import BytesIO
import lzma
import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
from itertools import chain
from model_workspace import model_tempdir, carra_base_path
from zipfile import ZipFile

ENTRY=re.compile(r'([0-9a-f]{32})/([0-9a-f]{32})/(-?\d+)\.(\d+)',re.I)


def _script_key(file, file_id, path_id):
    if path_id and file_id == 0:
        obj = file.objects.get(path_id)
        if obj is not None and obj.class_id == 115:
            return ('local', id(file), path_id)
    if path_id and 0 < file_id <= len(file.externals):
        external = file.externals[file_id - 1]
        return external.path.casefold(), external.guid, external.type, path_id


def _game_files(unity, cache):
    from scan.resource_catalog import bundle_files, load_index, resolve_roots

    roots = resolve_roots(resource_root=cache)
    index, _ = load_index(roots['index_dir'], cache, auto_build=False)
    prefabs = {str(Path(name)) for name, item in (index or {}).get('entries', {}).items()
               if item.get('prefabs')}
    paths = sorted(bundle_files(cache), key=lambda path: str(path.relative_to(cache)) not in prefabs)
    for path in paths:
        try:
            yield from unity.load(str(path)).assets
        except (OSError, ValueError):
            continue


def _companion_files(unity, archive, groups, base_key):
    for key, members in groups.items():
        if key == base_key or len(members) != 1:
            continue
        data = archive.read(members[0])
        try:
            yield from unity.load(data).assets
        except (OSError, ValueError):
            continue


def _read_layout(node, data, target, *, complete=True):
    from UnityPy.helpers.TypeTreeHelper import read_typetree
    from UnityPy.streams import EndianBinaryReader

    return read_typetree(node, EndianBinaryReader(data, endian=target.reader.endian),
                         byte_size=len(data) if complete else None, check_read=complete, assetsfile=target)


def _mono_header(target):
    from UnityPy.files.ObjectReader import get_typetree_node
    from UnityPy.helpers.TypeTreeNode import TypeTreeNode

    def definitions():
        yield from (t.node for t in target.types if t.class_id == 114 and t.node)
        if target._m_target_platform != -2:
            yield get_typetree_node(114, target.version)

    for node in definitions():
        if not node:
            continue
        for i, field in enumerate(node.m_Children):
            if field.m_Type == 'PPtr<MonoScript>' and field.m_Name == 'm_Script':
                return TypeTreeNode(node.m_Level, node.m_Type, node.m_Name, node.m_ByteSize,
                                    node.m_Version, node.m_Children[:i + 1])
    raise ValueError('Carra2 底包没有可读取的脚本对象头定义')


_READ_ERRORS = (ValueError, RuntimeError, EOFError, struct.error, OverflowError, UnicodeError)


def _object_script(header, data, target):
    try:
        ref = _read_layout(header, data, target, complete=False)['m_Script']
        return ref['m_FileID'], ref['m_PathID']
    except _READ_ERRORS as error:
        raise ValueError('Carra2 对象缺少可读取的脚本引用') from error


def _recover_types(target, pending, donors):
    """Match every object in each missing slot before registering the selected layouts."""
    header = _mono_header(target)
    by_script = defaultdict(list)
    for index, objects in pending.items():
        refs = {_object_script(header, data, target) for _, data in objects}
        if len(refs) != 1:
            raise ValueError(f'Carra2 新增类型 {index} 缺少一致的脚本引用')
        file_id, path_id = refs.pop()
        key = _script_key(target, file_id, path_id)
        if key is None:
            raise ValueError(f'Carra2 新增类型 {index} 未引用可核对的游戏脚本')
        by_script[key].append((index, file_id))

    def schema(file):
        return (file.header.version, file.reader.endian, file.unity_version,
                file._m_target_platform, file._enable_type_tree)

    matches = {}
    rejected = {}
    for donor in donors:
        if schema(donor) != schema(target):
            continue
        for typ in donor.types:
            if (typ.class_id != 114 or not typ.node or typ.is_stripped_type or typ.type_dependencies
                    or not 0 <= typ.script_type_index < len(donor.script_types)):
                continue
            ref = donor.script_types[typ.script_type_index]
            key = _script_key(donor, ref.local_serialized_file_index, ref.local_identifier_in_file)
            if key not in by_script:
                continue
            for index, file_id in by_script[key]:
                if index in matches:
                    continue
                for pid, data in pending[index]:
                    try:
                        tree = _read_layout(typ.node, data, target)
                    except _READ_ERRORS:
                        rejected[index] = pid
                        break
                    if tree.get('m_Script') != {'m_FileID': file_id, 'm_PathID': ref.local_identifier_in_file}:
                        rejected[index] = pid
                        break
                else:
                    matches[index] = (typ, ref, file_id)
        if len(matches) == len(pending):
            break
    missing = sorted(pending.keys() - matches.keys())
    if missing:
        conflicts = [f'类型 {i} 的对象 {rejected[i]}' for i in missing if i in rejected]
        details = '；结构不匹配：' + '、'.join(conflicts) if conflicts else ''
        raise ValueError(f'Carra2 类型 {missing} 缺少匹配的脚本定义{details}')
    resolved = {}
    registered = {}
    for index, (typ, ref, file_id) in matches.items():
        key = (id(typ), file_id)
        if key in registered:
            resolved[index] = registered[key]
            continue
        script = copy(ref)
        script.local_serialized_file_index = file_id
        if script not in target.script_types:
            target.script_types.append(script)
        slot = target.script_types.index(script)
        existing = next((i for i, t in enumerate(target.types) if t is typ and t.script_type_index == slot), None)
        if existing is None:
            imported = copy(typ)
            imported.script_type_index = slot
            existing = len(target.types)
            target.types.append(imported)
        resolved[index] = registered[key] = existing
    return resolved


def materialize(z, base, changes, unity, *, cache=None, companions=()):
    from UnityPy.enums import ClassIDType
    from UnityPy.files.ObjectReader import ObjectReader
    env=unity.load(base)
    if len(env.assets)!=1:
        raise ValueError('Carra2 底包应只有一个序列化文件')
    file=env.assets[0]
    total=0
    seen=set()
    base_types=len(file.types)
    pending=defaultdict(list)
    anchors={}
    header=None
    for _,pid,idx in changes:
        obj=file.objects.get(pid)
        if obj is not None and anchors.setdefault(idx,obj.type_id)!=obj.type_id:
            raise ValueError(f'Carra2 类型 {idx} 的现有对象指向不同底包类型')

    def replace(pid, idx, data):
        obj=file.objects.get(pid)
        if obj is None:
            typ=file.types[idx]
            obj=ObjectReader(file,file.reader,pid,idx,typ,typ.class_id,ClassIDType(typ.class_id),0,len(data),None,None)
            file.objects[pid]=obj
        obj.set_raw_data(data)

    for info,pid,idx in changes:
        if pid in seen:
            raise ValueError(f'Carra2 含重复对象编号 {pid}')
        seen.add(pid)
        dec=lzma.LZMADecompressor(format=lzma.FORMAT_XZ,memlimit=512*1024**2)
        if info.file_size>128*1024**2:raise ValueError('Carra2 对象过大')
        data=dec.decompress(z.read(info),max_length=min(128*1024**2,512*1024**2-total)+1)
        total+=len(data)
        if not dec.eof or dec.unused_data or total>512*1024**2 or len(data)>128*1024**2:
            raise ValueError('Carra2 对象损坏或超出大小限制')
        slot=anchors.get(idx,idx)
        recover=slot>=base_types
        if slot==idx and not recover:
            typ=file.types[slot]
            if typ.class_id==114 and 0<=typ.script_type_index<len(file.script_types):
                if idx in anchors:
                    if header is None:
                        header=_mono_header(file)
                    script=file.script_types[typ.script_type_index]
                    if _object_script(header,data,file)!=(script.local_serialized_file_index,script.local_identifier_in_file):
                        raise ValueError(f'Carra2 类型 {idx} 的脚本与底包现有对象不一致')
                else:
                    # A new script may reuse an in-range author slot with a different layout.
                    recover=True
        if slot!=idx:
            typ=file.types[slot]
            if not typ.node:
                raise ValueError(f'Carra2 重排类型 {idx} 缺少可验证的底包定义')
            try:
                tree=_read_layout(typ.node,data,file)
            except _READ_ERRORS as error:
                raise ValueError(f'Carra2 对象 {pid} 与重排类型 {idx} 的底包定义不匹配') from error
            if typ.class_id==114:
                if not 0<=typ.script_type_index<len(file.script_types):
                    raise ValueError(f'Carra2 重排类型 {idx} 缺少可验证的脚本引用')
                script=file.script_types[typ.script_type_index]
                if tree.get('m_Script')!={'m_FileID':script.local_serialized_file_index,'m_PathID':script.local_identifier_in_file}:
                    raise ValueError(f'Carra2 重排类型 {idx} 的脚本与底包不一致')
        if recover:
            pending[idx].append((pid,data))
        else:
            replace(pid,slot,data)
    if pending:
        donors = _game_files(unity, cache) if cache is not None else ()
        resolved = _recover_types(file, pending, chain((file,), companions, donors))
        for index, objects in pending.items():
            for pid, data in objects:
                replace(pid, resolved[index], data)
    return env.file.save(packer='lz4')


@contextmanager
def expanded(path,root,unity=None,*,source_members=None):
    from skin_assets import _members
    with ZipFile(path) as outer:
        direct=path.suffix.lower()=='.carra2'
        nested=[i for i in outer.infolist() if i.filename.lower().endswith('.carra2')]
        if not direct and not nested:
            yield path
            return
        if unity is None:
            import resource_tools
            unity=resource_tools.unity()
        if not unity.config.FALLBACK_UNITY_VERSION:unity.config.FALLBACK_UNITY_VERSION='6000.3.0f1'
        from scan.resource_catalog import resolve_roots
        cache=resolve_roots(base=root)['resource_root']
        sources=defaultdict(list)
        for info,p in _members(outer):
            if p.name=='__data' and len(p.parts)>=3:sources[tuple(x.lower() for x in p.parts[-3:-1])].append(info)
        consumed=set()
        with model_tempdir() as tmp:
            target=Path(tmp)/(path.stem+'.zip')
            saved_bases=[]
            with ZipFile(target,'w') as result:
                emitted=set()
                for item in ([None] if direct else nested):
                    if item and item.file_size>512*1024**2:raise ValueError('Carra2 文件过大')
                    from skin_import import digest
                    payload=outer.read(item) if item else None
                    revision=hashlib.sha256(payload).hexdigest() if item else digest(path)
                    with ZipFile(BytesIO(payload) if item else path) as patch:
                        groups=defaultdict(list)
                        for meta in patch.infolist():
                            if meta.is_dir():continue
                            match=ENTRY.fullmatch(meta.filename)
                            if not match:raise ValueError('无法识别 Carra2 对象路径：'+meta.filename)
                            a,b,pid,idx=match.groups()
                            groups[a.lower(),b.lower()].append((meta,int(pid),int(idx)))
                        if not groups:raise ValueError('Carra2 没有包含模型对象')
                        for (a,b),changes in groups.items():
                            bundled=sources[a,b]
                            saved,legacy=carra_base_path(root,revision,a,b)
                            if len(bundled)>1:raise ValueError('Carra2 包含多个相同目标的底包')
                            if bundled:
                                base=outer.read(bundled[0]);consumed.add(bundled[0].filename)
                                staged=Path(tmp)/f'base-{len(saved_bases)}'
                                staged.write_bytes(base)
                                saved_bases.append((saved,staged,hashlib.sha256(base).hexdigest()))
                            else:
                                candidates=[saved,legacy]
                                if cache is not None:
                                    candidates.extend((cache/a/b/'__original',cache/a/b/'__data'))
                                source=next((p for p in candidates if p.is_file()),None)
                                if source is None:raise ValueError(f'Carra2 缺少匹配的游戏底包 {a}/{b}。可以选择同时带有 bundle 和 Carra2 的完整模组压缩包。')
                                base=source.read_bytes()
                            label=PurePosixPath(item.filename).stem if item else path.stem
                            dest=f'{label}/Installation/{a}/{b}/__data'
                            if dest in emitted:raise ValueError('多个 Carra2 条目冲突：'+dest)
                            emitted.add(dest)
                            if source_members is not None and item is not None:
                                source_members[dest.casefold()] = item.filename
                            companions=_companion_files(unity,outer,sources,(a,b))
                            result.writestr(dest,materialize(patch,base,changes,unity,cache=cache,companions=companions))
                if not direct:
                    for info in outer.infolist():
                        if info in nested or info.filename in consumed or info.is_dir():continue
                        with outer.open(info) as src,result.open(info.filename,'w',force_zip64=True) as dst:
                            shutil.copyfileobj(src,dst,1024*1024)
            yield target
            from skin_import import write_bundle
            for dest,src,checksum in saved_bases:
                write_bundle(dest,src,checksum)
