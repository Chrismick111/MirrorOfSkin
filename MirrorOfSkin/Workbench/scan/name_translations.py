"""Display provisional translations until a local Chinese name is available."""
import json
import pathlib
import re

def load(root):
    try:
        data=json.loads((pathlib.Path(root)/'Workbench/name_translations.json').read_text(encoding='utf-8-sig'))
        return data if isinstance(data,dict) else {}
    except (OSError, ValueError):
        return {}

def name(identity, current, translations):
    value=str(current or '')
    if re.search(r'[\u3400-\u9fff]',value):
        return value
    return translations.get(str(identity),value)
