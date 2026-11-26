"""Compose one CharacterAppearance from a base bundle and authored attack donors."""
from collections import deque
from copy import copy, deepcopy
import json
from pathlib import Path
import warnings
from zipfile import ZipFile

import UnityPy
from UnityPy.streams import EndianBinaryReader
import attack_discovery
from bundle_migration import archive_members, assets, builtin_recipe, validated_unpacked_size, verify_members
from sprite_facing import body_rig, body_mapping_indices, mirror_sprite

UnityPy.config.FALLBACK_UNITY_VERSION = '6000.3.0f1'
warnings.filterwarnings('ignore', category=UserWarning)


def ref(pid):
    return {'m_FileID': 0, 'm_PathID': pid}


def walk(data):
    if isinstance(data, dict):
        yield data
        for v in data.values():
            yield from walk(v)
    elif isinstance(data, (list, tuple)):
        for v in data:
            yield from walk(v)


class Prefab:
    def __init__(self, archive, resource):
        self._read(UnityPy.load(archive.read(resource['file'])), resource['root'])

    @classmethod
    def from_asset(cls, env, root):
        prefab = cls.__new__(cls)
        prefab._read(env, root)
        return prefab

    def _read(self, env, root):
        self.env = env
        self.file = self.env.assets[0]
        self.objects = self.file.objects
        self.edits = {}
        self.root = root if isinstance(root, int) else next(
            p for p, o in self.objects.items() if o.type.name == 'GameObject' and o.peek_name() == root)
        components = self.tree(self.root)['m_Component']
        self.app_id = next(i['component']['m_PathID'] for i in components
                           if 'motionList' in self.tree(i['component']['m_PathID']))
        self.director_id = next(i['component']['m_PathID'] for i in components
                                if self.objects[i['component']['m_PathID']].type.name == 'PlayableDirector')
        self.app = self.tree(self.app_id)
        self.director = self.tree(self.director_id)
        self.index_id = next(p for p,o in self.objects.items() if o.type.name=='AssetBundle')
        self.index = self.tree(self.index_id)
        self.stream_name = next(n for n in self.env.file.files if n.endswith('.resS'))

    def tree(self, pid):
        if pid in self.edits:return self.edits[pid]
        return self.objects[pid].read_typetree()


# Unity's animation binding path CRC32 for the visible character sprite.
BODY_PATH = 1257685109


def body_bindings(clip):
    return [b for b in clip['m_ClipBindingConstant']['genericBindings'] if b['isPPtrCurve']]


def has_body(clip, path=BODY_PATH):
    return any(b['typeID']==212 and b['path']==path for b in body_bindings(clip))


def replace_body_frames(pf, clip, sprites, mapping_rules, body_path):
    # Edit only animation clips whose pointer curves all target the visible
    # character. In mixed clips the other pointers drive gun smoke, shells
    # and slash overlays. Keep the original curves when they mix both targets.
    bindings=body_bindings(clip)
    if not has_body(clip, body_path) or any(b['path']!=body_path or b['typeID']!=212 for b in bindings):
        return 0
    mapping=clip['m_ClipBindingConstant']['pptrCurveMapping']
    assert not clip['m_PPtrCurves']
    edited=0
    for r in mapping:
        if not r['m_PathID']:continue
        assert not r['m_FileID']
        name=pf.objects[r['m_PathID']].peek_name()
        keep = mapping_rules.get('keep_sprite_substring')
        if keep and keep.casefold() in name.casefold():
            continue
        target = mapping_rules.get('exact', {}).get(name)
        if target is None:
            for rule in mapping_rules.get('ranges', ()):
                if name.startswith(rule['prefix']):
                    number = name[len(rule['prefix']):].split('_', 1)[0]
                    if number.isascii() and number.isdecimal() and len(number) <= 3:
                        if rule['first'] <= int(number) <= rule['last']:
                            target = rule['target']
                            break
        if target is None:
            target = next((sprite for prefix, sprite in mapping_rules.get('prefixes', {}).items()
                           if name.startswith(prefix)), None)
        if target not in sprites:
            raise ValueError('模型合并配方缺少精灵映射或目标：' + name)
        r['m_PathID']=sprites[target]
        edited+=1
    return edited


