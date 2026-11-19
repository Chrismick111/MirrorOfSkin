"""Read only the exact pool prefabs, their motion Timelines, active tracks and FMOD clips."""
import argparse
from collections import defaultdict
import gc
import gzip
import json
from pathlib import Path
import sys
import warnings
from appearance_voice_fmod import event_strings


def scan(env, asset, events, external):
    matches=[g for k,g in env.container.items() if k==asset and g.type.name=='GameObject']
    if len(matches)!=1:raise ValueError('Expected one prefab GameObject, found '+str(len(matches)))
    go=matches[0]
    cache={};owners={}
    unresolved=set()
    def tree(ref,parent=None):
        fid,pid=ref['m_FileID'],ref['m_PathID']
        if not pid: return {}
        owner=owners[id(parent)] if parent is not None else go.assetsfile
        if fid:
            owner=external(owner.externals[fid-1].path.rsplit('/',1)[-1].lower())
        if owner is None or pid not in owner.objects:
            unresolved.add((fid,pid))
            return {}
        key=(id(owner),pid)
        if key not in cache:
            cache[key]=owner.objects[pid].read_typetree()
            owners[id(cache[key])]=owner
        return cache[key]
    components=go.read_typetree()['m_Component']
    motions=[m for component in components for m in tree(component['component']).get('motionList',[])]
    clips=[]; n=0
    for motion in motions:
        for i,ref in enumerate(motion.get('timelineAssets',[])):
            tl=tree(ref)
            if not tl:continue
            n+=1
            stack=[(track,False,tl) for track in tl.get('m_Tracks',[])]
            while stack:
                ref,ancestor_voice,parent=stack.pop()
                track=tree(ref,parent)
                if not track or track.get('m_Muted'):continue
                voice=ancestor_voice or 'voice' in track.get('m_Name','').lower()
                stack.extend((child,voice,track) for child in track.get('m_Children',[]))
                for c in track.get('m_Clips',[]):
                    clip=tree(c['m_Asset'],track)
                    guids=[clip.get('EventReference',{}),clip.get('Template',{}).get('EventReference',{}) if isinstance(clip.get('Template'),dict) else {}]
                    resolved=set()
                    for entry in guids:
                        guid=entry.get('Guid',{}) if isinstance(entry,dict) else {}
                        if guid:
                            path=events.get(tuple(guid.get('Data'+str(k)) for k in range(1,5)))
                            if path and (voice or path.startswith('event:/Voice/')):resolved.add(path)
                    for path in sorted(resolved):
                        clips.append([tl['m_Name'],motion['_motiondetail'],i,c['m_Start'],path,c.get('m_DisplayName','')])
    return dict(game_object=go.path_id,timelines=n,motions=len(motions),unresolved_refs=sorted(unresolved),events=clips)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ['plugin','game-data','cache','output']:parser.add_argument('--'+arg,type=Path,required=True)
    parser.add_argument('--unitypy',type=Path)
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--repair-unresolved',action='store_true')
    args=parser.parse_args()
    if args.unitypy:sys.path.insert(0,str(args.unitypy))
    import UnityPy
    UnityPy.config.FALLBACK_UNITY_VERSION='6000.3.12f1'
    warnings.filterwarnings('ignore')
    events=event_strings(args.game_data)
    external_files={}
    cab_names=json.loads(gzip.decompress(sorted((args.archive/'cab_index').glob('*.gz'))[-1].read_bytes())) if args.archive else {}
    def external(cab):
        if cab not in external_files:
            external_files[cab]=None
            if cab in cab_names:
                for f in (args.archive/'bundle_index').glob(cab_names[cab]+'_*.json.gz'):
                    digest=f.name.removesuffix('.json.gz').rsplit('_',1)[-1]
                    for local in args.cache.glob('*/'+digest+'/__data'):
                        env=UnityPy.load(str(local))
                        for file in env.assets:
                            if file.name.lower()==cab:external_files[cab]=file
        return external_files[cab]
    pool=json.loads((args.plugin/'Assets/runtime/all_sinners_pools.json').read_text('utf8'))
    apps={u['appearance_name'] for v in pool.values() for u in v['entries']}
    index=json.loads((args.plugin/'Workbench/resource-cache/resource-index.json').read_text('utf8'))
    groups={b:{a:k for a,k in d['prefabs'].items() if a in apps} for b,d in index['entries'].items()}
    groups={b:g for b,g in groups.items() if g}
    result=defaultdict(list); errors=[]
    if args.repair_unresolved:
        prior=json.loads(args.output.read_text('utf8'))
        retry={a for a,rs in prior['appearances'].items() if any(r['unresolved_refs'] for r in rs)}
        retry.update(apps-prior['appearances'].keys())
        result.update({a:rs for a,rs in prior['appearances'].items() if a not in retry})
        groups={b:{a:k for a,k in g.items() if a in retry} for b,g in groups.items() if retry.intersection(g)}
    for n,(b,g) in enumerate(sorted(groups.items(),key=lambda x:'400003_QueenOfHatred' not in x[1])):
        try:
            env=UnityPy.load(str(args.cache/b))
            for app,asset in g.items():
                try:
                    row=scan(env,asset,events,external)
                    result[app].append(dict(bundle=b,asset=asset,**row))
                except Exception as ex:errors.append([b,app,str(ex)])
            del env
            gc.collect()
        except Exception as ex:errors.append([b,None,str(ex)])
        if n%20==0 or n+1==len(groups):
            print(n+1,len(groups),len(result),len(errors),flush=True)
            args.output.write_text(json.dumps(dict(appearances=result,errors=errors),ensure_ascii=False),'utf8')
if __name__=='__main__':main()
