"""Read Lethe Motions appearance declarations and packaged motion data."""

from collections import defaultdict
from dataclasses import dataclass, replace
import math
from pathlib import PurePosixPath
import re
from zipfile import ZipInfo

from custom_asset_manifest import MAX_BUNDLE, MAX_MODELS, UNITY_BUNDLE_MAGIC, relative_path
from private_server_appearance import Declaration, _member_root, _read_json, read_declarations, valid_appearance_key


_PREFIX = '!motions_'
_APPEARANCE = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_. -]{0,255}')
_ACTION = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}')


@dataclass(frozen=True)
class MotionBundleRecipe:
    declaration: Declaration
    bundle: ZipInfo
    base: str
    actions: dict
    stock_override: bool = False
    extra_resources: bool = False


def _finite_number(value):
    return type(value) is int or type(value) is float and math.isfinite(value)


def _read_action(archive, info, appearance, *, action=None):
    if action is None:
        action = _read_json(archive, info)
    coins = action.get('coins') if isinstance(action, dict) else None
    if not isinstance(coins, list) or not coins:
        raise ValueError(f'动作外观 {appearance} 的动作缺少硬币列表：{info.filename}')
    for coin in coins:
        duration = coin.get('totalDuration', 0) if isinstance(coin, dict) else None
        if not _finite_number(duration):
            raise ValueError(f'动作外观 {appearance} 的总时长无效：{info.filename}')
        hits = coin.get('hitCheckers')
        if hits is None:
            continue
        if not isinstance(hits, list):
            raise ValueError(f'动作外观 {appearance} 的命中数据无效：{info.filename}')
        for hit in hits:
            time = hit.get('time', 0) if isinstance(hit, dict) else None
            if not _finite_number(time):
                raise ValueError(f'动作外观 {appearance} 的命中时点无效：{info.filename}')
    return action


def _find_published_body(archive, candidates, unity, appearance):
    from motion_bundle_model import find_body_tracks

    if sum(info.file_size for info in candidates) > MAX_MODELS:
        raise ValueError('动作外观候选资源超出读取上限：' + appearance)
    matches = []
    for info in candidates:
        if info.file_size > MAX_BUNDLE:
            raise ValueError('动作外观候选模型过大：' + info.filename)
        with archive.open(info) as stream:
            if stream.read(len(UNITY_BUNDLE_MAGIC)) != UNITY_BUNDLE_MAGIC:
                continue
        if unity is None:
            import resource_tools
            unity = resource_tools.unity()
        env = unity.load(archive.read(info))
        clips = {PurePosixPath(address.replace('\\', '/')).name.casefold() for address in env.container}
        if {'idle.playable', 's1.playable'} <= clips and {'idle', 's1'} <= find_body_tracks(env).keys():
            matches.append(info)
    if len(matches) > 1:
        raise ValueError('同一声明目录发现多个包含待机及攻击主体的动作包：' + appearance)
    return matches


