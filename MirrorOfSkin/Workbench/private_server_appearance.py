"""Match private-server personality declarations to the packaged battle prefabs."""
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import PurePosixPath
import re
from unicodedata import category


@dataclass(frozen=True)
class Declaration:
    package_root: PurePosixPath
    personality: str
    appearance: str
    label: str
    has_motions: bool
    character_id: int = 0


def _member_root(path, marker):
    parts = tuple(part.casefold() for part in path.parts)
    if marker in parts:
        return PurePosixPath(*path.parts[:parts.index(marker)])
    return None


def appearance_package_root(path):
    root = _member_root(path, 'custom_appearance')
    return str(root).casefold() if root is not None else None


def base_appearance(value):
    return value[8:] if value.casefold().startswith('!custom_') else value


_DEVICE_NAME = re.compile(r'(?:con|prn|aux|nul|(?:com|lpt)[1-9¹²³])', re.I)
_INVISIBLE_LETTERS_OR_MARKS = {'\u034f', '\u115f', '\u1160', '\u17b4', '\u17b5',
                              '\u180b', '\u180c', '\u180d', '\u180f', '\u3164', '\uffa0'}


def valid_appearance_key(value, *, declaration=False):
    """Accept a visible Unicode identifier that can also name one Windows path component."""
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        return False
    if declaration:
        prefix = next((p for p in ('!custom_', '!motions_') if value.casefold().startswith(p)), '')
        value = value[len(prefix):]
    if (not value or value.endswith((' ', '.')) or
            not (value[0].isalnum() or value[0] in ('_!' if declaration else '_'))):
        return False
    punctuation = '_. -·・' + ('!' if declaration else '')
    for char in value:
        if (char in _INVISIBLE_LETTERS_OR_MARKS or '\ufe00' <= char <= '\ufe0f'
                or '\U000e0100' <= char <= '\U000e01ef'):
            return False
        if not (char in punctuation or char.isalnum() or category(char).startswith('M')):
            return False
    return len(value.encode('utf-16-le')) <= 510 and not _DEVICE_NAME.fullmatch(value.split('.', 1)[0].rstrip())


def _read_json(archive, info):
    try:
        if info.file_size <= 8 * 1024**2:
            return json.loads(archive.read(info).decode('utf-8-sig'))
    except (ValueError, RecursionError) as error:
        raise ValueError('无法读取私服人格数据：' + info.filename) from error
    raise ValueError('私服人格数据过大：' + info.filename)


def _plain_label(value):
    return ' '.join(re.sub(r'<[^>]*>', '', value).split()) if isinstance(value, str) else ''


def read_declarations(archive):
    definitions, labels = {}, defaultdict(set)
    definition_roots = {}
    motions = set()
    for info in archive.infolist():
        path = PurePosixPath(info.filename.replace('\\', '/'))
        motion_root = _member_root(path, 'custom_motions')
        if motion_root is not None and not info.is_dir() and len(path.parts) >= len(motion_root.parts)+3:
            motions.add((str(motion_root).casefold(), path.parts[len(motion_root.parts)+1].casefold()))
        if path.suffix.casefold() != '.json':
            continue
        root = _member_root(path, 'custom_limbus_data')
        if root is not None and tuple(s.casefold() for s in path.parts[len(root.parts)+1:-1]) == ('personality',):
            value = _read_json(archive, info)
            rows = value.get('list') if isinstance(value, dict) else value
            if not isinstance(rows, list):
                raise ValueError('私服人格数据缺少人格列表：' + info.filename)
            for row in rows:
                if not isinstance(row, dict) or 'appearance' not in row:
                    continue
                personality, appearance = str(row.get('id', '')), row['appearance']
                if (not re.fullmatch(r'[1-9][0-9]{0,15}', personality)
                        or not valid_appearance_key(appearance, declaration=True)):
                    raise ValueError('私服人格包含无效的标识或外观：' + info.filename)
                folded_root = str(root).casefold()
                prior_root = definition_roots.setdefault(folded_root, root)
                if prior_root != root:
                    raise ValueError(f'私服人格包目录大小写冲突：{prior_root} 与 {root}')
                key = (folded_root, personality)
                previous = definitions.get(key)
                if previous and previous[1].casefold() != appearance.casefold():
                    raise ValueError('同一私服人格声明了多个外观：' + personality)
                character_id = row.get('characterId')
                if type(character_id) is not int or not 1 <= character_id <= 12:
                    character_id = 0
                if previous and previous[2] and character_id and previous[2] != character_id:
                    raise ValueError('同一私服人格声明了多个基础罪人：' + personality)
                definitions[key] = (root, appearance, character_id or (previous[2] if previous else 0))
            continue
        root = _member_root(path, 'custom_limbus_locale')
        suffix = path.parts[len(root.parts)+1:] if root is not None else ()
        if len(suffix) != 3 or suffix[1].casefold() != 'personalitylist':
            continue
        value = _read_json(archive, info)
        rows = value.get('dataList', value) if isinstance(value, dict) else value
        if isinstance(rows, dict):
            rows = rows.items()
        elif isinstance(rows, list):
            rows = ((str(row.get('id', '')), row) for row in rows if isinstance(row, dict))
        else:
            continue
        language = suffix[0].casefold()
        priority = 0 if language in ('cn', 'zh', 'zh-cn', 'zhs') else 1 if language == 'en' else 2
        for personality, row in rows:
            if not isinstance(row, dict):
                continue
            label = _plain_label(row.get('title')) or _plain_label(row.get('name'))
            if label:
                labels[str(root).casefold(), personality].add((priority, label))
    declarations = []
    for key, (root, appearance, character_id) in definitions.items():
        choices = sorted(labels[key])
        preferred = {label for priority, label in choices if priority == choices[0][0]}
        label = next(iter(preferred)) if len(preferred) == 1 else ''
        has_motions = (key[0], appearance.casefold().removesuffix('.prefab')) in motions
        declarations.append(Declaration(root, key[1], appearance, label, has_motions, character_id))
    return declarations


