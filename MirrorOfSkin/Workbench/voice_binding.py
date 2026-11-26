"""Rebuild the worn-appearance voice map from locally imported assets."""
import json
from pathlib import Path
import re
import unicodedata

import os
import tempfile
import time


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


def signal_runtime(root):
    """Notify a running game after all imported voice resources are ready."""
    library=(Path(root)/'Assets/ImportedVoices').resolve()
    if not library.is_dir():return
    fd,name=tempfile.mkstemp(prefix='.voice-revision-',dir=library)
    try:
        with os.fdopen(fd,'wb') as f:f.write(str(time.time_ns()).encode('ascii'))
        os.replace(name,library/'runtime-revision')
    finally:
        Path(name).unlink(missing_ok=True)


def validate_voice_policy(policy):
    if not isinstance(policy, dict) or set(policy) != {'owner', 'bank'}:
        raise ValueError('外观语音配置需要 owner 和 bank')
    owner, bank = policy['owner'], policy['bank']
    if not isinstance(owner, str) or not re.fullmatch(r'[1-9][0-9]{2,7}', owner):
        raise ValueError('外观语音 owner 应为游戏语音事件的角色编号')
    if (not isinstance(bank, str) or len(bank) >= 246 or bank.lower().startswith('master.')
            or not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.assets)?\.bank', bank, re.ASCII | re.I)):
        raise ValueError('外观语音 bank 应为可播放的 FMOD 文件名')
    return policy


def model_info(root,entry):
    look=entry.get('appearance_name','')
    if not re.fullmatch(r'WBImp_[0-9a-f]{24}',look):
        return None
    path=root/'Assets/ImportedSkins'/(look+'.cfg')
    if not path.is_file():return None
    lines=path.read_text(encoding='ascii').splitlines()
    from core.mos_data import imported_config_shape
    if not imported_config_shape(lines):return None
    owners=set()
    for key in ([] if lines[0] == 'WBMOD3' else lines[1:3]+[lines[4]]):
        match=re.match(r'(\d{4,8})_',key.rsplit('/',1)[-1])
        if match:owners.add(match[1])
    names={family(entry.get(k,'')) for k in ('name','import_source')}
    return look,owners,names-{''},entry['name']


def sync_bubble_text(folder, owners):
    """Publish only dialogue supplied by this bank for its bound wearers."""
    from appearance_dialogue import battle_dialogue, subtitle_file

    by_key={}
    lines={}
    for path in sorted(folder.glob('*.json')):
        kind = subtitle_file(path.name)
        if kind is None or not path.is_file():
            continue
        try:
            data=json.loads(path.read_bytes())
        except (OSError, ValueError, RecursionError):
            continue
        priority = 2 if path.name.casefold().startswith('voice_') else (
            1 if path.name.casefold() == 'battlespeechbubbledlg.json' else 0)
        for key, owner, line in battle_dialogue(data, path.name):
            if owner in owners and key.startswith('battle'):
                lines.setdefault((owner, key), {}).setdefault(priority, set()).add(line)
    for key, choices in lines.items():
        preferred = choices[max(choices)]
        if len(preferred) == 1:
            by_key[key] = next(iter(preferred))
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
    declared={}
    for group in catalog.values():
        for entry in group['entries']:
            model=model_info(root,entry)
            if model:
                models[model[0]]=model
                if 'imported_voice' in entry:
                    try:
                        declared[model[0]] = validate_voice_policy(entry['imported_voice'])
                    except ValueError:
                        declared[model[0]] = None
    choices={look:[] for look in models}
    index={}
    for path in sorted(library.glob('*/voice.json')):
        try:
            meta=json.loads(path.read_bytes())
            if not isinstance(meta,dict) or not isinstance(meta.get('banks'),list) or not isinstance(meta.get('targets'),list):continue
        except (OSError,ValueError):continue
        rev=path.parent.name
        if not re.fullmatch('[a-f0-9]{64}',rev) or meta.get('revision')!=rev:continue
        if not meta.get('playable_banks') or not meta['targets']:
            if evidence is None:
                import bank_evidence as evidence
            playable=meta.get('playable_banks') or evidence.playable_banks(path.parent,meta['banks'])
            targets=meta['targets']
            probe_key=evidence.target_probe_key(path.parent,playable) if not targets and playable else None
            if probe_key and probe_key!=meta.get('target_probe_key'):
                targets=sorted(evidence.probe_targets(path.parent,playable))
            if (playable!=meta.get('playable_banks') or targets!=meta['targets'] or
                    (probe_key and probe_key!=meta.get('target_probe_key'))):
                meta.setdefault('imported_at',path.stat().st_mtime_ns)
                meta.update(playable_banks=playable,targets=targets)
                if probe_key:meta['target_probe_key']=probe_key
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
        scoped=meta.get('scoped_to_appearances') or bool(together.intersection(declared))
        included_has_match=any(look in together and bool(owners&targets)
                               for look,owners,_,_ in models.values())
        included_layouts={frozenset(owners) for look,owners,_,_ in models.values()
                          if look in together and owners}
        scores={}
        selected_banks={}
        for look,owners,aliases,label in models.values():
            if scoped and look not in together:
                continue
            if look in declared:
                rule=declared[look]
                if rule and look in together and rule['owner'] in targets:
                    matched=[b for b in banks if b.casefold()==rule['bank'].casefold()]
                    if len(matched)==1:
                        selected_banks[look]=matched
                        scores[look]=(4,rule['owner'])
                continue
            overlap=owners&targets
            related=bool(aliases&names)
            if targets and owners and not overlap:
                # A single-target voice included with otherwise unmatched
                # artwork is explicit evidence even when its prefab layout
                # uses another identity. Do not steal a voice from a matching
                # companion when the package contains unrelated artwork.
                if (look not in together or len(targets)!=1 or included_has_match or
                        len(included_layouts)>1):continue
            possible=overlap or targets or owners
            if len(possible)!=1:continue
            score=3 if look in together else 2 if related else 1 if overlap else 0
            if score:scores[look]=(score,next(iter(possible)))
        if not scores:continue
        for owner in {value[1] for value in scores.values()}:
            best=max(score for score,o in scores.values() if o==owner)
            winners=[k for k,v in scores.items() if v==(best,owner)]
            if len(winners)>1 and not all(k in together for k in winners):continue
            for k in winners:choices[k].append((best,owner,meta['revision'],selected_banks.get(k,banks)))
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