def bind_attack_bodies(pf, groups, body_path=BODY_PATH, *, timelines=None):
    # Some group tracks in the original personality prefab get their Animator
    # assigned by the original personality at runtime. The merged prefab owns
    # the same sprite hierarchy and can bind those body tracks explicitly.
    current={b['key']['m_PathID']:b['value']['m_PathID'] for b in pf.director['m_SceneBindings']}
    if timelines is None:
        timelines = [r for m in pf.app['motionList'] if m['_motiondetail'] in groups for r in m['timelineAssets']]
    pending=[r['m_PathID'] for r in timelines]
    visited=set()
    body_clips=set()
    while pending:
        i=pending.pop()
        if i in visited:continue
        visited.add(i)
        t=pf.tree(i)
        if t.get('m_Muted'):continue
        pending.extend(v['m_PathID'] for v in t.get('m_Tracks',[])+t.get('m_Children',[]))
        if 'm_InfiniteClip' not in t:continue
        clips=[t['m_InfiniteClip']]+[pf.tree(c['m_Asset']['m_PathID']).get('m_Clip',ref(0)) for c in t['m_Clips']]
        matched={r['m_PathID'] for r in clips if not r['m_FileID'] and r['m_PathID']
                 and has_body(pf.tree(r['m_PathID']), body_path)}
        if not matched:continue
        body_clips.update(matched)
        if current.get(i):
            assert current[i]==pf.app['_anim']['m_PathID']
        else:
            rows=[b for b in pf.director['m_SceneBindings'] if b['key']==ref(i)]
            if rows:
                for b in rows:b['value']=deepcopy(pf.app['_anim'])
            else:
                pf.director['m_SceneBindings'].append({'key':ref(i),'value':deepcopy(pf.app['_anim'])})
            current[i]=pf.app['_anim']['m_PathID']
    return body_clips

def selected_director_entries(prefab, timelines):
    """Keep scene bindings and exposed objects reachable from the chosen tracks."""
    visited, exposed = set(), set()
    pending = [timeline['m_PathID'] for timeline in timelines]
    while pending:
        pid = pending.pop()
        if pid in visited:
            continue
        obj = prefab.objects.get(pid)
        if obj is None or obj.type.name != 'MonoBehaviour':
            continue
        visited.add(pid)
        tree = prefab.tree(pid)
        pending.extend(attack_discovery.refs(tree))
        exposed.update(value['exposedName'] for value in walk(tree) if 'exposedName' in value)
    return (
        [binding for binding in prefab.director['m_SceneBindings']
         if binding['key']['m_PathID'] in visited],
        [(name, value) for name, value in prefab.director['m_ExposedReferences']['m_References']
         if name in exposed],
    )