def gameplay_only_package(archive):
    """Identify rule-only Lethe packages after all supported visual readers have declined."""
    rules = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = PurePosixPath(info.filename.replace('\\', '/'))
        ext = path.suffix.casefold()
        if ext not in ('.json', '.md', '.txt'):
            return False
        root = _member_root(path, 'custom_limbus_data')
        if root is None or ext != '.json':
            continue
        kind = tuple(v.casefold() for v in path.parts[len(root.parts) + 1:-1])
        if kind == ('personality',):
            return False
        if kind in (('skill',), ('passive',), ('personality-passive',), ('ego',),
                    ('buff',), ('abnormality-unit',)):
            rules.append(info)
    for info in rules:
        document = _read_json(archive, info)
        rows = document.get('list') if isinstance(document, dict) else document
        if isinstance(rows, list) and any(isinstance(row, dict) and
                                          ('id' in row or 'personalityID' in row) for row in rows):
            return True
    return False


def select_models(declarations, published, stock_keys=(), *, loader_models=None, alternate_declarations=()):
    """Prefer the exact appearance key, then the base behind a !custom_ key."""
    by_package = defaultdict(list)
    from custom_asset_manifest import bundle_directory

    loader_models = loader_models or {}
    for path, roots in published.items():
        bundle_folder = bundle_directory(path)
        root = appearance_package_root(path)
        if path in loader_models:
            folder = bundle_folder or _member_root(path, 'installation')
            if root is None and folder is not None:
                root = str(folder.parent if bundle_folder else folder).casefold()
        if root is not None:
            for prefab in roots:
                bindings = loader_models.get(path, {}).get(prefab[:3], ())
                if bundle_folder is not None and not bindings:
                    continue
                address, _, _, layout = prefab
                names = {PurePosixPath(address.replace('\\', '/')).stem.casefold(), layout.casefold()}
                aliases = {binding.resource_id.casefold().removesuffix('.prefab') for binding in bindings
                           if binding.label == 'SD_Personality'}
                by_package[root].append((path, prefab, names, aliases))
    selected = defaultdict(list)
    stock_names = Counter(PurePosixPath(key).stem.casefold() for key in stock_keys)
    for declaration in declarations:
        candidates = by_package[str(declaration.package_root).casefold()]
        key = declaration.appearance.casefold().removesuffix('.prefab')
        base = base_appearance(key)
        matches = [(path, prefab) for path, prefab, _, aliases in candidates if key in aliases]
        if not matches:
            matches = [(path, prefab) for path, prefab, names, _ in candidates if key in names]
        if not matches and base != key:
            matches = [(path, prefab) for path, prefab, _, aliases in candidates if base in aliases]
            if not matches:
                matches = [(path, prefab) for path, prefab, names, _ in candidates if base in names]
        if not matches:
            if declaration in alternate_declarations or (base == key and stock_names[key] == 1 and not declaration.has_motions):
                continue
            raise ValueError('未找到私服人格声明的战斗外观：' + declaration.appearance)
        if len(matches) > 1:
            raise ValueError('私服人格外观匹配到多个战斗预制体：' + declaration.appearance)
        path, prefab = matches[0]
        selected[path].append((declaration, prefab))
    return selected
