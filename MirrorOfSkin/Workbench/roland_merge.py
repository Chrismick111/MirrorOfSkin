"""Build one CharacterAppearance with the authored attack tracks of all three bundles."""
from collections import deque
from copy import copy, deepcopy
import json
from pathlib import Path
import warnings
from zipfile import ZipFile

import UnityPy
from UnityPy.streams import EndianBinaryReader
import attack_discovery

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
        self.env = UnityPy.load(archive.read(resource['file']))
        self.file = self.env.assets[0]
        self.objects = self.file.objects
        self.edits = {}
        self.root = next(p for p, o in self.objects.items()
                         if o.type.name == 'GameObject' and o.peek_name() == resource['root'])
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


def has_body(clip):
    return any(b['typeID']==212 and b['path']==BODY_PATH for b in body_bindings(clip))


def replace_body_frames(pf, detail, clip, sprites):
    # Edit only animation clips whose pointer curves all target the visible
    # character. In mixed clips the other pointers drive gun smoke, shells
    # and slash overlays. The originals already have Roland on their body lane.
    bindings=body_bindings(clip)
    if not has_body(clip) or any(b['path']!=BODY_PATH or b['typeID']!=212 for b in bindings):
        return 0
    mapping=clip['m_ClipBindingConstant']['pptrCurveMapping']
    assert not clip['m_PPtrCurves']
    edited=0
    for r in mapping:
        if not r['m_PathID']:continue
        assert not r['m_FileID']
        name=pf.objects[r['m_PathID']].peek_name()
        if 'roland' in name.lower():continue
        if detail==24:
            if name=='dead':
                target='roland_dmg_f'
            else:
                # Original gun S1 winds up then cycles three fire/recoil poses.
                lookup={'skill1_1':0,'skill1_2':12,'skill1_3':13,
                        'skill1_4,7,10':14,'skill1_5,8':16,'skill1_6,9':17}
                target='roland_gun_f_'+str(lookup[name])
        elif detail==25:
            neutral={'idle':'roland_idle_f','miss':'roland_miss_f','dead':'roland_dmg_f'}
            if name in neutral:target=neutral[name]
            else:
                # The four author-drawn greatsword poses depict ready, windup,
                # airborne swing and ground impact. Preserve all key times.
                lookup={'skill1_1':0,'skill1_2':0,'skill1_3':1,'skill1_4':2,'skill1_5':3,'skill1_6':3,'skill1_7':1,
                        'skill2_6':0,'skill2_7':1,'skill2_8':2,'skill2_9':3,'skill2_10':1,
                        'skill3_1':0,'skill3_2':1,'skill3_3':2,'skill3_4':3,'skill3_5':2,'skill3_6':3}
                if name.startswith('reload_'):target='roland_ultrasword_f_0'
                else:target='roland_ultrasword_f_'+str(lookup[name])
        else:
            if name=='dmg':target='roland_dmg'
            elif name.startswith('skill_'):
                step=int(name.split('_')[1])
                target=('roland_special_0' if step<=8 else 'roland_ready_0' if step<=16 else 'roland_ready_1')
            else:raise ValueError('unmapped base body sprite '+name)
        r['m_PathID']=sprites[target]
        edited+=1
    return edited


def bind_attack_bodies(pf, groups):
    # Some group tracks in the original personality prefab get their Animator
    # assigned by the original personality at runtime. The merged prefab owns
    # the same sprite hierarchy and can bind those body tracks explicitly.
    current={b['key']['m_PathID']:b['value']['m_PathID'] for b in pf.director['m_SceneBindings']}
    pending=[r['m_PathID'] for m in pf.app['motionList'] if m['_motiondetail'] in groups for r in m['timelineAssets']]
    visited=set()
    while pending:
        i=pending.pop()
        if i in visited:continue
        visited.add(i)
        t=pf.tree(i)
        if t.get('m_Muted'):continue
        pending.extend(v['m_PathID'] for v in t.get('m_Tracks',[])+t.get('m_Children',[]))
        if 'm_InfiniteClip' not in t:continue
        clips=[t['m_InfiniteClip']]+[pf.tree(c['m_Asset']['m_PathID']).get('m_Clip',ref(0)) for c in t['m_Clips']]
        if not any(not r['m_FileID'] and r['m_PathID'] and has_body(pf.tree(r['m_PathID'])) for r in clips):continue
        if current.get(i):
            assert current[i]==pf.app['_anim']['m_PathID']
        else:
            rows=[b for b in pf.director['m_SceneBindings'] if b['key']==ref(i)]
            if rows:
                for b in rows:b['value']=deepcopy(pf.app['_anim'])
            else:
                pf.director['m_SceneBindings'].append({'key':ref(i),'value':deepcopy(pf.app['_anim'])})
            current[i]=pf.app['_anim']['m_PathID']

