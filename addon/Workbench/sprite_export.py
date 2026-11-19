"""Export a verified Sprite slice at its original resolution to a local cache."""
import hashlib,os,pathlib,re,tempfile
import resource_catalog

def export_path(index_dir,name):
    if not isinstance(name,str) or not re.fullmatch(r'[0-9a-f]{64}\.png',name):return None
    path=pathlib.Path(index_dir)/'sprite-originals'/name
    return path if path.is_file() else None

def export_original(entry,roots,unity_py=None):
    if not isinstance(entry,dict) or not isinstance(roots,dict):raise ValueError('素材信息无效')
    rel=entry.get('bundle');cab=entry.get('cab');pid=entry.get('path_id');key=entry.get('sprite_key')
    if not all(isinstance(x,str) and x for x in (rel,cab,pid,key)) or key!=cab+':'+pid:raise ValueError('素材标识无效')
    try:path_id=int(pid)
    except ValueError:raise ValueError('素材标识无效')
    if str(path_id)!=pid:raise ValueError('素材标识无效')
    if not roots.get('resource_root') or not roots.get('index_dir'):raise ValueError('未找到游戏资源目录')
    root=pathlib.Path(roots['resource_root']).resolve();relative=pathlib.Path(rel)
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('资源包路径无效')
    bundle=(root/relative).resolve()
    try:bundle.relative_to(root)
    except ValueError:raise ValueError('资源包路径无效')
    if bundle.name!='__data' or not bundle.is_file():raise ValueError('素材资源包不存在')
    stat=bundle.stat();fingerprint=f'{bundle}|{stat.st_size}|{stat.st_mtime_ns}|{key}'
    name=hashlib.sha256(fingerprint.encode('utf8')).hexdigest()+'.png'
    existing=export_path(roots['index_dir'],name)
    if existing:return name
    if unity_py is None:import UnityPy as unity_py
    resource_catalog._ensure_unity_config(unity_py)
    env=unity_py.load(str(bundle));obj=next((o for o in env.objects if o.type.name=='Sprite' and o.path_id==path_id and o.assets_file.name==cab),None)
    if obj is None:raise ValueError('资源包中找不到该素材，请重新读取')
    image=obj.read().image
    folder=pathlib.Path(roots['index_dir'])/'sprite-originals';folder.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=str(folder),prefix='.sprite-',suffix='.tmp');os.close(fd)
    try:
        image.save(temp,format='PNG');os.replace(temp,folder/name)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return name
