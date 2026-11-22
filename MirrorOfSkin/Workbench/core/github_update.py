"""Install only complete, integrity-checked releases from the configured GitHub repository."""
import ast, hashlib, io, json, os, pathlib, re, shutil, subprocess, tempfile, urllib.error, urllib.request, zipfile
from urllib.parse import urlparse
from file_lock import FileLock

REPO='Chrismick111/MirrorOfSkin'
API='https://api.github.com/repos/'+REPO+'/releases/latest'
ASSET='FaustRandomIdentity-WarpHook.zip'
CATALOG='Assets/runtime/all_sinners_pools.json'
MAX_ZIP=200*1024*1024
MAX_TOTAL=512*1024*1024
PROTECTED={'随机设置.json','自定义人格池.json','演出编排.json','native_pools.bin','停止随机运行.flag','workbench_rules.bin','workbench_forms.bin','Assets/runtime/all_sinners_pools.json','auto_forms.bin','auto_internal_forms.jsonl','auto_form_annotations.json','auto_registry.json','identity_catalog.json','Workbench/data/portrait_source.local.json','Workbench/portrait_source.local.json'}
PROTECTED.update({'Workbench/weekly_scan_status.json','Workbench/weekly_scan.lock','Workbench/auto_translation_cache.json','Workbench/chapter_art/chapters.discovered.json','Workbench/chapter_art/discovered-assets.json'})
PROTECTED.add('workbench-instance.json')
PROTECTED.add('Assets/Roland/BRoland.bundle')
PROTECTED.update({'规则集状态.json','stage_director.json','特效启用状态.json','fx-active.bin'})
PROTECTED_PREFIXES=('animation-times-', '方案/', '规则集/', '特效方案/', 'plugin-backups/', 'backup/', 'backups/', 'workbench/user_portraits/', 'workbench/local_portraits/', 'assets/importedskins/', 'assets/importedvoices/', 'assets/carrabases/')

class UpdateError(ValueError):pass

def _version(s):
 m=re.match(r'^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$',s or '')
 if not m:raise UpdateError('版本号格式无效')
 return tuple(map(int,m.groups()))

def _fetch(url,limit):
 req=urllib.request.Request(url,headers={'User-Agent':'FaustRandomIdentity-Updater','Accept':'application/vnd.github+json'})
 try:
  with urllib.request.urlopen(req,timeout=20) as response:
   b=response.read(limit+1)
   if len(b)>limit:raise UpdateError('下载内容过大')
   return b
 except urllib.error.HTTPError as exc:
  if exc.code==404:raise UpdateError('仓库尚未发布可安装版本') from exc
  raise UpdateError('GitHub 更新请求失败：HTTP '+str(exc.code)) from exc
 except (urllib.error.URLError,TimeoutError,OSError) as exc:raise UpdateError('无法连接 GitHub，请检查网络') from exc

def _check(current):
 raw=_fetch(API,2*1024*1024)
 try: release=json.loads(raw)
 except (ValueError,TypeError) as exc:raise UpdateError('发布信息格式无效') from exc
 tag=release.get('tag_name',''); new=_version(tag); old=_version(current)
 assets=[a for a in release.get('assets',[]) if a.get('name')==ASSET and a.get('state')=='uploaded']
 if len(assets)!=1:
  if new<=old:return {'available':False,'version':tag,'message':'当前已是最新版本；此版本没有安装包'}
  raise UpdateError('新版本缺少插件安装包：'+ASSET)
 a=assets[0]; digest=a.get('digest') or ''; url=a.get('browser_download_url',''); p=urlparse(url)
 if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest):raise UpdateError('发布包缺少 SHA-256 校验值')
 if p.scheme!='https' or p.netloc.lower()!='github.com' or not p.path.startswith('/'+REPO+'/releases/download/'):raise UpdateError('发布包地址不属于指定仓库')
 return {'available':new>old,'version':tag,'url':url,'digest':digest.lower(),'message':'发现新版本' if new>old else '当前已是最新版本'}

