"""Collect author-provided FMOD banks and companion dialogue in the local library."""
import hashlib
import json
import re
import os
import time
from pathlib import Path, PurePosixPath
from zipfile import ZipFile
from tempfile import TemporaryDirectory
from shutil import copyfileobj
from file_lock import FileLock


def import_banks(archive, root, name=None, *,source=None,included=()):
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
            for info,p in banks+[(i,p) for i,p in items if p.name.lower()=='battlespeechbubbledlg.json'
                                 or re.fullmatch(r'Voice_[\w-]+\.json',p.name,re.I)]:
                if not re.fullmatch(r'[\w.-]+',p.name) or p.name.casefold() in files:
                    raise ValueError('语音包内有重复或不支持的文件名：'+p.name)
                dst = folder/p.name
                if info.file_size>1024**3 or (p.suffix.lower()=='.json' and info.file_size>16*1024**2):
                    raise ValueError('语音文件超出读取上限')
                with z.open(info) as src,dst.open('xb') as out:
                    copyfileobj(src,out,1024*1024)
                if p.suffix.lower()=='.bank':
                    with dst.open('rb') as f:
                        h=f.read(12)
                    if h[:4]!=b'RIFF' or h[8:]!=b'FEV ' or int.from_bytes(h[4:8],'little')+8!=info.file_size:
                        raise ValueError('FMOD bank 文件损坏或格式不支持：'+p.name)
                else:
                    lines=json.loads(dst.read_bytes()).get('dataList')
                    if not isinstance(lines,list):raise ValueError('台词文件格式有误：'+p.name)
                    match=re.fullmatch(r'Voice_.+_(\d+)\.json',p.name,re.I)
                    if match:targets.add(match[1])
                from skin_import import digest
                files[p.name.casefold()]=digest(dst)
            key=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
            from bank_evidence import playable_banks,probe_targets
            bank_names=sorted(p.name for _,p in banks)
            playable=playable_banks(folder,bank_names)
            if not targets:targets.update(probe_targets(folder,playable))
            meta=dict(kind='voice',name=name or archive.stem,source=source or archive.stem,
                      included_looks=sorted(set(included)),revision=key,targets=sorted(targets),
                      banks=bank_names,playable_banks=playable,imported_at=time.time_ns(),files=files)
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
                    meta['targets']=sorted(set(old.get('targets',[]))|targets)
                    if meta!=old:write_atomic(path,encode(meta))
            return dict(meta,status=('updated' if repaired else 'existing') if existing else 'added')
