import copy, math
SCHEMA=1
def apply_custom_pools(pools, config):
 if config.get('schema')!=SCHEMA:raise ValueError('不支持的自定义池版本')
 catalog={}
 for pool in pools.values():
  for entry in pool['entries']:
   identity=str(entry['identity_id'])
   if identity in catalog:raise ValueError('人格目录存在重复ID: '+identity)
   catalog[identity]=entry
 result=copy.deepcopy(pools)
 for target,profile in config.get('characters',{}).items():
  if str(target) not in result:raise ValueError('无效出战角色: '+str(target))
  if not profile.get('enabled',False):continue
  selected=[];seen=set()
  for item in profile.get('entries',[]):
   identity=str(item['identity_id']);weight=float(item['weight'])
   if identity not in catalog:raise ValueError('未知人格: '+identity)
   if identity in seen:raise ValueError('同一池存在重复人格: '+identity)
   if not math.isfinite(weight) or not 0<=weight<=1000000:raise ValueError('无效权重')
   seen.add(identity);entry=copy.deepcopy(catalog[identity]);entry['weight']=weight;selected.append(entry)
  if not any(e['weight']>0 for e in selected):raise ValueError('自定义池至少需要一个正权重人格')
  if len(selected)>256:raise ValueError('当前版本每个池最多256个人格')
  result[str(target)]['entries']=selected
 return result