def merge(target, donor, spec, next_id, stream, new_preloads, *, legacy, selected_motion=None):
    # Keep the animator paths used by the original clips. Reuse the common
    # rig and sprite renderer, and graft each donor's own effects into that rig.
    ids = {0:0, donor.root:target.root, donor.app_id:target.app_id, donor.director_id:target.director_id}
    queue = deque()
    new_objects = {}
    source_body, source_facing, source_paths = body_rig(donor)
    target_body, target_facing, target_paths = body_rig(target)
    if source_body != target_body or source_paths != target_paths:
        raise ValueError('主体渲染器路径不同，无法安全合并动作')
    mirror_body = source_facing != target_facing
    mirrored = {}
    target_externals = {external.path: i for i, external in enumerate(target.file.externals, 1)}
    externals = [0] + [target_externals.get(external.path) for external in donor.file.externals]
    if selected_motion is None and None in externals:
        raise ValueError('供体引用了基础外观中不存在的外部资源')

    def external_index(i):
        mapped = externals[i]
        if mapped is None:
            raise ValueError('供体片段需要额外的游戏数据：' + donor.file.externals[i-1].path)
        return mapped
    streamed_at = len(stream)
    stream.extend(donor.env.file.files[donor.stream_name].bytes)
    target_stream = next(o.read_typetree()['m_StreamData']['path'] for o in target.objects.values()
                         if o.type.name=='Texture2D' and o.read_typetree()['m_StreamData']['size'])

    def allocate(pid):
        if pid not in ids:
            dst = next(next_id)
            assert dst not in target.objects
            ids[pid] = new_objects[pid] = dst
            queue.append(pid)
        return ids[pid]

    exposed_remap = {}
    def rewrite(data):
        for d in walk(data):
            if d.get('exposedName') in exposed_remap:
                d['exposedName']=exposed_remap[d['exposedName']]
            if 'm_PathID' in d and 'm_FileID' in d:
                if not d['m_FileID']:
                    d['m_PathID'] = allocate(d['m_PathID'])
                else:
                    d['m_FileID'] = external_index(d['m_FileID'])
            if d.get('size') and isinstance(d.get('path'), str) and d['path'].endswith('.resS'):
                assert d['path'].endswith(donor.stream_name)
                d.update(path=target_stream,offset=d['offset']+streamed_at)
        return data

    def bind_rig(src, dst):
        so, to = donor.tree(src), target.tree(dst)
        ids[src] = dst
        sg = so['m_GameObject']['m_PathID']
        tg = to['m_GameObject']['m_PathID']
        ids[sg] = tg
        def components(prefab, go):
            return [c['component']['m_PathID'] for c in prefab.tree(go)['m_Component']]
        tcs=components(target,tg)
        for c in components(donor,sg):
            if c in ids: continue
            typ=donor.objects[c].type.name
            matches=[k for k in tcs if target.objects[k].type.name==typ]
            if typ=='MonoBehaviour':
                script=donor.tree(c)['m_Script']['m_PathID']
                matches=[k for k in matches if target.tree(k)['m_Script']['m_PathID']==script]
            if len(matches)==1:ids[c]=matches[0]
        def name(prefab, child):
            return prefab.tree(prefab.tree(child['m_PathID'])['m_GameObject']['m_PathID'])['m_Name']
        children={name(target,x):x['m_PathID'] for x in to['m_Children']}
        for child in so['m_Children']:
            n=name(donor,child)
            # Even identically named FX can have different emitted textures.
            if n in children and donor.tree(sg)['m_Name']!='[Transform]DefaultEffectPivot':
                bind_rig(child['m_PathID'],children[n])
            else:
                to['m_Children'].append(ref(allocate(child['m_PathID'])))
        target.edits[dst]=to
        target.objects[dst].save_typetree(to)

    bind_rig(donor.tree(donor.root)['m_Component'][0]['component']['m_PathID'],
             target.tree(target.root)['m_Component'][0]['component']['m_PathID'])
    if selected_motion is None:
        groups, detail = spec['groups'], spec['detail']
        merged_motion = None
        found_groups = set()
        for m in donor.app['motionList']:
            if m['_motiondetail'] not in groups:continue
            if m['motionObjects'] or m['damageObj'] or m['isSpineAnim']:
                raise ValueError('供体动作包含不支持的非时间轴动画')
            found_groups.add(m['_motiondetail'])
            if merged_motion is None:
                merged_motion=deepcopy(m)
                merged_motion.update(_motiondetail=detail,timelineAssets=[])
            merged_motion['timelineAssets'].extend(rewrite(deepcopy(m['timelineAssets'])))
        if found_groups != set(groups) or merged_motion is None or len(merged_motion['timelineAssets']) != spec['segments']:
            raise ValueError('供体动作组或时间轴段数与配方不符')
        target.app['motionList'].append(merged_motion)
        body_clips = bind_attack_bodies(donor,groups,source_body)
    else:
        merged_motion = rewrite(deepcopy(selected_motion))
        body_clips = set()
        for timeline in selected_motion['timelineAssets']:
            clips = bind_attack_bodies(donor, (), source_body, timelines=(timeline,))
            if not clips:
                raise ValueError('供体片段没有可验证的主体精灵轨道：' + donor.objects[timeline['m_PathID']].peek_name())
            body_clips.update(clips)
    if selected_motion is None:
        bindings = donor.director['m_SceneBindings']
        exposures = donor.director['m_ExposedReferences']['m_References']
    else:
        bindings, exposures = selected_director_entries(donor, selected_motion['timelineAssets'])
    existing = dict(target.director['m_ExposedReferences']['m_References'])
    # Unity stores ExposedReference ids as serialized PropertyNames (hashed
    # string identifiers). Give conflicting keys distinct ids and rewrite the clips.
    used_names=set(existing)|{k for k,v in exposures}
    spare=iter(range(1850000000,2000000000))
    for name,value in exposures:
        v=rewrite(deepcopy(value))
        if name in existing:
            if existing[name] != v:
                new=next(str(i) for i in spare if str(i) not in used_names)
                used_names.add(new)
                exposed_remap[name]=new
                target.director['m_ExposedReferences']['m_References'].append((new,v))
        else:
            existing[name]=v
            target.director['m_ExposedReferences']['m_References'].append((name,v))
    for b in bindings:
        if b['key']['m_PathID'] and b['value']['m_PathID']:
            target.director['m_SceneBindings'].append(rewrite(deepcopy(b)))

    rules = spec.get('sprites')
    sprites = ({o.peek_name(): pid for pid, o in donor.objects.items() if o.type.name == 'Sprite'}
               if rules else {})
    edits=0
    typemap={}
    def type_index(obj):
        if obj.type_id in typemap:return typemap[obj.type_id]
        st=obj.serialized_type
        idx=next((i for i,t in enumerate(target.file.types) if
                  (t.class_id,t.script_id,t.old_type_hash)==(st.class_id,st.script_id,st.old_type_hash)),None)
        if idx is None:
            st=copy(st)
            assert not st.type_dependencies
            if st.script_type_index>=0:
                script=copy(donor.file.script_types[st.script_type_index])
                script.local_serialized_file_index=external_index(script.local_serialized_file_index)
                if script not in target.file.script_types:target.file.script_types.append(script)
                st.script_type_index=target.file.script_types.index(script)
            idx=len(target.file.types)
            target.file.types.append(st)
        typemap[obj.type_id]=idx
        return idx

    def save_asset(orig, path, data):
        obj=copy(orig)
        obj.assets_file=target.file
        obj.type_id=type_index(orig)
        obj.serialized_type=target.file.types[obj.type_id]
        obj.path_id=path
        target.objects[path]=obj
        obj.save_typetree(data)
        if obj.type.name in ('Transform','RectTransform','GameObject'):target.edits[path]=data

    while queue:
        pid=queue.popleft()
        orig=donor.objects[pid]
        data=orig.read_typetree()
        selected = {}
        if orig.type.name=='AnimationClip':
            if rules:
                edits += replace_body_frames(donor, data, sprites, rules, BODY_PATH if legacy else source_body)
            if mirror_body and pid in body_clips:
                mapping = data['m_ClipBindingConstant']['pptrCurveMapping']
                for index in body_mapping_indices(data, source_body, source_paths):
                    sprite_pid = mapping[index]['m_PathID']
                    if not sprite_pid:
                        continue
                    if mapping[index]['m_FileID'] or donor.objects[sprite_pid].type.name!='Sprite':
                        raise ValueError('主体动画引用无法镜像的精灵')
                    if sprite_pid not in mirrored:
                        sprite = donor.objects[sprite_pid]
                        tree, texture, texture_tree = mirror_sprite(donor, sprite)
                        sprite_id, texture_id = next(next_id), next(next_id)
                        tree = rewrite(tree)
                        tree['m_RD']['texture'] = ref(texture_id)
                        save_asset(texture, texture_id, texture_tree)
                        save_asset(sprite, sprite_id, tree)
                        mirrored[sprite_pid] = sprite_id
                        new_preloads.extend(((0,texture_id),(0,sprite_id)))
                    selected[index] = mirrored[sprite_pid]
                    mapping[index] = ref(0)
        data=rewrite(data)
        for index, sprite_id in selected.items():
            data['m_ClipBindingConstant']['pptrCurveMapping'][index] = ref(sprite_id)
        save_asset(orig, ids[pid], data)

    # Match the donor's preload order. This includes external shaders and
    # MonoScripts present in the stock base prefab's four dependency archives.
    for p in donor.index['m_PreloadTable']:
        if p['m_FileID'] and externals[p['m_FileID']] is not None:
            new_preloads.append((externals[p['m_FileID']],p['m_PathID']))
        elif p['m_PathID'] in new_objects:
            new_preloads.append((0,new_objects[p['m_PathID']]))
    new_preloads.extend((0,p) for p in new_objects.values())
    if mirror_body and not mirrored:
        raise ValueError('主体渲染器方向相反，但未找到可修复的主体精灵映射')
    if selected_motion is None:
        print(f'{detail}: copied {len(new_objects)} objects, {edits} donor body references replaced, '
              f'{len(mirrored)} mirrored sprites, {len(merged_motion["timelineAssets"])} segments',flush=True)
    return merged_motion


