"""Incrementally gather directly decodable local Unity portraits and chapter art.

Never replaces existing/custom portraits. Ambiguous and atlas-only sprites are
reported for a later pass instead of installing an unverified image.
"""
import hashlib,json,os,pathlib,re
import scan_chapters

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
    if re.search(r'/(?:Sprite/Chapter/[^/]+|card_pack/Canto_Pilgrimage|Sprite/Banner/banner_Dawn_en|stage-node-id_910603)\.png$',key,re.I):return ('chapter',pathlib.PurePosixPath(key).name)
    return None

def extract(root,cache,unity,files=None,*,game=None,index=None,progress=lambda *args: None,portraits=True,images=True):
    root=pathlib.Path(root); cache=pathlib.Path(cache); wb=root/'Workbench';out=wb/'local_portraits';out.mkdir(parents=True,exist_ok=True)
    def load(path,default):
        try:return json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError,ValueError):return default
    manifest_path=out/'local_portraits.json'; manifest=load(manifest_path,{})
    wanted=candidates(load(root/'Assets/runtime/all_sinners_pools.json',{}),load(wb/'portrait_manifest.json',{}),manifest)
    if not portraits or not images: wanted = {}
    matches={}; chapters={};errors=[]
    paths=files if files is not None else (pathlib.Path(d)/'__data' for d,_,f in os.walk(cache) if '__data' in f)
    paths = ((cache/key, row['art_keys']) for key,row in index.items()) if index is not None else ((p,None) for p in paths)
    for path, keys in paths:
        try:
            if keys is None: keys = unity.load(str(path)).container
            for key in keys:
                hit=classify_asset(key)
                if not hit:continue
                kind,id=hit
                if kind=='chapter':chapters.setdefault(id,[]).append((str(path),key))
                elif id in wanted:matches.setdefault(id,[]).append((str(path),key,kind))
        except Exception as exc:errors.append({'bundle':str(path),'error':str(exc)[:200]})
    added=[]; unresolved=[]
    for count, (ident, identities) in enumerate(wanted.items()):
        progress("portraits",count,len(wanted))
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
    folder = wb/'chapter_art'
    manifest_file = folder/'discovered-assets.json'
    previous = scan_chapters.read(manifest_file)
    known = dict(previous)
    cards_file = folder/'chapters.discovered.json'
    old_cards = scan_chapters.read(cards_file)
    curated = scan_chapters.read(folder/'chapters.json')
    detected = scan_chapters.detect(game, chapters, errors)
    new_images = []
    loaded_bundle = None
    container = None
    for count, (name, options) in enumerate(sorted(chapters.items(), key=lambda pair:pair[1][0][0])):
        progress('images', count, len(chapters))
        if not images or len(options) != 1:
            continue
        bundle, key = options[0]
        mark = index[str(pathlib.Path(bundle).relative_to(cache))]['fingerprint'] if index is not None else None
        filename = hashlib.sha256(key.encode('utf8')).hexdigest()[:24]+'.png'
        if previous.get(name, {}).get('fingerprint') == mark and (folder/filename).is_file():
            continue
        try:
            if loaded_bundle != bundle:
                container = unity.load(bundle).container
                loaded_bundle = bundle
            img = container[key].read().image
            folder.mkdir(parents=True, exist_ok=True)
            tmp = folder/(filename+'.tmp')
            img.save(tmp, format='PNG')
            os.replace(tmp, folder/filename)
            known[name] = dict(file=filename, source=key, fingerprint=mark)
            new_images.append(name)
        except Exception as exc:
            errors.append(dict(asset=key, error=str(exc)[:200]))
    progress('images',len(chapters),len(chapters))
    if images and known != previous:
        scan_chapters.save(manifest_file, known)
    art = {name.lower():row for name,row in known.items()}
    cards = dict(old_cards)
    missing = []
    for key, row in detected.items():
        card = dict(row)
        asset = card.pop('asset') or ''
        image = art.get(asset.lower(), {}).get('file')
        if images and image and (folder/image).is_file():
            card.update(image=image, art_note='本地游戏章节图片')
        elif images and not (curated.get(key, {}).get('image') and (folder/curated[key]['image']).is_file()):
            missing.append(key)
        cards[key] = card
    scan_chapters.save(cards_file, cards)
    return dict(added=added, unresolved=unresolved, chapters_detected=len(detected),
                new_chapters=sorted(set(detected)-set(old_cards)-set(curated)), disabled=not images,
                chapter_extracted=new_images, chapter_unresolved=missing, errors=errors)
