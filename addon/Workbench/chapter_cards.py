"""Serve chapter card metadata and locally extracted artwork."""
import json
import pathlib
import re

def _entries(root):
    folder = pathlib.Path(root) / 'Workbench/chapter_art'
    try:
        data = json.loads((folder/'chapters.json').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return folder, {}
    if not isinstance(data, dict):
        return folder, {}
    try:
        discovered = json.loads((folder/'chapters.discovered.json').read_text(encoding='utf-8-sig'))
        if isinstance(discovered, dict):
            data = {**discovered, **data}  # curated cards always win
    except (OSError, ValueError):
        pass
    result = {}
    for key, value in data.items():
        if not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9_]+',key) or not isinstance(value,dict):
            continue
        filename = value.get('image')
        if filename is not None and (not isinstance(filename,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+\.png',filename) or '..' in filename ):
            continue
        result[key] = value
    return folder, result

def load(root):
    folder, entries = _entries(root)
    return {key: {'chapter':str(value.get('chapter','')), 'title':str(value.get('title','')),
                  'timeline':str(value.get('timeline','')), 'rank':value.get('rank',20000), 'art_note':str(value.get('art_note','')),
                  'image_url':('api/chapter-image/'+key) if value.get('image') and (folder/value['image']).is_file() else ''}
            for key,value in entries.items()}

def image(root, key):
    folder, entries = _entries(root)
    name = entries.get(key,{}).get('image')
    if not name: return None
    try: return (folder/name).read_bytes()
    except OSError: return None
