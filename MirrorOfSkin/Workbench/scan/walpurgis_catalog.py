"""Add locally researched event memberships and provisional translations."""
import json
import pathlib
import name_translations

def load(root):
    try:
        data=json.loads((pathlib.Path(root)/'Workbench/data/walpurgis_data.json').read_text(encoding='utf-8-sig'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):
        return {}

def apply(catalog, data):
    translations={str(k):v.get('name','') for k,v in data.get('translations',{}).items() if isinstance(v,dict) and isinstance(v.get('name'),str)}
    for identity, entry in catalog.items():
        original=entry.get('name','')
        translated=name_translations.name(identity,original,translations)
        if translated!=original:
            entry['original_name']=original
            entry['name']=translated
            entry['translation_status']='暂译'
    category=data.get('category',{})
    ident=category.get('id');label=category.get('label');rank=category.get('rank',20000)
    if not ident or not label:return
    for identity in category.get('members',[]):
        entry=catalog.get(str(identity))
        if not entry:continue
        current=entry.get('chapter')
        memberships=list(entry.get('chapter_memberships') or ([{'chapter':current,'label':entry.get('chapter_label',current)}] if current else []))
        if not any(x.get('chapter')==ident for x in memberships if isinstance(x,dict)):
            memberships.append({'chapter':ident,'label':label})
        entry['chapter_memberships']=memberships
        if not current or current=='unassigned':
            entry.update(chapter=ident,chapter_label=label,chapter_rank=rank)
