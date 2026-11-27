"""Convert a published battle appearance into its own local Unity bundle."""
import base64
import hashlib
import json
import os
import re
import struct
from collections import Counter
from functools import lru_cache
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from bundle_migration import archive_members, assets, builtin_recipe, read_recipe, verify_members
from custom_asset_manifest import UNITY_BUNDLE_MAGIC, bundle_directory, read_bindings, resolve_prefabs


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
    rx=rb'SD_(?:Enemy|Personality|Abnormality)/[A-Za-z0-9_/-]+\.prefab'
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


def _dependency(layout,address,keys,*,required=True):
    ambiguous = False
    for base in (layout+'.prefab',PurePosixPath(address).name):
        matches=sorted(k for k in keys if k.rsplit('/',1)[-1].lower()==base.lower())
        if len(matches)==1:return matches[0]
        ambiguous |= len(matches) > 1
    if required or ambiguous:
        raise ValueError('当前游戏资源目录中找不到可预载此外观依赖的角色 '+layout+'；请检查游戏资源目录或 LIMBUS_ADDRESSABLE_CATALOG_DIR。')


def _independent_trigger(character_id, keys):
    pattern = rf'SD_Personality/1{character_id:02}01_[A-Za-z0-9]+_BaseAppearance\.prefab'
    matches = [key for key in keys if re.fullmatch(pattern, key, re.I)]
    if len(matches) != 1:
        raise ValueError('未能在游戏资源目录中确认独立外观声明的基础人格加载项')
    return matches[0]


def _loader_dependency(bindings, layout, address, keys, *, required=True):
    known = {key.casefold(): key for key in keys}
    matches = set()
    for binding in bindings:
        resource = binding.resource_id.casefold().removeprefix(binding.label.casefold() + '/')
        key = binding.label.casefold() + '/' + resource.removesuffix('.prefab') + '.prefab'
        if key in known:
            matches.add(known[key])
    if len(matches) == 1:
        return next(iter(matches))
    if len(matches) > 1 and not required:
        raise ValueError('CustomAssetLoader 为同一模型指定了多个游戏预载项')
    return _dependency(layout, address, keys, required=required)


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


