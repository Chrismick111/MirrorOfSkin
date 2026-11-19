"""Resolve external MonoScripts from the user's own cache, without Archive."""
import pathlib
import threading
import UnityPy
import resource_identity

class ScriptResolver:
 def __init__(self,root):
  self.root=pathlib.Path(root).resolve();self.cabs={};self.failures=[];self.loaded=False;self.lock=threading.Lock()
 def _load(self):
  if self.loaded:return
  for folder in sorted(self.root.glob('*_monoscripts')):
   for path in sorted(folder.rglob('__data')):
    try:
     rel=path.resolve().relative_to(self.root).as_posix()
     info=resource_identity.bundle_info(self.root,rel)
     env=UnityPy.load(str(path)); found={}
     for o in env.objects:
      if o.type.name!='MonoScript':continue
      cab=o.assets_file.name.lower();obj=o.read()
      found.setdefault((cab,id(o.assets_file)),{})[str(o.path_id)]={'class':obj.m_ClassName,'namespace':obj.m_Namespace,'assembly':obj.m_AssemblyName}
     if resource_identity.bundle_info(self.root,rel)!=info:raise ValueError('bundle changed while reading')
     for (cab,_),objects in found.items():self.cabs.setdefault(cab,[]).append((info,objects))
    except Exception as exc:self.failures.append({'bundle':str(path),'error':str(exc)})
  self.loaded=True
 def resolve(self,ref):
  try:
   with self.lock:self._load()
   if self.failures:return {'status':'unresolved','reason':'some script bundles failed to load'}
   if ref is None or not ref.m_PathID:return {'status':'unresolved','reason':'empty script reference'}
   owner=ref.assetsfile
   if ref.m_FileID==0:cab=owner.name.lower()
   elif 0<ref.m_FileID<=len(owner.externals):cab=owner.externals[ref.m_FileID-1].name.lower()
   else:return {'status':'unresolved','reason':'invalid external file id'}
   candidates=self.cabs.get(cab,[])
   if len(candidates)!=1:return {'status':'unresolved','reason':'missing or ambiguous script CAB','cab':cab,'candidates':len(candidates)}
   info,objects=candidates[0];result=objects.get(str(ref.m_PathID))
   if not result:return {'status':'unresolved','reason':'script id missing','cab':cab,'path_id':str(ref.m_PathID)}
   return dict(result,status='resolved',cab=cab,path_id=str(ref.m_PathID),source=info)
  except Exception as exc:return {'status':'unresolved','reason':str(exc)}

_cache_lock=threading.Lock()
_cache={}
def shared(root):
 """Reuse index while cached script bundle metadata is unchanged."""
 root=pathlib.Path(root).resolve(); entries=[]
 for folder in root.glob('*_monoscripts'):
  for p in folder.rglob('__data'):
   stat=p.stat();entries.append((str(p.relative_to(root)),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns))
 signature=tuple(sorted(entries));key=str(root)
 with _cache_lock:
  current=_cache.get(key)
  if current is None or current[0]!=signature:
   current=(signature,ScriptResolver(root));_cache[key]=current
  return current[1]