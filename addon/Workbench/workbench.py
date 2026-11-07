from urllib.parse import unquote, quote
from file_lock import FileLock
import director
import struct
import subprocess
import argparse,hashlib,json,math,os,pathlib,re,secrets,threading,time,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

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
 def __init__(self,root):self.root=pathlib.Path(root);self.lock=FileLock(self.root/'workbench-save.lock');self.portraits=read(self.root/'Workbench/portrait_manifest.json',{})
 def portrait(self,identity):
  row=self.portraits.get(identity,{})
  name=row.get('file','')
  if not name or pathlib.Path(name).name!=name or '/' in name or '\\' in name or not name.endswith('.png'):return None
  path=self.root/'Workbench/portraits'/name
  return path.read_bytes() if path.is_file() else None
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
 def validate(self,target,p,known):
  if target not in {str(i) for i in range(101,113)}:raise ValueError('无效出战角色')
  if not isinstance(p.get('enabled'),bool):raise ValueError('启用状态无效')
  entries=p.get('entries',[]);seen=set();total=0
  if not isinstance(entries,list) or len(entries)>256:raise ValueError('每池最多256项')
  for e in entries:
   identity=str(e['identity_id']);w=e['weight']
   if identity not in known or identity in seen:raise ValueError('未知或重复人格：'+identity)
   if isinstance(w,bool) or not isinstance(w,(int,float)) or not math.isfinite(w) or not 0<=w<=1000000:raise ValueError('权重应为0至1000000的有限数字')
   seen.add(identity);total+=w
  if p['enabled'] and total<=0:raise ValueError('启用的池至少需要一个正权重人格')
 def replace(self,config,revision,known):
  if config.get('schema')!=1 or not isinstance(config.get('characters'),dict):raise ValueError('方案格式不受支持')
  for target,p in config['characters'].items():self.validate(target,p,known)
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
  path=self.root/'workbench_rules.bin'
  if path.exists():
   tick=path.stat().st_mtime_ns//100+116444736000000000;key=f"{tick>>32}:{tick&0xffffffff}"
   status['draw']='核心已读取' if ('workbench draw rules applied revision='+key) in tail else '已保存，等待核心读取'
  formPath=self.root/'workbench_forms.bin'
  if formPath.exists():
   raw=formPath.read_bytes();revision=struct.unpack_from('<I',raw,8)[0] if len(raw)>=16 else None
   status['forms']='核心已读取' if revision is not None and f'workbench forms loaded revision={revision} rules=' in tail else '已保存，等待核心读取确认'
  pool=read(self.root/'pool_update_status.json',{})
  status['pool']='等待运行中的插件读取'
  if pool.get('config_revision')==self.snapshot()['revision']:
   status['pool']='核心已读取成员与权重' if pool.get('published') and pool.get('applied')==pool.get('published') else '已发布，等待核心读取'
  return status
 def data(self):
  pools=read(self.root/'Assets/runtime/all_sinners_pools.json',{})
  catalog={str(e['identity_id']):dict(e,source="Boss" if e.get("category")=="humanoid_boss" else key) for key,p in pools.items() for e in p.get('entries',[])}
  for e in read(self.root/'identity_catalog.json',{}).get('rows',[]):
   catalog.setdefault(str(e['id']),{'identity_id':str(e['id']),'name':e['appearance'],'source':str(100+int(e['character']))})
  for identity,e in catalog.items():
   if identity in self.portraits:e['portrait_url']='api/portrait/'+quote(identity,safe='')
  chapters=read(self.root/'boss_chapters.json',{})
  for identity,e in catalog.items():
   if e.get('category')=='humanoid_boss':
    group=chapters.get(identity,{})
    e.update(chapter=group.get('chapter','unassigned'),chapter_label=group.get('label','未归档'),chapter_memberships=group.get('memberships',[{'chapter':group.get('chapter','unassigned'),'label':group.get('label','未归档')}]))
    e.update(chapter_rank=group.get('rank',20000),chapter_sources=group.get('appearances_in',[]),source_note='；'.join(x.get('note','') for x in group.get('special_evidence',[])),source_evidence_level=group.get('confidence',''),source_battles=sorted({str(x['battle_id']) for x in group.get('battle_evidence',[]) if x.get('battle_id') is not None}))
  return dict(self.snapshot(),settings=self.settings_snapshot(),runtime=self.runtime_status(),director=self.director_snapshot(),formAnnotations=self.form_annotations(),catalog=list(catalog.values()),pools=pools,forms=read(self.root/'native_forms.json',{}),warmup=read(self.root/'warmup_status.json',{}),version=read(self.root/'addon_info.json',{}).get('version','未知'))
 def events(self):
  path=self.root/'native_runtime.log'
  if not path.exists():return []
  with path.open('rb') as f:
   f.seek(0,2);size=f.tell();f.seek(max(0,size-2*1024*1024));text=f.read().decode('utf8','replace')
  lines=text.splitlines()
  return [parse_event(s) for s in lines if any(k in s for k in ['coin metadata','coin play','coin draw','event=','clash camera','projection ','idle blocked','retained after'])][-600:]

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--addon',required=True);ap.add_argument('--no-browser',action='store_true');args=ap.parse_args()
 store=Store(args.addon);token=secrets.token_urlsafe(24);html=(pathlib.Path(__file__).parent/'index.html').read_bytes()
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def send(self,body,status=200,ctype='application/json; charset=utf-8',cache='no-store'):
   data=body if isinstance(body,bytes) else json.dumps(body,ensure_ascii=False,allow_nan=False).encode('utf8');self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Cache-Control',cache);self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
  def route(self):
   prefix='/'+token
   if self.path==prefix+'/':return 'index'
   if self.path.startswith(prefix+'/api/'):return self.path[len(prefix+'/api/'):]
   return None
  def do_GET(self):
   route=self.route()
   try:
    if route=='index':return self.send(html,ctype='text/html; charset=utf-8')
    if route=='data':return self.send(store.data())
    if route=='events':return self.send(store.events())
    if route and route.startswith('portrait/'):
     image=store.portrait(unquote(route[len('portrait/'):]))
     if image is not None:return self.send(image,ctype='image/png',cache='private, max-age=600')
    return self.send({'error':'未找到'},404)
   except Exception as e:return self.send({'error':str(e)},500)
  def do_POST(self):
   route=self.route()
   if route not in ('save','import','legacy','director','bundle','boss-preview','update-check','update-install'):return self.send({'error':'未找到'},404)
   if self.headers.get('X-Workbench')!=token:return self.send({'error':'请求无效'},403)
   try:
    n=int(self.headers.get('Content-Length',0))
    if not 0<n<=1024*1024:raise ValueError('方案文件过大或为空')
    body=json.loads(self.rfile.read(n))
    if route in ('update-check','update-install'):
     import github_update
     return self.send(github_update.check(store.root) if route=='update-check' else github_update.install(store.root))
    if route=='boss-preview':return self.send(add_boss_members(body['profile'],store.data()['catalog'],body.get('chapter')))
    if route=='legacy':
     subprocess.Popen(['powershell.exe','-NoProfile','-STA','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',str(store.root/'Settings.ps1')],cwd=store.root,creationflags=subprocess.CREATE_NO_WINDOW)
     return self.send({'opened':True})
    known={str(e['identity_id']) for e in store.data()['catalog']}
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
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);url=f'http://127.0.0.1:{server.server_port}/{token}/';print(url,flush=True)
 if not args.no_browser:webbrowser.open(url)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
if __name__=='__main__':main()