def _safe_path(name):
 if not isinstance(name,str) or not name or '\\' in name or ':' in name or name.startswith('/') or any(p in ('','.','..') or p.endswith((' ','.')) for p in name.split('/')):raise UpdateError('安装包含无效路径')
 return name

def _protected(name):
 low=name.casefold()
 return (low in {x.casefold() for x in PROTECTED} or low.startswith(PROTECTED_PREFIXES) or low.endswith(('.log','.bak','.flag','.lock','.tmp')) or pathlib.PurePosixPath(low).name.startswith(('native_runtime','auto_registry','pool_update_status','warmup_status','workbench-save')))

def merge_catalog(local_bytes,release_bytes):
 try: old=json.loads(local_bytes.decode('utf-8-sig'));new=json.loads(release_bytes.decode('utf-8-sig'))
 except (ValueError,UnicodeError) as exc:raise UpdateError('人格目录格式无效') from exc
 if not isinstance(old,dict) or not isinstance(new,dict) or set(old)!=set(new) or set(new)!={str(i) for i in range(101,113)}:raise UpdateError('人格目录角色范围不匹配')
 result={}
 for role in new:
  original=old[role];incoming=new[role]
  if not isinstance(original,dict) or not isinstance(incoming,dict) or not isinstance(original.get('entries'),list) or not isinstance(incoming.get('entries'),list):raise UpdateError('人格目录条目无效')
  def indexed(rows):
   out={}
   for e in rows:
    if not isinstance(e,dict) or not isinstance(e.get('identity_id'),str) or not e['identity_id'] or e['identity_id'] in out:raise UpdateError('人格目录含无效或重复条目')
    out[e['identity_id']]=e
   return out
  before=indexed(original['entries']);after=indexed(incoming['entries'])
  rows=[]
  for key,e in after.items():
   entry=dict(e)
   if key in before:
    if key.startswith('story_WBImp_'):
     entry.update(before[key])
    for field in ('weight','enabled'):
     if field in before[key]:entry[field]=before[key][field]
   rows.append(entry)
  rows.extend(v for k,v in before.items() if k not in after)
  result[role]={**original,**incoming,'entries':rows}
 return (json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf8')

def _running():
 if os.name!='nt':return False
 try:
  r=subprocess.run(['tasklist','/NH'],capture_output=True,text=True,timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  if r.returncode!=0:raise UpdateError('无法检查游戏进程')
  return any(x in r.stdout.lower() for x in ('limbuscompany.exe','faustlauncher.exe','yisangmodloader.exe'))
 except (OSError,subprocess.TimeoutExpired) as exc:raise UpdateError('无法检查游戏进程') from exc

def _current(root):
 try:return json.loads((pathlib.Path(root)/'addon_info.json').read_text(encoding='utf-8-sig'))['version']
 except (OSError,KeyError,ValueError) as exc:raise UpdateError('无法读取当前插件版本') from exc

def check(root):
 current=_current(root);info=_check(current)
 return {'current':current,'latest':info['version'],'available':info['available'],'message':info['message']}

def install(root):
 root=pathlib.Path(root).resolve()
 with FileLock(root/'github-update.lock'):
  return _install_locked(root)

def _install_locked(root):
 if _running():raise UpdateError('请完全退出游戏与启动器后再更新')
 info=_check(_current(root))
 if not info['available']:return info
 blob=_fetch(info['url'],MAX_ZIP)
 if hashlib.sha256(blob).hexdigest()!=info['digest'][7:]:raise UpdateError('发布包 SHA-256 不匹配')
 try:
  with zipfile.ZipFile(io.BytesIO(blob)) as z:
   files={};total=0
   for member in z.infolist():
    if member.is_dir():continue
    if (member.external_attr >> 16)&0o170000==0o120000:raise UpdateError('安装包不能包含符号链接')
    n=_safe_path(member.filename)
    if n in files or n.casefold() in (x.casefold() for x in files):raise UpdateError('安装包存在重复路径')
    total+=member.file_size
    if total>MAX_TOTAL:raise UpdateError('解压内容过大')
    files[n]=z.read(member)
 except (zipfile.BadZipFile,RuntimeError) as exc:raise UpdateError('安装包损坏') from exc
 try:
  manifest=json.loads(files['compatibility.json'].decode('utf-8-sig'))
  addon=json.loads(files['addon_info.json'].decode('utf-8-sig'))
  if manifest.get('schema')!=1 or not isinstance(manifest.get('game_files'),dict) or not manifest['game_files']:raise UpdateError('不支持的兼容性清单')
  if _version(manifest['version'])!=_version(info['version']) or _version(addon['version'])!=_version(info['version']):raise UpdateError('发布版本与包内版本不一致')
  expected=manifest['package_files']; dll=_safe_path(manifest['dll'])
  if not isinstance(expected,dict) or not expected or dll not in expected or 'scr.py' not in expected or 'addon_info.json' not in expected:raise UpdateError('安装包缺少必要文件')
  for name,h in expected.items():
   _safe_path(name)
   if _protected(name) or name not in files or not re.fullmatch('[0-9a-fA-F]{64}',h) or hashlib.sha256(files[name]).hexdigest()!=h.lower():raise UpdateError('安装包文件校验失败：'+name)
  if set(files)!=set(expected)|{'compatibility.json',CATALOG}:raise UpdateError('安装包含未声明文件或缺少发行目录')
  catalog_path=root.joinpath(*CATALOG.split('/'))
  files[CATALOG]=merge_catalog(catalog_path.read_bytes(),files[CATALOG])
  parsed=ast.parse(files['scr.py'].decode('utf8'))
  dll_names=[n.value.value for n in parsed.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DLL_NAME' for t in n.targets) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str)]
  if dll_names!=[dll]:raise UpdateError('安装包脚本与 DLL 清单不一致')
  # Keep launcher-owned switches (auto-open/tutorial) across an update.
  try:
   previous=json.loads((root/'addon_info.json').read_text(encoding='utf-8-sig'))
  except (OSError,ValueError):
   previous={}
  previous_settings=previous.get('settings') if isinstance(previous.get('settings'),dict) else {}
  if previous_settings:
   merged_addon=dict(addon)
   merged_addon['settings']={**dict(merged_addon.get('settings') or {}),**previous_settings}
   merged_bytes=(json.dumps(merged_addon,ensure_ascii=False,indent=2)+'\n').encode('utf8')
   files['addon_info.json']=merged_bytes
   expected['addon_info.json']=hashlib.sha256(merged_bytes).hexdigest()
   manifest['package_files']['addon_info.json']=expected['addon_info.json']
   files['compatibility.json']=(json.dumps(manifest,ensure_ascii=False,indent=1)+'\n').encode('utf8')
 except UpdateError:raise
 except (KeyError,TypeError,ValueError,UnicodeError,SyntaxError) as exc:raise UpdateError('安装包清单无效') from exc
 if _running():raise UpdateError('请完全退出游戏与启动器后再更新')
 backup=pathlib.Path(tempfile.mkdtemp(prefix='FaustRandomIdentity-backup-',dir=root.parent))
 written=[]
 try:
  for name in list(expected)+[CATALOG,'compatibility.json']:
   dst=root.joinpath(*name.split('/'))
   if not dst.resolve().is_relative_to(root):raise UpdateError('安装路径无效')
   saved=backup.joinpath(*name.split('/'))
   if dst.exists():saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dst,saved)
   dst.parent.mkdir(parents=True,exist_ok=True)
   temp=dst.with_name(dst.name+'.update-tmp');temp.write_bytes(files[name]);os.replace(temp,dst);written.append(name)
 except Exception:
  for name in reversed(written):
   dst=root.joinpath(*name.split('/'));saved=backup.joinpath(*name.split('/'))
   if saved.exists():shutil.copy2(saved,dst)
   elif dst.exists():dst.unlink()
  raise
 return {'available':True,'version':info['version'],'installed':True,'message':'更新完成，请完全重启启动器和游戏','backup':str(backup)}
