"""Add uniquely identified sinner appearances to the selectable catalog."""
import re

def merge(pools, discovered, metadata):
    groups={}
    for name,item in discovered.items():
        match=re.fullmatch(r'(10[1-9]|11[0-2])\d{2}_[A-Za-z0-9_]+Appearance',name)
        if not match or item.get('group_confidence')!='catalog':continue
        key=item.get('asset_key','')
        if key != 'SD_Personality/'+name+'.prefab':continue
        ident=name[:5];groups.setdefault(ident,[]).append((name,item,match.group(1)))
    known={str(e.get('identity_id','')) for p in pools.values() for e in p.get('entries',[])}
    added=[]; ambiguous=[]
    for ident, choices in sorted(groups.items()):
        if ident in known:continue
        if len(choices)!=1:ambiguous.append(ident);continue
        name,item,sinner=choices[0];label=metadata.resolve_label(name)
        pools.setdefault(sinner,{'entries':[]}).setdefault('entries',[]).append({'identity_id':ident,'appearance_name':name,'asset_key':item['asset_key'],'forms':[name], 'name':label['name'],'weight':0,'translation_status':label['translation_status'],'discovery_source':'local_cache'})
        known.add(ident);added.append(ident)
    return added,ambiguous