def merge(target, donor, groups, detail, next_id, stream, new_preloads):
    # Keep the animator paths used by the original clips. Reuse the common
    # rig and sprite renderer, and graft each donor's own effects into that rig.
    ids = {0:0, donor.root:target.root, donor.app_id:target.app_id, donor.director_id:target.director_id}
    queue = deque()
    new_objects = {}
    externals = [0] + [1+next(i for i,t in enumerate(target.file.externals) if t.path==s.path)
                       for s in donor.file.externals]
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
                    d['m_FileID'] = externals[d['m_FileID']]
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
    merged_motion = None
    for m in donor.app['motionList']:
        if m['_motiondetail'] not in groups:continue
        assert not m['motionObjects'] and not m['damageObj'] and not m['isSpineAnim']
        if merged_motion is None:
            merged_motion=deepcopy(m)
            merged_motion.update(_motiondetail=detail,timelineAssets=[])
        merged_motion['timelineAssets'].extend(rewrite(deepcopy(m['timelineAssets'])))
    assert len(merged_motion['timelineAssets'])==16
    target.app['motionList'].append(merged_motion)

    bind_attack_bodies(donor,groups)
    bindings = donor.director['m_SceneBindings']
    exposures = donor.director['m_ExposedReferences']['m_References']
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

    sprites={o.peek_name():pid for pid,o in donor.objects.items() if o.type.name=='Sprite' and 'roland' in o.peek_name().lower()}
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
                script.local_serialized_file_index=externals[script.local_serialized_file_index]
                if script not in target.file.script_types:target.file.script_types.append(script)
                st.script_type_index=target.file.script_types.index(script)
            idx=len(target.file.types)
            target.file.types.append(st)
        typemap[obj.type_id]=idx
        return idx
    while queue:
        pid=queue.popleft()
        orig=donor.objects[pid]
        obj=copy(orig)
        data=orig.read_typetree()
        if orig.type.name=='AnimationClip':edits+=replace_body_frames(donor,detail,data,sprites)
        data=rewrite(data)
        obj.assets_file=target.file
        obj.type_id=type_index(orig)
        obj.serialized_type=target.file.types[obj.type_id]
        obj.path_id=ids[pid]
        target.objects[obj.path_id]=obj
        obj.save_typetree(data)
        if obj.type.name in ('Transform','RectTransform','GameObject'):target.edits[obj.path_id]=data

    # Match the donor's preload order. This includes external shaders and
    # MonoScripts present in the stock base prefab's four dependency archives.
    for p in donor.index['m_PreloadTable']:
        if p['m_FileID']:
            new_preloads.append((externals[p['m_FileID']],p['m_PathID']))
        elif p['m_PathID'] in new_objects:
            new_preloads.append((0,new_objects[p['m_PathID']]))
    new_preloads.extend((0,p) for p in new_objects.values())
    print(f'{detail}: copied {len(new_objects)} objects, {edits} donor body references replaced, {len(merged_motion["timelineAssets"])} segments',flush=True)


