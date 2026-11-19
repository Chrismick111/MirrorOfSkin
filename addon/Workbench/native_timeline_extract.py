"""Read game Unity bundles only. Requires Python 3.12 and UnityPy; no Archive data."""
import argparse,json,math,pathlib,sys
import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION='6000.3.0f1'
def scalar(v,depth=0):
 if v is None or isinstance(v,(str,bool,int)):return v
 if isinstance(v,float):return v if math.isfinite(v) else None
 if hasattr(v,'m_PathID'):return {'file_id':v.m_FileID,'path_id':str(v.m_PathID)}
 if isinstance(v,(list,tuple)):return [scalar(x,depth+1) for x in v[:512]] if depth<4 else '<depth-limit>'
 if hasattr(v,'__dict__') and depth<4:return {k:scalar(x,depth+1) for k,x in vars(v).items() if k not in ('object_reader','assetsfile') and not k.startswith('_')}
 return str(v)
def resolve(ref):
 if not ref or not ref.m_PathID:return {'status':'null'}
 try:
  x=ref.read();return {'status':'resolved','name':getattr(x,'m_Name',None),'fields':scalar(x)}
 except Exception as e:return {'status':'unresolved','error':str(e),'ref':scalar(ref)}
def tracks(timeline,script_resolver=None):
 out=[];seen=set()
 def walk(ref,parent=None,path=()):
  key=(ref.m_FileID,ref.m_PathID)
  if key in seen:return
  seen.add(key)
  try:
   t=ref.read();row={'name':getattr(t,'m_Name',''),'ref':scalar(ref),'parent':parent,'track_path':list(path),'script':script_resolver.resolve(getattr(t,'m_Script',None)) if script_resolver else resolve(getattr(t,'m_Script',None)),'muted':getattr(t,'m_Muted',None),'clips':[],'markers':[]}
   for c in getattr(t,'m_Clips',[]) or []:
    row['clips'].append({'name':getattr(c,'m_DisplayName',None),'start':getattr(c,'m_Start',None),'duration':getattr(c,'m_Duration',None),'asset':resolve(getattr(c,'m_Asset',None))})
   markers=getattr(getattr(t,'m_Markers',None),'m_Objects',[]) or []
   for p in markers:row['markers'].append(resolve(p))
   out.append(row)
   for i,p in enumerate(getattr(t,'m_Children',[]) or []):walk(p,row['name'],path+(i,))
  except Exception as e:out.append({'ref':scalar(ref),'status':'unresolved','error':str(e)})
 for i,ref in enumerate(getattr(timeline,'m_Tracks',[]) or []):walk(ref,None,(i,))
 return out
def extract(bundle,appearance,script_resolver=None):
 env=UnityPy.load(bundle);variants=[];errors=[]
 for obj in env.objects:
  try:
   if obj.type.name!='MonoBehaviour':continue
   d=obj.read()
   if not hasattr(d,'motionList') or d.m_GameObject.read().m_Name!=appearance:continue
   motions=[]
   for m in d.motionList:
    parts=[]
    for i,ref in enumerate(m.timelineAssets or []):
     part={'index':i,'ref':scalar(ref)}
     try:
      t=ref.read();part.update({'name':getattr(t,'m_Name',None),'duration_mode':getattr(t,'m_DurationMode',None),'fixed_duration':getattr(t,'m_FixedDuration',None),'tracks':tracks(t,script_resolver),'status':'resolved'})
     except Exception as e:part.update({'status':'unresolved','error':str(e)})
     parts.append(part)
    motions.append({'detail':m._motiondetail,'parts':parts})
   variants.append({'owner_path_id':str(obj.path_id),'motions':motions})
  except Exception as e:
   if len(errors)<30:errors.append({'path_id':str(obj.path_id),'error':str(e)})
 return {'bundle':bundle,'appearance':appearance,'variants':variants,'object_errors_sample':errors,'note':'Game bundle fields only; fixed_duration is not necessarily playback duration. Unresolved pointers remain explicit.'}
def main():
 p=argparse.ArgumentParser();p.add_argument('bundle');p.add_argument('appearance');p.add_argument('--output',required=True);a=p.parse_args();r=extract(a.bundle,a.appearance);pathlib.Path(a.output).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8');print('variants',len(r['variants']),'object_errors_sample',len(r['object_errors_sample']));return 0 if r['variants'] else 2
if __name__=='__main__':sys.exit(main())
