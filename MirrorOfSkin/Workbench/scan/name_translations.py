"""Display provisional translations until a local Chinese name is available."""
import json
import pathlib
import re

NAME_FIXES={'story_8372_Barber_NicoleAppearance':'理发师·妮可莉娜'}

def load(root):
    try:
        data=json.loads((pathlib.Path(root)/'Workbench/name_translations.json').read_text(encoding='utf-8-sig'))
        return data if isinstance(data,dict) else {}
    except (OSError, ValueError):
        return {}

def name(identity, current, translations):
    if str(identity) in NAME_FIXES:return NAME_FIXES[str(identity)]
    value=str(current or '')
    if re.search(r'[\u3400-\u9fff]',value):
        return value
    return translations.get(str(identity),value)
