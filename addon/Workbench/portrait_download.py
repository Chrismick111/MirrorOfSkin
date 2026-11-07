"""Download the optional portraits published with the latest stable release."""
import hashlib,io,json,os,pathlib,re,zipfile
from urllib.parse import urlparse
from file_lock import FileLock
from github_update import API, REPO, _fetch, _version, UpdateError
ASSET='FaustRandomIdentity-Portraits.zip'
MAX_ZIP=200*1024*1024
MAX_TOTAL=300*1024*1024

def download(root):
 root=pathlib.Path(root).resolve()
 with FileLock(root/'github-update.lock'):
  return _download_locked(root)

def _download_locked(root):
 release=json.loads(_fetch(API,2*1024*1024))
 current=json.loads((root/'addon_info.json').read_text(encoding='utf-8-sig')).get('version','')
 if _version(current)!=_version(release.get('tag_name','')):raise UpdateError('头像包版本与当前插件不同，请先更新核心')
 assets=[a for a in release.get('assets',[]) if a.get('name')==ASSET and a.get('state')=='uploaded']
 if len(assets)!=1:raise UpdateError('当前 Release 没有头像资源包')
 asset=assets[0];digest=asset.get('digest') or '';url=asset.get('browser_download_url','');p=urlparse(url)
 if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest):raise UpdateError('头像包缺少 SHA-256 校验值')
 if p.scheme!='https' or p.netloc.lower()!='github.com' or not p.path.startswith('/'+REPO+'/releases/download/'):raise UpdateError('头像包地址不属于指定仓库')
 blob=_fetch(url,MAX_ZIP)
 if hashlib.sha256(blob).hexdigest()!=digest[7:].lower():raise UpdateError('头像包 SHA-256 不匹配')
 hashfile=root/'Workbench/portrait_hashes.json'
 if not hashfile.is_file():raise UpdateError('当前插件尚不支持分离头像包，请先更新核心插件')
 manifest=json.loads((root/'Workbench/portrait_manifest.json').read_text(encoding='utf-8-sig'))
 names={v.get('file') for v in manifest.values() if isinstance(v,dict) and isinstance(v.get('file'),str)}
 hashes=json.loads(hashfile.read_text(encoding='utf-8-sig'))
 if not isinstance(hashes,dict) or any(not re.fullmatch(r'Workbench/portraits/[0-9a-f]{24}\.png',k) or not isinstance(v,str) or not re.fullmatch(r'[0-9a-fA-F]{64}',v) or k.rsplit('/',1)[-1] not in names for k,v in hashes.items()):raise UpdateError('头像校验清单无效')
 compat=json.loads((root/'compatibility.json').read_text(encoding='utf-8-sig'));tracked=compat.get('package_files',{})
 files={};total=0
 try:
  with zipfile.ZipFile(io.BytesIO(blob)) as z:
   for info in z.infolist():
    if info.is_dir():continue
    name=info.filename
    if name=='portrait-hashes.json':
     if info.file_size>1024*1024 or json.loads(z.read(info).decode('utf8'))!=hashes:raise UpdateError('头像包清单与核心不符')
     continue
    if not re.fullmatch(r'Workbench/portraits/[0-9a-f]{24}\.png',name) or name.rsplit('/',1)[-1] not in names or name in files:raise UpdateError('头像包包含未声明的文件')
    if (info.external_attr>>16)&0o170000==0o120000:raise UpdateError('头像包不能包含符号链接')
    total+=info.file_size
    if total>MAX_TOTAL:raise UpdateError('头像包解压内容过大')
    data=z.read(info)
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise UpdateError('头像图片格式无效')
    if name not in hashes or hashlib.sha256(data).hexdigest()!=hashes[name].lower():raise UpdateError('头像与核心校验清单不符')
    if name in tracked and hashlib.sha256(data).hexdigest()!=tracked[name].lower():raise UpdateError('头像不符合当前插件校验清单')
    dst=root.joinpath(*name.split('/'))
    if not dst.resolve().is_relative_to(root):raise UpdateError('头像路径无效')
    files[name]=data
 except (zipfile.BadZipFile,RuntimeError) as exc:raise UpdateError('头像资源包损坏') from exc
 if not files:raise UpdateError('头像资源包为空')
 if set(files)!=set(hashes):raise UpdateError('头像包不完整')
 written=[];before={}
 try:
  for name,data in files.items():
   path=root.joinpath(*name.split('/'));path.parent.mkdir(parents=True,exist_ok=True)
   before[name]=path.read_bytes() if path.exists() else None
   tmp=path.with_name(path.name+'.portrait-tmp');tmp.write_bytes(data);os.replace(tmp,path);written.append(name)
 except Exception:
  for name in reversed(written):
   path=root.joinpath(*name.split('/'));old=before[name]
   if old is None:path.unlink(missing_ok=True)
   else:path.write_bytes(old)
  raise
 return {'count':len(files),'message':'头像资源已下载，请刷新工作台'}
