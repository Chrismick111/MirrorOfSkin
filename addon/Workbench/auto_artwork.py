"""Incrementally gather directly decodable local Unity portraits and chapter art.

Never replaces existing/custom portraits. Ambiguous and atlas-only sprites are
reported for a later pass instead of installing an unverified image.
"""
import hashlib,json,os,pathlib,re

def candidates(pools, known, local):
    result={}
    for p in pools.values():
        for e in p.get('entries',[]):
            ident=str(e.get('identity_id','')); name=str(e.get('appearance_name',''))
            if not ident or ident in known or ident in local:continue
            m=re.match(r'^(\d+)_',name)
            if m and not (ident.startswith('story_') and re.fullmatch(r'10[1-9]\d{2}|11[0-2]\d{2}',m.group(1))):
                result.setdefault(m.group(1),[]).append(ident)
    return result

def classify_asset(key):
    m=re.search(r'/Sprite/Unit/Portrait/(\d+)_portrait\.png$',key,re.I)
    if m:return ('portrait',m.group(1))
    m=re.search(r'/SkinPreview/(?:[^/]+/)*(\d+)\.png$',key,re.I)
    if m:return ('preview',m.group(1))
    if re.search(r'/Sprite/Chapter/[^/]+\.png$',key,re.I):return ('chapter',pathlib.PurePosixPath(key).name)
    return None

def extract(root,cache,unity,files=None):
    root=pathlib.Path(root); cache=pathlib.Path(cache); wb=root/'Workbench';out=wb/'local_portraits';out.mkdir(parents=True,exist_ok=True)
    def load(path,default):
        try:return json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError,ValueError):return default
    manifest_path=out/'local_portraits.json'; manifest=load(manifest_path,{})
    wanted=candidates(load(root/'Assets/runtime/all_sinners_pools.json',{}),load(wb/'portrait_manifest.json',{}),manifest)
    matches={}; chapters={};errors=[]
    paths=files if files is not None else (pathlib.Path(d)/'__data' for d,_,f in os.walk(cache) if '__data' in f)
    for path in paths:
        try:
            env=unity.load(str(path))
            for key in env.container:
                hit=classify_asset(key)
                if not hit:continue
                kind,id=hit
                if kind=='chapter':chapters.setdefault(id,[]).append((str(path),key))
                elif id in wanted:matches.setdefault(id,[]).append((str(path),key,kind))
        except Exception as exc:errors.append({'bundle':str(path),'error':str(exc)[:200]})
    added=[]; unresolved=[]
    for ident, identities in wanted.items():
        rows=matches.get(ident,[]); preferred=[r for r in rows if r[2]=='portrait'] or [r for r in rows if r[2]=='preview']
        if len(preferred)!=1:unresolved.extend(identities);continue
        bundle,key,kind=preferred[0]
        try:
            img=unity.load(bundle).container[key].read().image
            # Reject opaque extracted sprites: atlas alpha loss is known to create black rectangles.
            if 'A' not in img.getbands() or img.getchannel('A').getextrema()==(255,255):raise ValueError('transparent mask unavailable')
            filename=hashlib.sha256(key.encode('utf8')).hexdigest()[:24]+'.png';tmp=out/(filename+'.tmp')
            img.save(tmp,format='PNG');os.replace(tmp,out/filename)
            for identity in identities:manifest[identity]={'file':filename,'source':key,'kind':kind};added.append(identity)
        except Exception as exc:unresolved.extend(identities);errors.append({'asset':key,'error':str(exc)[:200]})
    if added:
        tmp=manifest_path.with_name(manifest_path.name+'.tmp');tmp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8');os.replace(tmp,manifest_path)
    # Keep chapter assets indexed by exact Unity asset name. Matching a new
    # chapter to an image is a separate evidence-based classification step.
    chapter_out=wb/'chapter_art';chapter_manifest=chapter_out/'discovered-assets.json';known=load(chapter_manifest,{})
    new_chapters=[]
    for name, options in chapters.items():
        if name in known or len(options)!=1:continue
        bundle,key=options[0]
        try:
            img=unity.load(bundle).container[key].read().image
            chapter_out.mkdir(parents=True,exist_ok=True)
            filename=hashlib.sha256(key.encode('utf8')).hexdigest()[:24]+'.png';tmp=chapter_out/(filename+'.tmp')
            img.save(tmp,format='PNG');os.replace(tmp,chapter_out/filename)
            known[name]={'file':filename,'source':key};new_chapters.append(name)
        except Exception as exc:errors.append({'asset':key,'error':str(exc)[:200]})
    if new_chapters:
        tmp=chapter_manifest.with_name(chapter_manifest.name+'.tmp');tmp.write_text(json.dumps(known,ensure_ascii=False,indent=2)+'\n',encoding='utf8');os.replace(tmp,chapter_manifest)
    # A numeric chapter_N and an exact chapterN.png are an unambiguous pair.
    # Existing curated chapter cards always win; other categories remain visible
    # without an invented image and are listed as unresolved.
    curated=load(chapter_out/'chapters.json',{});discovered_path=chapter_out/'chapters.discovered.json';cards=load(discovered_path,{})
    categories={}
    for pool in load(root/'Assets/runtime/all_sinners_pools.json',{}).values():
        for entry in pool.get('entries',[]):
            for item in entry.get('chapter_memberships') or []:
                if isinstance(item,dict) and item.get('chapter'):categories[str(item['chapter'])]=str(item.get('label') or item['chapter'])
            if entry.get('chapter'):categories[str(entry['chapter'])]=str(entry.get('chapter_label') or entry['chapter'])
    unresolved_chapters=[]
    for category,label in categories.items():
        if category in curated or category in cards or category=='unassigned':continue
        match=re.fullmatch(r'chapter_(\d+)',category)
        if not match:unresolved_chapters.append(category);continue
        assets=[item for name,item in known.items() if name.lower()==('chapter'+match.group(1)+'.png')]
        if len(assets)!=1:unresolved_chapters.append(category);continue
        cards[category]={'chapter':label,'title':label,'rank':int(match.group(1))*100,'image':assets[0]['file'],'art_note':'本地游戏章节图片'}
    if cards:
        tmp=discovered_path.with_name(discovered_path.name+'.tmp');tmp.write_text(json.dumps(cards,ensure_ascii=False,indent=2)+'\n',encoding='utf8');os.replace(tmp,discovered_path)
    return {'added':added,'unresolved':unresolved,'chapter_candidates':chapters,'chapter_extracted':new_chapters,'chapter_unresolved':unresolved_chapters,'errors':errors}
