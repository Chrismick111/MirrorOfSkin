"""Convert a published battle appearance into its own local Unity bundle."""
import base64
import hashlib
import json
import os
import re
import struct
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

ROLAND_MEMBERS = {
    'broland.bundle': '26263b7a6fbb11a604e7d1ef3741e077fa8e68b8693cfda8ce17468c0dca3f2e',
    'brolandgun.bundle': 'b85a52a52f64b633f01969b13767162bb3cded9d77bd4287c573c55b77f99d7b',
    'brolandultrasword.bundle': '473cff26cbf4c4a0b3c069d54cfce792642dde4b94e68c9360e42f0d460fef33',
}


def _dicts(value):
    if isinstance(value,dict):
        yield value
        for v in value.values():
            if isinstance(v,(dict,list,tuple)):yield from _dicts(v)
    elif isinstance(value,(list,tuple)):
        for v in value:
            if isinstance(v,(dict,list,tuple)):yield from _dicts(v)


def _bundle_directory(path):
    """Read only UnityFS's small directory table, leaving texture data on disk."""
    from UnityPy.helpers.CompressionHelper import decompress_lz4, decompress_lzma
    with path.open('rb') as f:
        header=f.read(256)
        if not header.startswith(b'UnityFS\0'):return []
        version=struct.unpack_from('>I',header,8)[0]
        pos=header.index(b'\0',12)+1
        pos=header.index(b'\0',pos)+1
        _,size,plain,flags=struct.unpack_from('>QIII',header,pos)
        if not 0<size<=16*1024*1024 or not 0<plain<=32*1024*1024:return []
        pos+=20
        if flags&128:f.seek(-size,2)
        else:f.seek((pos+15)&~15 if version>=7 else pos)
        data=f.read(size)
    if flags&63 in (2,3):data=decompress_lz4(data,plain)
    elif flags&63==1:data=decompress_lzma(data)
    elif flags&63:return []
    # Directory entries contain ASCII CAB filenames. Full names prevent
    # another installed version of a personality from satisfying a request.
    return [s.decode('ascii') for s in re.findall(rb'(CAB-[0-9a-fA-F]{32}\.resS)\x00',data)]


def _low_dir():
    return Path(os.environ.get('USERPROFILE',str(Path.home())))/'AppData/LocalLow'


class _Streams:
    def __init__(self,unity):
        self.unity=unity
        self.paths=None
        self.bytes={}

    def get(self,env,name):
        if name in env.file.files:return env.file.files[name].bytes
        if not re.fullmatch(r'CAB-[a-fA-F0-9]{32}\.resS',name):
            raise ValueError('无法定位 Unity 资源流 '+name)
        if self.paths is None:
            self.paths={}
            self.cache_root=Path(os.environ.get('LIMBUS_RESOURCE_ROOT') or (_low_dir()/'Unity/ProjectMoon_LimbusCompany'))
            cache=self.cache_root
            if cache.is_dir():
                for file in sorted(cache.glob('*/*/__data')):
                    try:
                        for stream in _bundle_directory(file):self.paths[stream]=file
                    except (OSError,ValueError,IndexError,struct.error):continue
        if name not in self.paths:
            raise ValueError(f'外观需要纹理 {name}。在 {self.cache_root} 未找到对应数据包。请下载游戏资源，或用 LIMBUS_RESOURCE_ROOT 指定已下载的 Unity 缓存目录。')
        if name not in self.bytes:
            other=self.unity.load(str(self.paths[name]))
            self.bytes[name]=other.file.files[name].bytes
        return self.bytes[name]


def _catalog_keys():
    catalog=Path(os.environ.get('LIMBUS_ADDRESSABLE_CATALOG_DIR') or (_low_dir()/'ProjectMoon/LimbusCompany/com.unity.addressables'))
    rx=rb'SD_(?:Enemy|Personality)/[A-Za-z0-9_/-]+\.prefab'
    keys=set()
    for p in sorted(catalog.glob('catalog*.json')):
        try:
            data=base64.b64decode(json.loads(p.read_bytes())['m_KeyDataString'])
            keys.update(k.decode('ascii') for k in re.findall(rx,data))
        except (OSError,ValueError,KeyError):continue
    # Binary catalogs may store the folder and the prefab basename separately.
    import mos_data
    roster=mos_data.path(Path(__file__).resolve().parents[1], 'Assets/runtime/all_sinners_pools.json')
    known=[]
    if roster.is_file():
        known=[r.get('asset_key','') for group in json.loads(roster.read_bytes()).values() for r in group['entries']]
    for p in sorted(catalog.glob('catalog*.bin')):
        raw=p.read_bytes()
        keys.update(k.decode('ascii') for k in re.findall(rx,raw))
        names=set(re.findall(rb'[A-Za-z0-9_-]+\.prefab',raw))
        keys.update(k for k in known if re.fullmatch(rx.decode(),k) and k.rsplit('/',1)[-1].encode() in names)
    return keys


