"""Add cached appearances without attack evidence to the selectable catalog."""
import copy
import re
import discovery_metadata

def has_attack(motions):
    return any(isinstance(m,(list,tuple)) and len(m)>=2 and isinstance(m[0],int)
               and (7<=m[0]<=16 or 24<=m[0]<=34) and m[1]>0 for m in motions)

def merge(pools, report, index):
    result=copy.deepcopy(pools)
    existing={e.get('appearance_name'):e for group in result.values() for e in group.get('entries',[])}
    added=0
    for name, item in report.get('units',{}).items():
        motions=item.get('motions') or []
        if has_attack(motions): continue
        key=item.get('asset_key')
        if not isinstance(key,str) or not re.fullmatch(r'SD_(?:Enemy|Personality|Abnormality|EGO|DeadScene)/[A-Za-z0-9_]+\.prefab',key): continue
        if key.rsplit('/',1)[-1] != name+'.prefab' or len(name.encode('ascii'))>=58: continue
        entry=existing.get(name)
        if entry is not None:
            # An empty scanner result can mean parsing failed; don't override
            # already verified attack metadata for an existing appearance.
            if entry.get('category') != 'humanoid_boss' or entry.get('verified_attack_details'): continue
            metadata=entry.get('story_metadata') or {}
            if any(isinstance(row,dict) and isinstance(row.get('motionDetail'),int)
                   and (7<=row['motionDetail']<=16 or 24<=row['motionDetail']<=34)
                   and row.get('motionTimelineDatas') for row in metadata.get('motionList',[])): continue
            entry['no_attack']=True
            entry['motion_status']='unknown' if not motions else 'no_attack_observed'
            continue
        meta=discovery_metadata.resolve(index,name)
        entry={'sinner':'101','identity_id':'story_'+name,'appearance_name':name,
               'asset_key':key,'forms':[name],'name':meta['name'],'weight':0,
               'category':'humanoid_boss','no_attack':True,
               'motion_status':'unknown' if not motions else 'no_attack_observed',
               'translation_status':meta['translation_status'],
               'chapter':meta['category'],'chapter_label':meta['category_label'],
               'chapter_memberships':meta['category_memberships'] or [{'chapter':meta['category'],'label':meta['category_label']}],
               'discovery_source':'local_cache'}
        result['101']['entries'].append(entry);existing[name]=entry;added+=1
    return result,added
