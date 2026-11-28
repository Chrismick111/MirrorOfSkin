"""Read cosmetic entries from published models and chapter resource packages."""
from collections import defaultdict
from functools import lru_cache
from io import BytesIO
import json
from pathlib import PurePosixPath
import re
from zipfile import BadZipFile, ZipFile

from bundle_migration import validated_unpacked_size
from skill_ui import (_appearance, _archive_index, _author_units, _icon_field, _identifier, _image, _index, _key,
                      _levels, _localized_names, _passives, _private_roles, _read_rows, _regular,
                      _rows, _scope_data, _status_keys, _TOKEN, _UNIT_KINDS)


_RESOURCE = ('assets', 'resources_moved')
_PREFAB = _RESOURCE + ('prefab', 'sd')
_SKILL = _RESOURCE + ('sprite', 'skillicon')
_PORTRAIT = _RESOURCE + ('sprite', 'unit', 'portrait')
_PROFILE = _RESOURCE + ('sprite', 'unit', 'profile', 'normal')
_STATUS = _RESOURCE + ('buf',)
_ICON = re.compile(r'([1-9][0-9]{3,9})(?:_([1-9][0-9]?))?\.png\Z')
_FILE = re.compile(r'[^/\\:\s]+\.bundle\Z', re.I)
_LANGUAGES = ('cn', 'zh', 'zh-cn', 'zh-hans', 'zhs', 'zh-tw', 'zh-hant', 'en', 'en-us', 'en-gb',
              'jp', 'ja', 'ja-jp', 'kr', 'ko', 'ko-kr')
_LOCALE = re.compile(r'(?:(%s)[_-])?(?:textdata[_-]?)?skill(?:list)?(?:[_-][^/]*)?\.json\Z'
                     % '|'.join(sorted(_LANGUAGES, key=len, reverse=True)))
_EMPTY = (None, [], {}, b'')
_DATA_LIMIT = 2 * 1024**2
_BUNDLE_LIMIT = 256 * 1024**2
_TEXT_FOLDERS = {'locale', 'localization', 'textdata', 'textdata_skill', 'skilllist', *_LANGUAGES}


def supported_member(path, size):
    path = _key(str(path).replace('\\', '/'))
    if not path or not 0 < size <= _BUNDLE_LIMIT:
        return False
    if path[-1] == 'archive_locations.tsv':
        return size <= _DATA_LIMIT
    if len(path) >= 2 and path[-2] == 'archived_bundles' and _FILE.fullmatch(path[-1]):
        return True
    if path[-1] == '__data' and 'uninstallation' in path:
        return True
    return size <= _DATA_LIMIT and bool(_LOCALE.fullmatch(path[-1]))


def _catalogues(archive, members):
    result = {}
    remaining = 8 * _DATA_LIMIT
    for path, info in members.items():
        if path[-1] != 'archive_locations.tsv' or not 0 < info.file_size <= min(_DATA_LIMIT, remaining):
            continue
        if not _regular(info):
            continue
        remaining -= info.file_size
        try:
            text = archive.read(info).decode('utf-8-sig')
        except (ValueError, OSError, RuntimeError, BadZipFile):
            continue
        entries = defaultdict(set)
        for line in text.splitlines():
            cells = line.split('\t')
            if len(cells) != 4 or not _FILE.fullmatch(cells[2]):
                continue
            kind, address, bundle, _ = cells
            address = _key(address.replace('\\', '/'))
            if kind in ('UnityEngine.Sprite', 'UnityEngine.GameObject', 'UnityEngine.TextAsset'):
                entries[address].add((kind.rsplit('.', 1)[-1], bundle.casefold()))
        result[path[:-1]] = {address: next(iter(choices)) for address, choices in entries.items()
                             if len(choices) == 1}
    return result


def _patch_ids(archive, info, source):
    from carra_import import ENTRY

    def ids(patch):
        result = set()
        for name in patch.namelist():
            match = ENTRY.fullmatch(name)
            if match and tuple(item.casefold() for item in match.groups()[:2]) == source[-3:-1]:
                result.add(int(match[3]))
        return result

    if info is None:
        return ids(archive)
    if not _regular(info) or not 0 < info.file_size <= _BUNDLE_LIMIT:
        return set()
    try:
        with ZipFile(BytesIO(archive.read(info))) as patch:
            return ids(patch)
    except (OSError, ValueError, RuntimeError, BadZipFile):
        return set()


