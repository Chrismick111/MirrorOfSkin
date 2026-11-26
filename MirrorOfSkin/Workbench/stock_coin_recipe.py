"""Read declarative stock-appearance choreography without executing mod scripts."""
from collections import defaultdict, deque
from pathlib import PurePosixPath
import re

from private_server_appearance import _member_root, _read_json, read_declarations, valid_appearance_key


_APPEARANCE = re.compile(r'[!A-Za-z0-9_][!A-Za-z0-9_. -]{0,255}')
_MOTION = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}')
_SCRIPT_KINDS = (
    ('ChangeAppearance_', 'appearance'),
    ('ChangeSkillMotion_', 'motion'),
    ('ChangeSkillOnConditional_', 'conditional'),
)


def _integer(value, minimum=1):
    if isinstance(value, str) and re.fullmatch(r'[0-9]{1,16}', value):
        value = int(value)
    return value if type(value) is int and minimum <= value < 10**16 else None


def _list(value):
    return value if isinstance(value, list) else []


def _name(value, pattern):
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


def _changes(scripts, issue):
    if scripts is not None and not isinstance(scripts, list):
        issue('invalid_ability_list', value=scripts)
    changes = []
    for script in _list(scripts):
        if not isinstance(script, dict) or not isinstance(script.get('scriptName'), str):
            issue('invalid_ability', value=script)
            continue
        name = script['scriptName']
        for prefix, kind in _SCRIPT_KINDS:
            if not name.startswith(prefix):
                continue
            suffix = name[len(prefix):]
            change = {'kind': kind, 'script': script}
            if kind == 'appearance':
                change['appearance'] = _name(suffix, _APPEARANCE)
                if not change['appearance']:
                    issue('invalid_appearance_change', script=script)
            elif kind == 'motion':
                change['motion'] = _name(suffix, _MOTION)
                buff = script.get('buffData')
                # The turn field selects the source motion fragment. A one-coin
                # attack can explicitly select a later fragment such as S3/3.
                change['fragment'] = _integer(buff.get('turn')) if isinstance(buff, dict) else None
                if not change['motion']:
                    issue('invalid_motion_change', script=script)
                if change['fragment'] is None:
                    issue('missing_motion_fragment', script=script)
            else:
                change['skillId'] = _integer(suffix)
                if change['skillId'] is None:
                    issue('invalid_conditional_skill', script=script)
            changes.append(change)
            break
    return changes


def _resolve(changes, kind, fields, default, default_source, source, issue):
    values = {tuple(change[field] for field in fields) for change in changes if change['kind'] == kind}
    if len(values) > 1:
        issue('ambiguous_' + kind)
        return (None,) * len(fields), source
    if values:
        return values.pop(), source
    return default, default_source


def _levels(rows, issue):
    states = defaultdict(dict)
    for row in rows:
        data = row.get('skillData')
        if not isinstance(data, list):
            issue('invalid_skill_data', value=data)
        for level in _list(data):
            stage = _integer(level.get('gaksungLevel')) if isinstance(level, dict) else None
            if stage is None:
                issue('invalid_gaksung_level', value=level)
                continue
            current = states[stage]
            for key, value in level.items():
                if key in current and current[key] != value:
                    issue('conflicting_level_field', gaksungLevel=stage, field=key,
                          previous=current[key], value=value)
                current[key] = value
    merged = {}
    for stage, fields in sorted(states.items()):
        merged.update(fields)
        yield stage, merged


