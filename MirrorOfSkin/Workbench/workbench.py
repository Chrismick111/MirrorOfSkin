# -*- coding: utf-8 -*-
import sys
from pathlib import Path
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import _module_paths
import prepare_view
import mos_data
import feature_settings
import chapter_nine
import imported_catalog
import chapter_cards
import chapter_categories
import name_translations
import local_portraits
import walpurgis_catalog
from urllib.parse import unquote, quote
from file_lock import FileLock
import director
import stage_files
import custom_portraits
import imported_portraits
import mod_packages
import rulesets
import group_entries
import schemes
import effect_schemes
import effect_timelines
import sprite_gallery
import sprite_export
import sprite_jobs
import resource_catalog
import effect_plan
import fx_activation
import instance_control
import host_lifetime
import skin_import_jobs
import struct
import socket
import select
import subprocess
import argparse,hashlib,importlib.util,json,math,os,pathlib,re,secrets,threading,time,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

_STARTUP_VERSION=''
try:
 _STARTUP_VERSION=json.loads((pathlib.Path(__file__).resolve().parent.parent/'addon_info.json').read_text(encoding='utf-8-sig')).get('version','')
except Exception:
 pass
_BUILD_FILE='Workbench/server_build.json'

_PORTRAIT_LOCK=threading.Lock()
_PORTRAIT_THREAD=None
_PORTRAIT_JOB={'stage':'idle','done':0,'total':0,'percent':0,'message':'等待开始','updated':0}

_CHILD_LOCK=threading.Lock()
_CHILDREN=set()
_CHILD_STOPPING=False
def _spawn_child(*args,**kwargs):
 with _CHILD_LOCK:
  if _CHILD_STOPPING:raise RuntimeError('工作台正在退出')
  proc=subprocess.Popen(*args,**kwargs);_CHILDREN.add(proc);return proc
def _forget_child(proc):
 with _CHILD_LOCK:_CHILDREN.discard(proc)

def _workbench_script(name):
 base=_HERE
 for folder in ('scan','fx','pool','core','tools'):
  path=base/folder/name
  if path.is_file():return path
 for path in base.rglob(name):
  if path.is_file():return path
 return base/name
def _stop_children():
 global _CHILD_STOPPING
 with _CHILD_LOCK:_CHILD_STOPPING=True;children=list(_CHILDREN)
 for proc in children:
  try:
   if proc.poll() is None:proc.terminate()
  except OSError:pass
 for proc in children:
  try:proc.wait(timeout=5)
  except subprocess.TimeoutExpired:
   try:proc.kill();proc.wait(timeout=2)
   except OSError:pass

