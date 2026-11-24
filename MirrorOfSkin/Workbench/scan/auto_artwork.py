"""Incrementally gather directly decodable local Unity portraits and chapter art.

Never replaces existing/custom portraits. Ambiguous and atlas-only sprites are
reported for a later pass instead of installing an unverified image.
"""
import hashlib,json,os,pathlib,re
import scan_chapters

def candidates(pools, known, local, *, root=None):
    result={}
    def available(manifest, identity, folder):
        row=manifest.get(identity)
        if root is None:return identity in manifest
        if not isinstance(row,dict):return False
        name=row.get('file')
        return isinstance(name,str) and re.fullmatch(r'[0-9a-f]{24}\.png',name) is not None and (pathlib.Path(root)/'Workbench'/folder/name).is_file()
    for p in pools.values():
        for e in p.get('entries',[]):
            ident=str(e.get('identity_id','')); name=str(e.get('appearance_name',''))
            if not ident or available(known,ident,'portraits') or available(local,ident,'local_portraits'):continue
            m=re.match(r'^(\d+)_',name)
            if m and not (ident.startswith('story_') and re.fullmatch(r'10[1-9]\d{2}|11[0-2]\d{2}',m.group(1))):
                result.setdefault(m.group(1),[]).append(ident)
    return result


def prefab_sprite(env, appearance):
    """Return the visible default SpriteRenderer attached to this exact prefab."""
    names={}; transforms={}; parents={}; owners={}; renderers=[]; objects={}
    for obj in env.objects:
        try:
            objects[obj.path_id]=obj
            kind=obj.type.name
            if kind=='GameObject':names[obj.path_id]=obj.parse_as_dict().get('m_Name','')
            elif kind in ('Transform','RectTransform'):
                data=obj.parse_as_dict();go=data['m_GameObject']['m_PathID']
                transforms[go]=obj.path_id;owners[obj.path_id]=go;parents[obj.path_id]=data['m_Father']['m_PathID']
            elif kind=='SpriteRenderer':renderers.append(obj.parse_as_dict())
        except Exception:continue
    found=[]
    for data in renderers:
        go=data.get('m_GameObject',{}).get('m_PathID');node=go
        for _ in range(64):
            parent=parents.get(transforms.get(node))
            if not parent or parent not in owners:break
            node=owners[parent]
        ref=data.get('m_Sprite') or {};pid=ref.get('m_PathID')
        if names.get(node)!=appearance or ref.get('m_FileID') or not pid or not data.get('m_Enabled',1):continue
        obj=objects.get(pid)
        if obj and obj.type.name=='Sprite':
            rank={'[SpRenderer]':0,'FrontSprite':1}.get(names.get(go),2)
            found.append((rank,pid,obj))
    if not found:return None
    found.sort(key=lambda item:(item[0],item[1]))
    return found[0][2].read().image

def classify_asset(key):
    m=re.search(r'/Sprite/Unit/Portrait/(\d+)_portrait\.png$',key,re.I)
    if m:return ('portrait',m.group(1))
    m=re.search(r'/SkinPreview/(?:[^/]+/)*(\d+)\.png$',key,re.I)
    if m:return ('preview',m.group(1))
    m=re.search(r'/SkinPreview-Archived/(?:[^/]+/)*(1(?:0[1-9]|1[0-2])\d{2})_[^/]*_idle\.png$',key,re.I)
    if m:return ('archive_preview',m.group(1))
    if re.search(r'/(?:Sprite/Chapter/[^/]+|card_pack/Canto_Pilgrimage|Sprite/Banner/banner_Dawn_en|stage-node-id_910603)\.png$',key,re.I):return ('chapter',pathlib.PurePosixPath(key).name)
    return None


