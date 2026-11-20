# -*- coding: utf-8 -*-
"""Restore workbench images from the local game's cached Unity bundles."""
import argparse,json,os,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import _module_paths
from file_lock import FileLock

def emit(stage,done=0,total=0,message='',**extra):
    print(json.dumps(dict(stage=stage,done=done,total=total,message=message,**extra),ensure_ascii=False),flush=True)

def read(path):
    try:
        value=json.loads(path.read_text(encoding='utf-8-sig'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def safe_name(name):
    return isinstance(name,str) and bool(name) and pathlib.PurePosixPath(name).name==name and pathlib.PureWindowsPath(name).name==name and name.lower().endswith('.png')

def scan(root,cache,unity):
    wb=root/'Workbench'; targets={}; chapters={}
    for folder,manifest in [('portraits','portrait_manifest.json'),('local_portraits','local_portraits/local_portraits.json')]:
        for row in read(wb/manifest).values():
            if not isinstance(row,dict):continue
            name,source=row.get('file'),row.get('source')
            if not safe_name(name) or not isinstance(source,str):continue
            dest=wb/folder/name
            if not dest.is_file():targets.setdefault(source.lower().replace('\\','/'),set()).add(dest)
    for row in read(wb/'chapter_art/chapters.json').values():
        if not isinstance(row,dict):continue
        name=row.get('image')
        if safe_name(name) and not (wb/'chapter_art'/name).is_file():chapters[name.lower()]=wb/'chapter_art'/name
    # Discovered assets retain exact original Unity keys and output names.
    for name,row in read(wb/'chapter_art/discovered-assets.json').items():
        if not isinstance(row,dict):continue
        destname,source=row.get('file'),row.get('source')
        if safe_name(destname) and isinstance(source,str) and not (wb/'chapter_art'/destname).is_file():
            targets.setdefault(source.lower().replace('\\','/'),set()).add(wb/'chapter_art'/destname)
    total_missing=sum(map(len,targets.values()))+len(chapters);saved=0;failed=0
    bundles=[pathlib.Path(d)/'__data' for d,_,files in os.walk(cache) if '__data' in files]
    emit('scanning',0,len(bundles),'正在检索本地游戏资源',missing=total_missing)
    for n,bundle in enumerate(bundles,1):
        try:
            env=unity.load(str(bundle))
            for key,obj in env.container.items():
                normalized=str(key).lower().replace('\\','/')
                destinations=set(targets.get(normalized,()))
                basename=normalized.rsplit('/',1)[-1]
                is_chapter='/sprite/chapter/' in normalized
                if is_chapter and basename in chapters:destinations.add(chapters[basename])
                if not destinations:continue
                try:
                    image=obj.read().image
                    for dest in destinations:
                        if dest.is_file():continue
                        dest.parent.mkdir(parents=True,exist_ok=True)
                        tmp=dest.with_name(dest.name+'.resource-tmp');image.save(tmp,format='PNG');os.replace(tmp,dest);saved+=1
                    targets.pop(normalized,None)
                    if is_chapter:chapters.pop(basename,None)
                except Exception:failed+=1
        except Exception:failed+=1
        if n%20==0 or n==len(bundles):emit('scanning',n,len(bundles),'正在检索本地游戏资源',saved=saved,missing=total_missing)
        if not targets and not chapters:break
    remaining=sum(map(len,targets.values()))+len(chapters)
    emit('done',saved,total_missing,'已从本地游戏资源恢复 %d 张图片，%d 张未找到'%(saved,remaining),count=saved,missing=remaining,errors=failed)
    return {'count':saved,'missing':remaining,'errors':failed}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--addon',required=True);parser.add_argument('--cache');parser.add_argument('--game')
    args=parser.parse_args();root=pathlib.Path(args.addon)
    try:
        import scan_units
        from resource_tools import unity
        cache=scan_units.cache_root(args.game or scan_units.find_game_dir(),args.cache)
        if cache is None:raise RuntimeError('未找到本地游戏资源，请先启动一次游戏')
        with FileLock(root/'Workbench/image_resources.lock'):
            (root/'Workbench/images_disabled.flag').unlink(missing_ok=True)
            UnityPy=unity()
            UnityPy.config.FALLBACK_UNITY_VERSION='6000.3.0f1'
            scan(root,cache,UnityPy)
        return 0
    except Exception as exc:
        emit('error',message='本地资源读取失败：'+str(exc));return 1
if __name__=='__main__':sys.exit(main())
