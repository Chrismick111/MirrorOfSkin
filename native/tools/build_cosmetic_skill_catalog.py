"""Build battle-display lookup tables from extracted game definitions.

The JSON input maps static asset paths to their decoded documents. Optional
unit/enemy archives supply equality evidence for named variants. Only numeric
keys and appearance identifiers are written; display text comes from the game.
"""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re


def rows(documents, kind):
    for path, document in sorted(documents.items()):
        if '/static-data/' + kind + '/' in path:
            yield from document.get('list', [])


def skill_labels(databases):
    labels = defaultdict(set)
    for path in databases:
        with gzip.open(path, 'rt', encoding='utf8') as stream:
            db = json.load(stream)
        skills = list(db.get('skills', {}).values())
        for unit in db.get('ids', []):
            skills.extend(unit['skills'] + unit['defense'])
        for skill in skills:
            labels[skill['id']].update(v['name'].strip().casefold() for v in skill.get('up', {}).values() if v.get('name'))
    names = sorted({next(iter(names)) for names in labels.values() if len(names) == 1})
    ids = {name: i for i, name in enumerate(names, 1)}
    return {key: ids[next(iter(names))] for key, names in labels.items() if len(names) == 1}


def display_signature(row, record):
    # Alternate name/icon fields have no verified resolution order here.
    if 'nameID' in row or 'iconID' in row or row.get('isHiddenForUI'):
        return None
    text = row.get('textID', row['id'])
    defense, motion, tier, conditional, _ = record
    if not isinstance(text, int) or text <= 0 or not motion or not tier or conditional < 0:
        return None
    stages = row['skillData']
    levels = [s.get('gaksungLevel', 0) for s in stages]
    if sorted(set(levels)) != levels or not stages[0].get('skillMotion') or not stages[0].get('defType'):
        return None
    icon = row['id']
    icons = []
    for level, stage in zip(levels, stages):
        if 'iconId' in stage:
            return None
        icon = stage.get('iconID', icon)
        if not isinstance(icon, int) or icon <= 0:
            return None
        icons.append((level, icon))
    return text, tuple(icons), defense, motion, tier, conditional


def shared_members(variants, skills, signatures):
    common = {s for s in set.intersection(*variants) if skills.get(s)}
    if len(variants) == 1:
        return sorted(common)
    groups = []
    for members in variants:
        by_display = defaultdict(set)
        for skill in members:
            if skills.get(skill) and signatures.get(skill):
                by_display[signatures[skill]].add(skill)
        groups.append(by_display)
    for signature in set.intersection(*(set(group) for group in groups)):
        candidates = [group[signature] for group in groups]
        if any(len(ids) != 1 for ids in candidates):
            continue
        ids = set.union(*candidates)
        # Publish one verified source skill for name and image lookup.
        # A reference to a third, unrelated skill does not establish ownership.
        canonical = signature[0]
        if canonical in ids and not ids.intersection(common):
            common.add(canonical)
    return sorted(common)


def generate(documents, labels, portraits_by_identity):
    owners = defaultdict(list)
    portraits = defaultdict(set)
    aliases = {}
    uses = defaultdict(set)
    skills = {}
    signatures = {}
    parts = {r['id']: r for r in rows(documents, 'abnormality-part')}
    for kind in ('personality', 'enemy', 'abnormality-unit'):
        for row in rows(documents, kind):
            look = row.get('appearance')
            if not look or not re.fullmatch('[A-Za-z0-9_-]+', look):
                continue
            members = set()
            for unit in [row] + [parts[i] for i in row.get('abnormalityPartList', []) if i in parts]:
                for item in unit.get('attributeList', []):
                    skill = item['skillId']
                    members.add(skill)
                    uses[skill].add(int(item.get('number', 0) == 0))
                for skill in unit.get('defenseSkillIDList', []):
                    members.add(skill)
                    uses[skill].add(0)
            owners[look].append(members)
            if kind == 'personality':
                aliases[str(row['id'])] = look
                portraits[look].add(row['id'])
    types = {'ATTACK': 0, 'GUARD': 1, 'EVADE': 2, 'COUNTER': 3}
    for row in rows(documents, 'skill'):
        stages = row['skillData']
        defs = {s['defType'] for s in stages if s.get('defType')}
        if len(defs) != 1 or next(iter(defs)) not in types:
            signatures[row['id']] = None
            continue
        motions = {s['skillMotion'] for s in stages if s.get('skillMotion')}
        number = next(iter(motions)) if len(motions) == 1 else ''
        motion = int(number[1:]) if re.fullmatch(r'S(?:[1-9]|10)', number) else 0
        key = row['id']
        usage = uses[key]
        record = (types[next(iter(defs))], motion, row.get('skillTier', 0),
                  next(iter(usage)) if len(usage) == 1 else -1, labels.get(key, 0))
        signature = display_signature(row, record)
        if key not in signatures or signatures[key] == signature:
            signatures[key] = signature
        else:
            signatures[key] = None
        # Duplicate declarations with different semantics cannot decide a mapping.
        if key in skills and skills[key] != record:
            skills[key] = None
        else:
            skills[key] = record
    lines = ['/* Generated by build_cosmetic_skill_catalog.py. */',
             'static const SrUiSkill sr_ui_skills[] = {']
    for skill, values in sorted(skills.items()):
        if values:
            lines.append(' {%d,%d,%d,%d,%d,%d},' % (skill, *values))
    lines.append('};\nstatic const int sr_ui_member_ids[] = {')
    ranges = {}
    count = 0
    for look, variants in sorted(owners.items()):
        # Only use declarations shared by all variants that use this exact body.
        common = shared_members(variants, skills, signatures)
        ranges[look] = (count, len(common))
        if common:
            lines.append(' ' + ','.join(map(str, common)) + ',')
        count += len(common)
    lines.append('};\nstatic const SrUiOwner sr_ui_owners[] = {')
    for key in sorted(owners.keys() | aliases.keys()):
        look = aliases.get(key, key)
        ids = portraits[look]
        lines.append(' {"%s",%d,%d,%d},' % (key, *ranges[look], next(iter(ids)) if len(ids) == 1 else 0))
    lines.append('};\nstatic const SrUiPortraitFile sr_ui_portrait_files[] = {')
    for identity, source in sorted(portraits_by_identity.items()):
        if re.fullmatch('[A-Za-z0-9_-]+', identity) and isinstance(source, str) and source:
            # auto_artwork.extract uses the asset key for its local cache filename.
            filename = hashlib.sha256(source.encode('utf8')).hexdigest()[:24] + '.png'
            lines.append(' {"%s","%s"},' % (identity, filename))
    return '\n'.join(lines + ['};', ''])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('static_json', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--database', action='append', type=Path, default=[])
    parser.add_argument('--portrait-sources', required=True, type=Path)
    args = parser.parse_args()
    args.output.write_bytes(generate(json.loads(args.static_json.read_bytes()), skill_labels(args.database),
                                     json.loads(args.portrait_sources.read_bytes())).encode('utf8'))
