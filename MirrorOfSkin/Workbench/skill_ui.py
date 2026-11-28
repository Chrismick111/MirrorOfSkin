"""Prepare cosmetic battle labels and PNGs from the selected author's resources."""
from collections import defaultdict
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from pathlib import PurePosixPath
import re
import stat
from zipfile import BadZipFile

from framepack_manifest import read_framepacks


SUFFIX = '.skill-ui.tsv'
HEADER = 'MOSUI1'
PNG_NAME = re.compile(r'[a-f0-9]{64}\.png\Z')
STATUS = re.compile(r'[A-Za-z0-9_.-]{1,96}\Z')
_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|(,)(?=\s*[\]}])')
_GRANT = re.compile(r'(?<![A-Za-z])(?:buff|buf)\([^,()]+,\s*([A-Za-z0-9_.-]+)\s*,', re.I)
_CHANGE_SKILL = re.compile(r'(?:^|[/:])changeskill\(\s*([1-9][0-9]{0,9})\s*\)', re.I)
_LIMIT = 2 * 1024**2
_MAX_ROWS = 512
_UNIT_KINDS = ('personality', 'enemy', 'enemy-unit', 'assistant', 'abnormality-unit')
_IMAGE_FORMATS = {'.png': 'PNG', '.webp': 'WEBP', '.jpg': 'JPEG', '.jpeg': 'JPEG'}


def _identifier(value):
    if isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,9}', value):
        value = int(value)
    return value if type(value) is int and 0 < value <= 2147483647 else None


def _key(value):
    return tuple(part.casefold() for part in PurePosixPath(value).parts)


def _regular(info):
    return stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG)


def _rows(document):
    if isinstance(document, dict) and 'id' in document:
        return [document]
    if isinstance(document, dict):
        document = document.get('list', document.get('dataList', document))
    if isinstance(document, dict):
        return [dict(row, id=row.get('id', key)) for key, row in document.items()
                if isinstance(row, dict)]
    return [row for row in document if isinstance(row, dict)] if isinstance(document, list) else []


def _read_rows(archive, info, *, locale=False):
    if not 0 < info.file_size <= _LIMIT or not _regular(info):
        return []
    try:
        raw = archive.read(info)
        text = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
        if locale:
            # Some original private-server localization files contain trailing
            # commas and raw tabs. Accept only these cosmetic data documents.
            text = _TOKEN.sub(lambda token: '' if token[1] else token[0], text)
        return _rows(json.loads(text, strict=not locale))
    except (OSError, ValueError, RuntimeError, BadZipFile, NotImplementedError, RecursionError):
        return []


def _index(rows, identify):
    found, ambiguous = {}, set()
    for row in rows:
        key = identify(row)
        if key is None:
            continue
        if key in found and found[key] != row:
            ambiguous.add(key)
        found[key] = row
    return {key: row for key, row in found.items() if key not in ambiguous}


def _levels(rows, stage):
    if not isinstance(rows, list):
        return {}
    if len(rows) == 1 and isinstance(rows[0], dict) and stage not in rows[0]:
        return {0: rows[0]}
    return _index((row for row in rows if isinstance(row, dict)),
                  lambda row: row.get(stage) if type(row.get(stage)) is int and 0 <= row[stage] <= 32 else None)


def _name(value):
    if not isinstance(value, str):
        return ''
    cleaned = ' '.join(value.split())
    return ''.join(ch for ch in cleaned if ch.isprintable())[:160]


def _icon_field(value):
    if type(value) is int:
        value = str(value)
    return value if isinstance(value, str) and STATUS.fullmatch(value) else ''


