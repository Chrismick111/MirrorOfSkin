"""Build story contracts from serialized, locally cached timeline data."""
import boss_importer

def refs(value):
    if isinstance(value,dict):
        if 'm_PathID' in value:
            if not value.get('m_FileID'): yield value['m_PathID']
        else:
            for k,v in value.items():
                if k not in ('m_Parent','m_Script','m_GameObject'): yield from refs(v)
    elif isinstance(value,list):
        for v in value: yield from refs(v)

def gather(pid,trees):
    seen=set(); stack=[pid]; out=[]
    while stack:
        p=stack.pop()
        if p in seen: continue
        seen.add(p); tree=trees.get(p)
        if tree is not None: out.append(tree); stack.extend(refs(tree))
    return out

def from_trees(name,key,trees,display_name):
    owners={p:t.get('m_Name') for p,t in trees.items() if 'm_Component' in t}
    apps=[t for t in trees.values() if 'motionList' in t and owners.get(t.get('m_GameObject',{}).get('m_PathID'))==name]
    if not apps: raise ValueError('appearance motion list not found')
    grouped={}
    for app in apps:
        for motion in app.get('motionList',[]):
            detail=motion.get('_motiondetail'); timelines=motion.get('timelineAssets') or []
            if isinstance(detail,int) and (7<=detail<=16 or 24<=detail<=34) and timelines:
                grouped.setdefault(detail,[]).append(timelines)
    candidate=[]; rows=[]
    for detail, variants in grouped.items():
        if any(x!=variants[0] for x in variants): continue
        items=[]; contracts=[]
        for i,ref in enumerate(variants[0]):
            pid=ref.get('m_PathID'); tree=trees.get(pid)
            if ref.get('m_FileID') or not pid or not tree: break
            parts=gather(pid,trees)
            damages=[x for x in parts if 'm_Time' in x and 'ratios' in x and 'sturnInfo' in x]
            if not damages: break
            if tree.get('m_DurationMode')==1 and tree.get('m_FixedDuration',0)>0: duration=tree['m_FixedDuration']
            else:
                ends=[float(x['m_Time']) for x in parts if 'm_Time' in x]
                ends += [c['m_Start']+c['m_Duration'] for p in parts for c in p.get('m_Clips',[]) if isinstance(c,dict) and 'm_Start' in c and 'm_Duration' in c]
                duration=max(ends,default=0)
            damage=min(damages,key=lambda x:x['m_Time']); delay=damage.get('info',{}).get('afterDelay')
            if delay is None: break
            items.append({'motionIndex':i,'duration':duration,'hitMarkerTime':damage['m_Time'],'endMarkerTime':-1,'giveDamageDelay':delay})
            contracts.append({'name':tree.get('m_Name'),'null':False})
        if len(items)==len(variants[0]):
            rows.append({'motionDetail':detail,'motionTimelineDatas':items})
            candidate.append({'detail':detail,'timelines':contracts})
    metadata={'AppearanceName':name,'motionList':rows}
    entry,blob=boss_importer.build_entry({'appearance':name,'motions':candidate},metadata,key,display_name=display_name)
    entry.update(category='humanoid_boss',verified_attack_details=[r['motionDetail'] for r in rows],metadata_evidence='serialized timelines')
    return entry,blob

def read_trees(path,unity):
    env=unity.load(str(path)); trees={}
    for obj in env.objects:
        if obj.type.name in ('MonoBehaviour','GameObject'):
            try: trees[obj.path_id]=obj.read_typetree()
            except Exception: pass
    return trees