def _dependency(layout,address,keys):
    for base in (layout+'.prefab',PurePosixPath(address).name):
        matches=sorted(k for k in keys if k.rsplit('/',1)[-1].lower()==base.lower())
        if len(matches)==1:return matches[0]
    raise ValueError('当前游戏资源目录中找不到可预载此外观依赖的角色 '+layout+'；请检查游戏资源目录或 LIMBUS_ADDRESSABLE_CATALOG_DIR。')


def _roots(env):
    out=[]
    for a in env.assets:
        for idx in a.objects.values():
            if idx.type.name!='AssetBundle':continue
            for address,item in idx.read_typetree()['m_Container']:
                r=item['asset']
                if r['m_FileID'] or not address.lower().endswith('.prefab'):continue
                root=a.objects.get(r['m_PathID'])
                if root is None or root.type.name!='GameObject':continue
                for c in root.read_typetree()['m_Component']:
                    p=c['component']
                    o=a.objects.get(p['m_PathID']) if not p['m_FileID'] else None
                    if o and o.type.name=='MonoBehaviour' and 'motionList' in o.read_typetree():
                        out.append((address,root.path_id,idx.path_id))
                        break
    return list(dict.fromkeys(out))


def _convert(env,revision,look,address,pid,index,streams):
    from UnityPy.streams import EndianBinaryReader
    if len(env.assets)!=1:
        raise ValueError('暂不支持把多个序列化文件中的角色合并为单个外观')
    file=env.assets[0];objects=file.objects
    old=objects[pid].read_typetree();layout=old['m_Name']
    old['m_Name']=look
    # Include the source-byte identity in archive names: a revised skin can
    # coexist with a currently loaded copy of the earlier version.
    cab='CAB-'+hashlib.sha256((look+revision).encode()).hexdigest()[:32]
    packed=bytearray()
    stream_offsets={}
    todo=[pid];seen=set();prefetch=set();cache={}
    while todo:
        i=todo.pop()
        if i in seen:continue
        seen.add(i)
        obj=objects[i];tree=old if i==pid else obj.read_typetree()
        dirty=i==pid
        # Some replacements contain a voice clip whose playable asset was
        # already missing in the distributed mod. Drop this orphan clip only.
        if (obj.type.name=='MonoBehaviour' and 'fmod' in tree.get('m_Name','').lower()
                and 'voice' in tree.get('m_Name','').lower() and 'm_Clips' in tree):
            clips=tree['m_Clips']
            tree['m_Clips']=[c for c in clips if c['m_Asset']['m_FileID'] or c['m_Asset']['m_PathID'] in objects]
            dirty|=len(tree['m_Clips'])!=len(clips)
        for d in _dicts(tree):
            if 'm_FileID' in d and d.get('m_PathID'):
                f,p=d['m_FileID'],d['m_PathID']
                if f<0 or f>len(file.externals):raise ValueError('未解析的外部资源 '+str((f,p)))
                if f:prefetch.add((f,p))
                elif p not in objects:raise ValueError(f'{layout} 存在缺失的 {obj.type.name} 资源 {p}')
                elif p not in seen:todo.append(p)
            if d.get('path') and d.get('size') and 'offset' in d:
                path_key,offset_key,size_key='path','offset','size'
            elif d.get('m_Source') and d.get('m_Size') and 'm_Offset' in d:
                path_key,offset_key,size_key='m_Source','m_Offset','m_Size'
            else:continue
            source=PurePosixPath(d[path_key]).name
            off,size=d[offset_key],d[size_key]
            key=(source,off,size)
            if key not in stream_offsets:
                if source not in cache:cache[source]=streams.get(env,source)
                data=cache[source]
                if off<0 or size<0 or off+size>len(data):raise ValueError('外观纹理超出数据范围 '+source)
                packed.extend(b'\0'*(-len(packed)%16))
                stream_offsets[key]=len(packed)
                packed.extend(memoryview(data)[off:off+size])
            d[path_key]=f'archive:/{cab}/{cab}.resS'
            d[offset_key]=stream_offsets[key]
            dirty=True
        if dirty:obj.save_typetree(tree)
    index_obj=objects[index];meta=index_obj.read_typetree()
    selected=[(k,v) for k,v in meta['m_Container'] if k==address and v['asset']=={'m_FileID':0,'m_PathID':pid}]
    assert len(selected)==1
    preload=prefetch|{(0,p) for p in seen}
    ordered=dict.fromkeys((p['m_FileID'],p['m_PathID']) for p in meta['m_PreloadTable']
                          if (p['m_FileID'],p['m_PathID']) in preload)
    ordered.update(dict.fromkeys(sorted(preload-ordered.keys())))
    selected[0][1].update(preloadIndex=0,preloadSize=len(ordered))
    meta['m_Name']=meta['m_AssetBundleName']='workbench_'+cab[4:].lower()+'.bundle'
    meta['m_Container']=selected
    meta['m_PreloadTable']=[{'m_FileID':f,'m_PathID':p} for f,p in ordered]
    index_obj.save_typetree(meta)
    file.objects={p:o for p,o in objects.items() if p in seen or p==index}
    file.name=cab
    members={cab:file}
    if packed:
        reader=EndianBinaryReader(bytes(packed));reader.flags=0
        members[cab+'.resS']=reader
    env.file.files=members
    return env.file.save(packer='lz4'),layout


