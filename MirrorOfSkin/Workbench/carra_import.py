"""Materialize Carra2 object replacements in private Unity bundle copies."""
from collections import defaultdict
from contextlib import contextmanager
from io import BytesIO
import lzma
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from zipfile import ZipFile

ENTRY=re.compile(r'([0-9a-f]{32})/([0-9a-f]{32})/(-?\d+)\.(\d+)',re.I)


def materialize(z, base, changes, unity):
    from UnityPy.enums import ClassIDType
    from UnityPy.files.ObjectReader import ObjectReader
    env=unity.load(base)
    if len(env.assets)!=1:
        raise ValueError('Carra2 底包应只有一个序列化文件')
    file=env.assets[0]
    total=0
    seen=set()
    for info,pid,idx in changes:
        if pid in seen or idx>=len(file.types):
            raise ValueError('Carra2 含重复对象或无效类型索引')
        seen.add(pid)
        obj=file.objects.get(pid)
        if obj and obj.type_id!=idx:
            raise ValueError('Carra2 与底包的对象类型不一致')
        dec=lzma.LZMADecompressor(format=lzma.FORMAT_XZ,memlimit=512*1024**2)
        if info.file_size>128*1024**2:raise ValueError('Carra2 对象过大')
        data=dec.decompress(z.read(info),max_length=min(128*1024**2,512*1024**2-total)+1)
        total+=len(data)
        if not dec.eof or dec.unused_data or total>512*1024**2 or len(data)>128*1024**2:
            raise ValueError('Carra2 对象损坏或超出大小限制')
        if obj is None:
            typ=file.types[idx]
            obj=ObjectReader(file,file.reader,pid,idx,typ,typ.class_id,ClassIDType(typ.class_id),0,len(data),None,None)
            file.objects[pid]=obj
        obj.set_raw_data(data)
    return env.file.save(packer='lz4')


@contextmanager
def expanded(path,root,unity=None):
    from skin_assets import _members,_low_dir
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
        cache=Path(os.environ.get('LIMBUS_RESOURCE_ROOT') or _low_dir()/'Unity/ProjectMoon_LimbusCompany')
        sources=defaultdict(list)
        for info,p in _members(outer):
            if p.name=='__data' and len(p.parts)>=3:sources[tuple(x.lower() for x in p.parts[-3:-1])].append(info)
        consumed=set()
        with tempfile.TemporaryDirectory() as tmp:
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
                            saved=root/'Assets/CarraBases'/revision/a/b/'__data'
                            if len(bundled)>1:raise ValueError('Carra2 包含多个相同目标的底包')
                            if bundled:
                                base=outer.read(bundled[0]);consumed.add(bundled[0].filename)
                                staged=Path(tmp)/f'base-{len(saved_bases)}'
                                staged.write_bytes(base)
                                saved_bases.append((saved,staged,hashlib.sha256(base).hexdigest()))
                            else:
                                folder=cache/a/b
                                source=next((p for p in (saved,folder/'__original',folder/'__data') if p.is_file()),None)
                                if source is None:raise ValueError(f'Carra2 缺少匹配的游戏底包 {a}/{b}。可以选择同时带有 bundle 和 Carra2 的完整模组压缩包。')
                                base=source.read_bytes()
                            label=PurePosixPath(item.filename).stem if item else path.stem
                            dest=f'{label}/Installation/{a}/{b}/__data'
                            if dest in emitted:raise ValueError('多个 Carra2 条目冲突：'+dest)
                            emitted.add(dest)
                            result.writestr(dest,materialize(patch,base,changes,unity))
                if not direct:
                    for info in outer.infolist():
                        if info in nested or info.filename in consumed or info.is_dir():continue
                        with outer.open(info) as src,result.open(info.filename,'w',force_zip64=True) as dst:
                            shutil.copyfileobj(src,dst,1024*1024)
            yield target
            from skin_import import write_bundle
            for dest,src,checksum in saved_bases:
                write_bundle(dest,src,checksum)