def _convert(env,revision,look,address,pid,index,streams,*,output_address=None,standalone=None):
    from UnityPy.streams import EndianBinaryReader
    if len(env.assets)!=1:
        raise ValueError('暂不支持把多个序列化文件中的角色合并为单个外观')
    file=env.assets[0];objects=file.objects
    old=objects[pid].read_typetree();layout=old['m_Name']
    old['m_Name']=look
    # Include the source-byte identity in archive names: a revised skin can
    # coexist with a currently loaded copy of the earlier version.
    if standalone is not None:
        standalone.prepare_materials(env, pid)
        revision = standalone.revision(revision)
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
        linked_shader = None
        if standalone is not None and i in standalone.shaders:
            linked_shader = standalone.shader_pointer(i, tree['m_Shader'])
            tree['m_Shader'] = linked_shader
            dirty = True
        if standalone is not None and i in standalone.orphan_voice_tracks:
            missing = standalone.orphan_voice_tracks[i]
            tree['m_Tracks'] = [ref for ref in tree['m_Tracks']
                                if ref['m_FileID'] or ref['m_PathID'] not in missing]
            dirty = True
        # Some replacements contain a voice clip whose playable asset was
        # already missing in the distributed mod. Drop this orphan clip only.
        if (obj.type.name=='MonoBehaviour' and 'fmod' in tree.get('m_Name','').lower()
                and 'voice' in tree.get('m_Name','').lower() and 'm_Clips' in tree):
            clips=tree['m_Clips']
            tree['m_Clips']=[c for c in clips if c['m_Asset']['m_FileID'] or c['m_Asset']['m_PathID'] in objects]
            dirty|=len(tree['m_Clips'])!=len(clips)
        material_slots = {id(item) for item in tree.get('m_Materials', ())} if standalone is not None else set()
        for d in _dicts(tree):
            if 'm_FileID' in d and d.get('m_PathID'):
                f,p=d['m_FileID'],d['m_PathID']
                if d is linked_shader:
                    prefetch.add((f,p))
                    continue
                if f<0 or f>len(file.externals):raise ValueError('未解析的外部资源 '+str((f,p)))
                if standalone is not None and f:
                    mapped = standalone.file_ids.get(f)
                    if mapped is None:
                        reference = standalone.material_pointer(f, p) if id(d) in material_slots else None
                        if reference is None:
                            raise ValueError(f'{layout} 的 {obj.type.name} 需要外部游戏资源，未找到可验证的版本：'
                                             f'{file.externals[f-1].path} ({p})')
                        d['m_FileID'], d['m_PathID'] = reference
                        prefetch.add(reference)
                        dirty = True
                        continue
                    d['m_FileID'] = mapped
                    dirty |= mapped != f
                    f = mapped
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
    if output_address is not None:
        selected[0] = (output_address, selected[0][1])
    preload=prefetch|{(0,p) for p in seen}
    original_preload = [(p['m_FileID'],p['m_PathID']) for p in meta['m_PreloadTable']]
    resource_files = {}
    if standalone is not None:
        preload.update(standalone.material_preloads())
        original_preload = [
            standalone.preload_refs.get((f,p), (standalone.file_ids.get(f, -1) if f else 0,p))
            for f,p in original_preload
        ]
        resource_files = standalone.resource_files(file, cab)
    ordered=dict.fromkeys(p for p in original_preload if p in preload)
    ordered.update(dict.fromkeys(sorted(preload-ordered.keys())))
    selected[0][1].update(preloadIndex=0,preloadSize=len(ordered))
    if standalone is not None:
        for script in file.script_types:
            f = script.local_serialized_file_index
            if f:
                if f not in standalone.file_ids:
                    raise ValueError(f'{layout} 包含无法验证的外部脚本类型')
                script.local_serialized_file_index = standalone.file_ids[f]
        file.externals = standalone.externals
        meta['m_Dependencies'] = []
    meta['m_Name']=meta['m_AssetBundleName']='workbench_'+cab[4:].lower()+'.bundle'
    meta['m_Container']=selected
    meta['m_PreloadTable']=[{'m_FileID':f,'m_PathID':p} for f,p in ordered]
    index_obj.save_typetree(meta)
    file.objects={p:o for p,o in objects.items() if p in seen or p==index}
    file.name=cab
    members={cab:file, **resource_files}
    if packed:
        reader=EndianBinaryReader(bytes(packed));reader.flags=0
        members[cab+'.resS']=reader
    env.file.files=members
    return env.file.save(packer='lz4'),layout


def _legacy_member(path):
    folder = bundle_directory(path)
    scope = path.relative_to(folder) if folder is not None else path
    parts = [s.casefold() for s in scope.parts]
    hashed = len(parts) >= 3 and all(re.fullmatch('[0-9a-f]{32}', s) for s in parts[-3:-1])
    cache = path.name == '__data' and ('installation' in parts or hashed) and not any(
        s.casefold().startswith(('uninstall', 'backup', 'original', '卸载', '备份', '还原')) for s in path.parts)
    return cache or (path.suffix.casefold() == '.bundle' and 'custom_appearance' in parts)


def _members(z):
    candidates=[]
    for info in z.infolist():
        path=PurePosixPath(info.filename.replace('\\','/'))
        if not info.is_dir() and _legacy_member(path):
            candidates.append((info,path))
    return candidates