def read_motion_bundle_recipes(archive, *, declarations=None, unity=None):
    """Find declared Motions appearances and stock-named authored motion overrides."""
    if declarations is None:
        declarations = read_declarations(archive)
    selected = {}
    for declaration in declarations:
        appearance = declaration.appearance
        if appearance.casefold().startswith(_PREFIX):
            folder = appearance[len(_PREFIX):]
            if not valid_appearance_key(folder):
                raise ValueError('无效的动作外观声明：' + declaration.appearance)
            marker = 'motion_appearances'
        elif valid_appearance_key(appearance) and declaration.has_motions:
            folder, marker = appearance, 'custom_motions'
        else:
            continue
        key = str(declaration.package_root).casefold(), marker, folder.casefold()
        selected.setdefault(key, []).append(declaration)
    if not selected:
        return []

    files = defaultdict(dict)
    folders = {}
    extras = set()
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = PurePosixPath(info.filename.replace('\\', '/'))
        root = _member_root(path, 'motion_appearances')
        marker = 'motion_appearances'
        if root is None:
            root = _member_root(path, 'custom_motions')
            marker = 'custom_motions'
        if root is None or len(path.parts) < len(root.parts) + 3:
            continue
        key = str(root).casefold(), marker, path.parts[len(root.parts) + 1].casefold()
        if key not in selected:
            continue
        filename = path.name.casefold()
        if len(path.parts) != len(root.parts) + 3:
            if path.suffix.casefold() in ('.png', '.bundle'):
                extras.add(key)
            continue
        if path.suffix.casefold() not in ('.json', '.bundle'):
            continue
        if marker == 'custom_motions' and path.suffix.casefold() == '.bundle' and filename != 'motion.bundle':
            extras.add(key)
        relative_path(info.filename, 2048)
        if folders.setdefault(key, path.parent) != path.parent or filename in files[key]:
            raise ValueError('动作外观目录或文件重复：' + info.filename)
        files[key][filename] = info

    results = []
    total_size = 0
    for key, shapes in selected.items():
        stock_override = key[1] == 'custom_motions'
        appearance = shapes[0].appearance if stock_override else shapes[0].appearance[len(_PREFIX):]
        entries = files[key]
        bundles = [info for name, info in entries.items() if name.endswith('.bundle')]
        if stock_override:
            # Prefer the loader's explicit body file. For alternative packaging require
            # published idle and attack sprite tracks in exactly one local bundle.
            bundles = ([entries['motion.bundle']] if 'motion.bundle' in entries
                       else _find_published_body(archive, bundles, unity, appearance))
            if not bundles:
                continue
        if len(bundles) != 1:
            raise ValueError(f'动作外观 {appearance} 必须有唯一的同目录模型包')
        bundle, = bundles
        total_size += bundle.file_size
        if not len(UNITY_BUNDLE_MAGIC) <= bundle.file_size <= MAX_BUNDLE or total_size > MAX_MODELS:
            raise ValueError(f'动作外观 {appearance} 的模型包超出读取上限')
        with archive.open(bundle) as contents:
            if contents.read(len(UNITY_BUNDLE_MAGIC)) != UNITY_BUNDLE_MAGIC:
                raise ValueError(f'动作外观 {appearance} 的模型包不是 UnityFS 文件')
        base = appearance
        if not stock_override:
            if 'appearance.json' not in entries:
                raise ValueError(f'动作外观 {appearance} 缺少 appearance.json')
            definition = _read_json(archive, entries['appearance.json'])
            base = definition.get('base') if isinstance(definition, dict) else None
            if not isinstance(base, str) or not _APPEARANCE.fullmatch(base) or base.endswith((' ', '.')):
                raise ValueError(f'动作外观 {appearance} 的基础外观无效')
        actions = {}
        for name, info in entries.items():
            if name == 'appearance.json' or not name.endswith('.json'):
                continue
            action = name[:-5]
            if not _ACTION.fullmatch(action):
                raise ValueError(f'动作外观 {appearance} 的动作名无效：{info.filename}')
            if stock_override:
                document = _read_json(archive, info)
                if not isinstance(document, dict) or 'coins' not in document:
                    if isinstance(document, dict) and (document.get('allVFX') or document.get('props')):
                        extras.add(key)
                    continue
                actions[action] = _read_action(archive, info, appearance, action=document)
            else:
                actions[action] = _read_action(archive, info, appearance)
        for declaration in shapes:
            results.append(MotionBundleRecipe(replace(declaration, has_motions=True), bundle, base, actions,
                                              stock_override, key in extras))
    return results


def contains_runtime_addon(archive):
    """Identify a package of runtime components with no recognizable appearance or bank payload."""
    has_library = False
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = PurePosixPath(info.filename.replace('\\', '/'))
        if (path.suffix.casefold() in ('.bundle', '.bank', '.carra2') or path.name == '__data'
                or _member_root(path, 'custom_limbus_data') is not None
                or _member_root(path, 'motion_appearances') is not None):
            return False
        if path.suffix.casefold() == '.dll' and info.file_size >= 2:
            with archive.open(info) as contents:
                has_library = has_library or contents.read(2) == b'MZ'
    return has_library
