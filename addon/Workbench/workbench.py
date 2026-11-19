import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_view
import merged_appearances
import chapter_nine
import chapter_cards
import chapter_categories
import name_translations
import local_portraits
import walpurgis_catalog
from urllib.parse import unquote, quote
from file_lock import FileLock
import director
import stage_director
import custom_portraits
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
import struct
import subprocess
import argparse,hashlib,importlib.util,json,math,os,pathlib,re,secrets,threading,time,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

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
def _portrait_state():
 with _PORTRAIT_LOCK:return dict(_PORTRAIT_JOB)

def _portrait_update(stage,done=0,total=0,message=''):
 percent=100 if stage=='done' else (round(done*100/total,1) if total else 0)
 with _PORTRAIT_LOCK:
  _PORTRAIT_JOB.update(stage=stage,done=done,total=total,percent=percent,message=message,updated=time.time())

def _portrait_run(root):
 try:
  script=pathlib.Path(root)/'Workbench/resource_scan.py'
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
 except Exception as exc:
  with _PORTRAIT_LOCK:
   _PORTRAIT_JOB.update(stage='error',message=str(exc),updated=time.time())
   _PORTRAIT_JOB.pop('result',None)

def _delete_images(root):
 root=pathlib.Path(root);wb=root/'Workbench';count=0;size=0
 with FileLock(wb/'image_resources.lock'):
  (wb/'images_disabled.flag').write_text('图片已关闭；点击下载资源恢复。\n',encoding='utf8')
  for folder in ('portraits','local_portraits','user_portraits','chapter_art'):
   path=wb/folder
   if path.is_symlink() or not path.is_dir():continue
   for file in path.iterdir():
    if file.is_symlink() or not file.is_file() or file.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):continue
    size+=file.stat().st_size;file.unlink();count+=1
 return {'count':count,'bytes':size}

