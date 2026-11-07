import copy

def complete_snapshot(catalog,selected,previous):
 # Retain all canonical identities and prior cross-role rows at zero weight.
 result=copy.deepcopy(catalog)
 for target,pool in result.items():
  rows={str(e['identity_id']):dict(e,weight=0) for e in pool['entries']}
  for e in previous.get(target,[]):rows.setdefault(str(e['identity_id']),dict(e,weight=0))
  active=selected[target]['entries'];active_ids={str(e['identity_id']) for e in active}
  pool['entries']=copy.deepcopy(active)+[e for k,e in rows.items() if k not in active_ids]
 if sum(len(p['entries']) for p in result.values())>4096:raise ValueError('运行时人格目录超过4096项，未应用此次修改')
 return result