def _loader_models(z, members, bindings, unity):
    """Keep older workbench IDs when a mod publishes an identical legacy bundle."""
    from collections import defaultdict

    def package_root(path):
        folder = bundle_directory(path)
        if folder is not None:
            return str(folder.parent).casefold()
        for i, part in enumerate(path.parts[:-1]):
            if part.casefold() in ('custom_appearance', 'installation'):
                return str(PurePosixPath(*path.parts[:i])).casefold()
        return None

    def signature(info):
        return info.file_size, info.CRC

    def checksum(info):
        if info not in hashes:
            h = hashlib.sha256()
            with z.open(info) as source:
                for block in iter(lambda: source.read(1024*1024), b''):
                    h.update(block)
            hashes[info] = h.hexdigest()
        return hashes[info]

    copies = defaultdict(list)
    hashes, selected, published = {}, {}, {}
    for info, path in members:
        copies[package_root(path), signature(info)].append((info, path))
    for info, path, model_bindings in bindings:
        body = z.read(info)
        if not body.startswith(UNITY_BUNDLE_MAGIC):
            raise ValueError('CustomAssetLoader 清单指定的文件不是 UnityFS 模型包：' + str(path))
        hashes[info] = hashlib.sha256(body).hexdigest()
        group = package_root(path), signature(info)
        matches = [(old_info, old_path) for old_info, old_path in copies[group]
                   if checksum(old_info) == hashes[info]]
        if matches:
            _, canonical = min(matches, key=lambda pair: ('custom_appearance' not in
                                {part.casefold() for part in pair[1].parts}, str(pair[1]).casefold()))
        else:
            members.append((info, path))
            copies[group].append((info, path))
            canonical = path
        if canonical not in published:
            env = unity.load(body)
            if len(env.assets) != 1:
                raise ValueError('CustomAssetLoader 模型包必须只有一个 Unity 序列化文件：' + str(path))
            published[canonical] = [(*root, env.assets[0].objects[root[1]].peek_name()) for root in _roots(env)]
        exact = resolve_prefabs(path, model_bindings, [root[:3] for root in published[canonical]])
        for aliases, root in exact:
            selected.setdefault(canonical, {}).setdefault(root, []).extend(aliases)
    return selected, published


def _group(path, archive):
    group = next((p for p in path.parts
                  if p.casefold() not in ('assets', 'custom_appearance', 'custom_bundles', 'installation')), archive.stem)
    return archive.stem if group == path.name else group


def _local_look(group, path, address, personality=None):
    identity = '/'.join((group.casefold(), path.name.lower(), address.lower()))
    if personality is not None:
        identity += '/personality/' + personality
    return 'WBImp_' + hashlib.sha256(identity.encode('utf8')).hexdigest()[:24]


def _identity_group(path, archive, group):
    folder = bundle_directory(path)
    if folder is None:
        return group
    root = folder.parent if folder.parent.parts else PurePosixPath(archive.stem)
    return str(root / path.parent.relative_to(folder))


def _stock_voice_lookup(unity):
    """Return a lazy comparison against exact stock roots already indexed locally."""
    from scan.resource_catalog import fingerprint, load_index, resolve_roots
    from skin_motions import stock_voice_events

    @lru_cache(maxsize=1)
    def catalog():
        roots = resolve_roots()
        root = roots['resource_root']
        if root is None:
            return {}
        index, _ = load_index(roots['index_dir'], root, auto_build=False)
        matches = {}
        for relative, entry in (index or {}).get('entries', {}).items():
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                continue
            for address in entry.get('prefabs', {}).values():
                key = address.replace('\\', '/').casefold()
                matches.setdefault(key, {})[path] = entry.get('fingerprint')
        return matches

    @lru_cache(maxsize=1)
    def stock_file(path):
        return unity.load(path.read_bytes())

    @lru_cache(maxsize=None)
    def lookup(address, pid):
        try:
            matches = catalog().get(address.casefold(), {})
            if len(matches) != 1:
                return None
            (path, expected), = matches.items()
            if not path.is_file() or fingerprint(path) != expected:
                return None
            model = stock_file(path)
            if len(model.assets) != 1 or not any(a.casefold() == address.casefold() and root_pid == pid
                                                  for a, root_pid, _ in _roots(model)):
                return None
            return stock_voice_events(model.assets[0].objects[pid])
        except Exception:
            # An unavailable witness does not invalidate a mod's readable tracks.
            return None

    return lookup


def _framepack_base(skin, registered):
    declared = skin.manifest.get('private_server', {}).get('vanilla_appearance_id')
    if declared is None:
        matches = {row.get('appearance_name') for row in registered
                   if row.get('identity_id') == skin.personality}
        if len(matches) == 1:
            declared = matches.pop()
    if not isinstance(declared, str) or not re.fullmatch(r'[A-Za-z0-9_]+', declared):
        raise ValueError(f'{skin.label} 缺少可确认的基础模型，请检查人格 {skin.personality} 的游戏资源或包内声明。')
    return declared