def _status_keys(tree):
    """Read explicit effects and initial status declarations without running scripts."""
    result = set()
    stack = [tree]
    while stack:
        row = stack.pop()
        if isinstance(row, list):
            stack.extend(row)
        elif isinstance(row, dict):
            key = row.get('buff')
            if isinstance(key, str) and STATUS.fullmatch(key) and 'stack' in row:
                result.add(key)
            script = row.get('scriptName')
            if (isinstance(script, str) and script.casefold().startswith(('givebuff', 'addbuff', 'applybuff'))
                    and isinstance(row.get('buffData'), dict)):
                key = row['buffData'].get('buffKeyword')
                if isinstance(key, str) and STATUS.fullmatch(key):
                    result.add(key)
            stack.extend(row.values())
        elif isinstance(row, str) and row.startswith('Modular/'):
            result.update(_GRANT.findall(row))
    return result


def _image(archive, info):
    from PIL import Image
    if info is None or not 0 < info.file_size <= 8 * 1024**2 or not _regular(info):
        return b''
    try:
        suffix = PurePosixPath(info.filename).suffix.casefold()
        with Image.open(BytesIO(archive.read(info)), formats=[_IMAGE_FORMATS[suffix]]) as source:
            if max(source.size) > 4096 or getattr(source, 'is_animated', False):
                return b''
            icon = source.convert('RGBA')
            if icon.getchannel('A').getbbox() is None:
                return b''
            icon.thumbnail((512, 512), Image.Resampling.LANCZOS)
            target = BytesIO()
            icon.save(target, format='PNG')
            return target.getvalue()
    except (OSError, ValueError, RuntimeError, BadZipFile, NotImplementedError, Image.DecompressionBombError):
        return b''


def _localized_names(locales):
    result = defaultdict(dict)
    # Prefer Chinese, then supported fallback languages for missing names.
    for language in ('', 'cn', 'zh', 'zh-cn', 'zh-hans', 'zhs', 'zh-tw', 'zh-hant',
                     'en', 'en-us', 'en-gb', 'jp', 'ja', 'ja-jp', 'kr', 'ko', 'ko-kr'):
        for skill, row in _index(locales.get(language, ()), lambda row: _identifier(row.get('id'))).items():
            names = {level: name for level, item in _levels(row.get('levelList'), 'level').items()
                     if (name := _name(item.get('name')))}
            if name := _name(row.get('name')):
                names.setdefault(0, name)
            if 0 in names:
                names.setdefault(1, names[0])
            for level, name in names.items():
                result[skill].setdefault(level, name)
    return result


def _appearance(value):
    if not isinstance(value, str):
        return ''
    return PurePosixPath(value.replace('\\', '/')).name.casefold().removesuffix('.prefab').removeprefix('!custom_')


def _package_from_model(members, record):
    source = record.get('_source_member')
    if source is None:
        return None
    key = _key(str(source).replace('\\', '/'))
    if key in members:
        for index, part in enumerate(key[:-1]):
            if part in ('custom_appearance', 'custom_bundles', 'archived_bundles', 'installation'):
                return key[:index]
    return None


def _author_units(definitions, target, address):
    """Bind declared skills to the selected prefab and its declared body parts."""
    appearance = _appearance(address)
    candidates = {kind: _index(definitions[kind], lambda row: _identifier(row.get('id')))
                  for kind in _UNIT_KINDS}
    personality = candidates['personality'].get(target, {})
    unit = personality
    if not (personality.get('attributeList') or personality.get('defenseSkillIDList')):
        enemies = [row for kind in _UNIT_KINDS[1:] for row in candidates[kind].values()
                   if not appearance or _appearance(row.get('appearance')) == appearance]
        exact = [row for row in enemies if _identifier(row.get('id')) == target]
        # A model may carry a cosmetic ID distinct from the unit's data ID.
        # The use of its published prefab address still requires a unique match.
        matches = exact or (enemies if appearance else ())
        if len(matches) == 1:
            unit = matches[0]
    units = [unit]
    declared_parts = unit.get('abnormalityPartList')
    if isinstance(declared_parts, list):
        parts = _index(definitions['abnormality-part'], lambda row: _identifier(row.get('id')))
        units.extend(parts[ident] for value in declared_parts if (ident := _identifier(value)) in parts)
    return units