def _owner(address):
    if address[:len(_PREFAB)] != _PREFAB or len(address) <= len(_PREFAB):
        return None
    match = re.fullmatch(r'([1-9][0-9]{3,7})_[^/]+\.prefab', address[-1])
    return _identifier(match[1]) if match else None


def _skill_icon(address):
    if address[:-1] != _SKILL:
        return None
    match = _ICON.fullmatch(address[-1])
    if not match or (skill := _identifier(match[1])) is None:
        return None
    level = int(match[2] or 0)
    return (skill, level) if level <= 32 else None


def _role_scope(member):
    for section in ('archived_bundles', 'installation', 'custom_appearance', 'custom_bundles'):
        if section in member:
            return member[:member.index(section)]
    return member[:-1]


def _sprite(pointer, changed=None):
    from PIL import Image

    if pointer is None:
        return b''
    try:
        obj = pointer.read()
        source_texture = obj.m_RD.texture
        if changed is not None and pointer.path_id not in changed and (
                source_texture.file_id != 0 or source_texture.path_id not in changed):
            return b''
        texture = source_texture.read()
        if not 0 < min(texture.m_Width, texture.m_Height) <= max(texture.m_Width, texture.m_Height) <= 4096:
            return b''
        icon = obj.image.convert('RGBA')
        if icon.getchannel('A').getbbox() is None:
            return b''
        icon.thumbnail((512, 512), Image.Resampling.LANCZOS)
        output = BytesIO()
        icon.save(output, 'PNG')
        return output.getvalue()
    except Exception:
        # An absent streamed payload or unsupported Unity texture is optional artwork.
        return b''


def _embedded_locales(pointers, changed):
    locales = defaultdict(list)
    total = 0
    for address, pointer in pointers.items():
        match = _LOCALE.fullmatch(address[-1]) if address else None
        if not match or changed is not None and pointer.path_id not in changed:
            continue
        if not 0 < getattr(pointer, 'byte_size', _DATA_LIMIT) <= _DATA_LIMIT or total >= 8 * _DATA_LIMIT:
            continue
        try:
            content = pointer.read().m_Script
            if isinstance(content, bytes):
                content = content.decode('utf-8-sig')
            if isinstance(content, str) and 0 < len(content) <= _DATA_LIMIT:
                total += len(content)
                language = _locale_language(address, match)
                locales[language].extend(_rows(json.loads(
                    _TOKEN.sub(lambda token: '' if token[1] else token[0], content.lstrip('\ufeff')),
                    strict=False)))
        except Exception:
            continue
    return locales


def _locale_language(address, match):
    return match[1] or next((part for part in reversed(address[:-1]) if part in _LANGUAGES), '')


def _embedded_name_changes(authored, rollback):
    """Compare each locale at its effective upgrade level within the paired bundle."""
    result = defaultdict(dict)
    for language in ('', *_LANGUAGES):
        authored_names = _localized_names({'': authored.get(language, ())})
        rollback_names = _localized_names({'': rollback.get(language, ())})
        for skill, names in authored_names.items():
            baseline = rollback_names.get(skill, {})
            original = name = ''
            overriding = False
            for level in sorted(names.keys() | baseline.keys()):
                original = baseline.get(level, original)
                name = names.get(level, name)
                if name and name != original:
                    result[skill].setdefault(level, name)
                    overriding = True
                elif overriding:
                    result[skill].setdefault(level, None)
                    overriding = False
    return result


def _loose_locales(archive, members, root):
    locales = defaultdict(list)
    remaining = 8 * _DATA_LIMIT
    for path, info in members.items():
        if path[:len(root)] != root:
            continue
        relative = path[len(root):]
        if (not relative or any(part not in _TEXT_FOLDERS for part in relative[:-1])
                or not 0 < info.file_size <= min(remaining, _DATA_LIMIT)):
            continue
        match = _LOCALE.fullmatch(relative[-1])
        if match:
            language = _locale_language(relative, match)
            locales[language].extend(_read_rows(archive, info, locale=True))
            remaining -= info.file_size
    return locales