def merge_prepared(prepared_archive, recipe=None, *, legacy=True, with_voice=False):
    """Merge normalized appearance bundles and verify the authored motion contract."""
    recipe = builtin_recipe() if recipe is None else recipe
    with ZipFile(prepared_archive) as archive:
        base, *donors = json.loads(archive.read('resources.json'))
        target = Prefab(archive, base)
        base_spec = recipe['base']
        rules = base_spec.get('sprites')
        body_path = BODY_PATH if legacy else body_rig(target)[0]
        if rules:
            sprites = {o.peek_name(): pid for pid, o in target.objects.items() if o.type.name == 'Sprite'}
            clips = set(base_spec['replace_clips'])
            found_clips = set()
            for o in target.objects.values():
                if o.type.name == 'AnimationClip' and o.peek_name() in clips:
                    found_clips.add(o.peek_name())
                    ct = o.read_typetree()
                    if replace_body_frames(target, ct, sprites, rules, body_path):
                        o.save_typetree(ct)
            if found_clips != clips:
                raise ValueError('基础模型缺少配方指定的替换动画')
        bind_attack_bodies(target, base_spec['bind_groups'], body_path)
        original_motions = deepcopy(target.app['motionList'])
        if not legacy:
            used = {m['_motiondetail'] for m in original_motions}
            if used.intersection(donor['detail'] for donor in recipe['donors']):
                raise ValueError('合并供体的动作槽已被基础模型占用')
        next_id = (pid for pid in range(10000000000, 10010000000) if pid not in target.objects)
        stream = bytearray(target.env.file.files[target.stream_name].bytes)
        new_preloads = []
        for asset, spec in zip(donors, recipe['donors']):
            merge(target, Prefab(archive, asset), spec, next_id, stream, new_preloads, legacy=legacy)
        target.objects[target.app_id].save_typetree(target.app)
        target.objects[target.director_id].save_typetree(target.director)
        original_size = len(target.index['m_PreloadTable'])
        for k, info in target.index['m_Container']:
            if k.lower() != base['prefab'].lower():
                continue
            if len(target.index['m_PreloadTable']) == original_size:
                start, size = info['preloadIndex'], info['preloadSize']
                old = target.index['m_PreloadTable'][start:start + size]
                ordered = dict.fromkeys(new_preloads + [(p['m_FileID'], p['m_PathID']) for p in old])
                target.index['m_PreloadTable'].extend({'m_FileID': f, 'm_PathID': p} for f, p in ordered)
            info.update(preloadIndex=original_size, preloadSize=len(target.index['m_PreloadTable']) - original_size)
        target.objects[target.index_id].save_typetree(target.index)
        rd = EndianBinaryReader(bytes(stream))
        rd.flags = target.env.file.files[target.stream_name].flags
        target.env.file.files[target.stream_name] = rd
        encoded = target.env.file.save(packer='lz4')
    check = UnityPy.load(encoded)
    trees = {o.path_id: o.read_typetree() for o in check.objects if o.type.name in ('GameObject', 'MonoBehaviour')}
    motions = trees[target.app_id]['motionList']
    if motions[:-len(recipe['donors'])] != original_motions:
        raise ValueError('合并改变了原有动作列表')
    entry, blob = attack_discovery.from_trees(base['root'], base['address'], trees, recipe['name'])
    verified = entry['verified_attack_details']
    if (verified if legacy else sorted(verified)) != (
            recipe['verified_attack_details'] if legacy else sorted(recipe['verified_attack_details'])):
        raise ValueError('合并模型的已验证攻击组与配方不符')
    if with_voice:
        from skin_motions import _model_voice_evidence

        objects = check.assets[0].objects

        def read(pid):
            if pid not in trees and pid in objects:
                trees[pid] = objects[pid].read_typetree()
            return trees.get(pid)

        return encoded, blob, _model_voice_evidence(trees[target.app_id], read)
    return encoded, blob