def _level(stage, data, appearance, issue):
    def level_issue(code, **details):
        issue(code, gaksungLevel=stage, **details)

    changes = _changes(data.get('abilityScriptList'), level_issue)
    (default_appearance,), appearance_source = _resolve(
        changes, 'appearance', ('appearance',), (appearance,), 'personality', 'skill', level_issue)
    motion = _name(data.get('skillMotion'), _MOTION)
    (default_motion, default_fragment), _ = _resolve(
        changes, 'motion', ('motion', 'fragment'), (motion, None), 'skill', 'skill', level_issue)
    has_skill_motion_change = any(change['kind'] == 'motion' for change in changes)
    if default_appearance is None:
        level_issue('missing_default_appearance')
    if default_motion is None:
        level_issue('missing_default_motion')

    conditionals = [dict(change, coinIndex=None) for change in changes if change['kind'] == 'conditional']
    raw_coins = data.get('coinList')
    if not isinstance(raw_coins, list):
        level_issue('missing_coin_list', value=raw_coins)
    coins = []
    for index, coin in enumerate(_list(raw_coins), 1):
        def coin_issue(code, **details):
            level_issue(code, coinIndex=index, **details)

        if not isinstance(coin, dict):
            coin_issue('invalid_coin', value=coin)
            coins.append(dict(coinIndex=index, appearance=None, motion=None, fragment=None,
                              appearanceSource=None, motionSource=None, changes=[]))
            continue
        coin_changes = _changes(coin.get('abilityScriptList'), coin_issue)
        (coin_appearance,), coin_appearance_source = _resolve(
            coin_changes, 'appearance', ('appearance',), (default_appearance,),
            appearance_source, 'coin', coin_issue)
        (coin_motion, fragment), motion_source = _resolve(
            coin_changes, 'motion', ('motion', 'fragment'),
            (default_motion, default_fragment if has_skill_motion_change else index),
            'skill', 'coin', coin_issue)
        if coin_motion is None:
            fragment = None
        coins.append(dict(coinIndex=index, appearance=coin_appearance, motion=coin_motion, fragment=fragment,
                          appearanceSource=coin_appearance_source, motionSource=motion_source,
                          changes=coin_changes))
        conditionals.extend(dict(change, coinIndex=index) for change in coin_changes
                            if change['kind'] == 'conditional')
    return dict(gaksungLevel=stage, defaultAppearance=default_appearance, defaultMotion=default_motion,
                defaultFragment=default_fragment, changes=changes, coins=coins, conditionals=conditionals)


def build_stock_coin_recipe(personality, skills):
    """Use only the personality's declared or conditionally reachable skills.

    Keep the authored skill IDs and tier distinct, including when several skills
    share a tier. Coins and motion fragments each use their own one-based index.
    """
    definitions = defaultdict(list)
    for row in skills:
        skill_id = _integer(row.get('id')) if isinstance(row, dict) else None
        if skill_id is not None:
            definitions[skill_id].append(row)

    appearance = _name(personality.get('appearance'), _APPEARANCE)
    result = dict(schemaVersion=1, personalityId=_integer(personality.get('id')), appearance=appearance,
                  skills=[], issues=[])
    declared = {}
    for attribute in _list(personality.get('attributeList')):
        skill_id = _integer(attribute.get('skillId')) if isinstance(attribute, dict) else None
        if skill_id is None:
            result['issues'].append(dict(code='invalid_personality_skill', value=attribute))
            continue
        number = _integer(attribute.get('number'), 0)
        declared[skill_id] = ('reserve' if number == 0 else 'attack', number)
    for value in _list(personality.get('defenseSkillIDList')):
        skill_id = _integer(value)
        if skill_id is None:
            result['issues'].append(dict(code='invalid_personality_defense', value=value))
            continue
        declared.setdefault(skill_id, ('defense', None))

    pending = deque(declared)
    seen = set(declared)
    conditional_ids = set()
    by_id = {}
    while pending:
        skill_id = pending.popleft()

        def issue(code, **details):
            result['issues'].append(dict(code=code, skillId=skill_id, **details))

        rows = definitions.get(skill_id, [])
        if not rows:
            issue('missing_skill')
        tiers = {_integer(row.get('skillTier')) for row in rows if 'skillTier' in row}
        if len(tiers) > 1:
            issue('conflicting_skill_tier', tiers=sorted(tiers, key=lambda tier: tier or 0))
        role, number = declared.get(skill_id, ('conditional', None))
        levels = [_level(stage, data, appearance, issue) for stage, data in _levels(rows, issue)]
        if rows and not levels:
            issue('missing_skill_levels')
        recipe = dict(skillId=skill_id, skillTier=tiers.pop() if len(tiers) == 1 else None,
                      role=role, number=number, levels=levels)
        by_id[skill_id] = recipe
        result['skills'].append(recipe)
        for level in levels:
            for branch in level['conditionals']:
                target = branch['skillId']
                if target is not None:
                    conditional_ids.add(target)
                    if target not in seen:
                        seen.add(target)
                        pending.append(target)
    for recipe in result['skills']:
        if recipe['role'] == 'reserve' and recipe['skillId'] in conditional_ids:
            recipe['role'] = 'conditional'
        for level in recipe['levels']:
            for branch in level['conditionals']:
                target = by_id.get(branch['skillId'])
                usable_levels = [entry['gaksungLevel'] for entry in target['levels']
                                 if entry['gaksungLevel'] <= level['gaksungLevel']] if target else []
                branch['gaksungLevel'] = max(usable_levels, default=None)
                if target and target['levels'] and not usable_levels:
                    result['issues'].append(dict(code='missing_conditional_level', skillId=recipe['skillId'],
                                                 targetSkillId=branch['skillId'],
                                                 gaksungLevel=level['gaksungLevel']))
    return result