def collect_external(archive, records, *, model_archive=None, expanded_members=None, unity=None):
    """Return (target, skill rows, status PNGs, portrait PNG) in input order."""
    members = _archive_index(archive)
    model_archive = model_archive if model_archive is not None else archive
    models = members if model_archive is archive else _archive_index(model_archive)
    catalogues = _catalogues(archive, members)
    expanded_members = expanded_members or {}
    remaining = 1024**3

    @lru_cache(maxsize=4)
    def published(member):
        nonlocal remaining
        info = models.get(member) or members.get(member)
        if unity is None or info is None or not _regular(info) or not 0 < info.file_size <= _BUNDLE_LIMIT:
            return {}, {}, {}
        try:
            source = model_archive if member in models else archive
            content = source.read(info)
            size = validated_unpacked_size(content)
            if size > remaining:
                return {}, {}, {}
            remaining -= size
            env = unity.load(content)
            found = {'GameObject': {}, 'Sprite': {}, 'TextAsset': {}}
            duplicates = set()
            for address, pointer in env.container.items():
                kind = pointer.type.name
                if kind in found:
                    key = _key(address.replace('\\', '/'))
                    if key in found[kind]:
                        duplicates.add((kind, key))
                    found[kind][key] = getattr(pointer, 'deref', lambda: pointer)()
            for kind, key in duplicates:
                del found[kind][key]
            return found['GameObject'], found['Sprite'], found['TextAsset']
        except Exception:
            return {}, {}, {}

    @lru_cache(maxsize=64)
    def scope_data(root):
        definitions, locales = _scope_data(archive, members, root, None)
        for language, data in _loose_locales(archive, members, root).items():
            locales[language].extend(data)
        return definitions, locales

    @lru_cache(maxsize=8)
    def changes(member):
        source = '/'.join(member)
        if source in expanded_members:
            info = members.get(_key(str(expanded_members[source]).replace('\\', '/')))
            return _patch_ids(archive, info, member) if info is not None else set()
        if archive is not model_archive and any(re.fullmatch(r'[0-9a-f]{32}/[0-9a-f]{32}/-?\d+\.\d+', '/'.join(key))
                                                for key in members):
            return _patch_ids(archive, None, member)
        return None

    def collect(record):
        source = record.get('_source_member')
        if not source:
            return _EMPTY
        member = _key(str(source).replace('\\', '/'))
        if not member or 'uninstallation' in member:
            return _EMPTY
        root = _role_scope(member)
        chapter = member[-2:-1] == ('archived_bundles',)
        bindings = catalogues.get(root, {})
        prefabs, sprites, texts = published(member)
        selected = _key(str(record.get('_source_address', '')).replace('\\', '/'))
        if not selected and record.get('builtin'):
            owners = [path for path in prefabs if _owner(path)]
            if len(owners) == 1:
                selected = owners[0]
        if selected not in prefabs:
            return _EMPTY
        if chapter and bindings.get(selected) != ('GameObject', member[-1]):
            return _EMPTY
        owner = record.get('entry', {}).get('private_declaration', {})
        if owner:
            root = _key(owner.get('root', ''))
        elif original := expanded_members.get('/'.join(member)):
            root = _role_scope(_key(str(original).replace('\\', '/')))
        definitions, locales = scope_data(root)
        target = _identifier(owner.get('personality')) or _owner(selected)
        if target is None:
            candidates = {_identifier(unit.get('id')) for kind in _UNIT_KINDS for unit in definitions[kind]
                          if _appearance(unit.get('appearance')) == _appearance(selected[-1])}
            candidates.discard(None)
            if len(candidates) != 1:
                return _EMPTY
            target = next(iter(candidates))
        changed = changes(member)
        base_sprites, base_texts = {}, {}
        if 'installation' in member and changed is None:
            slot = member.index('installation')
            rollback = member[:slot] + ('uninstallation',) + member[slot + 1:]
            _, base_sprites, base_texts = published(rollback)

        skills = _index(definitions['skill'], lambda row: _identifier(row.get('id')))
        units = _author_units(definitions, target, '/'.join(selected))
        roles = {skill: role for unit in units for skill, role in _private_roles(unit, skills).items()}
        if chapter:
            texts = {}
            for address, (kind, bundle) in bindings.items():
                if kind == 'TextAsset' and _LOCALE.fullmatch(address[-1]):
                    _, _, refs = published(root + ('archived_bundles', bundle))
                    if address in refs:
                        texts[address] = refs[address]
        loose_names = _localized_names(locales)
        embedded_names = _embedded_name_changes(_embedded_locales(texts, changed),
                                                _embedded_locales(base_texts, None))

        @lru_cache(maxsize=256)
        def image(address):
            candidates = sprites
            if chapter:
                kind, bundle = bindings.get(address, ('', ''))
                if kind != 'Sprite':
                    return b''
                _, candidates, _ = published(root + ('archived_bundles', bundle))
            png = _sprite(candidates.get(address), changed)
            if png and png == _sprite(base_sprites.get(address)):
                return b''
            return png

        addresses = set(bindings if chapter else sprites)
        icons = defaultdict(dict)
        for address in sorted(addresses):
            if address and (icon := _skill_icon(address)):
                identifier, stage = icon
                icons[identifier][stage] = address
        if not roles:
            # Published skill icon and text IDs encode the owning personality/unit
            # followed by the game's two-digit local skill index.
            roles.update((skill, 'unknown') for skill in {*loose_names, *embedded_names, *icons}
                         if skill // 100 == target and skill % 100)
        else:
            for skill in loose_names.keys() | embedded_names.keys():
                if skill // 100 == target and skill % 100:
                    roles.setdefault(skill, 'unknown')

        output = []
        for skill, role in sorted(roles.items())[:256]:
            definition = skills.get(skill, {})
            text_id = _identifier(definition.get('textID')) or skill
            loose = loose_names.get(text_id, {})
            embedded = embedded_names.get(text_id, {})
            levels = _levels(definition.get('skillData'), 'gaksungLevel')
            icon_id = _identifier(definition.get('iconID')) or skill
            icon_ids = {icon_id, *(_identifier(value.get('iconID')) for value in levels.values())}
            loose_name = loose.get(1, loose.get(0, ''))
            embedded_name = embedded.get(1, embedded.get(0, ''))
            previous = None
            icon_stages = {stage for identifier in icon_ids for stage in icons.get(identifier, {})}
            for level in sorted({0, *loose, *embedded, *levels, *icon_stages}):
                icon_id = _identifier(levels.get(level or 1, {}).get('iconID')) or icon_id
                embedded_name = embedded.get(level, embedded_name)
                loose_name = loose.get(level, loose_name)
                name = loose_name or embedded_name
                stages = icons.get(icon_id, {})
                stage = max((stage for stage in stages if stage <= level), default=0)
                address = stages.get(stage)
                raw = image(address) if address else b''
                pair = name, raw
                restore = name is None and previous is not None and bool(previous[0])
                if (name or raw or restore) and pair != previous:
                    output.append((skill, role, level, None if restore else name or '', raw))
                previous = pair

        profile = _PROFILE + (f'{target}_normal_profile.png',)
        portrait = image(profile)
        if not portrait:
            profiles = sorted(address for address in addresses if address[:len(_PORTRAIT)] == _PORTRAIT
                              and address[-1] == f'{target}_portrait.png')
            if len(profiles) == 1:
                portrait = image(profiles[0])
        memberships = _index(definitions['personality-passive'], lambda row: _identifier(row.get('personalityID')))
        passives = _index(definitions['passive'], lambda row: _identifier(row.get('id')))
        buffs = _index(definitions['buff'], lambda row: _icon_field(row.get('id')) or None)
        status_keys = _status_keys([*units, *(skills.get(skill) for skill in roles),
                                    *(passives.get(key) for unit in units for key in _passives(
                                        unit, memberships.get(_identifier(unit.get('id')))))])
        statuses = {}
        for key in sorted(status_keys.intersection(buffs))[:256]:
            icon = _icon_field(buffs[key].get('iconId', buffs[key].get('iconID', key)))
            if icon and (raw := image(_STATUS + (icon.casefold() + '.png',))):
                statuses[key] = raw
            elif icon and (raw := _image(archive, members.get(root + ('custom_sprites', 'bufficon_' + icon.casefold() + '.png')))):
                statuses[key] = raw
        return (target, output, statuses, portrait) if output or statuses or portrait else _EMPTY

    return [collect(record) for record in records]