def _pattern_skills(value):
    stack = [value]
    while stack:
        row = stack.pop()
        if isinstance(row, list):
            stack.extend(row)
        elif isinstance(row, dict):
            if (skill := _identifier(row.get('skillID'))) is not None:
                yield skill
            stack.extend(row.values())


def _defense_subtype(definition):
    stages = definition.get('skillData', [])
    if not isinstance(stages, list):
        return None
    values = [row['defType'] for row in (definition, *stages) if isinstance(row, dict) and 'defType' in row]
    return (values[0] if values and values[0] in ('GUARD', 'EVADE', 'COUNTER')
            and all(value == values[0] for value in values) else None)


def _conditional_defense_targets(roles, skills):
    from stock_coin_recipe import _skill_script_names
    targets = set()
    for skill, role in roles.items():
        stages = skills.get(skill, {}).get('skillData', [])
        for script in _skill_script_names(stages if isinstance(stages, list) else []):
            if role != 'defense' and script.startswith('Modular/'):
                targets.update(target for target in map(int, _CHANGE_SKILL.findall(script)) if target != skill)
            elif script.startswith('ChangeSkillOnConditional_'):
                target = _identifier(script.removeprefix('ChangeSkillOnConditional_'))
                if target is not None and target != skill:
                    targets.add(target)
    return targets


def _private_roles(person, definitions):
    result = {}
    attributes = person.get('attributeList')
    for attribute in attributes if isinstance(attributes, list) else []:
        if not isinstance(attribute, dict) or (skill := _identifier(attribute.get('skillId'))) is None:
            continue
        tier = definitions.get(skill, {}).get('skillTier')
        number = attribute.get('number')
        result[skill] = ('conditional' if number == 0 else f'attack{tier}'
                         if type(number) is int and number > 0 and tier in (1, 2, 3) else 'unknown')
    defenses = person.get('defenseSkillIDList')
    for value in defenses if isinstance(defenses, list) else []:
        if (skill := _identifier(value)) is not None:
            result[skill] = 'defense'
    for skill in _pattern_skills(person.get('patternList')):
        result.setdefault(skill, 'unknown')
    for skill in result:
        levels = _levels(definitions.get(skill, {}).get('skillData'), 'gaksungLevel')
        types = {level.get('defType') for level in levels.values() if isinstance(level.get('defType'), str)}
        if types and types <= {'GUARD', 'EVADE', 'COUNTER'}:
            result[skill] = 'defense'
    return result


def _passives(person, membership):
    stack = [person.get('passiveSet'), person.get('supporterPassiveSet'), membership]
    ids = set()
    while stack:
        row = stack.pop()
        if isinstance(row, list):
            stack.extend(row)
        elif isinstance(row, dict):
            for key, value in row.items():
                if key.casefold() == 'passiveidlist' and isinstance(value, list):
                    ids.update(ident for item in value if (ident := _identifier(item)) is not None)
                stack.append(value)
    return ids


def _skill_rows(skill, role, definition, names, image):
    levels = _levels(definition.get('skillData'), 'gaksungLevel')
    current_icon = _icon_field(definition.get('iconID'))
    current_name = ''
    previous = None
    for level in sorted({0, *names, *levels}):
        current_icon = _icon_field(levels.get(level, {}).get('iconID')) or current_icon
        current_name = names.get(level, current_name)
        if level == 0 and 1 in levels:
            current_icon = _icon_field(levels[1].get('iconID')) or current_icon
        if level == 0 and 1 in names:
            current_name = names[1]
        icon = image('skill_' + current_icon) if current_icon else ''
        icon = icon or image('skill_' + str(skill))
        result = (current_name, icon)
        if any(result) and result != previous:
            yield ('S', str(skill), role, str(level), *result)
            previous = result


def _archive_index(archive):
    found, duplicates = {}, set()
    for info in archive.infolist():
        name = info.filename.replace('\\', '/')
        path = PurePosixPath(name)
        if info.is_dir() or path.is_absolute() or '..' in path.parts or ':' in name:
            continue
        key = _key(name)
        if key in found:
            duplicates.add(key)
        found[key] = info
    return {key: info for key, info in found.items() if key not in duplicates}