def _pick_local_skins():
 picked=_spawn_child(['powershell.exe','-NoProfile','-STA','-ExecutionPolicy','RemoteSigned','-File',
                      str(_HERE/'import_local.ps1'),'-PickOnly'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                     encoding='utf8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 try:out,err=picked.communicate()
 finally:_forget_child(picked)
 if picked.returncode:raise ValueError('打开文件选择窗口失败：'+err.strip()[-300:])
 return json.loads(out) if out.strip() else []

def _portrait_state():
 with _PORTRAIT_LOCK:return dict(_PORTRAIT_JOB)

def _portrait_update(stage,done=0,total=0,message=''):
 percent=100 if stage=='done' else (round(done*100/total,1) if total else 0)
 with _PORTRAIT_LOCK:
  _PORTRAIT_JOB.update(stage=stage,done=done,total=total,percent=percent,message=message,updated=time.time())

def _portrait_run(root):
 try:
  script=_workbench_script('resource_scan.py')
  flags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0)
  env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
  proc=_spawn_child([sys.executable,str(script),'--addon',str(root)],cwd=str(root),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace',creationflags=flags,env=env)
  details=[];result={}
  for line in proc.stdout:
   try:
    event=json.loads(line)
    if event.get('stage')=='done':result=event
    elif event.get('stage')=='error':details.append(event.get('message','资源读取失败'))
    else:_portrait_update('download',event.get('done',0),event.get('total',0),event.get('message','正在检索本地游戏资源'))
   except (ValueError,TypeError):details.append(line.strip())
  code=proc.wait();_forget_child(proc)
  if code:raise RuntimeError((details[-1] if details else '本地资源检索失败，请确认游戏已安装并运行过')[:400])
  with _PORTRAIT_LOCK:_PORTRAIT_JOB['result']=result
  _portrait_update('done',1,1,result.get('message','本地资源检索完成'))
  try:pathlib.Path(root,'Workbench/first_image_scan.done').write_text('1',encoding='ascii')
  except OSError:pass
  try:pathlib.Path(root,'Workbench/portrait_last_error.txt').unlink(missing_ok=True)
  except OSError:pass
 except Exception as exc:
  with _PORTRAIT_LOCK:
   _PORTRAIT_JOB.update(stage='error',message=str(exc),updated=time.time())
   _PORTRAIT_JOB.pop('result',None)
  # The job state lives in memory only, so a failed first run left no trace at all.
  try:pathlib.Path(root,'Workbench/portrait_last_error.txt').write_text(str(exc)+'\n',encoding='utf8')
  except OSError:pass

def _delete_images(root):
 root=pathlib.Path(root);wb=root/'Workbench';count=0;size=0
 with FileLock(wb/'image_resources.lock'):
  (wb/'images_disabled.flag').write_text('图片已关闭；点击下载资源恢复。\n',encoding='utf8')
  for folder in ('portraits','local_portraits','chapter_art'):
   path=wb/folder
   if path.is_symlink() or not path.is_dir():continue
   for file in path.iterdir():
    if file.is_symlink() or not file.is_file() or file.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):continue
    size+=file.stat().st_size;file.unlink();count+=1
 return {'count':count,'bytes':size}

def _portraits_missing(root):
 folder=pathlib.Path(root)/'Workbench/portraits'
 try:return not any(p.suffix.lower()=='.png' for p in folder.iterdir())
 except OSError:return True

def _portrait_start(root):
 global _PORTRAIT_THREAD
 with _PORTRAIT_LOCK:
  if _PORTRAIT_THREAD is not None and _PORTRAIT_THREAD.is_alive():return False
  _PORTRAIT_JOB.pop('result',None)
  _PORTRAIT_JOB.update(stage='starting',done=0,total=0,percent=0,message='准备检索本地资源',updated=time.time())
  _PORTRAIT_THREAD=threading.Thread(target=_portrait_run,args=(root,),name='PortraitDownload',daemon=True)
  _PORTRAIT_THREAD.start()
 return True

def _first_portrait_start(root):
 wb=pathlib.Path(root)/'Workbench'
 if (wb/'images_disabled.flag').exists() or (wb/'first_image_scan.done').exists():return False
 for folder in ('portraits','local_portraits','user_portraits'):
  path=wb/folder
  if path.is_dir() and any(p.is_file() and p.suffix.lower()=='.png' for p in path.iterdir()):return False
 return _portrait_start(root)

def _ruleset_payload(store):
 state, items, selected, entries, revision = store.ruleset_snapshot()
 return {'state': state, 'rulesets': items, 'activeRule': selected, 'entries': entries, 'revision': revision}

def read(path,default):
 try:return json.loads(path.read_text(encoding='utf-8-sig'))
 except FileNotFoundError:return default

def parse_event(line):
 fields=dict(re.findall(r'(\w+)=([^\s]+)',line));match=re.search(r'\]\s*([^=]+?)(?:\s+\w+=|$)',line)
 return {'raw':line,'kind':fields.get('event') or (match.group(1).strip() if match else '原生日志'),'fields':fields,'coin_type':{'unbreakable':'红色／不可摧毁','normal':'普通','unknown':'未确认'}.get(fields.get('coinType'),'未记录')}

def add_boss_members(profile,catalog,chapter=None):
 entries=[dict(e) for e in profile.get('entries',[])];seen={str(e['identity_id']) for e in entries}
 bosses=[str(e['identity_id']) for e in catalog if e.get('category')=='humanoid_boss' and (not chapter or any(g.get('chapter')==chapter for g in e.get('chapter_memberships',[{'chapter':e.get('chapter','unassigned')}])) )]
 for identity in bosses:
  if identity not in seen:entries.append({'identity_id':identity,'weight':1});seen.add(identity)
 if len(entries)>256:raise ValueError('加入Boss后超过每池256项，请先移除部分成员或逐项选择')
 return dict(profile,entries=entries)

class Store:
 def __init__(self,root):
  self.addon_root=pathlib.Path(root).resolve()
  self.root=mos_data.prepare(self.addon_root)
  self.evidence=prepare_view.SessionEvidence(self.root/'native_runtime.log')
  self.lock=FileLock(self.root/'workbench-save.lock');self.portraits=read(self.root/'Workbench/portrait_manifest.json',{});self.local_portraits=local_portraits.load(self.root)
  with self.lock:
   chapter_nine.migrate(self.root,stage_files)
  from voice_binding import refresh_saved_bindings
  try:
   refresh_saved_bindings(self.root)
  except (OSError,ValueError,TypeError,KeyError,TimeoutError) as error:
   print(f'外来语音绑定未能刷新：{error}',file=sys.stderr)
 def _launcher_background_init(self):
  if hasattr(self,'_launcher_bg_files'):return
  self._launcher_bg_files=[];self._launcher_bg_blur=7.5;self._launcher_bg_path=None
  try:
   launcher=self.addon_root.parent.parent
   settings=read(launcher/'config/settings.json',{})
   if not isinstance(settings,dict):settings={}
   blur_row=settings.get('bg_gaussian_blur_factor')
   try:blur=float(blur_row.get('value',3) if isinstance(blur_row,dict) else 3)
   except (TypeError,ValueError):blur=3
   self._launcher_bg_blur=round(max(0.0,min(10.0,blur))*2.5,1)
   skin_row=settings.get('skin')
   skin=str(skin_row.get('value') or '') if isinstance(skin_row,dict) else ''
   dirs=[]
   if skin:dirs.append(launcher/'_internal/web/app_skins'/skin/'assets/launcher/background')
   dirs.append(launcher/'assets/images/background')
   for folder in dirs:
    if not folder.is_dir():continue
    files=[p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.jpg','.jpeg','.png','.webp','.bmp')]
    if files:
     self._launcher_bg_files=files;break
  except (OSError,ValueError,TypeError):pass
 def _launcher_background_result(self,path):
  return {'url':'api/launcher-background','name':path.name,'blur':self._launcher_bg_blur,'mask':0.5,'count':len(self._launcher_bg_files)}
 def launcher_background(self):
  cached=getattr(self,'_launcher_bg',None)
  if cached is not None:return cached
  self._launcher_background_init()
  result={}
  if self._launcher_bg_files:
   import random
   self._launcher_bg_index=random.randrange(len(self._launcher_bg_files))
   self._launcher_bg_path=self._launcher_bg_files[self._launcher_bg_index]
   result=self._launcher_background_result(self._launcher_bg_path)
  self._launcher_bg=result
  return result
 def launcher_background_next(self):
  self._launcher_background_init()
  files=self._launcher_bg_files
  if not files:return self.launcher_background()
  if len(files)>1:
   import random
   current=getattr(self,'_launcher_bg_index',-1)
   self._launcher_bg_index=random.choice([i for i in range(len(files)) if i!=current])
   self._launcher_bg_path=files[self._launcher_bg_index]
   self._launcher_bg=self._launcher_background_result(self._launcher_bg_path)
  elif not getattr(self,'_launcher_bg',None):
   self.launcher_background()
  return self._launcher_bg
 def launcher_background_image(self):
  self.launcher_background()
  path=getattr(self,'_launcher_bg_path',None)
  if path is None or not path.is_file():return None,None
  ctype={'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp','.bmp':'image/bmp'}.get(path.suffix.lower(),'application/octet-stream')
  return path.read_bytes(),ctype
 def _refresh_local_portraits(self):
  path=self.root/'Workbench/local_portraits/local_portraits.json'
  try:stamp=path.stat().st_mtime_ns
  except OSError:stamp=None
  if getattr(self,'_local_portrait_stamp',object())!=stamp:
   self.local_portraits=local_portraits.load(self.root);self._local_portrait_stamp=stamp
 def portrait(self,identity):
  self._refresh_local_portraits()
  custom=custom_portraits.get(self.root,identity)
  if custom is not None:return custom
  imported=imported_portraits.get(self.root,identity)
  if imported is not None:return imported
  if isinstance(identity,str) and re.fullmatch(r'[A-Za-z0-9_-]+',identity):
   path=getattr(self,'addon_root',self.root)/'Workbench/data/bundled_portraits'/(identity+'.png')
   if path.is_file():return path.read_bytes()
  row=self.portraits.get(identity,{})
  name=row.get('file','')
  if name and pathlib.Path(name).name==name and '/' not in name and '\\' not in name and name.endswith('.png'):
   path=self.root/'Workbench/portraits'/name
   if path.is_file():return path.read_bytes()
  return local_portraits.get(self.root,self.local_portraits,identity)
 def snapshot(self):
  p=self.root/'custom_pools.json';data=p.read_bytes() if p.exists() else b''
  return {'revision':hashlib.sha256(data).hexdigest(),'config':json.loads(data.decode('utf-8-sig')) if data else {'schema':1,'characters':{}}}
 def settings_snapshot(self):
  p=self.root/'random_settings.json';data=p.read_bytes() if p.exists() else b''
  return {'revision':hashlib.sha256(data).hexdigest(),'config':json.loads(data.decode('utf-8-sig')) if data else {'enabled':True,'characters':{}}}
 def feature_settings_snapshot(self):
  p=self.root/feature_settings.FILE_NAME;data=p.read_bytes() if p.exists() else b''
  return {'revision':hashlib.sha256(data).hexdigest(),'config':feature_settings.load(self.root,self.addon_root,persist=False)}
 def save_feature_settings(self,config):
  with self.lock:
   settings=feature_settings.save(self.root,self.addon_root,config)
   p=self.root/feature_settings.FILE_NAME;data=p.read_bytes() if p.exists() else b''
   return {'revision':hashlib.sha256(data).hexdigest(),'config':settings}
 def save_pool_settings(self,target,profile,revision,known,settings=None,settings_revision=None):
  with self.lock:
   if settings is None:return self.save(target,profile,revision,known)
   if not isinstance(settings,dict) or not isinstance(settings.get('enabled'),bool) or not isinstance(settings.get('characters'),dict):raise ValueError('角色启用设置无效')
   if any(k not in {str(i) for i in range(101,113)} or not isinstance(v,bool) for k,v in settings['characters'].items()):raise ValueError('角色启用设置无效')
   if self.settings_snapshot()['revision']!=settings_revision:raise ValueError('启用设置已在其他窗口修改，请重新载入')
   names=['custom_pools.json','random_settings.json','stop_random.flag']
   before={n:(self.root/n).read_bytes() if (self.root/n).exists() else None for n in names}
   try:
    result=self.save(target,profile,revision,known)
    p=self.root/'random_settings.json';tmp=self.root/'random_settings.workbench.tmp'
    tmp.write_text(json.dumps(settings,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8');os.replace(tmp,p)
    flag=self.root/'stop_random.flag'
    if settings['enabled']:flag.unlink(missing_ok=True)
    else:flag.write_bytes(b'')
    result['settings']=self.settings_snapshot();return result
   except Exception:
    for name,blob in before.items():
     p=self.root/name
     if blob is None:p.unlink(missing_ok=True)
     else:
      tmp=self.root/(name+'.rollback');tmp.write_bytes(blob);os.replace(tmp,p)
    raise
 def validate(self,target,p,known):
  if target not in {str(i) for i in range(101,113)}:raise ValueError('无效出战角色')
  if not isinstance(p.get('enabled'),bool):raise ValueError('启用状态无效')
  entries=p.get('entries',[])
  if not isinstance(entries,list) or len(entries)>256:raise ValueError('每池最多256项')
  for entry in entries:
   w=entry.get('weight',1) if isinstance(entry,dict) else None
   if isinstance(w,bool) or not isinstance(w,(int,float)) or not math.isfinite(w) or not 0<=w<=1000000:raise ValueError('权重应为0至1000000的有限数字')
   if entry.get('entry_kind','appearance')!='appearance':raise ValueError('人格池仅接受外观条目')
  group_entries.validate_entries(entries,{str(x):{} for x in known},{})
 def replace(self,config,revision,known):
  if config.get('schema')!=1 or not isinstance(config.get('characters'),dict):raise ValueError('方案格式不受支持')
  for target,p in config['characters'].items():self.validate(target,p,known)
  with self.lock:
   old=self.snapshot()
   if old['revision']!=revision:raise ValueError('配置已在其他窗口更改，请重新载入后保存')
   path=self.root/'custom_pools.json'
   if path.exists():(self.root/'custom_pools.workbench.bak').write_bytes(path.read_bytes())
   temp=self.root/'custom_pools.workbench.tmp';temp.write_text(json.dumps(config,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8');os.replace(temp,path)
  return self.snapshot()
 def save(self,target,profile,revision,known):
  self.validate(target,profile,known);config=self.snapshot()['config'];config['characters'][target]=profile
  return self.replace(config,revision,known)
 def director_snapshot(self):return director.snapshot(self.root)
 def form_annotations(self):
  entries=read(self.root/'Assets/runtime/form_annotations.json',{}).get('entries',{})
  entries={k:v for k,v in entries.items() if v.get('supported') is True and str(k).isdigit()}
  for k,v in read(self.root/'auto_form_annotations.json',{}).get('entries',{}).items():
   if v.get('supported') is True and str(k).isdigit():entries.setdefault(k,v)
  for k,v in read(self.root/'native_forms.json',{}).get('identities',{}).items():
   if str(k).isdigit():entries.setdefault(k,{'supported':True,'forms':' → '.join(v.get('forms',[])),'method':'资源表中存在形态；沿用原生条件。'})
  return entries
 def save_director(self,config,revision,known):
  supported=self.form_annotations()
  if any(k not in supported for k in config.get('forms',{})):raise ValueError('所选人格没有已确认可用的形态资源')
  with self.lock:return director.save(self.root,config,revision,known)
 def runtime_status(self,pool=None,tail=None):
  compat=read(self.root/'compatibility.json',{});status={'protocol':compat.get('protocol'),'draw':'尚未保存','forms':'尚未保存'}
  if pool is None:pool=read(self.root/'pool_update_status.json',{})
  if tail is None:
   pid=pool.get('pid')
   tail=self.evidence.read(pid) if prepare_view.process_alive(pid) else ''
  path=self.root/'workbench_rules.bin'
  if path.exists():
   tick=path.stat().st_mtime_ns//100+116444736000000000;key=f"{tick>>32}:{tick&0xffffffff}"
   status['draw']='核心已读取' if ('workbench draw rules applied revision='+key) in tail else '已保存，等待核心读取'
  formPath=self.root/'workbench_forms.bin'
  if formPath.exists():
   raw=formPath.read_bytes();revision=struct.unpack_from('<I',raw,8)[0] if len(raw)>=16 else None
   status['forms']='核心已读取' if revision is not None and f'workbench forms loaded revision={revision} rules=' in tail else '已保存，等待核心读取确认'
  status['pool']=prepare_view.pool_status(pool,tail,self.root)
  return status
 def portrait_lookup(self):
  """Share one view of available portraits throughout a catalog request."""
  self._refresh_local_portraits()
  def filenames(folder):
   try:
    with os.scandir(folder) as files:
     return {entry.name.lower() for entry in files if entry.name.lower().endswith('.png') and entry.is_file()}
   except FileNotFoundError:
    return set()
  bundled=getattr(self,'addon_root',self.root)/'Workbench/data/bundled_portraits'
  try:available={p.stem for p in bundled.iterdir() if p.is_file() and re.fullmatch(r'[A-Za-z0-9_-]+\.png',p.name)}
  except FileNotFoundError:available=set()
  available.update(imported_portraits.identities(self.root))
  for folder,manifest in (('portraits',self.portraits),('local_portraits',self.local_portraits)):
   names=filenames(self.root/'Workbench'/folder)
   for identity,row in manifest.items():
    name=row.get('file') if isinstance(row,dict) else None
    if isinstance(name,str) and re.fullmatch(r'[0-9a-f]{24}\.png',name) and name in names:
     available.add(identity)
  user=filenames(custom_portraits.folder_for(self.root))
  if not user:return available.__contains__
  return lambda identity: identity in available or custom_portraits.filename(identity) in user
 def ruleset_snapshot(self,pool_data=None,portrait_ok=None):
  if pool_data is None:pool_data=rulesets.pools(self.root)
  state, items = rulesets.list_rulesets(self.root, portrait_ok or self.portrait_lookup(), pool_data)
  selected = None
  wanted = (state.get('selected') or {}).get('id')
  for item in items:
   if item['id'] == wanted:
    selected = item
    break
  if selected and selected.get('kind') == 'global':
   selected = dict(selected)
   selected['sinner'] = str((state.get('selected') or {}).get('sinner') or '101')
  entries = rulesets.entries(self.root, selected, pool_data) if selected else []
  revision = rulesets.revision(self.root, selected) if selected else hashlib.sha256(b'').hexdigest()
  return state, items, selected, entries, revision
 def known_appearance(self, identity):
  pools=read(self.root/'Assets/runtime/all_sinners_pools.json',{})
  if any(str(e['identity_id'])==identity for group in pools.values() for e in group.get('entries',[])):
   return True
  return any(str(e['id'])==identity for e in read(self.root/'identity_catalog.json',{}).get('rows',[]))
 def blood_visible_ids(self):
  try:
   lines=(self.root/mos_data.BLOOD_VISIBILITY_FILE).read_text(encoding='utf-8-sig').splitlines()
  except FileNotFoundError:
   return []
  return sorted({line for line in lines if line})
 def save_blood_visibility(self, identity, visible):
  if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,63}',identity) or type(visible) is not bool:
   raise ValueError('血迹设置无效')
  with self.lock:
   if not self.known_appearance(identity):raise ValueError('未知人格')
   saved=self.blood_visible_ids()
   if (identity in saved)!=visible:
    if visible and len(saved)>=4096:raise ValueError('显示血迹的外观已达 4096 个上限')
    saved=sorted([*saved,identity]) if visible else [item for item in saved if item!=identity]
    from skin_import import write_atomic
    write_atomic(self.root/mos_data.BLOOD_VISIBILITY_FILE,''.join(item+'\n' for item in saved).encode('utf8'))
  return {'blood_visible_ids':saved}
 def save_appearance_name(self, identity, name):
  if not isinstance(identity,str) or not isinstance(name,str) or len(name)>100 or any(not c.isprintable() for c in name):
   raise ValueError('名称最多可填写 100 个可显示字符')
  with self.lock:
   if not self.known_appearance(identity):raise ValueError('未知人格')
   path=self.root/'Workbench/appearance_names.json'
   names=read(path,{})
   if not isinstance(names,dict):raise ValueError('自定义名称文件无效')
   name=name.strip()
   if name:names[identity]=name
   else:names.pop(identity,None)
   from skin_import import write_atomic
   write_atomic(path,(json.dumps(names,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
  return {'name':name}
 def catalog_snapshot(self,pools=None,portrait_ok=None):
  if pools is None:pools=read(self.root/'Assets/runtime/all_sinners_pools.json',{})
  if portrait_ok is None:portrait_ok=self.portrait_lookup()
  catalog={str(e['identity_id']):dict(e,source="Boss" if e.get("category")=="humanoid_boss" else key) for key,p in pools.items() for e in p.get('entries',[])}
  for e in read(self.root/'identity_catalog.json',{}).get('rows',[]):
   catalog.setdefault(str(e['id']),{'identity_id':str(e['id']),'name':e['appearance'],'source':str(100+int(e['character']))})
  translations=name_translations.load(self.root)
  for identity,e in catalog.items():
   e['name']=name_translations.name(identity,e.get('name',''),translations)
   if portrait_ok(identity):e['portrait_url']='api/portrait/'+quote(identity,safe='')
  chapters=read(self.root/'boss_chapters.json',{})
  for identity,e in catalog.items():
   if identity in chapters:
    group=chapters.get(identity,{})
    e.update(chapter=group.get('chapter','unassigned'),chapter_label=group.get('label','未归档'),chapter_memberships=chapter_categories.memberships(group))
    e.update(chapter_rank=group.get('rank',20000),chapter_sources=group.get('appearances_in',[]),source_note='；'.join(x.get('note','') for x in group.get('special_evidence',[])),source_evidence_level=group.get('confidence',''),source_battles=sorted({str(x['battle_id']) for x in group.get('battle_evidence',[]) if x.get('battle_id') is not None}))
  walpurgis_catalog.apply(catalog,walpurgis_catalog.load(self.root))
  imported_catalog.apply(catalog,self.root,getattr(self,'addon_root',self.root))
  aliases=read(self.root/'Workbench/appearance_names.json',{})
  if isinstance(aliases,dict):
   for identity,e in catalog.items():
    if isinstance(aliases.get(identity),str) and aliases[identity]:
     e['default_name']=e.get('name','')
     e['name']=aliases[identity]
  for pair in read(self.root/'Workbench/data/appearance_pairs.json',{}).get('pairs',[]):
   entry=catalog.get(pair.get('pool_id') or pair['appearance'])
   if entry is not None:entry.setdefault('paired_identities',[]).append(str(pair['identity']))
  art,revision=chapter_cards.project(self.root,catalog)
  return catalog,art,revision
 def save_chapter(self,body):
  if not isinstance(body,dict):raise ValueError('章节数据无效')
  with self.lock:
   _,art,_=self.catalog_snapshot()
   return chapter_cards.save(self.root,body,art)
 def move_chapter(self,body):
  if not isinstance(body,dict):raise ValueError('章节数据无效')
  with self.lock:
   catalog,art,_=self.catalog_snapshot()
   return chapter_cards.move(self.root,body,catalog,art)
 def data(self):
  pools=read(self.root/'Assets/runtime/all_sinners_pools.json',{})
  portrait_ok=self.portrait_lookup()
  rule_state, rule_items, active_rule, rule_entries, rule_revision = self.ruleset_snapshot(pools,portrait_ok)
  catalog,chapter_art,chapter_revision=self.catalog_snapshot(pools,portrait_ok)
  native_forms=read(self.root/'native_forms.json',{})
  pool_status=read(self.root/'pool_update_status.json',{});pid=pool_status.get('pid');alive=prepare_view.process_alive(pid)
  evidence=self.evidence.read(pid) if alive else ''
  preparation=prepare_view.summarize(evidence,pid,alive,list(catalog.values()))
  addon_info=read(self.addon_root/'addon_info.json',{})
  tutorial=bool((addon_info.get('settings') or {}).get('是否展示教程',True))
  return dict(self.snapshot(),blood_visible_ids=self.blood_visible_ids(),preparation=preparation,rulesetState=rule_state,rulesets=rule_items,activeRule=active_rule,ruleEntries=rule_entries,ruleRevision=rule_revision,settings=self.settings_snapshot(),featureSettings=self.feature_settings_snapshot(),runtime=self.runtime_status(pool_status,evidence),director=self.director_snapshot(),formAnnotations=self.form_annotations(),catalog=list(catalog.values()),chapterArt=chapter_art,chapterRevision=chapter_revision,pools=pools,forms=native_forms,warmup=read(self.root/'warmup_status.json',{}),version=addon_info.get('version','未知'),tutorial=tutorial,launcherBackground=self.launcher_background())
 def known_appearances(self):
  """pool 里的外观名集合，按文件 mtime 缓存：扫描期间页面每 5 秒轮询，1.5 MB 的池文件不该重复解析。"""
  path=self.root/'Assets/runtime/all_sinners_pools.json'
  try:stamp=(path.stat().st_mtime_ns,path.stat().st_size)
  except OSError:return set()
  cache=getattr(self,'_known_cache',None)
  if cache and cache[0]==stamp:return cache[1]
  pools=read(path,{})
  known={str(e.get('appearance_name')) for p in pools.values() for e in p.get('entries',[])}
  self._known_cache=(stamp,known)
  return known
 def scan_state(self):
  """给页面的扫描状态：只给一句能用的话，不带子进程 stderr（常含本机路径）。
  完整错误在 Workbench/scan_last_error.txt。"""
  weekly=read(self.root/'Workbench/weekly_scan_status.json',{})
  if not isinstance(weekly,dict):weekly={}
  from datetime import datetime
  with SCAN_LOCK:
   manual = dict(SCAN)
  scheduled = weekly.get('status') == 'running'
  running = bool(manual.get('running') or scheduled)
  owner = weekly.get('started') if scheduled else str(manual.get('started'))
  progress = read(self.root/'Workbench/scan_progress.json', {}) if running else {}
  if not isinstance(progress,dict) or progress.get('run') != owner:progress={}
  try:weekly_time=datetime.fromisoformat(weekly.get('finished') or '').timestamp()
  except ValueError:weekly_time=0
  error = manual.get('error')
  if weekly_time > (manual.get('finished') or 0):
   error = '每周自动检测未完成，请查看检测记录' if weekly.get('status')=='failed' else None
  return dict(running=running,started=owner,progress=progress,error=None if running else error,
              weekly={k:weekly.get(k) for k in ('slot','status','finished')})
 def discovered(self):
  """New prefabs found by scan_units.py after a game update. The scan runs in a
  subprocess, so it never blocks a request thread; the page polls 'discovered'."""
  report=read(self.root/'Workbench/discovered_units.json',{})
  if not isinstance(report,dict) or not report:return {'available':False,'scan':self.scan_state(),'reason':'尚未扫描。点「开始扫描」比对一次本地缓存即可。'}
  units=[]
  known=self.known_appearances()
  for name,e in (report.get('units') or {}).items():
   if name in known:continue  # already adopted since the scan
   units.append({'appearance_name':name,'asset_key':e.get('asset_key'),'group':e.get('group'),'group_confidence':e.get('group_confidence'),'group_evidence':e.get('group_evidence'),'motions':e.get('motions') or []})
  by_confidence={}
  for u in units:
   key=u.get('group_confidence') or 'unknown'
   by_confidence.setdefault(key,[]).append(u['appearance_name'])
  return {'available':True,'generated':report.get('generated'),'catalog_hash':report.get('catalog_hash'),'catalog_changed':report.get('catalog_changed'),'bundles_total':report.get('bundles_total'),'bundles_rescanned':report.get('bundles_rescanned'),'pool_entries':report.get('pool_entries'),'new_prefabs':len(units),'auto_added_no_attack':report.get('auto_added_no_attack',0),'auto_added_attack':report.get('auto_added_attack',0),'attack_import_errors':report.get('attack_import_errors',{}),'artwork':report.get('artwork',{}),'translation':report.get('translation',{}),'auto_added_personalities':report.get('auto_added_personalities',[]),'by_confidence':by_confidence,'scan':self.scan_state(),'units':units}

 def events(self):
  path=self.root/'native_runtime.log'
  if not path.exists():return []
  with path.open('rb') as f:
   f.seek(0,2);size=f.tell();f.seek(max(0,size-2*1024*1024));text=f.read().decode('utf8','replace')
  keys=('coin metadata','coin play','coin draw','event=','clash camera','projection ','idle blocked','retained after')
  latest=[]
  for line in reversed(text.splitlines()):
   if any(key in line for key in keys):
    latest.append(parse_event(line))
    if len(latest)==600:break
  latest.reverse()
  return latest

SCAN={'running':False,'started':None,'finished':None,'error':None,'log':None}
SCAN_LOCK=threading.Lock()
# scan_units 用固定退出码表达失败原因（2=缺 UnityPy，3=找不到缓存，4=已有扫描），
# 不去猜 stderr 的内容——UnityPy 自己抛的异常也带这个词，会误报成「没装」。
SCAN_EXIT={'2':'资源读取组件准备失败，请检查网络后重试；详情见 Workbench/scan_last_error.txt','3':'找不到 Addressables 缓存，先启动一次游戏','4':'已有扫描在进行','5':'无法在工作台目录创建扫描锁','6':'人格池文件缺失或损坏，请检查插件安装'}
def should_scan_on_start(catalog_now, catalog_before):
 # Downloads can arrive after the catalog update; bundle fingerprints make an
 # unchanged-catalog pass incremental rather than skipping new cache contents.
 return bool(catalog_now)

def scan_error_text(code):
 return SCAN_EXIT.get(str(code),'扫描失败，详情见 Workbench/scan_last_error.txt')

def start_scan(root):
 """Run scan_units.py in the background. A full pass opens 1500+ bundles and takes
 minutes, so it must not block the request thread; the UI polls 'discovered'.
 The check-and-set runs under a lock: without it the startup scan and a page
 click can both pass the check and start two scans writing the same files."""
 with SCAN_LOCK:
  if SCAN['running']:return {'running':True,'already':True,'started':SCAN['started']}
  SCAN.update(running=True,started=time.time(),finished=None,error=None,log=None)
 def work():
  try:
   script=_workbench_script('scan_units.py')
   flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
   env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
   env['FAUST_SCAN_RUN']=str(SCAN['started'])
   proc=_spawn_child([sys.executable,str(script),'--addon',str(root)],cwd=str(root),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',creationflags=flags,env=env)
   try:stdout,stderr=proc.communicate(timeout=3600)
   except subprocess.TimeoutExpired:proc.kill();stdout,stderr=proc.communicate();raise
   finally:_forget_child(proc)
   SCAN['log']=(stdout or '')[-4000:]
   if proc.returncode!=0:
    detail=((stderr or stdout or '').strip()[-4000:] or '扫描退出码 %d'%proc.returncode)
    SCAN['error']=scan_error_text(proc.returncode)
    # 页面只说一句能用的话，真正的 traceback 落到插件目录里，排查时能拿到。
    try:(pathlib.Path(root)/'Workbench/scan_last_error.txt').write_text(detail,encoding='utf-8')
    except OSError:pass
  except Exception as e:
   SCAN['error']=scan_error_text(None)
   try:(pathlib.Path(root)/'Workbench/scan_last_error.txt').write_text(str(e),encoding='utf-8')
   except OSError:pass
  finally:
   with SCAN_LOCK:
    SCAN['finished']=time.time();SCAN['running']=False
  # scan_units only extracts portraits on the weekly pass, so a plain scan can
  # finish with portraits/ still empty. Hand off to the restore pass once it has
  # released image_resources.lock, otherwise the first run ends with no art.
  try:
   if not SCAN['error'] and _portraits_missing(root):_portrait_start(root)
  except Exception:pass
 threading.Thread(target=work,daemon=True).start()
 return {'running':True,'started':SCAN['started']}

GATEWAY = 'Workbench/workbench_gateway.json'
DEFAULT_GATEWAY_PORT = 47821


def _load_gateway(root):
 path = pathlib.Path(root) / GATEWAY
 try:
  data = json.loads(path.read_text(encoding='utf-8'))
  port = int(data.get('port'))
  token = str(data.get('token') or '')
 except (OSError, ValueError, TypeError):
  return None
 if not 1024 <= port <= 65535 or not re.fullmatch(r'[A-Za-z0-9_-]{16,64}', token):
  return None
 return {'port': port, 'token': token}


def _save_gateway(root, port, token):
 path = pathlib.Path(root) / GATEWAY
 path.parent.mkdir(parents=True, exist_ok=True)
 temp = path.with_suffix('.json.tmp')
 temp.write_text(json.dumps({'port': port, 'token': token}), encoding='utf8')
 temp.replace(path)


class WorkbenchServer(ThreadingHTTPServer):
 # SO_REUSEADDR on Windows permits multiple listeners on one port. An
 # exclusive bind makes a collision follow the ephemeral-port retry below.
 allow_reuse_address = os.name != 'nt'

 def server_bind(self):
  if os.name=='nt':
   self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
  super().server_bind()

 def __init__(self,*args):
  self.stopping=threading.Event()
  super().__init__(*args)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--addon',required=True);ap.add_argument('--no-browser',action='store_true');ap.add_argument('--host-pid',type=int);ap.add_argument('--game-pid',type=int);ap.add_argument('--startup-pid',type=int);args=ap.parse_args()
 data_root=mos_data.data_dir()
 instance=instance_control.Instance(data_root)
 if not instance.acquire():
  try:
   url=instance.existing()
   if not args.startup_pid:instance.attach(url,args.host_pid,args.game_pid)
   print(url,flush=True)
   if not args.no_browser:webbrowser.open(url)
  finally:instance.close()
  return
 lifetime=host_lifetime.Lifetime()
 if args.startup_pid:lifetime.register(args.startup_pid)
 else:lifetime.register(args.host_pid,args.game_pid)
 store=Store(args.addon)
 def import_local_skin(path, **callbacks):
  from skin_import import import_skin
  return import_skin(path,store.addon_root,**callbacks)
 def import_mod_package(path, **callbacks):
  from skin_import import import_skin
  item=mod_packages.find(store.addon_root,pathlib.Path(path).name)
  rows=mod_packages.unchanged_rows(store.addon_root,item)
  if rows is not None:return rows
  progress=callbacks.get('progress')
  with mod_packages.prepared_archive(store.addon_root,pathlib.Path(path).name,
                                     progress=progress) as prepared:
   extra={'default_portrait':prepared.portrait} if prepared.portrait else {}
   if prepared.source:
    extra.update(source=prepared.source,source_kind='mod',source_name=prepared.name,
                 source_version=prepared.version)
   return import_skin(prepared.archive,store.addon_root,**extra,**callbacks)
 skin_jobs=skin_import_jobs.ImportJobs(_pick_local_skins,import_local_skin)
 if lifetime.unowned():
  lifetime.close();instance.close();return
 gateway=_load_gateway(data_root)
 token=gateway['token'] if gateway else secrets.token_urlsafe(24)
 gateway_port=gateway['port'] if gateway else DEFAULT_GATEWAY_PORT
 html=(pathlib.Path(__file__).parent/'ui/index.html').read_bytes()
 class Handler(BaseHTTPRequestHandler):
  # Browsers can preconnect without sending a request. Bound the socket wait
  # so server_close can join those handlers when the launcher exits.
  timeout=5
  def handle(self):
   # Windows may leave a blocking recv pending even after shutdown(SHUT_RD).
   # Poll only before the first byte. Once a request starts it can finish saving.
   while not self.server.stopping.is_set():
    if select.select([self.connection],[],[],.1)[0]:
     return super().handle()
  def log_message(self,*a):pass
  def send(self,body,status=200,ctype='application/json; charset=utf-8',cache='no-store'):
   data=body if isinstance(body,bytes) else json.dumps(body,ensure_ascii=False,allow_nan=False).encode('utf8');self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Cache-Control',cache);self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
  def route(self):
   prefix='/'+token
   if self.path==prefix+'/':return 'index'
   if self.path==prefix+'/effect-editor':return 'effect-editor'
   if self.path.startswith(prefix+'/api/'):return self.path[len(prefix+'/api/'):]
   return None
  def do_GET(self):
   route=self.route()
   try:
    if route=='index':return self.send(html,ctype='text/html; charset=utf-8')
    if route=='effect-editor':return self.send((pathlib.Path(__file__).parent/'ui/effect-editor.html').read_bytes(),ctype='text/html; charset=utf-8')
    if route=='instance-ping':return self.send({'workbench':True,'version':_STARTUP_VERSION,'pid':os.getpid()})
    if route and (route=='launcher-background' or route.startswith('launcher-background?')):
     if 'next=1' in route:store.launcher_background_next()
     image,ctype=store.launcher_background_image()
     if image is not None:return self.send(image,ctype=ctype,cache='no-store')
     return self.send({'error':'未找到'},404)
    if route=='portrait-progress':return self.send(_portrait_state())
    if route=='local-skin-import-status':return self.send(skin_jobs.state())
    if route=='mod-packages':return self.send({'packages':mod_packages.scan(store.addon_root)})
    if route and route.startswith('mod-package-icon/'):
     image=mod_packages.icon_bytes(store.addon_root,unquote(route[len('mod-package-icon/'):].split('?',1)[0]))
     if image is not None:return self.send(image,ctype='image/png',cache='no-store')
     return self.send({'error':'未找到'},404)
    if route=='rulesets':return self.send(_ruleset_payload(store))
    if route=='data':return self.send(store.data())
    if route=='events':return self.send(store.events())
    if route=='discovered':return self.send(store.discovered())
    if route=='schemes':return self.send({'schemes':schemes.listing(store.root)})
    if route=='effect-schemes':return self.send({'schemes':effect_schemes.listing(store.root)})
    if route=='effect-selection':return self.send(fx_activation.read_selection(store.root))
    if route and route.startswith('chapter-image/'):
     image=chapter_cards.image(store.root,unquote(route[len('chapter-image/'):].split('?',1)[0]))
     if image is not None:return self.send(image,ctype='image/png',cache='no-store')
    if route and route.startswith('effect-sprite/'):
     roots=resource_catalog.resolve_roots()
     image=sprite_gallery.thumb_path(roots['index_dir'],unquote(route[len('effect-sprite/'):]))
     if image is not None:return self.send(image.read_bytes(),ctype='image/png',cache='no-store')
    if route and route.startswith('effect-sprite-original/'):
     roots=resource_catalog.resolve_roots()
     image=sprite_export.export_path(roots['index_dir'],unquote(route[len('effect-sprite-original/'):]))
     if image is not None:return self.send(image.read_bytes(),ctype='image/png',cache='no-store')
    if route and route.startswith('portrait/'):
     image=store.portrait(unquote(route[len('portrait/'):]))
     if image is not None:return self.send(image,ctype='image/png',cache='no-store')
    return self.send({'error':'未找到'},404)
   except Exception as e:return self.send({'error':str(e)},500)
  def do_POST(self):
   route=self.route()
   if route not in ('appearance-blood','appearance-name','chapter-save','chapter-move','package-folders','save','import','local-skin-import','local-skin-import-start','local-skin-delete','mod-package-import','director','bundle','boss-preview','update-check','update-install','portrait-save','portrait-reset','portrait-download','images-delete','ruleset-activate','ruleset-select','ruleset-save','ruleset-create','ruleset-only','ruleset-deactivate','ruleset-delete','ruleset-fill','ruleset-clear','scan','scheme-save','scheme-load','scheme-delete','scheme-import','scheme-get','feature-settings-save','effect-scheme-save','effect-scheme-get','effect-scheme-delete','effect-timelines','effect-live-start','effect-live-status','effect-plan-preview','effect-selection','effect-sprites','effect-sprites-start','effect-sprites-status','effect-sprites-cancel','effect-sprite-export','tutorial-complete','instance-shutdown','instance-attach','instance-release'):return self.send({'error':'未找到'},404)
   if self.headers.get('X-Workbench')!=token:return self.send({'error':'请求无效'},403)
   try:
    n=int(self.headers.get('Content-Length',0))
    limit={'chapter-save':3*1024*1024,'portrait-save':2*1024*1024}.get(route,1024*1024)
    if not 0<n<=limit:raise ValueError('请求过大或为空')
    body=json.loads(self.rfile.read(n))
    if route=='appearance-blood':return self.send(store.save_blood_visibility(body.get('identity_id'),body.get('visible')))
    if route=='appearance-name':return self.send(store.save_appearance_name(body.get('identity_id'),body.get('name')))
    if route=='chapter-save':return self.send(store.save_chapter(body))
    if route=='chapter-move':return self.send(store.move_chapter(body))
    if route=='package-folders':
     from package_lifecycle import synchronize
     return self.send(synchronize(store.root,store.addon_root))
    if route=='local-skin-delete':
     from delete_imported import delete
     identity=body.get('identity_id')
     if not isinstance(identity,str):raise ValueError('请选择要删除的导入外观')
     return self.send(delete(store.root,identity,lock_factory=lambda _path:store.lock,addon=store.addon_root))
    if route=='local-skin-import':return self.send(skin_jobs.run(body.get('paths')))
    if route=='local-skin-import-start':return self.send(skin_jobs.start(body.get('paths')))
    if route=='mod-package-import':
     key=body.get('id')
     package=mod_packages.find(store.addon_root,key)
     if package is None:raise ValueError('未找到外观包')
     if package['status']!='ready':raise ValueError(package['error'] or '外观包不可导入')
     return self.send(skin_jobs.start([str(package['_folder'])],importer=import_mod_package))
    if route=='tutorial-complete':
     path=store.addon_root/'addon_info.json'
     info=read(path,{})
     info.setdefault('settings',{})['是否展示教程']=False
     temp=path.with_name(path.name+'.tutorial.tmp');temp.write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf8');os.replace(temp,path)
     try:(store.root/'addon_info.json').write_bytes(path.read_bytes())
     except OSError:pass
     return self.send({'saved':True,'tutorial':False})
    if route=='instance-attach':
     lifetime.register(body.get('host_pid'),body.get('game_pid'),body.get('startup_pid'))
     if args.startup_pid and body.get('startup_pid')==args.startup_pid and args.startup_pid!=body.get('host_pid'):
      lifetime.release(args.startup_pid)
     return self.send({'attached':True})
    if route=='instance-release':lifetime.release(body.get('host_pid'));return self.send({'released':True})
    if route=='instance-shutdown':
     lifetime.begin_shutdown()
     try:self.send({'stopping':True})
     finally:threading.Thread(target=server.shutdown,daemon=True).start()
     return
    if route=='effect-selection':
     with store.lock:return self.send(fx_activation.select(store.root,body.get('name',''),body.get('enabled')))
    if route=='effect-plan-preview':return self.send(effect_plan.preview_workbench(body.get('scheme'),effect_timelines.state))
    if route=='effect-timelines':return self.send(effect_timelines.lookup(body.get('appearance')))
    if route=='effect-live-start':return self.send(effect_timelines.start(body.get('appearance')))
    if route=='effect-live-status':return self.send(effect_timelines.state(body.get('appearance')))
    if route=='effect-sprites-start':return self.send(sprite_jobs.start(body.get('appearance'),resource_catalog.resolve_roots()))
    if route=='effect-sprites-status':return self.send(sprite_jobs.state())
    if route=='effect-sprites-cancel':return self.send(sprite_jobs.cancel())
    if route=='effect-sprite-export':return self.send({'file':sprite_export.export_original(body.get('entry'),resource_catalog.resolve_roots())})
    if route=='effect-sprites':
     roots=resource_catalog.resolve_roots()
     return self.send(sprite_gallery.inventory(body.get('appearance'),roots))
    if route=='effect-scheme-get':return self.send({'scheme':effect_schemes.get(store.root,body.get('name'))})
    if route=='effect-scheme-save':
     with store.lock:return self.send({'saved':effect_schemes.save(store.root,body.get('name'),body.get('scheme'),bool(body.get('overwrite'))),'schemes':effect_schemes.listing(store.root)})
    if route=='effect-scheme-delete':
     with store.lock:
      effect_schemes.delete(store.root,body.get('name'));return self.send({'schemes':effect_schemes.listing(store.root)})
    if route=='portrait-download':
     return self.send({'started':_portrait_start(store.root),'progress':_portrait_state()})
    if route=='images-delete':
     if _PORTRAIT_THREAD is not None and _PORTRAIT_THREAD.is_alive():raise ValueError('资源检索正在进行，请结束后再删除')
     return self.send(_delete_images(store.root))
    if route=='scan':return self.send(start_scan(store.root))
    if route=='feature-settings-save':
     config=body.get('config')
     if not isinstance(config,dict):raise ValueError('设置内容无效')
     return self.send(store.save_feature_settings(config))
    if route in ('update-check','update-install'):
     import github_update
     return self.send(github_update.check(store.addon_root) if route=='update-check' else github_update.install(store.addon_root))
    if route=='boss-preview':return self.send(add_boss_members(body['profile'],store.data()['catalog'],body.get('chapter')))
    if route.startswith('ruleset-') and (body.get('rule') or body).get('kind')=='chapter':
     raise ValueError('父辈与子辈演出已改为按人格和覆盖外观自动匹配')
    if route=='ruleset-activate':
     rulesets.activate(store.root, body.get('rule') or body)
     return self.send(_ruleset_payload(store))
    if route=='ruleset-select':
     rulesets.select(store.root, body.get('rule') or body)
     return self.send(_ruleset_payload(store))
    if route=='ruleset-save':
     rulesets.save_entries(store.root, body['rule'], body.get('entries', []), body.get('revision', ''), {str(e['identity_id']) for e in rulesets.catalog(store.root).values()}, store.validate)
     return self.send(_ruleset_payload(store))
    if route=='ruleset-create':
     rulesets.create_identity(store.root, body['sinner'], body['identity'], rulesets.catalog(store.root))
     return self.send(_ruleset_payload(store))
    if route=='ruleset-only':
     rulesets.only(store.root, body.get('rule') or body)
     return self.send(_ruleset_payload(store))
    if route=='ruleset-deactivate':
     rulesets.deactivate(store.root, body.get('rule') or body)
     return self.send(_ruleset_payload(store))
    if route=='ruleset-delete':
     rulesets.delete(store.root, body.get('rule') or body)
     return self.send(_ruleset_payload(store))
    if route=='ruleset-fill':
     rulesets.fill_default(store.root, body.get('rule') or body, rulesets.pools(store.root))
     return self.send(_ruleset_payload(store))
    if route=='ruleset-clear':
     rulesets.clear(store.root, body.get('rule') or body)
     return self.send(_ruleset_payload(store))
    if route=='scheme-save':
     with store.lock:return self.send({'saved':schemes.save(store.root,body.get('name'),bool(body.get('overwrite'))),'schemes':schemes.listing(store.root)})
    if route=='scheme-import':
     with store.lock:return self.send({'saved':schemes.save(store.root,body.get('name'),bool(body.get('overwrite')),body.get('scheme')),'schemes':schemes.listing(store.root)})
    if route=='scheme-delete':
     with store.lock:
      schemes.delete(store.root,body.get('name'));return self.send({'schemes':schemes.listing(store.root)})
    if route=='scheme-get':return self.send(schemes.get(store.root,body.get('name')))
    known={str(e['identity_id']) for e in store.data()['catalog']}
    if route=='scheme-load':
     with store.lock:
      loaded=schemes.load(store,body.get('name'),known)
      return self.send({'loaded':loaded,'schemes':schemes.listing(store.root)})
    if route in ('portrait-save','portrait-reset'):
     identity=body.get('identity')
     if not isinstance(identity,str) or identity not in known:raise ValueError('未知人格')
     with store.lock:
      if route=='portrait-save':custom_portraits.save(store.root,identity,body.get('image'))
      else:custom_portraits.reset(store.root,identity)
     return self.send({'saved':True,'portrait_url':'api/portrait/'+quote(identity,safe='') if store.portrait(identity) else None})
    if route=='bundle':
     config=body['config'];pool=config['pools'];rules=config['director']
     if config.get('schema')!=2:raise ValueError('方案版本不支持')
     if pool.get('schema')!=1:raise ValueError('人格池格式不支持')
     for t,p in pool['characters'].items():store.validate(t,p,known)
     director.validate(rules,known)
     if any(k not in store.form_annotations() for k in rules.get('forms',{})):raise ValueError('方案包含未确认支持的形态人格')
     with store.lock:
      if store.snapshot()['revision']!=body['revision'] or store.director_snapshot()['revision']!=body['directorRevision']:raise ValueError('配置已在其他窗口修改，请重新载入')
      filenames=['custom_pools.json','director.json','workbench_rules.bin','workbench_forms.bin']
      before={n:(store.root/n).read_bytes() if (store.root/n).exists() else None for n in filenames}
      try:
       result=store.replace(pool,body['revision'],known)
       result['director']=store.save_director(rules,body['directorRevision'],known)
      except Exception:
       for name,blob in before.items():
        if blob is None:(store.root/name).unlink(missing_ok=True)
        else:
         tmp=store.root/(name+'.bundle-rollback');tmp.write_bytes(blob);os.replace(tmp,store.root/name)
       raise
     return self.send(result)
    if route=='director':return self.send(store.save_director(body['config'],body['revision'],known))
    if route=='save':result=store.save_pool_settings(body['target'],body['profile'],body['revision'],known,body.get('settingsConfig'),body.get('settingsRevision'))
    else:result=store.replace(body['config'],body['revision'],known)
    return self.send(result)
   except (ValueError,KeyError,TypeError) as e:return self.send({'error':str(e)},400)
   except Exception as e:return self.send({'error':str(e)},500)
 try:
  server=WorkbenchServer(('127.0.0.1',gateway_port),Handler)
 except OSError:
  server=WorkbenchServer(('127.0.0.1',0),Handler);gateway_port=server.server_port
 _save_gateway(data_root,gateway_port,token)
 try:
  build_path=data_root/_BUILD_FILE
  build_path.parent.mkdir(parents=True,exist_ok=True)
  build_path.write_text(json.dumps({'version':_STARTUP_VERSION,'pid':os.getpid()}),encoding='utf-8')
 except OSError:
  pass
 server.daemon_threads=False;lifetime.watch(server);url=f'http://127.0.0.1:{server.server_port}/{token}/';instance.publish(url);print(url,flush=True)
 if not args.no_browser:webbrowser.open(url)
 host_lifetime.contain_descendants()
 resource_catalog.resource_tools.prepare_in_background()
 _first_portrait_start(data_root)
 try:server.serve_forever(poll_interval=.1)
 except KeyboardInterrupt:pass
 finally:
  try:(data_root/_BUILD_FILE).unlink(missing_ok=True)
  except OSError:pass
  server.stopping.set();skin_jobs.stop();_stop_children();server.server_close()
  skin_jobs.join();lifetime.close();instance.close()
if __name__=='__main__':main()

