"""Derive main-chapter parts only from explicit battle-file evidence."""
import re

_CHAPTER = re.compile(r'^chapter_(\d+)$')
_PART = re.compile(r'(?:^|[-_])a1c(\d+)p(\d+)(?:[-_.]|$)', re.IGNORECASE)


def memberships(record):
    """Preserve original memberships and add verified part memberships.

    A battle file is evidence only for its own recorded chapter. Interludes
    and other appearances do not acquire a main-chapter part by accident.
    """
    chapter = record.get('chapter', 'unassigned')
    original = record.get('memberships') or [{'chapter': chapter, 'label': record.get('label', '未归档')}]
    result = [dict(item) for item in original if isinstance(item, dict)]
    ids = {item.get('chapter') for item in result}
    match = _CHAPTER.fullmatch(chapter)
    if not match:
        return result
    number = int(match.group(1))
    parts = set()
    for evidence in record.get('battle_evidence', []):
        if not isinstance(evidence, dict) or evidence.get('chapter') != chapter:
            continue
        filename = str(evidence.get('battle_file') or '').replace('\\', '/').rsplit('/', 1)[-1]
        found = _PART.search(filename)
        if found and int(found.group(1)) == number and int(found.group(2)) > 0:
            parts.add(int(found.group(2)))
    for part in sorted(parts):
        ident = f'{chapter}_part_{part}'
        if ident not in ids:
            result.append({'chapter': ident, 'label': f'{record.get("label", chapter)} · 第{part}部分', 'parent': chapter, 'part': part})
    return result