def _portrait_start(root):
 global _PORTRAIT_THREAD
 with _PORTRAIT_LOCK:
  if _PORTRAIT_THREAD is not None and _PORTRAIT_THREAD.is_alive():return False
  _PORTRAIT_JOB.pop('result',None)
  _PORTRAIT_JOB.update(stage='starting',done=0,total=0,percent=0,message='准备检索本地资源',updated=time.time())
  _PORTRAIT_THREAD=threading.Thread(target=_portrait_run,args=(root,),name='PortraitDownload',daemon=True)
  _PORTRAIT_THREAD.start()
 return True

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
  self.root=pathlib.Path(root);self.lock=FileLock(self.root/'workbench-save.lock');self.portraits=read(self.root/'Workbench/portrait_manifest.json',{});self.local_portraits=local_portraits.load(self.root)
  with self.lock:stage_director.migrate_legacy_groups(self.root)
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
  row=self.portraits.get(identity,{})
  name=row.get('file','')
  if name and pathlib.Path(name).name==name and '/' not in name and '\\' not in name and name.endswith('.png'):
   path=self.root/'Workbench/portraits'/name
   if path.is_file():return path.read_bytes()
  return local_portraits.get(self.root,self.local_portraits,identity)
 def snapshot(self):
  p=self.root/'自定义人格池.json';data=p.read_bytes() if p.exists() else b''
  return {'revision':hashlib.sha256(data).hexdigest(),'config':json.loads(data.decode('utf-8-sig')) if data else {'schema':1,'characters':{}}}
 def settings_snapshot(self):
  p=self.root/'随机设置.json';data=p.read_bytes() if p.exists() else b''
  return {'revision':hashlib.sha256(data).hexdigest(),'config':json.loads(data.decode('utf-8-sig')) if data else {'enabled':True,'characters':{}}}
 def save_pool_settings(self,target,profile,revision,known,settings=None,settings_revision=None):
  with self.lock:
   if settings is None:return self.save(target,profile,revision,known)
   if not isinstance(settings,dict) or not isinstance(settings.get('enabled'),bool) or not isinstance(settings.get('characters'),dict):raise ValueError('角色启用设置无效')
   if any(k not in {str(i) for i in range(101,113)} or not isinstance(v,bool) for k,v in settings['characters'].items()):raise ValueError('角色启用设置无效')
   if self.settings_snapshot()['revision']!=settings_revision:raise ValueError('启用设置已在其他窗口修改，请重新载入')
   names=['自定义人格池.json','随机设置.json','停止随机运行.flag']
   before={n:(self.root/n).read_bytes() if (self.root/n).exists() else None for n in names}
   try:
    result=self.save(target,profile,revision,known)
    p=self.root/'随机设置.json';tmp=self.root/'随机设置.workbench.tmp'
    tmp.write_text(json.dumps(settings,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8');os.replace(tmp,p)
    flag=self.root/'停止随机运行.flag'
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
 def validate(self,target,p,known,stage_groups=None):
  if target not in {str(i) for i in range(101,113)}:raise ValueError('无效出战角色')
  if not isinstance(p.get('enabled'),bool):raise ValueError('启用状态无效')
  entries=p.get('entries',[])
  if not isinstance(entries,list) or len(entries)>256:raise ValueError('每池最多256项')
  if stage_groups is None:stage_groups=stage_director.snapshot(self.root)['config'].get('groups',[])
  groups={g.get('id'):g for g in stage_groups if isinstance(g,dict)}
  for entry in entries:
   w=entry.get('weight',1) if isinstance(entry,dict) else None
   if isinstance(w,bool) or not isinstance(w,(int,float)) or not math.isfinite(w) or not 0<=w<=1000000:raise ValueError('权重应为0至1000000的有限数字')
  group_entries.validate_entries([e for e in entries if e.get('weight',1)>0],{str(x):{} for x in known},groups)
 def replace(self,config,revision,known,stage_groups=None):
  if config.get('schema')!=1 or not isinstance(config.get('characters'),dict):raise ValueError('方案格式不受支持')
  for target,p in config['characters'].items():self.validate(target,p,known,stage_groups)
  with self.lock:
   old=self.snapshot()
   if old['revision']!=revision:raise ValueError('配置已在其他窗口更改，请重新载入后保存')
   path=self.root/'自定义人格池.json'
   if path.exists():(self.root/'自定义人格池.workbench.bak').write_bytes(path.read_bytes())
   temp=self.root/'自定义人格池.workbench.tmp';temp.write_text(json.dumps(config,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8');os.replace(temp,path)
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
 def runtime_status(self):
  compat=read(self.root/'compatibility.json',{});status={'protocol':compat.get('protocol'),'draw':'尚未保存','forms':'尚未保存'}
  log=self.root/'native_runtime.log';tail=''
  if log.exists():
   with log.open('rb') as f:f.seek(0,2);size=f.tell();f.seek(max(0,size-1024*1024));tail=f.read().decode('utf8','replace')
  pool=read(self.root/'pool_update_status.json',{});pid=pool.get('pid')
  tail='\n'.join(prepare_view.session_lines(tail,pid)) if prepare_view.process_alive(pid) else ''
  path=self.root/'workbench_rules.bin'
  if path.exists():
   tick=path.stat().st_mtime_ns//100+116444736000000000;key=f"{tick>>32}:{tick&0xffffffff}"
   status['draw']='核心已读取' if ('workbench draw rules applied revision='+key) in tail else '已保存，等待核心读取'
  formPath=self.root/'workbench_forms.bin'
  if formPath.exists():
   raw=formPath.read_bytes();revision=struct.unpack_from('<I',raw,8)[0] if len(raw)>=16 else None
   status['forms']='核心已读取' if revision is not None and f'workbench forms loaded revision={revision} rules=' in tail else '已保存，等待核心读取确认'
  status['pool']='等待运行中的插件读取'
  if tail and pool.get('config_revision')==prepare_view.config_digest(self.root):
   status['pool']='核心已读取成员与权重' if pool.get('published') and pool.get('applied')==pool.get('published') else '已发布，等待核心读取'
  return status
 def has_portrait(self, identity):
  self._refresh_local_portraits()
  if custom_portraits.path_for(self.root,identity).is_file():return True
  for folder,entry in (('portraits',self.portraits.get(identity,{})),('local_portraits',self.local_portraits.get(identity,{}))):
   name=entry.get('file','') if isinstance(entry,dict) else ''
   if isinstance(name,str) and re.fullmatch(r'[0-9a-f]{24}\.png',name) and (self.root/'Workbench'/folder/name).is_file():return True
  return False
 def ruleset_snapshot(self,pool_data=None):
  if pool_data is None:pool_data=rulesets.pools(self.root)
  state, items = rulesets.list_rulesets(self.root, self.has_portrait, pool_data)
  items.extend(chapter_nine.rule_items(self.root, state, items, self.has_portrait))
  selected = None
  wanted = (state.get('selected') or {}).get('id')
  for item in items:
   if item['id'] == wanted:
    selected = item
    break
  if selected and selected.get('kind') == 'global':
   selected = dict(selected)
   selected['sinner'] = str((state.get('selected') or {}).get('sinner') or '101')
  if selected and selected['kind']=='chapter':
   return state,items,selected,[dict(entry_kind='group',group_id='ch9_'+selected['identity'],weight=1)],''
  entries = rulesets.entries(self.root, selected, pool_data) if selected else []
  revision = rulesets.revision(self.root, selected) if selected else hashlib.sha256(b'').hexdigest()
  return state, items, selected, entries, revision
 def data(self):
  pools=read(self.root/'Assets/runtime/all_sinners_pools.json',{})
  rule_state, rule_items, active_rule, rule_entries, rule_revision = self.ruleset_snapshot(pools)
  catalog={str(e['identity_id']):dict(e,source="Boss" if e.get("category")=="humanoid_boss" else key) for key,p in pools.items() for e in p.get('entries',[])}
  for e in read(self.root/'identity_catalog.json',{}).get('rows',[]):
   catalog.setdefault(str(e['id']),{'identity_id':str(e['id']),'name':e['appearance'],'source':str(100+int(e['character']))})
  translations=name_translations.load(self.root)
  for identity,e in catalog.items():
   e['name']=name_translations.name(identity,e.get('name',''),translations)
   if self.has_portrait(identity):e['portrait_url']='api/portrait/'+quote(identity,safe='')
  chapters=read(self.root/'boss_chapters.json',{})
  for identity,e in catalog.items():
   if identity in chapters:
    group=chapters.get(identity,{})
    e.update(chapter=group.get('chapter','unassigned'),chapter_label=group.get('label','未归档'),chapter_memberships=chapter_categories.memberships(group))
    e.update(chapter_rank=group.get('rank',20000),chapter_sources=group.get('appearances_in',[]),source_note='；'.join(x.get('note','') for x in group.get('special_evidence',[])),source_evidence_level=group.get('confidence',''),source_battles=sorted({str(x['battle_id']) for x in group.get('battle_evidence',[]) if x.get('battle_id') is not None}))
  walpurgis_catalog.apply(catalog,walpurgis_catalog.load(self.root))
  native_forms=read(self.root/'native_forms.json',{})
  for entry in catalog.values():entry['director_forms']=stage_director.director_forms(entry,native_forms)
  pool_status=read(self.root/'pool_update_status.json',{});pid=pool_status.get('pid');alive=prepare_view.process_alive(pid)
  preparation=prepare_view.summarize(prepare_view.read_tail(self.root/'native_runtime.log'),pid,alive,list(catalog.values()))
  return dict(self.snapshot(),preparation=preparation,rulesetState=rule_state,rulesets=rule_items,activeRule=active_rule,ruleEntries=rule_entries,ruleRevision=rule_revision,stageGroups=stage_director.snapshot(self.root)['config']['groups'],settings=self.settings_snapshot(),runtime=self.runtime_status(),director=self.director_snapshot(),formAnnotations=self.form_annotations(),catalog=list(catalog.values()),chapterArt=chapter_cards.load(self.root),pools=pools,forms=native_forms,warmup=read(self.root/'warmup_status.json',{}),version=read(self.root/'addon_info.json',{}).get('version','未知'))
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
  error=SCAN.get('error') or ('每周自动检测未完成，请查看检测记录' if weekly.get('status')=='failed' else None)
  return {'running':bool(SCAN.get('running') or weekly.get('status')=='running'),'started':SCAN.get('started'),'error':error,'weekly':{'slot':weekly.get('slot'),'status':weekly.get('status'),'finished':weekly.get('finished')}}
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
SCAN_EXIT={'2':'未安装 UnityPy：python -m pip install UnityPy','3':'找不到 Addressables 缓存，先启动一次游戏','4':'已有扫描在进行','5':'无法在工作台目录创建扫描锁','6':'人格池文件缺失或损坏，请检查插件安装'}
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
   script=pathlib.Path(root)/'Workbench/scan_units.py'
   flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
   env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
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
   SCAN['running']=False;SCAN['finished']=time.time()
 threading.Thread(target=work,daemon=True).start()
 return {'running':True,'started':SCAN['started']}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--addon',required=True);ap.add_argument('--no-browser',action='store_true');ap.add_argument('--host-pid',type=int);args=ap.parse_args()
 instance=instance_control.Instance(args.addon)
 if not instance.acquire():
  try:
   url=instance.existing();instance.attach(url,args.host_pid);print(url,flush=True)
   if not args.no_browser:webbrowser.open(url)
  finally:instance.close()
  return
 lifetime=host_lifetime.Lifetime();lifetime.register(args.host_pid)
 store=Store(args.addon);token=secrets.token_urlsafe(24);html=(pathlib.Path(__file__).parent/'index.html').read_bytes()
 class Handler(BaseHTTPRequestHandler):
  # Browsers can preconnect without sending a request. Bound the socket wait
  # so server_close can join those handlers when the launcher exits.
  timeout=5
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
    if route=='effect-editor':return self.send((pathlib.Path(__file__).parent/'effect-editor.html').read_bytes(),ctype='text/html; charset=utf-8')
    if route=='instance-ping':return self.send({'workbench':True})
    if route=='portrait-progress':return self.send(_portrait_state())
    if route=='rulesets':return self.send(_ruleset_payload(store))
    if route=='data':return self.send(store.data())
    if route=='form-merged':return self.send({'families':merged_appearances.families(store.data()['catalog']),'native_supported':True})
    if route=='form-director':
     state=stage_director.snapshot(store.root);state['candidates']=stage_director.candidates(store.data()['catalog'],store.form_annotations());return self.send(state)
    if route=='events':return self.send(store.events())
    if route=='discovered':return self.send(store.discovered())
    if route=='schemes':return self.send({'schemes':schemes.listing(store.root),'chapter_nine':chapter_nine.profiles(store.root)})
    if route=='effect-schemes':return self.send({'schemes':effect_schemes.listing(store.root)})
    if route=='effect-selection':return self.send(fx_activation.read_selection(store.root))
    if route and route.startswith('chapter-image/'):
     image=chapter_cards.image(store.root,unquote(route[len('chapter-image/'):]))
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
   if route not in ('save','import','director','form-director','form-merged-set','form-preview','form-trace','form-compare','form-group-to-pool','bundle','boss-preview','update-check','update-install','portrait-save','portrait-reset','portrait-download','images-delete','ruleset-activate','ruleset-save','ruleset-create','ruleset-only','ruleset-deactivate','scan','scheme-save','scheme-load','scheme-delete','scheme-import','scheme-get','effect-scheme-save','effect-scheme-get','effect-scheme-delete','effect-timelines','effect-live-start','effect-live-status','effect-plan-preview','effect-selection','effect-sprites','effect-sprites-start','effect-sprites-status','effect-sprites-cancel','effect-sprite-export','instance-shutdown','instance-attach','instance-release'):return self.send({'error':'未找到'},404)
   if self.headers.get('X-Workbench')!=token:return self.send({'error':'请求无效'},403)
   try:
    n=int(self.headers.get('Content-Length',0))
    limit=2*1024*1024 if route=='portrait-save' else 1024*1024
    if not 0<n<=limit:raise ValueError('请求过大或为空')
    body=json.loads(self.rfile.read(n))
    if route=='instance-attach':
     lifetime.register(body.get('host_pid'));return self.send({'attached':True})
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
    if route=='form-director':
     with store.lock:
      catalog=store.data()['catalog'];stage_director.validate(body['config'],catalog)
      warnings=stage_director.pool_link_warnings(store.root,body['config'])
      result=stage_director.save(store.root,body['config'],body['revision'],catalog);result['warnings']=warnings;return self.send(result)
    if route=='form-merged-set':
     with store.lock:
      catalog=store.data()['catalog'];families=merged_appearances.families(catalog)
      family=next((f for f in families if f['id']==body.get('family_id')),None)
      if not family:raise ValueError('该外观组不可用')
      group=merged_appearances.make_group(family,body.get('mode'))
      _,_,rule,entries,revision=store.ruleset_snapshot()
      incoming=body.get('rule') or {}; expected_id=body.get('rule_id') or incoming.get('id'); expected_sinner=body.get('sinner') or incoming.get('sinner')
      if not rule or rule['id']!=expected_id or str(rule.get('sinner'))!=str(expected_sinner):raise ValueError('当前规则集已改变，请刷新')
      if revision!=body.get('revision'):raise ValueError('规则池已改变，请刷新')
      selected=body.get('identity_id') or family['members'][0]
      if selected not in family['members']:raise ValueError('外观不属于此形态组')
      old_group=body.get('group_id')
      if old_group and old_group not in family['group_ids']:raise ValueError('形态组不属于此外观')
      idx=next((i for i,e in enumerate(entries) if (e.get('entry_kind')=='group' and old_group and e.get('group_id')==old_group) or (not old_group and e.get('entry_kind','appearance')=='appearance' and e.get('identity_id')==selected)),None)
      merge=body.get('merge_members',False)
      if type(merge) is not bool:raise ValueError('合并选项无效')
      indices=[i for i,e in enumerate(entries) if merge and e.get('entry_kind','appearance')=='appearance' and e.get('identity_id') in family['members']]
      if idx is not None and idx not in indices:indices.append(idx)
      indices.sort()
      if idx is None and indices:idx=indices[0]
      if idx is None and not body.get('add_if_missing'):raise ValueError('该外观不在当前规则池')
      if any(i not in indices and e.get('entry_kind')=='group' and e.get('group_id')==group['id'] for i,e in enumerate(entries)):raise ValueError('当前规则池已有该形态组')
      weight=sum(entries[i]['weight'] for i in indices) if indices else 1
      if weight>1000000:raise ValueError('合并后的权重超过上限，请先调整')
      item={'entry_kind':'group','group_id':group['id'],'weight':weight}
      if not indices:updated=list(entries)+[item]
      else:updated=[item if i==indices[0] else e for i,e in enumerate(entries) if i==indices[0] or i not in indices]
      if len(updated)>rulesets.MAX_ENTRIES:raise ValueError('规则池已满')
      before=stage_director.snapshot(store.root);config=merged_appearances.upgrade_legacy_groups({'schema':1,'groups':list(before['config'].get('groups',[]))})
      existing=next((g for g in config['groups'] if g.get('id')==group['id']),None)
      if existing and existing!=group:raise ValueError('已有同编号的自定义形态组，请先在形态导演中处理')
      if not existing:config['groups'].append(group)
      stage_director.validate(config,catalog)
      paths=[store.root/stage_director.FILE,store.root/'native_stage_groups.bin']; originals=[p.read_bytes() if p.exists() else None for p in paths]
      try:
       if config!=before['config']:stage_director.save(store.root,config,before['revision'],catalog)
       rulesets.save_entries(store.root,rule,updated,revision,{str(e['identity_id']) for e in catalog},store.validate,store.lock)
      except Exception:
       for path,data in zip(paths,originals):
        if data is None:path.unlink(missing_ok=True)
        else:
         tmp=path.with_name(path.name+'.merged-rollback');tmp.write_bytes(data);tmp.replace(path)
       raise
      return self.send(_ruleset_payload(store))
    if route=='form-preview':
     group=body['group'];stage_director.validate({'schema':1,'groups':[group]},store.data()['catalog'])
     return self.send(stage_director.preview(group,body['health'],body['sanity'],body['defense'],body.get('current_stage',0)))
    if route=='form-trace':
     group=body['group'];stage_director.validate({'schema':1,'groups':[group]},store.data()['catalog'])
     return self.send(stage_director.trace(group,body.get('steps'),body.get('current_stage',0)))
    if route=='form-compare':
     left=body['left'];right=body['right'];catalog=store.data()['catalog']
     stage_director.validate({'schema':1,'groups':[left]},catalog);stage_director.validate({'schema':1,'groups':[right]},catalog)
     steps=body.get('steps');return self.send({'left':stage_director.trace(left,steps,body.get('left_current',0)),'right':stage_director.trace(right,steps,body.get('right_current',0))})
    if route=='form-group-to-pool':
     with store.lock:
      group=next((g for g in stage_director.snapshot(store.root)['config'].get('groups',[]) if g.get('id')==body.get('group_id')),None)
      if not group or not group.get('enabled'):raise ValueError('请先保存并启用形态组')
      stage_director.validate({'schema':1,'groups':[group]},store.data()['catalog'])
      weight=body.get('weight')
      if isinstance(weight,bool) or not isinstance(weight,(int,float)) or not math.isfinite(weight) or not 0<weight<=1000000:raise ValueError('权重应大于 0 且不超过 1000000')
      _,_,rule,entries,revision=store.ruleset_snapshot()
      if not rule or rule['kind']=='chapter':raise ValueError('请先选择可编辑的规则集和目标角色')
      if rule['id']!=body.get('rule_id') or str(rule.get('sinner'))!=str(body.get('sinner')):raise ValueError('当前选择的规则集或目标角色已变化，请刷新后重试')
      if revision!=body.get('revision'):raise ValueError('规则池已变化，请刷新后重试')
      if any(e.get('entry_kind')=='group' and e.get('group_id')==group['id'] for e in entries):raise ValueError('规则池中已有该形态组')
      if len(entries)>=rulesets.MAX_ENTRIES:raise ValueError('规则池已满')
      entries.append({'entry_kind':'group','group_id':group['id'],'weight':weight})
      known={str(e['identity_id']) for e in store.data()['catalog']}
      rulesets.save_entries(store.root,rule,entries,revision,known,store.validate,store.lock)
      return self.send(_ruleset_payload(store))
    if route=='portrait-download':
     return self.send({'started':_portrait_start(store.root),'progress':_portrait_state()})
    if route=='images-delete':
     if _PORTRAIT_THREAD is not None and _PORTRAIT_THREAD.is_alive():raise ValueError('资源检索正在进行，请结束后再删除')
     return self.send(_delete_images(store.root))
    if route=='scan':return self.send(start_scan(store.root))
    if route in ('update-check','update-install'):
     import github_update
     return self.send(github_update.check(store.root) if route=='update-check' else github_update.install(store.root))
    if route=='boss-preview':return self.send(add_boss_members(body['profile'],store.data()['catalog'],body.get('chapter')))
    if route.startswith('ruleset-') and (body.get('rule') or body).get('kind')=='chapter':
     op={'ruleset-activate':'enable','ruleset-deactivate':'disable','ruleset-only':'only'}.get(route)
     if not op:raise ValueError('第九章内置规则的外观池固定')
     ident=(body.get('rule') or body).get('identity')
     if not isinstance(ident,str):raise ValueError('缺少第九章人格编号')
     chapter_nine.activate(store,ident,op)
     return self.send(_ruleset_payload(store))
    if route=='ruleset-activate':
     rulesets.activate(store.root, body.get('rule') or body)
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
      old=stage_director.snapshot(store.root)['config']
      loaded=chapter_nine.activate(store) if body.get('builtin')=='chapter-nine' else schemes.load(store,body.get('name'),known)
      warnings=stage_director.pool_link_warnings(store.root,stage_director.snapshot(store.root)['config'],old)
      return self.send({'loaded':loaded,'schemes':schemes.listing(store.root),'warnings':warnings})
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
      filenames=['自定义人格池.json','演出编排.json','workbench_rules.bin','workbench_forms.bin']
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
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=False;lifetime.watch(server);url=f'http://127.0.0.1:{server.server_port}/{token}/';instance.publish(url);print(url,flush=True)
 if not args.no_browser:webbrowser.open(url)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close();_stop_children();lifetime.close();instance.close()
if __name__=='__main__':main()
