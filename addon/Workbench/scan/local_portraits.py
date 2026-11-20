"""Read locally discovered portraits independently from user-selected images."""
import json
import pathlib
import re

def load(root):
    path = pathlib.Path(root) / 'Workbench/local_portraits/local_portraits.json'
    try:
        data=json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError): return {}
    return data if isinstance(data,dict) else {}

def get(root, manifest, identity):
    entry=manifest.get(str(identity),{})
    if not isinstance(entry,dict):return None
    name=entry.get('file')
    if not isinstance(name,str) or not re.fullmatch(r'[0-9a-f]{24}\.png',name):return None
    path=pathlib.Path(root)/'Workbench/local_portraits'/name
    try:return path.read_bytes()
    except OSError:return None
