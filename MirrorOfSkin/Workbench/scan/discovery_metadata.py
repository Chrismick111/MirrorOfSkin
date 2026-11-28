"""Resolve discovery labels from local Chinese localization and chapter evidence."""
import json
import pathlib
import re


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


def appearance_id(name):
    match = re.match(r'^(?:[A-Za-z]+_)?(\d{3,})[A-Za-z]?_', name or '')
    return match.group(1) if match else None


def load_metadata(game_dir, chapters_path):
    """Return a reusable index. Conflicting translations remain unresolved."""
    lang = pathlib.Path(game_dir) / 'LimbusCompany_Data/Lang/LLC_zh-CN'
    candidates = {'identity': {}, 'enemy': {}}
    chapter_candidates = {}
    part_candidates = {}
    for kind, prefix in (('identity', 'Personalities'), ('enemy', 'Enemies')):
        for path in sorted(lang.glob(prefix + '*.json')):
            doc = _read(path, {})
            if not isinstance(doc, dict) or not isinstance(doc.get('dataList'), list):
                continue
            for row in doc['dataList']:
                if not isinstance(row, dict) or row.get('id') is None:
                    continue
                name = str(row.get('name') or '').strip()
                title = str(row.get('title') or '').strip()
                if kind == 'identity' and title and name and title not in name:
                    name = title + ' ' + name
                if name and re.search(r'[\u3400-\u9fff]', name):
                    candidates[kind].setdefault(str(row['id']), set()).add(re.sub(r'\s+', ' ', name))
                    match = re.fullmatch(r'Enemies-a1c(\d+)p\d+\.json', path.name, re.IGNORECASE)
                    if kind == 'enemy' and match:
                        chapter_candidates.setdefault(str(row['id']), set()).add(int(match.group(1)))
                        part = re.fullmatch(r'Enemies-a1c(\d+)p(\d+)\.json', path.name, re.IGNORECASE)
                        if part: part_candidates.setdefault(str(row['id']), set()).add((int(part.group(1)), int(part.group(2))))
    chapters_path = pathlib.Path(chapters_path)
    if chapters_path.with_suffix('.json.xz').is_file():
        from mos_data import chapter_seed_bytes
        chapters = json.loads(chapter_seed_bytes(chapters_path))
    else:
        chapters = _read(chapters_path, {})
    return {'names': candidates, 'chapters': chapters if isinstance(chapters, dict) else {}, 'chapter_candidates': chapter_candidates, 'part_candidates': part_candidates}


def resolve(index, appearance_name):
    """Return display name, translation status and evidence-based category."""
    ident = appearance_id(appearance_name)
    kind = 'identity' if ident and (len(ident) == 5 and ident[:3] in tuple(str(i) for i in range(101, 113)) or ident.startswith('400') and len(ident) == 6) else 'enemy'
    choices = index['names'][kind].get(ident, set())
    translated = len(choices) == 1
    chapter = index['chapters'].get(appearance_name) or index['chapters'].get('story_' + appearance_name, {})
    if not isinstance(chapter, dict):
        chapter = {}
    chapter_evidence = '既有章节记录' if chapter.get('chapter') else ''
    possible = index.get('chapter_candidates', {}).get(ident, set()) if kind == 'enemy' else set()
    if not chapter.get('chapter') and len(possible) == 1:
        number = next(iter(possible))
        chapter = {'chapter': 'chapter_%d' % number, 'label': '第%d章' % number}
        chapter_evidence = '中文敌人文本文件推定'
    memberships = [dict(item) for item in chapter.get('memberships', []) if isinstance(item,dict)]
    if not memberships and chapter.get('chapter'):
        memberships = [{'chapter':chapter['chapter'],'label':chapter.get('label',chapter['chapter'])}]
    # A localization file is evidence for the part it names, not for unrelated chapters.
    base = chapter.get('chapter') or 'unassigned'
    match = re.fullmatch(r'chapter_(\d+)', base)
    if match:
        for number,part in sorted(index.get('part_candidates', {}).get(ident, set())):
            ident_part = f'chapter_{number}_part_{part}'
            if number == int(match.group(1)) and not any(x.get('chapter')==ident_part for x in memberships):
                memberships.append({'chapter':ident_part,'label':f'第{number}章 · 第{part}部分','parent':base,'part':part})
    return {'name': next(iter(choices)) if translated else appearance_name,
            'translated': translated, 'translation_status': '本地中文' if translated else '未翻译',
            'category': base,
            'category_label': chapter.get('label') or '未归档',
            'category_memberships': memberships, 'category_evidence': chapter_evidence}


def refresh_discovered(pools, index):
    """Fill newly available local translations for discovered entries only."""
    changed=0
    for pool in pools.values():
        for entry in pool.get('entries', []):
            if entry.get('discovery_source') != 'local_cache': continue
            appearance=entry.get('appearance_name')
            if not appearance: continue
            result=resolve(index,appearance); dirty=False
            old=str(entry.get('name') or '')
            if result['translated'] and (entry.get('translation_status')=='自动暂译' or not re.search(r'[\u3400-\u9fff]',old)):
                entry['name']=result['name'];entry['translation_status']=result['translation_status'];dirty=True
            if entry.get('chapter','unassigned')=='unassigned' and result['category']!='unassigned':
                entry['chapter']=result['category'];entry['chapter_label']=result['category_label'];entry['chapter_memberships']=result['category_memberships'];entry['category_evidence']=result['category_evidence'];dirty=True
            if dirty:changed+=1
    return changed