def collect(archive, records, portraits=None, *, external=None):
    """Return (encoded sidecar, {digest.png: data}) in record order."""
    portraits = portraits or {}
    members = _archive_index(archive)
    load_image = lru_cache(maxsize=256)(lambda info: _image(archive, info))
    skins = {(_key(str(skin.package_root)), _identifier(skin.personality)): skin
             for skin in read_framepacks(archive)}
    grouped = {}

    def scope_data(root, skin):
        scope = (root, skin.locale_exclusive_dir if skin else None)
        if scope not in grouped:
            definitions, locales = _scope_data(archive, members, root, skin)
            grouped[scope] = definitions, _localized_names(locales)
        return grouped[scope]

    result = []
    for index, record in enumerate(records):
        entry = record.get('entry', {})
        owner = entry.get('private_declaration', {})
        target = _identifier(owner.get('personality'))
        root = _key(owner.get('root', ''))
        skin = skins.get((root, target))
        address = record.get('_source_address')
        if not owner and _appearance(address) and (package := _package_from_model(members, record)) is not None:
            definitions, _ = scope_data(package, None)
            unit = _author_units(definitions, None, address)[0]
            if target := _identifier(unit.get('id')):
                root = package
        images = {}
        image_bytes = 0

        def keep(blob):
            nonlocal image_bytes
            if not blob:
                return ''
            filename = sha256(blob).hexdigest() + '.png'
            if filename not in images:
                if image_bytes + len(blob) > 16 * _LIMIT:
                    return ''
                images[filename] = blob
                image_bytes += len(blob)
            return filename

        def image(stem):
            folder = root + (('assets', 'skill_icons') if skin else ('custom_sprites',))
            for suffix in _IMAGE_FORMATS:
                if blob := load_image(members.get(folder + (stem.casefold() + suffix,))):
                    return keep(blob)
            return ''

        rows = []
        defense_types = {}
        if target:
            rows.append(('T', str(target)))
        identity = 'story_BRolandBaseAppearance' if record.get('builtin') == 'roland' else entry.get('identity_id')
        portrait = portraits.get(identity)
        portrait_name = keep(portrait)
        if target is not None:
            definitions, locale = scope_data(root, skin)
            skills = _index(definitions['skill'], lambda row: _identifier(row.get('id')))
            units = _author_units(definitions, target, address)
            unit = units[0]
            if not skin and not portrait_name:
                for ident in dict.fromkeys((target, _identifier(unit.get('viewid')), _identifier(unit.get('id')))):
                    if ident is not None and (portrait_name := image(f'profile_{ident}')):
                        break
            roles = {}
            for declared in units:
                for skill, role in _private_roles(declared, skills).items():
                    if role != 'unknown' or skill not in roles:
                        roles[skill] = role
            conditional_targets = _conditional_defense_targets(roles, skills)
            for route in record.get('coin_routes', []):
                if len(route) == 5 and route[4]:
                    conditional_targets.add(route[0])
                    if roles.get(route[0]) != 'defense':
                        roles[route[0]] = 'conditional'
            if skin:
                roles = {skill: 'unknown' for skill in locale}
            for skill, role in sorted(roles.items()):
                definition = skills.get(skill, {})
                if role == 'defense':
                    subtype = _defense_subtype(definition)
                    if skill in conditional_targets:
                        subtype = f'CONDITIONAL_{subtype}' if subtype else 'CONDITIONAL'
                    if subtype:
                        defense_types[str(skill)] = subtype
                text_id = _identifier(definition.get('textID')) or skill
                rows.extend(_skill_rows(skill, role, definition, locale.get(text_id, {}), image))
            memberships = _index(definitions['personality-passive'],
                                 lambda row: _identifier(row.get('personalityID')))
            passives = _index(definitions['passive'], lambda row: _identifier(row.get('id')))
            passive_ids = set().union(*(_passives(declared, memberships.get(_identifier(declared.get('id'))))
                                        for declared in units))
            passive_ids.update(_passives({}, memberships.get(target)))
            status = _status_keys([units, *(skills.get(skill) for skill in roles),
                                   *(passives.get(key) for key in passive_ids)])
            declared = _index(definitions['buff'], lambda row: _icon_field(row.get('id')) or None)
            for key in sorted(status.intersection(declared)):
                icon = _icon_field(declared[key].get('iconId', declared[key].get('iconID', key)))
                if icon and (filename := image('buffIcon_' + icon)):
                    rows.append(('B', key, filename))
        if portrait_name:
            rows.insert(1 if target else 0, ('P', portrait_name))
        if external is not None:
            from skill_ui_merge import merge_external
            rows = merge_external(rows, external[index], keep, address=record.get('_source_address'))
        rows = rows[:_MAX_ROWS]
        display_defenses = {r[1] for r in rows if r[0] in ('S', 'R') and r[2] == 'defense'}
        for skill, subtype in defense_types.items():
            if len(rows) == _MAX_ROWS:
                break
            if skill in display_defenses:
                rows.append(('D', skill, subtype))
        referenced = {row[-1] for row in rows if row[-1] in images}
        data = (HEADER + '\n' + ''.join('\t'.join(row) + '\n' for row in rows)).encode('utf-8') if rows else b''
        result.append((data, {name: images[name] for name in referenced}))
    return result