class BundleReader:
    """Resolve Unity external CABs across the player's downloaded cache."""
    def __init__(self, unity, paths, index=None):
        self.unity=unity
        self.paths=iter(paths)
        self.cabs={}
        self._bundle=None;self._env=None;self._loaded=set()
        if index:
            for path,row in index.items():
                for cab in row.get('cab_keys',[]):
                    self.cabs.setdefault(cab.lower(),path)

    def find(self, name):
        name=name.lower()
        if name in self.cabs:return self.cabs[name]
        for path in self.paths:
            try:
                env=self.unity.load(str(path))
                for cab in env.cabs:self.cabs.setdefault(str(cab).lower(),path)
            except Exception:
                continue
            if name in self.cabs:return self.cabs[name]
        return None

    def image(self, bundle, key):
        if self._bundle!=str(bundle):
            self._env=self.unity.load(str(bundle));self._bundle=str(bundle);self._loaded=set()
        env=self._env;loaded=self._loaded
        for _ in range(12):
            try:return env.container[key].read().image
            except FileNotFoundError as exc:
                match=re.search(r'File (cab-[0-9a-f]+(?:\.ress)?) not found',str(exc),re.I)
                if not match:raise
                cab=match.group(1).lower();dep=self.find(cab)
                if dep is None or cab in loaded:raise
                env.load_file(str(dep));loaded.add(cab)
        raise ValueError('图片资源依赖过多')

