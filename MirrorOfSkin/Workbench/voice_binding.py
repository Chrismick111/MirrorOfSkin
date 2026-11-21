"""Rebuild the worn-appearance voice map from locally imported assets."""
import json
from pathlib import Path
import re
import unicodedata

import os


def family(text):
    text=unicodedata.normalize('NFKC',text).casefold()
    text=re.sub(r'\b(?:audio|voices?|skins?|models?|sound|pack|fixed)\b',' ',text.replace('_',' '))
    text=re.sub(r'语音包?|音频包?|皮肤包?|外观包?|(?:修复|调整坐标|修正)版?', '',text)
    return ''.join(c for c in text if c.isalnum())


def companion_archive(skin):
    """Only consider an explicitly voice-labelled sibling of the selected mod."""
    key=family(skin.stem)
    if not key:return None
    matches=[p for p in skin.parent.iterdir()
             if p!=skin and p.suffix.casefold() in ('.zip','.rar','.7z') and p.is_file()
             and re.search(r'语音|音频|\b(?:voices?|audio)\b',p.stem.replace('_',' '),re.I)
             and family(p.stem)==key]
    return matches[0] if len(matches)==1 else None


def model_info(root,entry):
    look=entry.get('appearance_name','')
    if not re.fullmatch(r'WBImp_[0-9a-f]{24}',look):
        return None
    path=root/'Assets/ImportedSkins'/(look+'.cfg')
    if not path.is_file():return None
    lines=path.read_text(encoding='ascii').splitlines()
    if len(lines)!=7 or lines[0]!='WBMOD1':return None
    owners=set()
    for key in lines[1:3]+[lines[4]]:
        match=re.match(r'(\d{4,8})_',key.rsplit('/',1)[-1])
        if match:owners.add(match[1])
    names={family(entry.get(k,'')) for k in ('name','import_source')}
    return look,owners,names-{''},entry['name']


def sync_bubble_text(folder, owners):
    """Publish only dialogue supplied by this bank for its bound wearers."""
    by_key={}
    sources=[(folder/'BattleSpeechBubbleDlg.json',None)]
    for path in sorted(folder.glob('Voice_*.json')):
        match=re.fullmatch(r'Voice_.+_([1-9][0-9]{2,7})\.json',path.name,re.I)
        if match and match[1] in owners:sources.append((path,match[1]))
    for path,owner in sources:
        if not path.is_file():continue
        try:
            data=json.loads(path.read_bytes())
        except (OSError,ValueError):continue
        rows=data.get('dataList') if isinstance(data,dict) else None
        if not isinstance(rows,list):continue
        for row in rows:
            if not isinstance(row,dict):continue
            key=row.get('id')
            line=row.get('dlg')
            if not isinstance(key,str) or not re.fullmatch(r'battle[A-Za-z0-9_-]{0,185}',key) or not isinstance(line,str):continue
            ids={part for part in key.split('_') if part in owners or re.fullmatch('[1-9][0-9]{4}',part)}
            who=owner or (next(iter(ids)) if len(ids)==1 else None)
            if who not in owners or (ids and who not in ids):continue
            line=' '.join(re.sub(r'[\x00-\x1f\x7f]',' ',line).split())
            if line and len(line.encode('utf8'))<=4095:by_key[who,key]=line
    content=''.join(f'{owner}\t{key}\t{line}\n' for (owner,key),line in sorted(by_key.items())).encode('utf8')
    target=folder/'bubbles.tsv'
    if not target.is_file() or target.read_bytes()!=content:
        tmp=folder/'bubbles.tmp'
        tmp.write_bytes(content)
        os.replace(tmp,target)


def reconcile(root):
    from file_lock import FileLock
    with FileLock(root/'workbench-save.lock'):
        return reconcile_locked(root)


def reconcile_locked(root,evidence=None):
    library=root/'Assets/ImportedVoices'
    catalog=json.loads((root/'Assets/runtime/all_sinners_pools.json').read_bytes())
    models={}
    for group in catalog.values():
        for entry in group['entries']:
            model=model_info(root,entry)
            if model:models[model[0]]=model
    choices={look:[] for look in models}
    index={}
    for path in sorted(library.glob('*/voice.json')):
        try:
            meta=json.loads(path.read_bytes())
            if not isinstance(meta,dict) or not isinstance(meta.get('banks'),list) or not isinstance(meta.get('targets'),list):continue
        except (OSError,ValueError):continue
        rev=path.parent.name
        if not re.fullmatch('[a-f0-9]{64}',rev) or meta.get('revision')!=rev:continue
        if not meta.get('playable_banks'):
            if evidence is None:
                import bank_evidence as evidence
            playable=evidence.playable_banks(path.parent,meta['banks'])
            targets=meta['targets'] or sorted(evidence.probe_targets(path.parent,playable))
            if playable!=meta.get('playable_banks') or targets!=meta['targets']:
                meta.setdefault('imported_at',path.stat().st_mtime_ns)
                meta.update(playable_banks=playable,targets=targets)
                staging=path.with_suffix('.tmp')
                staging.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf8')
                os.replace(staging,path)
        banks=[b for b in meta.get('playable_banks',meta['banks']) if isinstance(b,str) and len(b)<246
               and re.fullmatch(r'[A-Za-z0-9_-]+(?:\.assets)?\.bank',b,re.I|re.ASCII)
               and not b.lower().startswith('master.') and (path.parent/b).is_file()]
        if not banks:continue
        source=meta.get('source') or meta['name']
        # Revisions of the same named archive supersede earlier imports.
        group=(source.casefold(),tuple(sorted(meta['targets'])))
        stamp=(meta.get('imported_at',path.stat().st_mtime_ns),rev)
        if group not in index or stamp>index[group][0]:
            index[group]=(stamp,meta,banks)
    for _,meta,banks in index.values():
        targets=set(meta['targets'])
        names={family(meta.get(k,'')) for k in ('name','source')}-{''}
        together=set(meta.get('included_looks',[]))
        scores={}
        for look,owners,aliases,label in models.values():
            overlap=owners&targets
            related=bool(aliases&names)
            if targets and owners and not overlap:continue
            possible=overlap or targets or owners
            if len(possible)!=1:continue
            score=3 if look in together else 2 if related else 1 if overlap else 0
            if score:scores[look]=(score,next(iter(possible)))
        if not scores:continue
        for owner in {value[1] for value in scores.values()}:
            best=max(score for score,o in scores.values() if o==owner)
            winners=[k for k,v in scores.items() if v==(best,owner)]
            if len(winners)>1:continue
            for k in winners:choices[k].append((best,owner,meta['revision'],banks))
    mapped={}
    lines=[]
    owners_by_revision={}
    for look,options in sorted(choices.items()):
        if not options:continue
        best=max(o[0] for o in options)
        matches=[o for o in options if o[0]==best]
        if len(matches)!=1:continue
        _,owner,rev,banks=matches[0]
        if not re.fullmatch(r'[1-9][0-9]{2,7}',owner):continue
        mapped[look]=(rev,models[look][3])
        owners_by_revision.setdefault(rev,set()).add(owner)
        lines.extend(f'{look}\t{owner}\t{rev}\t{b}\n' for b in sorted(banks))
    if library.exists():
        for revision,owners in owners_by_revision.items():
            sync_bubble_text(library/revision,owners)
        target=library/'bindings.tsv'
        data=''.join(lines).encode('ascii')
        if not target.exists() or target.read_bytes()!=data:
            staging=target.with_suffix('.tmp')
            staging.write_bytes(data)
            os.replace(staging,target)
    return mapped
