"""Resolve the user's own Limbus Company install and the local, rebuildable
resource index. Nothing here reads a developer machine path or Limbus Archive;
every root can be overridden by argument, environment variable, or a small
config file written next to the workbench."""

import json
import os
import pathlib
import resource_tools
import mos_data

HERE = pathlib.Path(__file__).resolve().parents[1]
DATA = mos_data.data_dir()
TIMELINE = HERE / 'timeline_data'

CONFIG_NAME = 'resource-paths.json'
INDEX_NAME = 'resource-index.json'
STATE_NAME = 'resource-scan-state.json'
INDEX_VERSION = 1

# Container key prefix inside every bundle that carries appearance prefabs.
PREFAB_MARKER = 'Resources_moved/Prefab/'
SD_MARKER = PREFAB_MARKER + 'SD/'

ENV_GAME = 'LIMBUS_GAME_DIR'
ENV_RESOURCE = 'LIMBUS_RESOURCE_ROOT'
ENV_INDEX = 'LIMBUS_RESOURCE_INDEX'
ENV_TIMELINE = 'LIMBUS_TIMELINE_INDEX'

PROBLEMS = []

def _note(problem):
    if problem not in PROBLEMS:
        PROBLEMS.append(problem)

def problems():
    return list(PROBLEMS)

def _config_path(root=None):
    return pathlib.Path(root or DATA) / CONFIG_NAME

def read_config(root=None):
    """Config is optional; a missing or broken file must never stop a lookup."""
    path = _config_path(root)
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}
    if not isinstance(value, dict):
        _note('配置文件不是对象：%s' % path)
        return {}
    return {k: v for k, v in value.items() if isinstance(v, str) and v.strip()}

def write_config(values, root=None):
    """Persist the roots so the next start does not have to guess again."""
    path = _config_path(root)
    current = read_config(root)
    for key, value in values.items():
        if value:
            current[key] = str(pathlib.Path(value).resolve())
        else:
            current.pop(key, None)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return current