def extract(root,cache,unity,files=None,*,game=None,index=None,progress=lambda *args: None,portraits=True,images=True,aliases=None):
    root=pathlib.Path(root); cache=pathlib.Path(cache); wb=root/'Workbench';out=wb/'local_portraits';out.mkdir(parents=True,exist_ok=True)
    def load(path,default):
        try:return json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError,ValueError):return default
    manifest_path=out/'local_portraits.json'; manifest=load(manifest_path,{})
    pools=load(root/'Assets/runtime/all_sinners_pools.json',{})
    appearances={str(e.get('identity_id','')):str(e.get('appearance_name','')) for p in pools.values() for e in p.get('entries',[])}
    wanted=candidates(pools,load(wb/'portrait_manifest.json',{}),manifest,root=root)
    source_paths=load(wb/'data/portrait_source_paths.json',{})
    if not isinstance(source_paths,dict):source_paths={}
    source_lookup={}
    for identity,source in source_paths.items():
        if identity in appearances and isinstance(source,str) and source.startswith('Assets/'):
            source_lookup.setdefault(source.lower().replace('\\','/'),[]).append(identity)
    already={identity for identities in wanted.values() for identity in identities}
    curated=load(wb/'portrait_manifest.json',{})
    for identity in source_paths:
        if identity not in appearances or identity in already:continue
        row=manifest.get(identity,{});known=curated.get(identity,{})
        if isinstance(row,dict) and (out/str(row.get('file',''))).is_file():continue
        if isinstance(known,dict) and (wb/'portraits'/str(known.get('file',''))).is_file():continue
        wanted['@'+identity]=[identity]
    if not portraits or not images: wanted = {}
    matches={}; explicit={};chapters={};errors=[]
    bundle_paths=[cache/key for key in index] if index is not None else list(files if files is not None else (pathlib.Path(d)/'__data' for d,_,f in os.walk(cache) if '__data' in f))
    indexed={str(cache/key):row for key,row in index.items()} if index is not None else None
    reader=BundleReader(unity,bundle_paths,indexed)
    paths = ((cache/key, row['art_keys']) for key,row in index.items()) if index is not None else ((p,None) for p in bundle_paths)
    for path, keys in paths:
        try:
            if keys is None: keys = unity.load(str(path)).container
            for key in keys:
                for identity in source_lookup.get(str(key).lower().replace('\\','/'),()):
                    explicit.setdefault(identity,[]).append((str(path),key,'known_source'))
                hit=classify_asset(key)
                if not hit:continue
                kind,id=hit
                if kind=='chapter':chapters.setdefault(id,[]).append((str(path),key))
                else:matches.setdefault(id,[]).append((str(path),key,kind))
        except Exception as exc:errors.append({'bundle':str(path),'error':str(exc)[:200]})
    added=[]; unresolved=[]
    for count, (ident, identities) in enumerate(wanted.items()):
        progress("portraits",count,len(wanted))
        rows=matches.get(ident,[])
        if not rows and aliases:
            alternatives={str(alt) for identity in identities for alt in aliases.get(appearances.get(identity,''),()) if str(alt) in matches}
            if len(alternatives)==1:rows=matches[next(iter(alternatives))]
        for identity in identities:
            preferred=(explicit.get(identity) or [r for r in rows if r[2]=='portrait'] or
                       [r for r in rows if r[2]=='preview'] or [r for r in rows if r[2]=='archive_preview'])
            if len({str(row[1]).lower().replace('\\','/') for row in preferred})!=1:
                unresolved.append(identity);continue
            failure=None
            for bundle,key,kind in preferred:
                try:
                    img=reader.image(bundle,key)
                    filename=hashlib.sha256(key.encode('utf8')).hexdigest()[:24]+'.png';tmp=out/(filename+'.tmp')
                    img.save(tmp,format='PNG');os.replace(tmp,out/filename)
                    manifest[identity]={'file':filename,'source':key,'kind':kind};added.append(identity)
                    failure=None;break
                except Exception as exc:failure={'asset':key,'error':str(exc)[:200]}
            if failure is not None:unresolved.append(identity);errors.append(failure)
    # Some game props have no portrait asset; their prefab references a visible
    # sprite directly. Only use the renderer belonging to the exact prefab.
    prefab_index={}
    if index:
        for rel,row in index.items():
            for key in row.get('prefab_keys',[]):
                prefab_index.setdefault(pathlib.PurePosixPath(key).stem,[]).append((cache/rel,key))
    if prefab_index:
        from custom_portraits import get as custom_image
        for identity,look in appearances.items():
            if identity.startswith('story_WBImp_') or identity=='story_BRolandBaseAppearance':continue
            if custom_image(root,identity) is not None or identity in added:continue
            existing=manifest.get(identity,{})
            if isinstance(existing,dict) and (out/str(existing.get('file',''))).is_file():continue
            curated=load(wb/'portrait_manifest.json',{}).get(identity,{})
            if isinstance(curated,dict) and (wb/'portraits'/str(curated.get('file',''))).is_file():continue
            options=prefab_index.get(look,[])
            if len(options)!=1:continue
            path,key=options[0]
            try:
                image=prefab_sprite(unity.load(str(path)),look)
                if image is None:continue
                filename=hashlib.sha256(('prefab:'+key).encode('utf8')).hexdigest()[:24]+'.png'
                tmp=out/(filename+'.tmp');image.save(tmp,format='PNG');os.replace(tmp,out/filename)
                manifest[identity]={'file':filename,'source':key,'kind':'prefab_sprite'};added.append(identity)
                if identity in unresolved:unresolved.remove(identity)
            except Exception as exc:errors.append({'asset':key,'error':str(exc)[:200]})
    if added:
        tmp=manifest_path.with_name(manifest_path.name+'.tmp');tmp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8');os.replace(tmp,manifest_path)
    folder = wb/'chapter_art'
    manifest_file = folder/'discovered-assets.json'
    previous = scan_chapters.read(manifest_file)
    known = dict(previous)
    cards_file = folder/'chapters.discovered.json'
    old_cards = scan_chapters.read(cards_file)
    curated = load(wb/'data/chapter_cards.json',{})
    curated.update(scan_chapters.read(folder/'chapters.json'))
    detected = scan_chapters.detect(game, chapters, errors)
    new_images = []
    for count, (name, options) in enumerate(sorted(chapters.items(), key=lambda pair:pair[1][0][0])):
        progress('images', count, len(chapters))
        if not images or len({key.lower().replace('\\','/') for _,key in options})!=1:
            continue
        bundle, key = options[0]
        mark = index[str(pathlib.Path(bundle).relative_to(cache))]['fingerprint'] if index is not None else None
        filename = hashlib.sha256(key.encode('utf8')).hexdigest()[:24]+'.png'
        if previous.get(name, {}).get('fingerprint') == mark and (folder/filename).is_file():
            continue
        failure=None
        for candidate, candidate_key in dict.fromkeys(options):
            try:
                img=reader.image(candidate,candidate_key)
                folder.mkdir(parents=True,exist_ok=True)
                tmp=folder/(filename+'.tmp');img.save(tmp,format='PNG');os.replace(tmp,folder/filename)
                mark=index[str(pathlib.Path(candidate).relative_to(cache))]['fingerprint'] if index is not None else None
                known[name]=dict(file=filename,source=candidate_key,fingerprint=mark)
                new_images.append(name);failure=None;break
            except Exception as exc:failure=dict(asset=candidate_key,error=str(exc)[:200])
        if failure:errors.append(failure)
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
