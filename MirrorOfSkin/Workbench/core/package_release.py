import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import _module_paths
"""Build the release archive consumed by github_update without changing the addon."""
import argparse, hashlib, json, pathlib, zipfile
from github_update import ASSET, CATALOG, _protected, _safe_path, UpdateError

def package(root, output, *, launcher=False):
 root=pathlib.Path(root).resolve();output=pathlib.Path(output).resolve()
 if output.is_relative_to(root):raise UpdateError('发布包输出必须位于插件目录之外')
 manifest_path=root/'compatibility.json';manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
 if manifest.get('schema')!=1 or not isinstance(manifest.get('package_files'),dict) or not manifest['package_files']:raise UpdateError('兼容性清单无效')
 expected=manifest['package_files'];items={}
 for name,digest in expected.items():
  _safe_path(name)
  if _protected(name):raise UpdateError('清单包含个人数据：'+name)
  path=root.joinpath(*name.split('/'))
  if not path.resolve().is_relative_to(root) or not path.is_file():raise UpdateError('文件不存在或路径无效：'+name)
  value=path.read_bytes()
  if hashlib.sha256(value).hexdigest()!=digest.lower():raise UpdateError('文件校验失败：'+name)
  items[name]=value
 catalog=root.joinpath(*CATALOG.split('/'))
 if not catalog.resolve().is_relative_to(root) or not catalog.is_file():raise UpdateError('人格目录不存在')
 try:
  pools=json.loads(catalog.read_text(encoding='utf-8-sig'))
  if not isinstance(pools,dict) or set(pools)!={str(i) for i in range(101,113)}:raise ValueError('invalid roles')
  for p in pools.values():
   if not isinstance(p,dict) or not isinstance(p.get('entries'),list):raise ValueError('invalid entries')
   for entry in p['entries']:
    if not isinstance(entry,dict) or not isinstance(entry.get('identity_id'),str):raise ValueError('invalid identity')
    if 'weight' in entry:entry['weight']=1
    entry.pop('enabled',None)
  items[CATALOG]=(json.dumps(pools,ensure_ascii=False,indent=2)+'\n').encode('utf8')
 except (ValueError,TypeError,UnicodeError) as exc:raise UpdateError('人格目录格式无效') from exc
 items['compatibility.json']=manifest_path.read_bytes()
 output.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  prefix = 'MirrorOfSkin/' if launcher else ''
  for name,data in sorted(items.items()):z.writestr(prefix+name,data)
 return len(items)

if __name__=='__main__':
 p=argparse.ArgumentParser(description='从已校验插件创建 GitHub Release 安装包')
 p.add_argument('--addon',required=True);p.add_argument('--output',required=True,help='插件目录外的输出文件（Release 资产名必须为 '+ASSET+'）')
 p.add_argument('--launcher',action='store_true',help='为启动器本地导入添加固定的 MirrorOfSkin 插件目录')
 a=p.parse_args();print('已打包文件数:',package(a.addon,a.output,launcher=a.launcher))
 if not a.launcher:print('Release 资产名必须为:',ASSET)