def _members(z):
    candidates=[]
    for info in z.infolist():
        path=PurePosixPath(info.filename.replace('\\','/'))
        parts=[s.lower() for s in path.parts]
        hashed=len(parts)>=3 and all(re.fullmatch('[0-9a-f]{32}',s) for s in parts[-3:-1])
        cache=path.name=='__data' and ('installation' in parts or hashed) and not any(
            s.startswith(('uninstall','backup','original','卸载','备份','还原')) for s in parts)
        custom=path.suffix.lower()=='.bundle' and 'custom_appearance' in parts
        if cache or custom:candidates.append((info,path))
    return candidates


def build_assets(archive,work,unity,*,name=None):
    """Yield validated local skin records. Never run ZIP programs or edit the game cache."""
    from skin_motions import analyze_motion
    from imported_catalog import display_name
    archive,work=Path(archive),Path(work)
    if not unity.config.FALLBACK_UNITY_VERSION:
        unity.config.FALLBACK_UNITY_VERSION='6000.3.0f1'
    with ZipFile(archive) as z:
        members=_members(z)
        if not members:raise ValueError('未找到战斗外观或 FMOD 语音库')
        basenames={p.name.lower() for _,p in members}
        if len(members)==3 and basenames==ROLAND_MEMBERS.keys() and all(
                hashlib.sha256(z.read(info)).hexdigest()==ROLAND_MEMBERS[p.name.lower()] for info,p in members):
            yield {'builtin':'roland'}
            return
        keys=_catalog_keys()
        streams=_Streams(unity)
        produced=set()
        for info,path in members:
            body=z.read(info)
            revision=hashlib.sha256(body).hexdigest()
            env=unity.load(body)
            published=_roots(env)
            # Cache replacements publish their actual mod at a stock address.
            # custom_appearance bundles can also include cached stock prefabs.
            # Prefer explicit custom prefab names in that mixed case.
            if 'custom_appearance' in [s.lower() for s in path.parts]:
                stock_files={k.rsplit('/',1)[-1].lower() for k in keys}
                custom=[p for p in published if PurePosixPath(p[0]).name.lower() not in stock_files]
                if custom:published=custom
            for n,(address,pid,index) in enumerate(published):
                if n:env=unity.load(body)
                layout=env.assets[0].objects[pid].peek_name()
                dep=_dependency(layout,address,keys)
                group=next((s for s in path.parts if s.lower() not in ('assets','custom_appearance','installation')),archive.stem)
                if group==path.name:group=archive.stem
                label=name or display_name(group,archive.stem)
                identity='/'.join((group.casefold(),path.name.lower(),address.lower()))
                look='WBImp_'+hashlib.sha256(identity.encode('utf8')).hexdigest()[:24]
                if look in produced:raise ValueError('外观包包含重复的角色标识 '+address)
                produced.add(look)
                if len(published)>1 or len(members)>1:label+=' · '+PurePosixPath(address).stem
                encoded,layout=_convert(env,revision,look,address,pid,index,streams)
                work.mkdir(parents=True,exist_ok=True)
                dest=work/(look+'.bundle')
                dest.write_bytes(encoded)
                parsed=unity.load(encoded)
                root=parsed.assets[0].objects[pid]
                assert root.peek_name()==look and _roots(parsed)==[(address,pid,index)]
                asset_key='Imported/'+look+'.prefab'
                entry,timing,actions=analyze_motion(parsed,root,look,asset_key,label)
                yield dict(look=look,name=label,asset=address,layout=layout,dependency=dep,
                           bundle=dest,entry=entry,timing=timing,actions=actions)
        if not produced:raise ValueError('未找到可独立克隆的已发布战斗角色')