def _framepack_records(archive, skins, work, unity, name, source, registered, report, framepack_dialogue):
    from frame_pack_model import build_frame_pack_record
    from framepack_manifest import portrait_png
    from import_progress import progress_range
    from imported_catalog import display_name
    from private_identity import recipe_identities
    from stock_coin_import import _locate

    identities = recipe_identities(skins, 'declared-frames', source, registered)
    bases = [_framepack_base(skin, registered) for skin in skins]
    files = _locate(set(bases), unity, progress_range(report, 0, 15))
    keys = _catalog_keys()
    for i, (skin, base) in enumerate(zip(skins, bases)):
        identity = identities[skin]
        label = display_name(name or skin.label, Path(source).stem)
        if name and len(skins) > 1:
            label = display_name(name + ' · ' + skin.label, Path(source).stem)
        step = progress_range(report, 15 + 85*i//len(skins), 15 + 85*(i+1)//len(skins))
        step(0, '正在读取逐帧外观：' + label)
        partners = [(archive, other, files[other_base]) for other, other_base in zip(skins, bases)
                    if other is not skin]
        record = build_frame_pack_record(archive, skin, files[base], work, unity, identity.look, label,
                                         partners=partners, progress=step,
                                         dependency=_dependency(base, files[base][1], keys))
        record['entry']['private_declaration'] = identity.owner
        record['portrait'] = portrait_png(archive, skin)
        if framepack_dialogue:
            from framepack_dialogue import collect
            record['framepack_dialogue'] = collect(archive, skin, work)
        yield record


def build_assets(archive,work,unity,*,name=None,progress=None,registered=(),source_name=None,workflow=None,
                 framepack_dialogue=False):
    """Yield validated local skin records. Never run ZIP programs or edit the game cache."""
    from skin_motions import analyze_motion
    from imported_catalog import display_name
    from import_progress import progress_range
    report = progress_range(progress)
    report(0, '正在识别外观和演出格式')
    archive,work=Path(archive),Path(work)
    if not unity.config.FALLBACK_UNITY_VERSION:
        unity.config.FALLBACK_UNITY_VERSION='6000.3.0f1'
    with ZipFile(archive) as z:
        from framepack_manifest import read_framepacks
        frame_skins = read_framepacks(z)
        if frame_skins:
            yield from _framepack_records(z, frame_skins, work, unity, name,
                                          source_name or archive.name, registered, report, framepack_dialogue)
            return
        from generic_skin_policy import apply_action_policy, read_manifest
        policies=read_manifest(z)
        unmatched=set(policies)
        members=_members(z)
        migration = read_recipe(z)
        if migration is not None:
            if any(path.name == '__data' for _, path in members):
                raise ValueError('模型合并包不能同时包含游戏缓存替换')
            report(10, '正在合并外观模型和武器动作')
            yield _migrated_record(z, migration, policies, work, unity, name)
            return
        bindings = read_bindings(z)
        from motion_bundle_recipe import contains_runtime_addon
        from private_appearance_workflow import PrivateAppearanceWorkflow
        from private_body_discovery import discover_private_bodies
        from private_server_appearance import (appearance_package_root, base_appearance,
                                               select_models, valid_appearance_key)
        if workflow is None:
            workflow = PrivateAppearanceWorkflow.discover(z, unity)
        declarations = workflow.remaining
        from private_identity import PrivateIdentities, recipe_identities
        source = source_name or archive.name
        motion_recipes = workflow.motions
        all_declared = [*declarations, *(recipe.declaration for recipe in motion_recipes)]
        unconventional = None
        motion_only = set()
        if motion_recipes:
            from motion_bundle_import import build_motion_records
            motion_ids = {(r.declaration.package_root, r.declaration.personality) for r in motion_recipes}
            if not policies:
                motion_only = ({str(root).casefold() for root, _ in motion_ids}
                               - {str(d.package_root).casefold() for d in declarations})
                # Explicit loader bindings are still resolved below. Legacy
                # discovery must not publish a backup from a declared mod.
                if not bindings:
                    members = [(info, path) for info, path in members
                               if appearance_package_root(path) not in motion_only]
            has_other = bool(members or bindings or declarations)
            if policies and not has_other:
                raise ValueError('动作资源包中的外观覆盖清单没有可匹配的独立预制体')
            boundary = 65 if has_other else 100
            yield from build_motion_records(z, motion_recipes, work, unity, name, archive.stem,
                                            progress_range(report, 0, boundary), source=source, registered=registered)
            if not has_other:
                return
            report = progress_range(report, boundary, 100)
        if not members and not bindings and declarations:
            unconventional = discover_private_bodies(z, declarations, all_declared, unity)
            members.extend((info, path) for path, info in unconventional[1].items())
        if not members and not bindings:
            recipes = workflow.coin_recipes
            coin_owners = {d for d, _ in recipes}
            unresolved = [d for d in declarations if d not in coin_owners and
                          (d.has_motions or d.appearance.startswith('!'))]
            if unresolved:
                missing = unconventional[3] if unconventional else []
                required = '需要本地原版游戏资源：' + '、'.join(missing) if missing else ''
                raise ValueError(workflow.missing_body(unresolved) + required)
            if not recipes:
                if contains_runtime_addon(z):
                    raise ValueError('这是私服运行依赖包，未包含可导入的外观。请选择包含角色模型或动作资源的模组压缩包。')
                if declarations and not motion_recipes:
                    raise ValueError(workflow.missing_body(declarations))
                if motion_recipes:
                    return
                from private_server_appearance import gameplay_only_package
                if gameplay_only_package(z):
                    raise ValueError('这是玩法改动包，只包含游戏配置，没有可导入的独立外观。人格池未添加条目。')
                raise ValueError('未找到战斗外观或 FMOD 语音库')
            if policies:
                raise ValueError('逐币换形配方不能与模型动作覆盖清单合用。')
            from stock_coin_import import build_coin_record
            keys = _catalog_keys()
            ids = recipe_identities((d for d, _ in recipes), 'stock-coins', source, registered)
            for i, (declaration, recipe) in enumerate(recipes):
                phase = progress_range(report, i * 100 // len(recipes), (i + 1) * 100 // len(recipes))
                yield build_coin_record(declaration, recipe, work, unity, name, keys, archive.stem,
                                        ids[declaration], progress=phase)
            return
        legacy = builtin_recipe()
        legacy_names = {asset['member'].casefold() for asset in assets(legacy)}
        if not policies and not bindings and len(members) == len(legacy_names) and {p.name.casefold() for _, p in members} == legacy_names:
            legacy_members = archive_members(z, legacy)
            try:
                verify_members(z, legacy, legacy_members)
            except ValueError:
                # Same file names with changed data are ordinary custom models.
                pass
            else:
                folders = {path.parent for _, path in members}
                yield {'builtin': 'roland', 'model_voice_evidence': {'state': 'unknown', 'count': 0},
                       '_source_member': members[0][1] if len(folders) == 1 else None}
                return
        report(5, '正在核对游戏资源目录')
        keys=_catalog_keys()
        streams=_Streams(unity)
        stock_voice = _stock_voice_lookup(unity)
        produced=set()
        private_models = {}
        loader_models, published_models = _loader_models(z, members, bindings, unity)
        if motion_only and bindings:
            # Keep canonical IDs for manifest bindings with an identical legacy copy.
            members = [(info, path) for info, path in members
                       if path in loader_models or appearance_package_root(path) not in motion_only]
        member_start = 10
        borrowed_proofs = {}
        if declarations:
            roots = {str(declaration.package_root).casefold() for declaration in declarations}
            for info, path in members:
                if path in published_models or appearance_package_root(path) not in roots:
                    continue
                env = unity.load(z.read(info))
                published_models[path] = [(*prefab, env.assets[0].objects[prefab[1]].peek_name())
                                          for prefab in _roots(env)]
            custom = {d for d in declarations if d.appearance.casefold().startswith('!custom_')}
            coin_owners = {d for d, _ in workflow.coin_recipes}
            private_models = select_models(declarations, published_models, keys, loader_models=loader_models,
                                           alternate_declarations=custom | coin_owners)
            resolved = {d for selection in private_models.values() for d, _ in selection}
            if unconventional is None:
                unconventional = discover_private_bodies(z, [d for d in declarations if d in custom - resolved],
                                                          all_declared, unity)
                members.extend((info, path) for path, info in unconventional[1].items())
            extra_models, _, borrowed_proofs, missing = unconventional
            private_models.update(extra_models)
            resolved.update(d for selection in extra_models.values() for d, _ in selection)
            if custom - resolved:
                unresolved = [d for d in declarations if d in custom - resolved]
                required = '需要本地原版游戏资源：' + '、'.join(missing) if missing else ''
                raise ValueError(workflow.missing_body(unresolved) + required)
            recipes = workflow.remaining_coins(private_models)
            if recipes:
                from stock_coin_import import build_coin_record
                member_start = 60
                ids = recipe_identities((d for d, _ in recipes), 'stock-coins', source, registered)
                for i, (declaration, recipe) in enumerate(recipes):
                    phase = progress_range(report, 10 + i * 50 // len(recipes), 10 + (i + 1) * 50 // len(recipes))
                    record = build_coin_record(declaration, recipe, work, unity, name, keys, archive.stem,
                                               ids[declaration], progress=phase)
                    produced.add(record['look'])
                    yield record
        choices = []
        for path, selection in private_models.items():
            selected = {root[:3] for _, root in selection}
            duplicate_addresses = Counter(root[0].casefold() for _, root in selection)
            duplicate_addresses.update(root[0].casefold() for root in loader_models.get(path, {})
                                       if root not in selected)
            group = _identity_group(path, archive, _group(path, archive))
            for declaration, root in selection:
                address = root[0]
                personality = declaration.personality if duplicate_addresses[address.casefold()] > 1 else None
                choices.append((declaration, _local_look(group, path, address, personality)))
        identities = PrivateIdentities(choices, registered, source) if choices else None
        stock_files = {k.rsplit('/',1)[-1].casefold() for k in keys}

        def is_stock(root):
            return PurePosixPath(root[0]).name.casefold() in stock_files

        for i, (info,path) in enumerate(members):
            report(member_start + i * (100 - member_start) // len(members), '正在读取战斗模型：' + path.name)
            private = private_models.get(path)
            explicit = loader_models.get(path, {})
            if path in published_models and not private and not explicit:
                continue
            body=z.read(info)
            revision=hashlib.sha256(body).hexdigest()
            env=unity.load(body)
            published=_roots(env)
            group = _group(path, archive)
            identity_group = _identity_group(path, archive, group)
            # Cache replacements publish their actual mod at a stock address.
            # The legacy custom-bundle path preferred non-stock addresses.
            legacy_published = published
            if policies:
                legacy_published = [root for root in published if root[0].casefold() in policies]
            elif appearance_package_root(path) is not None:
                legacy_published = [root for root in published if not is_stock(root)] or published
            obsolete_stock_ids = []
            if private:
                targets = {root[:3] for _, root in private}
                # Report stock prefabs the previous importer would have exposed.
                obsolete_stock_ids = ['story_' + _local_look(group, path, root[0])
                                      for root in legacy_published if root not in targets and is_stock(root)]
                chosen = [(declaration, root[:3]) for declaration, root in private]
            else:
                chosen = [(None, root) for root in legacy_published if not explicit or root[0].casefold() in policies]
            covered = {root for _, root in chosen}
            chosen.extend((None, root) for root in explicit if root not in covered)
            addresses = Counter(root[0].casefold() for _, root in chosen)
            for n,(declaration, (address,pid,index)) in enumerate(chosen):
                if n:env=unity.load(body)
                loader_bindings = explicit.get((address, pid, index), ())
                layout=env.assets[0].objects[pid].peek_name()
                if declaration is not None or loader_bindings:
                    layout = base_appearance(layout)
                key = address.casefold()
                policy = policies.get(key)
                if policy is not None:
                    if key not in unmatched:
                        raise ValueError('外观配置的预制体地址在包中有多个匹配项：'+address)
                    unmatched.remove(key)
                dep=policy.get('dependency') if policy else None
                dep_address = base_appearance(PurePosixPath(address).name) if declaration is not None else address
                if dep is not None:
                    if not isinstance(dep,str) or dep not in keys:raise ValueError('外观配置指定的依赖不在游戏资源目录中')
                elif loader_bindings:
                    dep = _loader_dependency(loader_bindings, layout, dep_address, keys,
                                             required=declaration is None)
                else:
                    dep=_dependency(layout,dep_address,keys,required=declaration is None)
                default_label = display_name(group, archive.stem)
                label = name or default_label
                shared_model = declaration is not None and addresses[key] > 1
                legacy_look = _local_look(identity_group, path, address, declaration.personality if shared_model else None)
                look = identities.look(declaration, legacy_look) if declaration is not None else legacy_look
                if look in produced:raise ValueError('外观包包含重复的角色标识 '+address)
                produced.add(look)
                model_revision = revision
                output_address = address
                legacy_name = None
                presentation_notes = []
                if declaration is not None:
                    legacy_name = default_label
                    if len(legacy_published) > 1 or len(members) > 1:
                        legacy_name += ' · ' + PurePosixPath(address).stem
                    from private_server_art import adapt_private_appearance
                    replacement = adapt_private_appearance(z, declaration.package_root, declaration.appearance,
                                                           env, pid, unity, stock_keys=keys)
                    if replacement:
                        model_revision = hashlib.sha256((revision + '/' + replacement).encode('ascii')).hexdigest()
                    if not name:
                        label = display_name(declaration.package_root.name or group, archive.stem)
                    if not name and declaration.label:
                        label += ' · ' + declaration.label
                    elif len(declarations) > 1:
                        label += ' · ' + (declaration.label or declaration.appearance) + ' (' + declaration.personality + ')'
                elif loader_bindings and (len(chosen)>1 or len(members)>1):
                    label += ' · ' + display_name(loader_bindings[0].resource_id, archive.stem)
                elif not loader_bindings and (len(legacy_published)>1 or len(members)>1):
                    label+=' · '+PurePosixPath(address).stem
                if (declaration is not None or loader_bindings) and not re.fullmatch(
                        r'(?i:assets)/[a-zA-Z0-9_ ./-]+\.prefab', address):
                    output_address = 'Assets/MirrorOfSkin/' + look + '.prefab'
                conversion = {'output_address': output_address} if output_address != address else {}
                standalone = None
                if dep is None:
                    from standalone_materials import StandaloneMaterials

                    dep = _independent_trigger(declaration.character_id, keys)
                    model_progress = progress_range(report, member_start + i * (100 - member_start) // len(members),
                                                    member_start + (i + 1) * (100 - member_start) // len(members))
                    standalone = StandaloneMaterials(env.assets[0], unity, progress=model_progress)
                    conversion['standalone'] = standalone
                proof = borrowed_proofs.get((path, pid))
                if proof is not None:
                    from borrowed_motion import sanitize_borrowed_motion
                    from stock_coin_recipe import referenced_custom_forms

                    presentation_notes.extend(sanitize_borrowed_motion(env, pid, proof, unity=unity))
                    changed = hashlib.sha256(bytes.fromhex(revision))
                    for object_id, obj in sorted(env.assets[0].objects.items()):
                        if obj.data is not None:
                            changed.update(struct.pack('<qQ', object_id, len(obj.data)))
                            changed.update(obj.data)
                    model_revision = changed.hexdigest()
                    forms = referenced_custom_forms(z, declaration)
                    if forms:
                        presentation_notes.append('技能另引用 ' + '、'.join(forms) +
                                                  '，当前使用已识别的主体，未绑定这些独立形态')
                encoded,_=_convert(env,model_revision,look,address,pid,index,streams,**conversion)
                if policy and 'native_layout' in policy:layout=policy['native_layout']
                work.mkdir(parents=True,exist_ok=True)
                dest=work/(look+'.bundle')
                dest.write_bytes(encoded)
                parsed=unity.load(encoded)
                root=parsed.assets[0].objects[pid]
                assert root.peek_name()==look and _roots(parsed)==[(output_address,pid,index)]
                # The native config uses ASCII layout IDs to compare stock slot layouts.
                # An independently named Unicode prefab has the generated root name instead.
                if declaration is not None and not layout.isascii() and valid_appearance_key(layout):
                    layout = look
                asset_key='Imported/'+look+'.prefab'
                entry,timing,actions=analyze_motion(parsed,root,look,asset_key,label,
                                                    declared_roles=bool(policy and ('clash' in policy or 'defense' in policy)),
                                                    stock_voice=lambda: stock_voice(address, pid))
                if policy is not None:
                    actions = apply_action_policy(policy, actions, entry['verified_attack_details'])
                    actions.pop('declarable_timeline_roles', None)
                if standalone is not None and standalone.orphan_voice_tracks:
                    attacks = {part for action in actions['attack'] for part in action['parts']}
                    if any(env.assets[0].objects[pid].peek_name() not in attacks for pid in standalone.orphan_voice_tracks):
                        raise ValueError('原包缺少语音轨道的技能动作无法完整验证')
                if declaration is not None:
                    entry['private_declaration'] = identities.owner(declaration)
                yield dict(look=look,name=label,asset=output_address,layout=layout,dependency=dep,
                           bundle=dest,entry=entry,timing=timing,actions=actions,policy=policy,
                           _source_member=path, _source_address=address,
                           model_voice_evidence=actions.pop('model_voice_evidence', dict(state='unknown', count=0)),
                           voice_warning=standalone.voice_warning() if standalone is not None else '',
                           presentation_warning='；'.join(presentation_notes),
                           _uses_legacy_private_id=declaration is not None and look == legacy_look,
                           _obsolete_stock_ids=obsolete_stock_ids,
                           private_server_appearance=declaration is not None, legacy_name=legacy_name)
        if unmatched:raise ValueError('外观配置指向包中不存在的预制体：'+min(unmatched))
        if not produced:raise ValueError('未找到可独立克隆的已发布战斗角色')


def _migrated_record(archive, recipe, policies, work, unity, label):
    members = archive_members(archive, recipe)
    verify_members(archive, recipe, members)
    dependency = recipe['dependency']
    if dependency not in _catalog_keys():
        raise ValueError('模型合并配方指定的依赖不在游戏资源目录中')
    from generic_skin_policy import apply_action_policy
    from roland_merge import build_migrated_bundle
    from skin_motions import analyze_motion

    stable = 'migration/' + recipe['id'] + '/' + recipe['base']['prefab'].casefold()
    look = 'WBImp_' + hashlib.sha256(stable.encode('utf8')).hexdigest()[:24]
    model, _, address, layout = build_migrated_bundle(archive, recipe, members, look=look)
    env = unity.load(model)
    matches = [root for root in _roots(env) if root[0] == address]
    if len(matches) != 1 or env.assets[0].objects[matches[0][1]].peek_name() != look:
        raise ValueError('合并模型缺少唯一的主外观')
    _, pid, index = matches[0]
    revision = hashlib.sha256(model).hexdigest()
    encoded, _ = _convert(env, revision, look, address, pid, index, _Streams(unity))
    if policies and set(policies) != {address.casefold()}:
        raise ValueError('模型合并的外观配置须指向合并后的主预制体')
    policy = policies.get(address.casefold())
    if policy:
        if policy.get('dependency', dependency) != dependency:
            raise ValueError('模型合并配方与外观配置指定的依赖不一致')
        layout = policy.get('native_layout', layout)
    label = label or recipe['name']
    parsed = unity.load(encoded)
    root = parsed.assets[0].objects[pid]
    entry, timing, actions = analyze_motion(parsed, root, look, 'Imported/' + look + '.prefab', label,
                                           declared_roles=bool(policy and ('clash' in policy or 'defense' in policy)))
    if set(entry['verified_attack_details']) != set(recipe['verified_attack_details']):
        raise ValueError('合并主外观的实际攻击组与配方不符')
    if policy is not None:
        actions = apply_action_policy(policy, actions, entry['verified_attack_details'])
        actions.pop('declarable_timeline_roles', None)
    work.mkdir(parents=True, exist_ok=True)
    dest = work / (look + '.bundle')
    dest.write_bytes(encoded)
    return dict(look=look, name=label, asset=address, layout=layout, dependency=dependency,
                bundle=dest, entry=entry, timing=timing, actions=actions, policy=policy,
                _source_member=members[0].filename, _source_address=address,
                model_voice_evidence=actions.pop('model_voice_evidence', dict(state='unknown', count=0)))