def _scope_data(archive, members, root, skin):
    definitions, locales = defaultdict(list), defaultdict(list)
    exclusive = _key(str(skin.locale_exclusive_dir)) if skin and skin.locale_exclusive_dir else None
    remaining = 16 * _LIMIT
    for key, info in sorted(members.items()):
        if not key or not key[-1].endswith('.json') or key[:len(root)] != root:
            continue
        if not 0 < info.file_size <= min(remaining, _LIMIT):
            continue
        rel = key[len(root):]
        if exclusive and key[:len(exclusive)] == exclusive and key[len(exclusive):-1] == ('skilllist',):
            locales[''].extend(_read_rows(archive, info, locale=True))
        elif not skin and len(rel) == 4 and rel[0] == 'custom_limbus_locale' and rel[2] == 'skilllist':
            locales[rel[1]].extend(_read_rows(archive, info, locale=True))
        elif not skin and len(rel) == 3 and rel[0] == 'custom_limbus_data' and rel[1] in (
                *_UNIT_KINDS, 'abnormality-part', 'skill', 'personality-passive', 'passive', 'buff'):
            definitions[rel[1]].extend(_read_rows(archive, info))
        else:
            continue
        remaining -= info.file_size
    return definitions, locales


def icon_names(sidecar):
    """Return only valid content-addressed PNG names from a managed sidecar."""
    from framepack_dialogue import plain_file
    if not plain_file(sidecar) or sidecar.stat().st_size > _LIMIT:
        raise ValueError('战斗外观资料文件无效')
    lines = sidecar.read_text(encoding='utf8').splitlines()
    if not lines or lines[0] != HEADER:
        raise ValueError('战斗外观资料文件格式无效')
    lengths = {'P': 2, 'S': 6, 'R': 6, 'B': 3}
    return {fields[-1] for line in lines[1:] for fields in [line.split('\t')]
            if len(fields) == lengths.get(fields[0]) and PNG_NAME.fullmatch(fields[-1])}


def obsolete_icons(folder, candidates, *, excluding=()):
    """A PNG can be shared by several models in the same installed package."""
    from framepack_dialogue import plain_file
    keep = set(candidates)
    try:
        for path in folder.glob('*' + SUFFIX):
            if path not in excluding:
                keep.difference_update(icon_names(path))
    except (OSError, UnicodeError, ValueError):
        return set()
    obsolete = set()
    for name in keep:
        path = folder / name
        try:
            if (PNG_NAME.fullmatch(name) and plain_file(path) and path.stat().st_size <= _LIMIT
                    and sha256(path.read_bytes()).hexdigest() == name[:-4]):
                obsolete.add(path)
        except OSError:
            continue
    return obsolete