def steam_libraries():
    roots = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam'),
                          (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam')):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    for name in ('SteamPath', 'InstallPath'):
                        try:
                            roots.append(pathlib.Path(winreg.QueryValueEx(handle, name)[0]))
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    for drive in 'CDEFGH':
        for suffix in (':\\Steam', ':\\Program Files (x86)\\Steam', ':\\SteamLibrary'):
            roots.append(pathlib.Path(drive + suffix))
    seen = []
    for root in roots:
        if root.is_dir() and root not in seen:
            seen.append(root)
    libraries = list(seen)
    for root in seen:
        try:
            text = (root / 'steamapps/libraryfolders.vdf').read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        import re
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            library = pathlib.Path(match.group(1))
            if library.is_dir() and library not in libraries:
                libraries.append(library)
    return libraries


def find_game_dir():
    """Install directory that holds LimbusCompany_Data, or None."""
    for library in steam_libraries():
        for data in library.glob('steamapps/common/*/LimbusCompany_Data'):
            if (data / 'StreamingAssets/aa/catalog.bin').is_file() or (data / 'StreamingAssets').is_dir():
                return data.parent
    return None


def _addressables_base(game_dir):
    """The Addressables download cache root for this player.

    Unity names the folder '<company>_<product>' from LimbusCompany_Data/app.info,
    so the folder follows the install instead of a substring guess. The
    substring scan stays as a fallback for layouts without a readable app.info.
    """
    base = pathlib.Path(os.environ.get('USERPROFILE', '') or pathlib.Path.home()) / 'AppData/LocalLow/Unity'
    if not base.is_dir():
        return None
    if game_dir:
        try:
            lines = (pathlib.Path(game_dir) / 'LimbusCompany_Data/app.info').read_text(
                encoding='utf-8-sig').splitlines()
        except OSError:
            lines = []
        if len(lines) >= 2 and lines[0].strip() and lines[1].strip():
            exact = base / (lines[0].strip() + '_' + lines[1].strip())
            if exact.is_dir():
                return exact
    for candidate in base.iterdir():
        if candidate.is_dir() and 'Limbus' in candidate.name:
            return candidate
    return None


def find_resource_root(game_dir=None):
    """Directory that holds one folder per downloaded bundle.

    Two layouts exist on a real player machine: the Addressables download cache
    (one hashed folder per bundle, what a launched game fills) and the install's
    StreamingAssets/aa (what Steam ships). Both are accepted; the download cache
    is preferred because it is the superset after an update.
    """
    candidates = []
    cache = _addressables_base(game_dir)
    if cache:
        candidates.append(cache)
    if game_dir:
        candidates.append(pathlib.Path(game_dir) / 'LimbusCompany_Data/StreamingAssets/aa')
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def resolve_roots(game_dir=None, resource_root=None, index_dir=None, base=None):
    """All three roots plus where each one came from.

    Precedence, highest first: explicit argument, environment variable, the
    workbench config file, automatic detection. The source string is recorded so
    a report can say why a directory was chosen instead of asserting it.
    """
    config = read_config(base)
    out = {'problems': []}

    def pick(explicit, env_name, config_key, finder, label):
        if explicit:
            value, source = explicit, 'argument'
        elif os.environ.get(env_name):
            value, source = os.environ[env_name], 'env:' + env_name
        elif config.get(config_key):
            value, source = config[config_key], 'config:' + config_key
        else:
            value, source = finder(), 'auto'
        path = pathlib.Path(value).resolve() if value else None
        if value and not path.is_dir():
            out['problems'].append('%s 指向的目录不存在：%s' % (label, path))
            path = None
        out[label] = path
        out[label + '_source'] = source
        return path

    game = pick(game_dir, ENV_GAME, 'game_dir', lambda: find_game_dir(), 'game_dir')
    resource = pick(resource_root, ENV_RESOURCE, 'resource_root',
                    lambda: find_resource_root(game), 'resource_root')
    index = pick(index_dir, ENV_INDEX, 'index_dir',
                 lambda: DATA / 'resource-cache', 'index_dir')
    for label, fallback in (('index_dir', DATA / 'resource-cache'), ('timeline_dir', TIMELINE)):
        if out.get(label) is None:
            out[label] = fallback
            out[label + '_source'] = 'fallback:' + str(fallback.name)
    if index is None:
        out['index_dir'] = DATA / 'resource-cache'
    timeline = pick(None, ENV_TIMELINE, 'timeline_dir', lambda: TIMELINE, 'timeline_dir')
    if timeline is None:
        out['timeline_dir'] = TIMELINE
        out['timeline_dir_source'] = 'fallback:timeline_data'
    return out


def index_paths(index_dir):
    index_dir = pathlib.Path(index_dir)
    return index_dir / INDEX_NAME, index_dir / STATE_NAME


def bundle_files(resource_root):
    """Every '__data' file under the resource root, junctions skipped."""
    found = []
    root = pathlib.Path(resource_root)
    for current, dirs, files in os.walk(root, followlinks=False):
        keep = []
        for name in dirs:
            child = os.path.join(current, name)
            try:
                if os.stat(child, follow_symlinks=False).st_file_attributes & 0x400:
                    continue  # FILE_ATTRIBUTE_REPARSE_POINT
            except (OSError, AttributeError):
                continue
            keep.append(name)
        dirs[:] = keep
        if '__data' in files:
            candidate = pathlib.Path(current) / '__data'
            if candidate.is_file():
                found.append(candidate)
    return sorted(found)


def fingerprint(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns]


UNITY_FALLBACK = '6000.3.0f1'


def _ensure_unity_config(unity_py):
    """Bundles carry no version string, so every read needs the fallback set.

    It is applied at the read boundary because callers (a unit test, the CLI, the
    live reader) each reach this module without sharing setup.
    """
    try:
        unity_py.config.FALLBACK_UNITY_VERSION = UNITY_FALLBACK
    except AttributeError:
        pass


def _prefabs_in_bundle(path, unity_py):
    """Container keys of one bundle, reduced to SD appearance prefabs.

    A bundle we did not write must not end the scan: any failure reports an empty
    result and the caller records it as skipped.
    """
    _ensure_unity_config(unity_py)
    env = unity_py.load(str(path))
    found = {}
    for key in env.container:
        text = str(key).replace('\\', '/')
        if SD_MARKER not in text or not text.endswith('.prefab'):
            continue
        # Container keys appear both with and without an 'Assets/' prefix, so the
        # marker is located rather than assumed to be at position 0.
        name = text[text.index(SD_MARKER) + len(SD_MARKER):].rsplit('/', 1)[-1][:-len('.prefab')]
        found[name] = text
    return found


def build_index(resource_root, index_dir, full=False, unity_py=None, progress=None):
    """Scan the local bundles once and write the appearance index.

    Rebuilds are incremental on (size, mtime). Deleting the index file, or any
    single entry in it, is the supported way to force a rescan; nothing else on
    disk is required to be present.
    """
    if unity_py is None:
        unity_py = resource_tools.unity()
    _ensure_unity_config(unity_py)
    root = pathlib.Path(resource_root).resolve()
    index_dir = pathlib.Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    index_file, state_file = index_paths(index_dir)
    try:
        state = json.loads(state_file.read_text(encoding='utf-8'))
        if not isinstance(state, dict) or state.get('__version__') != INDEX_VERSION:
            state = {}
    except (OSError, ValueError):
        state = {}
    bundles = bundle_files(root)
    entries = {}
    scanned = 0
    failures = []
    for position, bundle in enumerate(bundles, 1):
        relative = bundle.relative_to(root).as_posix()
        try:
            mark = fingerprint(bundle)
        except OSError as exc:
            failures.append({'bundle': relative, 'error': str(exc)})
            continue
        cached = state.get(relative)
        if not full and isinstance(cached, dict) and cached.get('fingerprint') == mark:
            entries[relative] = cached
            if progress:
                progress(position, len(bundles), scanned)
            continue
        try:
            prefabs = _prefabs_in_bundle(bundle, unity_py)
        except Exception as exc:
            failures.append({'bundle': relative, 'error': str(exc)})
            prefabs = {}
        entries[relative] = {'fingerprint': mark, 'prefabs': prefabs}
        scanned += 1
        if progress:
            progress(position, len(bundles), scanned)
    payload = {
        '__version__': INDEX_VERSION,
        'resource_root': str(root),
        'bundles': len(bundles),
        'prefabs': sum(len(v.get('prefabs') or {}) for v in entries.values()),
        'entries': entries,
        'failures': failures[:50],
        'failure_count': len(failures),
    }
    tmp = index_file.with_name(index_file.name + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(index_file)
    state_file.write_text(json.dumps(entries, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return payload


def load_index(index_dir, resource_root=None, auto_build=True, unity_py=None):
    """Read the index; build it when missing or when the resource root changed."""
    index_file, _ = index_paths(index_dir)
    root = str(pathlib.Path(resource_root).resolve()) if resource_root else None
    payload = None
    try:
        payload = json.loads(index_file.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        payload = None
    if isinstance(payload, dict) and payload.get('__version__') == INDEX_VERSION:
        if root is None or payload.get('resource_root') == root:
            return payload, 'cached'
    if not auto_build or root is None:
        return None, 'missing'
    return build_index(resource_root, index_dir, unity_py=unity_py), 'built'


def appearance_table(index):
    """prefab name -> bundle path relative to the resource root."""
    table = {}
    for relative, entry in (index or {}).get('entries', {}).items():
        for name in (entry.get('prefabs') or {}):
            table.setdefault(name, relative)
    return table


def alias_map(index_dir=None, base=None):
    """identity / appearance-name key -> real prefab name.

    The audited snapshot in timeline_data/identity-map.json stays authoritative
    for ids whose timeline name differs from the prefab family (story_1079 ->
    1079_Sancho_BerserkAppearance). It is data, not a code path: delete it and
    the resolver still works for names that map to themselves.
    """
    root = pathlib.Path(index_dir) if index_dir else TIMELINE
    try:
        value = json.loads((root / 'identity-map.json').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items() if isinstance(v, str)}


def resolve_appearance(identity, index=None, aliases=None):
    """identity -> (prefab name, how it was resolved) or (None, reason)."""
    if not isinstance(identity, str) or not identity.strip():
        return None, '选择为空'
    key = identity.strip()
    aliases = aliases if aliases is not None else alias_map()
    if key in aliases:
        return aliases[key], 'snapshot'
    table = appearance_table(index)
    if key in table:
        return key, 'resource-index'
    for candidate in (key + 'Appearance', key + 'Appearacne'):
        if candidate in table:
            return candidate, 'resource-index'
    return None, '资源包索引里没有该外观'
