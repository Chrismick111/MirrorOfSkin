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

def scan(root,cache,unity,game=None):
    wb=root/'Workbench'; targets={}; chapters={}
    import auto_artwork
    local_manifest=read(wb/'local_portraits/local_portraits.json')
    pools=read(root/'Assets/runtime/all_sinners_pools.json')
    curated=read(wb/'portrait_manifest.json')
    candidates=auto_artwork.candidates(pools,
                         curated,local_manifest,root=root)
    appearance_names={str(e.get('appearance_name','')) for p in pools.values() for e in p.get('entries',[])
                      if str(e.get('identity_id','')).startswith('story_') and not str(e.get('identity_id','')).startswith('story_WBImp_')}
    def file_present(manifest,identity,folder):
        row=manifest.get(identity,{})
        name=row.get('file','') if isinstance(row,dict) else ''
        return safe_name(name) and (wb/folder/name).is_file()
    from custom_portraits import get as custom_image
    def missing_looks(local):
        missing=set()
        for group in pools.values():
            for entry in group.get('entries',[]):
                identity=str(entry.get('identity_id',''))
                if not identity:continue
                if identity=='story_BRolandBaseAppearance' and not (root/'Assets/Roland/BRoland.bundle').is_file():continue
                if not file_present(curated,identity,'portraits') and not file_present(local,identity,'local_portraits') and custom_image(root,identity) is None:
                    missing.add(identity)
        return missing
    needs_prefabs=any(not file_present(curated,str(e.get('identity_id','')),'portraits') and
                      not file_present(local_manifest,str(e.get('identity_id','')),'local_portraits') and
                      custom_image(root,str(e.get('identity_id',''))) is None
                      for p in pools.values() for e in p.get('entries',[])
                      if str(e.get('identity_id','')).startswith('story_') and
                      not str(e.get('identity_id','')).startswith('story_WBImp_') and
                      e.get('identity_id')!='story_BRolandBaseAppearance')
    needs_discovery=bool(candidates) or needs_prefabs
    import chapter_cards
    chapter_folder,card_entries=chapter_cards._entries(root)
    def missing_chapters():
        folder,entries=chapter_cards._entries(root)
        return {key for key,row in entries.items() if not row.get('image') or not (folder/row['image']).is_file()}
    needs_chapters=bool(missing_chapters())
    needs_art_scan=needs_discovery or needs_chapters
    art_index={};aliases={}
    known_sources={v.lower().replace('\\','/') for v in read(wb/'data/portrait_source_paths.json').values() if isinstance(v,str) and v.startswith('Assets/')}
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
    total_missing=len(missing_looks(local_manifest))+len(missing_chapters());saved=0;failed=0
    bundles=[pathlib.Path(d)/'__data' for d,_,files in os.walk(cache) if '__data' in files]
    emit('scanning',0,len(bundles),'正在检索本地游戏资源',missing=total_missing)
    for n,bundle in enumerate(bundles,1):
        try:
            env=unity.load(str(bundle))
            art_keys=[];prefab_keys=[]
            for key,obj in env.container.items():
                low=str(key).lower().replace('\\','/')
                if needs_discovery and '/prefab/sd/' in low and low.endswith('.prefab') and pathlib.PurePosixPath(str(key)).stem in appearance_names:
                    prefab_keys.append(str(key))
                if needs_discovery and ('/static-data/enemy/' in low or '/static-data/abnormality-unit/' in low):
                    try:
                        raw=obj.read().m_Script
                        if isinstance(raw,bytes):raw=raw.decode('utf-8-sig')
                        table=json.loads(raw)
                        for row in table.get('list',[]) if isinstance(table,dict) else []:
                            if isinstance(row,dict) and isinstance(row.get('appearance'),str):
                                values=aliases.setdefault(row['appearance'],[])
                                for field in ('sdPortrait','viewid','nameID','id'):
                                    value=row.get(field)
                                    if value is not None and str(value) not in values:values.append(str(value))
                    except (AttributeError,TypeError,ValueError,UnicodeError):pass
                if needs_art_scan and (auto_artwork.classify_asset(str(key)) or low in known_sources):
                    art_keys.append(str(key))
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
            if needs_art_scan:
                art_index[str(bundle.relative_to(cache))]={'art_keys':list(dict.fromkeys(art_keys)),'prefab_keys':list(dict.fromkeys(prefab_keys)),'cab_keys':list(getattr(env,'cabs',{})),'fingerprint':None}
        except Exception:failed+=1
        if n%20==0 or n==len(bundles):emit('scanning',n,len(bundles),'正在检索本地游戏资源',saved=saved,missing=total_missing)
        if not targets and not chapters and not needs_art_scan:break
    if needs_art_scan:
        emit('scanning',len(bundles),len(bundles),'正在提取外观和章节图片')
        artwork=auto_artwork.extract(root,cache,unity,index=art_index,game=game,aliases=aliases,portraits=needs_discovery)
        saved+=len(artwork['added'])
        saved+=len(artwork['chapter_extracted'])
        failed+=len(artwork['errors'])
    remaining=len(missing_looks(read(wb/'local_portraits/local_portraits.json')))+len(missing_chapters())
    emit('done',saved,total_missing,'已从本地游戏资源恢复 %d 张图片，%d 张未找到'%(saved,remaining),count=saved,missing=remaining,errors=failed)
    return {'count':saved,'missing':remaining,'errors':failed}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--addon',required=True);parser.add_argument('--cache');parser.add_argument('--game')
    args=parser.parse_args();root=pathlib.Path(args.addon)
    try:
        import scan_units
        from resource_tools import unity
        game=args.game or scan_units.find_game_dir()
        cache=scan_units.cache_root(game,args.cache)
        if cache is None:raise RuntimeError('未找到本地游戏资源，请先启动一次游戏')
        # The startup scan can hold this lock for minutes; a 15 s default timeout
        # used to fail the whole restore before it wrote a single portrait.
        emit('verify',0,0,'等待资源扫描结束')
        with FileLock(root/'Workbench/image_resources.lock',timeout=1800):
            (root/'Workbench/images_disabled.flag').unlink(missing_ok=True)
            UnityPy=unity()
            UnityPy.config.FALLBACK_UNITY_VERSION='6000.3.0f1'
            scan(root,cache,UnityPy,game=game)
        return 0
    except Exception as exc:
        emit('error',message='本地资源读取失败：'+str(exc));return 1
if __name__=='__main__':sys.exit(main())
