"""Stable bundle provenance for offline resource plans."""
import hashlib,pathlib

def bundle_info(root, relative):
 root=pathlib.Path(root).resolve(); path=(root/relative).resolve()
 if root not in path.parents or not path.is_file(): raise ValueError('resource bundle outside cache or missing')
 rel=path.relative_to(root).as_posix()
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return {'bundle_path':rel,'bundle_key':hashlib.sha256(rel.casefold().encode('utf8')).hexdigest(),'bundle_sha256':h.hexdigest()}

def motion_key(r):
 return '{}:{}:{}:{}'.format(r.get('detail'),r.get('index'),r.get('path_id') or r.get('name'),r.get('bundle_key'))

def verify_plan(root, plan):
 """Rehash source bundles immediately before handoff; do not apply changes."""
 if not isinstance(plan,dict) or plan.get('format')!='personality-workbench.effect-plan' or plan.get('version')!=4 or not isinstance(plan.get('operations'),list):
  raise ValueError('unsupported plan')
 cache={}
 for op in plan['operations']:
  if not isinstance(op,dict) or not isinstance(op.get('bundle_path'),str) or not op['bundle_path']:
   raise ValueError('missing source bundle')
  path=op['bundle_path']
  if path not in cache: cache[path]=bundle_info(root,path)
  actual=cache[path]
  if any(op.get(key)!=actual[key] for key in ('bundle_path','bundle_key','bundle_sha256')):
   raise ValueError('source bundle changed: '+path)
  kind=op.get('track_type')
  if not isinstance(kind,dict) or kind.get('class')!='EffectActivateTimelineTrack' or any(not isinstance(kind.get(k),str) for k in ('assembly','namespace','cab','path_id')):
   raise ValueError('missing or invalid track type')
  source=kind.get('source')
  if not isinstance(source,dict) or not isinstance(source.get('bundle_path'),str) or not source['bundle_path']:
   raise ValueError('missing track script source')
  script_path=source['bundle_path']
  if script_path not in cache: cache[script_path]=bundle_info(root,script_path)
  if any(source.get(key)!=cache[script_path][key] for key in ('bundle_path','bundle_key','bundle_sha256')):
   raise ValueError('track script bundle changed: '+script_path)
 return {'verified_bundles':len(cache),'verified_operations':len(plan['operations'])}