def _scoped_skill_data(archive, roots):
    people, skills = defaultdict(dict), defaultdict(list)
    for info in archive.infolist():
        path = PurePosixPath(info.filename.replace('\\', '/'))
        if path.suffix.casefold() != '.json':
            continue
        root = _member_root(path, 'custom_limbus_data')
        key = str(root).casefold()
        if root is None or key not in roots:
            continue
        folder = tuple(part.casefold() for part in path.parts[len(root.parts) + 1:-1])
        if folder not in (('personality',), ('skill',)):
            continue
        document = _read_json(archive, info)
        rows = document.get('list') if isinstance(document, dict) else document
        if not isinstance(rows, list):
            raise ValueError('私服数据缺少列表：' + info.filename)
        if folder == ('skill',):
            skills[key].extend(rows)
        else:
            for row in rows:
                if isinstance(row, dict) and _integer(row.get('id')) is not None:
                    people[key].setdefault(str(row['id']), {}).update(row)
    return people, skills


def _skill_script_names(levels):
    for level in levels:
        if not isinstance(level, dict):
            continue
        for owner in [level, *_list(level.get('coinList'))]:
            if not isinstance(owner, dict):
                continue
            for ability in _list(owner.get('abilityScriptList')):
                if isinstance(ability, dict) and isinstance(ability.get('scriptName'), str):
                    yield ability['scriptName']


def referenced_custom_forms(archive, declaration):
    """Find extra forms requested by a borrowed body's own skill or coin scripts."""
    root = str(declaration.package_root).casefold()
    people, skills = _scoped_skill_data(archive, {root})
    person = people[root].get(declaration.personality, {})
    pending = [_integer(a.get('skillId')) for a in _list(person.get('attributeList')) if isinstance(a, dict)]
    pending.extend(_integer(s) for s in _list(person.get('defenseSkillIDList')))
    by_id = defaultdict(list)
    for row in skills[root]:
        if isinstance(row, dict):
            by_id[_integer(row.get('id'))].extend(_list(row.get('skillData')))
    forms = {}
    visited = {None}
    while pending:
        skill_id = pending.pop()
        if skill_id in visited:
            continue
        visited.add(skill_id)
        for name in _skill_script_names(by_id.get(skill_id, ())):
            if name.startswith('ChangeSkillOnConditional_'):
                pending.append(_integer(name.removeprefix('ChangeSkillOnConditional_')))
            elif name.startswith('ChangeAppearance_'):
                form = name.removeprefix('ChangeAppearance_')
                key = form.casefold()
                if (key.startswith('!custom_') and key != declaration.appearance.casefold()
                        and valid_appearance_key(form, declaration=True)):
                    forms.setdefault(key, form)
    return tuple(forms[key] for key in sorted(forms))


def read_stock_coin_recipes(archive, *, declarations=None):
    """Join each stock declaration to only its own package root's skill data."""
    declarations = [entry for entry in (read_declarations(archive) if declarations is None else declarations)
                    if not entry.appearance.casefold().startswith('!custom_')]
    if not declarations:
        return []
    people, skills = _scoped_skill_data(archive, {str(d.package_root).casefold() for d in declarations})
    recipes = []
    for declaration in declarations:
        root = str(declaration.package_root).casefold()
        personality = people[root].get(declaration.personality)
        if personality is None:
            continue
        recipe = build_stock_coin_recipe(personality, skills[root])
        if any(change['kind'] == 'appearance' and change['appearance']
               for skill in recipe['skills'] for level in skill['levels']
               for owner in [level, *level['coins']] for change in owner['changes']):
            recipes.append((declaration, recipe))
    return recipes