def build_migrated_bundle(source, recipe, members, *, look=None, with_voice=False):
    """Build from validated ZIP members without extracting any mod files."""
    import hashlib
    import re
    from model_workspace import model_tempdir
    from zipfile import ZIP_STORED

    legacy = look is None
    namespace = recipe['cab_namespace'] if legacy else 'workbench.migration.' + recipe['id'] + '.'
    with model_tempdir(prefix='faust-model-migration-') as folder:
        prepared = Path(folder) / 'prepared.zip'
        resources = []
        expanded = 0
        with ZipFile(prepared, 'w', ZIP_STORED) as output:
            for index, (spec, info) in enumerate(zip(assets(recipe), members)):
                bundle, prefab = Path(spec['member']).stem, spec['prefab']
                original = source.read(info)
                if not legacy:
                    expanded += validated_unpacked_size(original)
                    if expanded > 2 * 1024**3:
                        raise ValueError('外部合并包的全部模型解包总量超出读取上限')
                env = UnityPy.load(original)
                found = [(k, v) for k, v in env.container.items()
                         if k.endswith('/' + prefab + '.prefab') and v.type.name == 'GameObject']
                if len(env.assets) != 1 or len(found) != 1:
                    raise ValueError('模型缺少唯一的配方预制体：' + prefab)
                key, root = found[0]
                tree = root.read_typetree()
                if index == 0:
                    layout = tree['m_Name']
                name = spec['root'] if legacy else look if index == 0 else look + 'Donor' + str(index)
                tree['m_Name'] = name
                root.deref().save_typetree(tree)
                index_object = next(o for o in env.objects if o.type.name == 'AssetBundle')
                tree = index_object.read_typetree()
                tree['m_Name'] = tree['m_AssetBundleName'] = 'workbench_' + bundle.lower() + '.bundle'
                index_object.save_typetree(tree)
                streams = [n for n in env.file.files if n.endswith('.resS')]
                match = re.fullmatch(r'(CAB-[a-f0-9]{32})\.resS', streams[0]) if len(streams) == 1 else None
                if not match:
                    raise ValueError('模型纹理资源或标识无效：' + bundle)
                own = match.group(1)
                revision = bundle if legacy else bundle + spec['sha256']
                unique = 'CAB-' + hashlib.sha256((namespace + revision).encode()).hexdigest()[:32]
                raw = env.file.save(packer='none')
                if own.encode() not in raw:
                    raise ValueError('模型资源标识缺失：' + bundle)
                raw = raw.replace(own.encode(), unique.encode()).replace(own.lower().encode(), unique.lower().encode())
                encoded = UnityPy.load(raw).file.save(packer='lz4')
                member = 'Bundles/' + bundle + '.bundle'
                output.writestr(member, encoded)
                address = spec['address'] if legacy else 'Imported/' + name + '.prefab'
                resources.append({'address': address, 'file': member, 'prefab': key, 'root': name})
                del original, env, raw, encoded
            output.writestr('resources.json', json.dumps(resources, ensure_ascii=False).encode('utf8'))
        merged = merge_prepared(prepared, recipe, legacy=legacy, with_voice=with_voice)
        return (*merged, resources[0]['prefab'], layout)


def build_roland_bundle(source_archive, *, with_voice=False):
    """Rebuild the original unified model and metadata using the bundled recipe."""
    recipe = builtin_recipe()
    with ZipFile(source_archive) as source:
        members = archive_members(source, recipe)
        verify_members(source, recipe, members)
        merged = build_migrated_bundle(source, recipe, members, with_voice=with_voice)
        return merged[:-2]