def merge_prepared(prepared_archive):
    """Merge the three normalized, user-provided Roland bundles."""
    with ZipFile(prepared_archive) as archive:
        base,gun,sword=json.loads(archive.read('resources.json'))
        target=Prefab(archive,base)
        sprites={o.peek_name():pid for pid,o in target.objects.items() if o.type.name=='Sprite' and 'roland' in o.peek_name().lower()}
        for o in target.objects.values():
            if o.type.name=='AnimationClip' and o.peek_name() in ('Index_father_Phase2_Dead','Index_father_Phase2_Special'):
                ct=o.read_typetree()
                if replace_body_frames(target,0,ct,sprites):o.save_typetree(ct)
        bind_attack_bodies(target,tuple(range(7,17))+(20,21,32,33))
        original_motions=deepcopy(target.app['motionList'])
        next_id=iter(range(10000000000,10010000000))
        stream=bytearray(target.env.file.files[target.stream_name].bytes)
        new_preloads=[]
        for asset,groups,detail in [(gun,(7,8,9,15,16),24),(sword,(7,8,9,10,11,12),25)]:
            merge(target,Prefab(archive,asset),groups,detail,next_id,stream,new_preloads)
        target.objects[target.app_id].save_typetree(target.app)
        target.objects[target.director_id].save_typetree(target.director)
        original_size=len(target.index['m_PreloadTable'])
        for k,info in target.index['m_Container']:
            if k.lower()!=base['prefab'].lower():continue
            if len(target.index['m_PreloadTable'])==original_size:
                start,size=info['preloadIndex'],info['preloadSize']
                old=target.index['m_PreloadTable'][start:start+size]
                ordered=dict.fromkeys(new_preloads+[(p['m_FileID'],p['m_PathID']) for p in old])
                target.index['m_PreloadTable'].extend({'m_FileID':f,'m_PathID':p} for f,p in ordered)
            info.update(preloadIndex=original_size,preloadSize=len(target.index['m_PreloadTable'])-original_size)
        target.objects[target.index_id].save_typetree(target.index)
        rd=EndianBinaryReader(bytes(stream))
        rd.flags=target.env.file.files[target.stream_name].flags
        target.env.file.files[target.stream_name]=rd
        encoded=target.env.file.save(packer='lz4')
    check=UnityPy.load(encoded)
    trees={o.path_id:o.read_typetree() for o in check.objects if o.type.name in ('GameObject','MonoBehaviour')}
    motions=trees[target.app_id]['motionList']
    assert motions[:-2]==original_motions
    entry,blob=attack_discovery.from_trees(base['root'],base['address'],trees,'罗兰·漆黑缄默')
    assert entry['verified_attack_details']==list(range(7,17))+[24,25]
    return encoded, blob


def build_roland_bundle(source_archive):
    """Rebuild the unified model locally from the three original bundles."""
    import hashlib
    import re
    import tempfile
    from zipfile import ZIP_STORED
    from skin_assets import ROLAND_MEMBERS
    forms = [('BRoland','BRolandBase'), ('BRolandGun','BRolandGun'),
             ('BRolandUltraSword','BRolandUltraSword')]
    with tempfile.TemporaryDirectory(prefix='faust-roland-') as folder:
        prepared = Path(folder) / 'prepared.zip'
        resources = []
        with ZipFile(source_archive) as source, ZipFile(prepared, 'w', ZIP_STORED) as output:
            for bundle, prefab in forms:
                matches = [i for i in source.infolist() if not i.is_dir()
                           and Path(i.filename.replace('\\','/')).name.lower() == (bundle+'.bundle').lower()]
                if len(matches) != 1:
                    raise ValueError('罗兰资源包缺少唯一的 ' + bundle + '.bundle')
                original = source.read(matches[0])
                if hashlib.sha256(original).hexdigest() != ROLAND_MEMBERS[(bundle+'.bundle').lower()]:
                    raise ValueError('罗兰模型校验失败：' + bundle)
                env = UnityPy.load(original)
                found = [(k,v) for k,v in env.container.items()
                         if k.endswith('/'+prefab+'.prefab') and v.type.name=='GameObject']
                if len(found) != 1: raise ValueError('罗兰模型缺少对应预制体：' + prefab)
                key, root = found[0]
                tree = root.read_typetree(); name = prefab+'Appearance'; tree['m_Name'] = name
                root.deref().save_typetree(tree)
                index = next(o for o in env.objects if o.type.name=='AssetBundle')
                tree = index.read_typetree(); tree['m_Name'] = tree['m_AssetBundleName'] = 'workbench_'+bundle.lower()+'.bundle'
                index.save_typetree(tree)
                streams = [n for n in env.file.files if n.endswith('.resS')]
                if len(streams)!=1: raise ValueError('罗兰模型纹理资源不完整：' + bundle)
                match=re.fullmatch(r'(CAB-[a-f0-9]{32})\.resS',streams[0])
                if not match: raise ValueError('罗兰模型资源标识无效：' + bundle)
                own=match.group(1); unique='CAB-'+hashlib.sha256(('workbench.roland.'+bundle).encode()).hexdigest()[:32]
                raw=env.file.save(packer='none')
                if own.encode() not in raw: raise ValueError('罗兰模型资源标识缺失：' + bundle)
                raw=raw.replace(own.encode(),unique.encode()).replace(own.lower().encode(),unique.lower().encode())
                encoded=UnityPy.load(raw).file.save(packer='lz4')
                member='Bundles/'+bundle+'.bundle';output.writestr(member,encoded)
                resources.append({'address':'Roland/'+prefab+'.prefab','file':member,'prefab':key,'root':name})
            output.writestr('resources.json',json.dumps(resources,ensure_ascii=False).encode('utf8'))
        return merge_prepared(prepared)
