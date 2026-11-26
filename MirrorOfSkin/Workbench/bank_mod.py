"""Collect author-provided FMOD banks and companion dialogue in the local library."""
import hashlib
from collections import defaultdict
import json
import re
import os
import time
from pathlib import Path, PurePosixPath
from zipfile import ZipFile
from tempfile import TemporaryDirectory
from shutil import copyfileobj
from file_lock import FileLock
from appearance_dialogue import subtitle_file, subtitle_owner


def _subtitle_members(archive, items):
    grouped = defaultdict(list)
    for info, path in items:
        if not subtitle_file(path) or not re.fullmatch(r'[\w.-]+', path.name) or info.file_size > 16 * 1024**2:
            continue
        try:
            raw = archive.read(info)
            data = json.loads(raw)
        except (ValueError, RecursionError, UnicodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get('dataList'), list):
            grouped[path.name.casefold()].append((path, raw))
    for entries in grouped.values():
        # Locale directories may publish the same basename in several languages.
        # Prefer an explicit archive-root file, otherwise keep identical copies only.
        at_root = [(path, raw) for path, raw in entries if len(path.parts) == 1]
        choices = at_root or entries
        if all(raw == choices[0][1] for _, raw in choices):
            path, raw = choices[0]
            yield path.name, raw


def import_banks(archive, root, name=None, *,source=None,included=(),scoped=False):
    with ZipFile(archive) as z:
        items = [(i, PurePosixPath(i.filename.replace('\\','/'))) for i in z.infolist() if not i.is_dir()]
        banks = [(i,p) for i,p in items if p.suffix.lower()=='.bank']
        if not banks:
            return None
        library = (root/'Assets/ImportedVoices').resolve()
        library.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=library) as tmp:
            folder = Path(tmp)/'data'
            folder.mkdir()
            files = {}
            targets = set()
            for info,p in banks:
                if not re.fullmatch(r'[\w.-]+',p.name) or p.name.casefold() in files:
                    raise ValueError('语音包内有重复或不支持的文件名：'+p.name)
                dst = folder/p.name
                if info.file_size>1024**3:
                    raise ValueError('语音文件超出读取上限')
                with z.open(info) as src,dst.open('xb') as out:
                    copyfileobj(src,out,1024*1024)
                with dst.open('rb') as f:
                    h=f.read(12)
                if h[:4]!=b'RIFF' or h[8:]!=b'FEV ' or int.from_bytes(h[4:8],'little')+8!=info.file_size:
                    raise ValueError('FMOD bank 文件损坏或格式不支持：'+p.name)
                from skin_import import digest
                files[p.name.casefold()]=digest(dst)
            for filename, raw in _subtitle_members(z, items):
                # Unrecognized locale basenames remain detection-only.
                if not subtitle_file(filename):
                    continue
                (folder / filename).write_bytes(raw)
                owner = subtitle_owner(filename)
                if owner:
                    targets.add(owner)
                files[filename.casefold()] = hashlib.sha256(raw).hexdigest()
            key=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
            from bank_evidence import playable_banks,probe_targets
            bank_names=sorted(p.name for _,p in banks)
            playable=playable_banks(folder,bank_names)
            if not targets:targets.update(probe_targets(folder,playable))
            meta=dict(kind='voice',name=name or archive.stem,source=source or archive.stem,
                      included_looks=sorted(set(included)),revision=key,targets=sorted(targets),
                      banks=bank_names,playable_banks=playable,imported_at=time.time_ns(),files=files)
            if scoped:
                meta['scoped_to_appearances']=True
            (folder/'voice.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf8')
            with FileLock(root/'workbench-save.lock'):
                existing=(library/key).is_dir()
                repaired=False
                if not existing:os.rename(folder,library/key)
                else:
                    from skin_import import write_atomic,write_bundle,digest,encode
                    path=library/key/'voice.json'
                    try:old=json.loads(path.read_bytes())
                    except (OSError,ValueError):old={}
                    if not isinstance(old,dict):old={}
                    # A launcher reinstall can remove individual banks while
                    # leaving the revision directory and metadata behind.
                    # Restore the exact archived bytes, including subtitles.
                    for source_file in folder.iterdir():
                        expected=files.get(source_file.name.casefold())
                        if not expected:continue
                        target=library/key/source_file.name
                        if not target.is_file() or digest(target)!=expected:
                            write_bundle(target,source_file,expected)
                            repaired=True
                    meta['imported_at']=old.get('imported_at',path.stat().st_mtime_ns if path.exists() else time.time_ns())
                    meta['name']=name or old.get('name',meta['name'])
                    meta['source']=old.get('source',meta['source'])
                    meta['included_looks']=sorted(set(old.get('included_looks',[]))|set(included))
                    if old.get('scoped_to_appearances'):
                        meta['scoped_to_appearances']=True
                    meta['targets']=sorted(set(old.get('targets',[]))|targets)
                    if meta!=old:write_atomic(path,encode(meta))
            return dict(meta,status=('updated' if repaired else 'existing') if existing else 'added')
