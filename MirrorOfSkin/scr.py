"""FaustLauncher host for the native Sinners Random addon.

The launcher resolves the obfuscated il2cpp export names, writes them into a
shared section with a heartbeat, injects the versioned native DLL, and mirrors the
DLL status into native.log. No Frida, no bundled Python.
"""
import ctypes as C
from ctypes import wintypes as W
import json, mmap, os, pathlib, re, struct, subprocess, tempfile, threading, time, traceback, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent if '__file__' in globals() else (pathlib.Path('addons') / ADDON_ARG['AddonName']).resolve()
MANAGER = ADDON_ARG['AddonManager']; NAME = ADDON_ARG['AddonName']
STOP = threading.Event()
_NAMESPACES = ADDON_ARG.get('Namespaces')
if _NAMESPACES is None:
    raise RuntimeError('需要支持 Namespaces 的新启动器及 WarpHook')
_WARP = _NAMESPACES.space('warp')
if _WARP is None:
    raise RuntimeError('WarpHook 尚未加载，请检查插件依赖')

MAGIC = 0x3152534e
VERSION = 75
OFF_STATE = 20
OFF_HITS = 28
OFF_MESSAGE = 32 + 37 * 64
OFF_TUNABLE = OFF_MESSAGE + 256
SIZE = OFF_TUNABLE + 32
ERRORS = {0: 'ok', 1: 'il2cpp-export-missing', 2: 'assembly-or-class-missing',
          6: 'no-frame-hook'}
SESSION_NAME = 'Local\\FaustNativeSinners_v75_%d'
DLL_NAME = 'SinnersNative-v64.dll'
PID_MISS_LIMIT = 4
POOL_APPLY_TIMEOUT = 1.5
POOL_RETRY_LIMIT = 3
API_NAMES = ['domain_get', 'domain_get_assemblies', 'assembly_get_image', 'image_get_name',
             'class_from_name', 'class_get_method_from_name', 'class_get_field_from_name',
             'field_get_offset', 'object_get_class', 'class_get_parent', 'runtime_invoke',
             'object_unbox', 'thread_attach', 'thread_detach', 'class_get_type',
             'type_get_object', 'gchandle_new', 'gchandle_free', 'class_get_methods',
             'method_get_name', 'method_get_param_count', 'method_get_param',
             'type_get_name', 'free', 'class_get_name', 'image_get_class_count',
             'image_get_class', 'string_new', 'method_get_object', 'method_get_from_reflection', 'array_new', 'gc_wbarrier_set_field', 'object_new', 'method_get_return_type', 'field_get_type', 'field_get_value_object', 'class_is_valuetype']

K = C.WinDLL('kernel32', use_last_error=True)
P = C.c_void_p


def bind(name, result, *args):
    f = getattr(K, name); f.restype = result; f.argtypes = list(args); return f


bind('CreateToolhelp32Snapshot', W.HANDLE, W.DWORD, W.DWORD)
bind('CloseHandle', W.BOOL, W.HANDLE)
bind('GetTickCount', W.DWORD)


class Process(C.Structure):
    _fields_ = [('size', W.DWORD), ('usage', W.DWORD), ('pid', W.DWORD), ('heap', C.c_size_t),
                ('module', W.DWORD), ('threads', W.DWORD), ('parent', W.DWORD),
                ('priority', W.LONG), ('flags', W.DWORD), ('name', W.WCHAR * 260)]


class Module(C.Structure):
    _fields_ = [('size', W.DWORD), ('module', W.DWORD), ('pid', W.DWORD),
                ('global_usage', W.DWORD), ('usage', W.DWORD), ('base', P), ('bytes', W.DWORD),
                ('handle', W.HMODULE), ('name', W.WCHAR * 256), ('path', W.WCHAR * 260)]


for prefix, typ, suffix in [('Process32', Process, 'W'), ('Module32', Module, 'W')]:
    for action in ['First', 'Next']:
        bind(prefix + action + suffix, W.BOOL, W.HANDLE, C.POINTER(typ))


def snapshot(flag, pid, typ, prefix, tries=3):
    """Module enumeration races with a starting game: ERROR_PARTIAL_COPY (299) is
    transient, so retry instead of logging a traceback for it."""
    for attempt in range(tries):
        h = K.CreateToolhelp32Snapshot(flag, pid)
        if h == C.c_void_p(-1).value:
            error = C.get_last_error()
            if error == 299 and attempt + 1 < tries:
                time.sleep(0.05 * (attempt + 1))
                continue
            raise OSError(error, 'toolhelp snapshot failed')
        try:
            obj = typ(); obj.size = C.sizeof(obj)
            ok = getattr(K, prefix + 'FirstW')(h, C.byref(obj))
            while ok:
                yield typ.from_buffer_copy(obj)
                ok = getattr(K, prefix + 'NextW')(h, C.byref(obj))
        finally:
            K.CloseHandle(h)
        return


_snapshot = snapshot


def _load_data_module():
    import importlib.util
    path = ROOT / 'Workbench' / 'core' / 'mos_data.py'
    spec = importlib.util.spec_from_file_location('_sinners_mos_data', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_DATA_MODULE = _load_data_module()
DATA_ROOT = pathlib.Path(_DATA_MODULE.prepare(ROOT))


def log(message):
    try:
        import warphook
        warphook.log(str(message), prefix='[' + str(NAME) + ']')
    except Exception:
        pass
    with (DATA_ROOT / 'native.log').open('a', encoding='utf8') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + str(message) + '\n')


def addon_settings():
    try:
        return (MANAGER.get_addon_info(NAME) or {}).get('settings') or {}
    except Exception:
        return {}


def modules(pid):
    return {m.name.lower(): m for m in _snapshot(0x18, pid, Module, 'Module32')}


class WarpHookLoadError(RuntimeError):
    """The launcher declined the load for this game session."""


def inject(pid, mods):
    import warphook
    if DLL_NAME.lower() in mods:
        return
    ok, message = warphook.inject_dll(pid, str((ROOT / DLL_NAME).resolve()))
    if not ok:
        raise WarpHookLoadError('WarpHook 加载失败：' + str(message))
    if DLL_NAME.lower() not in modules(pid):
        raise WarpHookLoadError('WarpHook 加载后未发现目标 DLL')


def report(session, previous):
    """Mirror the DLL status into native.log whenever it changes."""
    state, error, hits = struct.unpack_from('<III', session, OFF_STATE)
    message = session[OFF_MESSAGE:OFF_MESSAGE + 256].split(b'\0')[0].decode('utf8', 'replace')
    key = (state, error, hits, message)
    if key == previous:
        return previous
    log('native hook state=%d error=%d(%s) hits=%d message=%r'
        % (state, error, ERRORS.get(error, 'unknown'), hits, message))
    return key



ROW4 = struct.Struct('<IIII d 64s 128s 64s 64s')
ROW = struct.Struct('<IIII d 64s 128s 64s 64s I 64s')
ROW3 = struct.Struct('<IIII d 64s 128s 64s')
RULESET_DIR = DATA_ROOT / '规则集'
RULESET_STATE = DATA_ROOT / '规则集状态.json'

DEFAULT_SETTINGS = {'max_cached_skins': 3, 'prewarm_full_pool': False, 'disable_special_clash': True, 'enabled': True, 'characters': {str(i): False for i in range(101, 113)}}
DEFAULT_CUSTOM_POOLS = {'schema': 1, 'characters': {}}
DEFAULT_DIRECTOR = {'schema': 1, 'characters': {}, 'forms': {}}
DEFAULT_RULESET_STATE = {'schema': 1, 'global': False, 'active': {}}


def ensure_user_config():
    try:
        RULESET_DIR.mkdir(exist_ok=True)
    except OSError:
        pass
    defaults = {'随机设置.json': DEFAULT_SETTINGS, '自定义人格池.json': DEFAULT_CUSTOM_POOLS, '演出编排.json': DEFAULT_DIRECTOR, '规则集状态.json': DEFAULT_RULESET_STATE}
    for name, data in defaults.items():
        path = DATA_ROOT / name
        if path.exists():
            continue
        temp = path.with_name(path.name + '.default.tmp')
        try:
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')
            temp.replace(path)
        except OSError:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


def load_user_json(name, default):
    path = DATA_ROOT / name
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict):
            raise ValueError('配置不是 JSON 对象')
        return data
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        log('读取用户配置失败，使用默认值: ' + name + ' (' + str(exc) + ')')
        return default


ensure_user_config()


def stopped_by_flag():
    try:
        saved = json.loads((DATA_ROOT / '随机设置.json').read_text(encoding='utf-8-sig'))
        return not bool(saved.get('enabled', True))
    except (OSError, ValueError):
        return (DATA_ROOT / '停止随机运行.flag').exists()


def prewarm_settings():
    settings = load_user_json('随机设置.json', DEFAULT_SETTINGS)
    try:
        skins = int(settings.get('max_cached_skins', 3))
    except (TypeError, ValueError):
        skins = 3
    skins = max(2, min(256, skins))
    mode = 1 if settings.get('prewarm_full_pool', False) else 0
    clash = 1 if settings.get('disable_special_clash', True) else 2
    return mode, skins, clash

def _json_file(path, default=None):
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        return data if isinstance(data, dict) else default
    except (OSError, ValueError):
        return default


def ruleset_state():
    data = _json_file(RULESET_STATE, DEFAULT_RULESET_STATE) or DEFAULT_RULESET_STATE
    active = data.get('active') if isinstance(data.get('active'), dict) else {}
    return {'schema': 1, 'global': bool(data.get('global')), 'active': {str(k): str(v) for k, v in active.items()}}


def _identity_ruleset_path(identity):
    return RULESET_DIR / ('人格-%s.json' % identity)


def _identity_ruleset(identity):
    data = _json_file(_identity_ruleset_path(identity))
    if not data or data.get('scope') != 'identity' or str(data.get('identity')) != str(identity):
        return None
    return data


def _global_ruleset():
    data = _json_file(RULESET_DIR / '全局.json')
    if not data or data.get('scope') != 'global':
        return None
    if not isinstance(data.get('entries'), list) and not isinstance(data.get('pools'), dict):
        return None
    return data


def _catalog_by_identity(pools):
    catalog = {}
    for pool in pools.values():
        for entry in pool.get('entries', []):
            identity = str(entry.get('identity_id', ''))
            if identity:
                catalog.setdefault(identity, entry)
    return catalog


def _resolve_rows(items, base, catalog, include_zero=False):
    import math
    for item in items or []:
        if not isinstance(item, dict):
            continue
        try:
            weight = float(item.get('weight', 1))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(weight) or weight < 0 or weight > 1000000:
            continue
        if weight <= 0 and not include_zero:
            continue
        kind = item.get('entry_kind', 'appearance')
        if kind != 'appearance':
            continue
        identity = str(item.get('identity_id', ''))
        source = catalog.get(identity)
        if not source:
            continue
        yield dict(source, weight=weight, entry_kind=kind, group_id='', base_identity=base)


def _pool_row_key(sinner, row):
    return (int(sinner), str(row.get('base_identity', '')), str(row.get('identity_id', '')),
            str(row.get('entry_kind', 'appearance')), str(row.get('group_id', '')))


def _rule_paths():
    return _pool_evidence.config_paths(DATA_ROOT)


def _config_digest():
    return _pool_evidence.config_digest(DATA_ROOT)


def _old_pool_rows():
    path = DATA_ROOT / 'native_pools.bin'
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    if len(raw) < 16:
        return []
    magic, version, count, size = struct.unpack_from('<4sIII', raw, 0)
    if magic not in (b'SRP4', b'SRP5') or count > 4096:
        return []
    if magic == b'SRP5' and version == 5 and size == ROW.size:
        fmt, has_base = ROW, True
    elif magic == b'SRP4' and version == 4 and size == ROW4.size:
        fmt, has_base = ROW4, True
    elif magic == b'SRP4' and version == 3 and size == ROW3.size:
        fmt, has_base = ROW3, False
    else:
        return []
    if len(raw) < 16 + count * fmt.size:
        return []
    rows = []
    for index in range(count):
        fields = fmt.unpack_from(raw, 16 + index * fmt.size)
        sinner, enabled, excluded, story, weight, identity, asset, look = fields[:8]
        base = fields[8] if has_base else b''
        rows.append({
            'sinner': sinner,
            'identity_id': identity.split(b'\0')[0].decode('utf-8', 'replace'),
            'asset_key': asset.split(b'\0')[0].decode('utf-8', 'replace'),
            'appearance_name': look.split(b'\0')[0].decode('utf-8', 'replace'),
            'base_identity': base.split(b'\0')[0].decode('utf-8', 'replace'),
            'entry_kind': 'group' if fmt is ROW and fields[9] == 1 else 'appearance',
            'group_id': fields[10].split(b'\0')[0].decode('ascii') if fmt is ROW else '',
            'weight': 0,
            '_mask': excluded,
            '_story': bool(story),
        })
    return rows


def _pool_workbench_module(name):
    import importlib.util
    base = ROOT / 'Workbench'
    path = next((base / folder / (name + '.py') for folder in ('core','pool','scan','fx','tools') if (base / folder / (name + '.py')).is_file()), None)
    if path is None:
        path = next((p for p in base.rglob(name + '.py') if p.is_file()), base / (name + '.py'))
    spec = importlib.util.spec_from_file_location('_sinners_pool_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_pool_evidence = _pool_workbench_module('prepare_view')

def prepare_native_pools():
    lock = getattr(prepare_native_pools, 'lock', None)
    if lock is None:
        lock = _pool_workbench_module('file_lock').FileLock(DATA_ROOT / 'workbench-save.lock')
        prepare_native_pools.stage_files = _pool_workbench_module('stage_files')
        prepare_native_pools.lock = lock
    with lock:
        if not getattr(prepare_native_pools, 'story_ready', False):
            _pool_workbench_module('chapter_nine').migrate(DATA_ROOT, prepare_native_pools.stage_files)
            _pool_workbench_module('story_defaults').restore(ROOT)
            try:
                _pool_workbench_module('voice_binding').reconcile_locked(DATA_ROOT, _pool_workbench_module('bank_evidence'))
            except (OSError, ValueError, KeyError) as error:
                log('Voice binding refresh failed: '+str(error))
            prepare_native_pools.story_ready = True
        source_stamp = probability_stamp()
        rows = _prepare_native_pools_unlocked()
        prepare_native_pools.config_revision = _config_digest()
        prepare_native_pools.source_stamp = source_stamp
        return rows


def _prepare_native_pools_unlocked():
    import math
    pools = json.loads((DATA_ROOT / 'Assets/runtime/all_sinners_pools.json').read_text(encoding='utf-8-sig'))
    catalog = _catalog_by_identity(pools)
    custom = load_user_json('自定义人格池.json', DEFAULT_CUSTOM_POOLS)
    state = ruleset_state()
    settings = load_user_json('随机设置.json', DEFAULT_SETTINGS)

    known = {}

    def add(sinner, row):
        key = _pool_row_key(sinner, row)
        if key[2] and key not in known:
            known[key] = dict(row, sinner=int(sinner), weight=0)

    def add_profile(sinner, profile, base=''):
        if isinstance(profile, dict):
            for row in _resolve_rows(profile.get('entries', []), base, catalog, include_zero=True):
                add(sinner, row)

    def default_entries(sinner):
        # Mirrors Workbench/rulesets._default_entries. Used only as a safety net:
        # a cleared or damaged active rule set must not leave the unit with zero
        # candidates, which would silently disable every appearance for the game.
        result = []
        for entry in pools.get(str(sinner), {}).get('entries', []):
            identity = str(entry.get('identity_id', ''))
            if not identity.isdigit() or len(identity) != 5 or identity[:3] != str(sinner):
                continue
            if entry.get('story_metadata') or entry.get('category') == 'humanoid_boss':
                continue
            try:
                weight = float(entry.get('weight', 1))
            except (TypeError, ValueError):
                continue
            if weight > 0:
                result.append({'identity_id': identity, 'weight': weight})
        return result[:256]

    # Keep every catalog identity at zero weight so changing rule sets never
    # has to remove native rows (the hot reload path requires old rows).
    for sinner, pool in pools.items():
        for entry in pool.get('entries', []):
            add(sinner, dict(entry, base_identity=''))

    for target, profile in (custom.get('characters') or {}).items():
        add_profile(target, profile)

    global_rule = _global_ruleset()
    if global_rule:
        if isinstance(global_rule.get('entries'), list):
            for sinner in range(101, 113):
                for row in _resolve_rows(global_rule['entries'], '', catalog, include_zero=True):
                    add(str(sinner), row)
        else:
            for target, profile in global_rule.get('pools', {}).items():
                if str(target) in pools:
                    add_profile(target, profile)

    if RULESET_DIR.exists():
        for path in sorted(RULESET_DIR.glob('人格-*.json')):
            data = _json_file(path)
            if not data or data.get('scope') != 'identity':
                continue
            identity = str(data.get('identity', ''))
            sinner = str(data.get('sinner', ''))
            if sinner not in pools or identity not in catalog:
                continue
            add_profile(sinner, data, identity)

    # Stage transitions may request a different prefab owned by another catalog pool.
    for group in prepare_native_pools.stage_files.automatic_groups(DATA_ROOT):
        sinner = group['id'][4:7]
        for stage in group['stages']:
            source = catalog.get(stage['identity_id'])
            if source:
                add(sinner, dict(source, base_identity=''))

    for row in _old_pool_rows():
        sinner = str(row.get('sinner', ''))
        if sinner in pools:
            # Keep previous appearance and group rows. Native hot reload indexes
            # old rows synchronously, so dropping any of them makes it reject
            # the whole snapshot and leave the last weights active.
            add(sinner, row)

    active_rows = {}
    for sinner in range(101, 113):
        key = str(sinner)
        base = ''
        source = ''
        entries = []
        if state['global']:
            source = 'global'
            if global_rule and isinstance(global_rule.get('entries'), list):
                entries = global_rule['entries']
            elif global_rule and isinstance(global_rule.get('pools'), dict):
                profile = global_rule['pools'].get(key)
                if isinstance(profile, dict):
                    entries = profile.get('entries', [])
        else:
            active = state['active'].get(key, 'none')
            if active == 'sinner':
                source = 'sinner:' + key
                profile = (custom.get('characters') or {}).get(key)
                entries = profile.get('entries', []) if isinstance(profile, dict) else pools[key].get('entries', [])
            elif active.startswith('identity:'):
                base = active.split(':', 1)[1]
                source = active
                rule = _identity_ruleset(base)
                if rule and str(rule.get('sinner')) == key:
                    entries = rule.get('entries', [])
        if not source:
            continue
        resolved = False
        for row in _resolve_rows(entries, base, catalog):
            row['sinner'] = sinner
            row_key = _pool_row_key(sinner, row)
            active_rows.setdefault(row_key, row)
            known.pop(row_key, None)
            resolved = True
        if resolved:
            continue
        fallback = default_entries(sinner)
        if not fallback:
            log('Active ruleset %s for sinner=%s resolved 0 rows and no default candidates exist; native pool will be empty for this unit' % (source, key))
            continue
        log('Active ruleset %s for sinner=%s resolved 0 rows; falling back to %s default candidates' % (source, key, len(fallback)))
        for row in _resolve_rows(fallback, base, catalog):
            row['sinner'] = sinner
            row_key = _pool_row_key(sinner, row)
            active_rows.setdefault(row_key, row)
            known.pop(row_key, None)

    # The first eligible occurrence wins; inactive rows follow in catalog order.
    rows = [*active_rows.values(), *known.values()]
    if len(rows) > 4096:
        raise ValueError('Too many identities')

    actions = {'evade': 1, 'attack': 2, 'attack-preparation': 4, 'clash': 8, 'clash-preparation': 16}
    packed = []
    for row in rows:
        sinner = int(row['sinner'])
        if sinner < 101 or sinner > 112:
            raise ValueError('Invalid sinner')
        identity = str(row['identity_id'])
        raw = identity.encode('ascii')
        source = catalog.get(identity)
        asset_key = source['asset_key'] if source and source.get('appearance_name') == row['appearance_name'] else row['asset_key']
        asset = str(asset_key).encode('ascii')
        look = str(row['appearance_name']).encode('ascii')
        weight = float(row.get('weight', 0))
        if not math.isfinite(weight) or weight < 0 or weight > 1000000:
            raise ValueError('Invalid weight')
        if not raw or len(raw) >= 64:
            raise ValueError('Invalid identity')
        if not asset or len(asset) >= 128:
            raise ValueError('Invalid asset key')
        if not look or len(look) >= 64:
            raise ValueError('Invalid appearance name')
        base = str(row.get('base_identity', '')).encode('ascii')
        if len(base) >= 64:
            raise ValueError('Invalid base identity')
        kind = row.get('entry_kind', 'appearance')
        gid = str(row.get('group_id', '')).encode('ascii')
        if kind not in ('appearance', 'group') or (kind == 'appearance' and gid) or (kind == 'group' and (not gid or len(gid) >= 64)): raise ValueError('Invalid group entry')
        excluded = row.get('excluded_actions', [])
        if any(x not in actions for x in excluded):
            raise ValueError('Unknown excluded action')
        if '_mask' in row:
            mask = int(row['_mask'])
        else:
            mask = sum(actions[x] for x in set(excluded))
        if row.get('auto_discovered') and not row.get('no_attack'):
            mask |= 0x80000000
        if row.get('no_attack'):
            mask |= 0x40000000
        imported = identity.startswith('story_WBImp_') or identity == 'story_BRolandBaseAppearance'
        story = 0 if imported else (1 if row.get('_story') or row.get('story_metadata') or row.get('no_attack') else 0)
        enabled = 1 if weight > 0 and settings.get('enabled', True) else 0
        packed.append(ROW.pack(sinner, enabled, mask, story, weight, raw, asset, look, base, int(kind == 'group'), gid))

    candidate = next((row for row in active_rows.values() if not row.get('story_metadata') and not row.get('no_attack')), None)
    if candidate:
        (DATA_ROOT / 'probe_asset.txt').write_text(str(candidate['asset_key']), encoding='utf8')

    form_data = {'version': 1, 'policy': 'donor follows current unit sanity/state', 'identities': {}}
    for sinner, pool in pools.items():
        for entry in pool.get('entries', []):
            forms = entry.get('forms') or [entry['appearance_name']]
            if len(forms) > 1:
                form_data['identities'][str(entry['identity_id'])] = {
                    'sinner': int(sinner),
                    'asset_key': entry['asset_key'],
                    'base': entry['appearance_name'],
                    'forms': forms,
                }
    form_path = DATA_ROOT / 'native_forms.json'
    form_temp = form_path.with_suffix('.tmp')
    form_temp.write_text(json.dumps(form_data, ensure_ascii=False, indent=2), encoding='utf8')
    form_temp.replace(form_path)

    dest = DATA_ROOT / 'native_pools.bin'
    temp = dest.with_suffix('.tmp')
    temp.write_bytes(struct.pack('<4sIII', b'SRP5', 5, len(packed), ROW.size) + b''.join(packed))
    temp.replace(dest)
    return len(packed)


def probability_stamp():
    rows = []
    for path in _rule_paths():
        try:
            info = path.stat()
        except FileNotFoundError:
            rows.append((path, None, None))
        else:
            rows.append((path, info.st_mtime_ns, info.st_size))
    return tuple(rows)


def _delay_ready(detected_at, now):
    return detected_at is not None and now - detected_at >= 30.0

def _confirmed_pid(found, current, misses):
    """Require several consecutive misses before declaring the game gone."""
    if not found and current is not None:
        misses += 1
        if misses < PID_MISS_LIMIT:
            return current, misses
        return None, misses
    return found, 0


def prepare_fx_for_injection(root, game_dir, logger, cancelled=None):
    import importlib.util
    active = DATA_ROOT / 'fx-active.bin'
    active.unlink(missing_ok=True)
    try:
        base = pathlib.Path(root) / 'Workbench'
        path = base / 'fx/fx_handoff.py'
        if not path.is_file():
            path = next((p for p in base.rglob('fx_handoff.py') if p.is_file()), base / 'fx_handoff.py')
        spec = importlib.util.spec_from_file_location('_sinners_fx_handoff', path)
        handoff = importlib.util.module_from_spec(spec); spec.loader.exec_module(handoff)
        handoff.prepare(root, game_dir, logger, cancelled=cancelled)
    except Exception as exc:
        active.unlink(missing_ok=True)
        logger('特效未启用：' + str(exc))

def inject_if_running(stop, injector, pid, mods):
    if stop.is_set():raise RuntimeError('插件已停止，取消加载原生模块')
    return injector(pid, mods)

def worker():
    session = None
    load_guard = None
    discovery = None
    current = None
    detected_at = None
    attempted = None
    previous = None
    last_error = None
    pool_stamp = None
    revision = 0
    published_config = None
    published_at = None
    publish_retries = 0
    applied_warned = False
    pid_misses = 0
    try:
        while not STOP.wait(.5):
            try:
                import warphook
                pid, pid_misses = _confirmed_pid(warphook.find_game_pid(), current, pid_misses)
                if pid != current:
                    _workbench_game_changed(pid)
                    if session:
                        log('game process ended, closing shared section')
                        session.close()
                    if load_guard:
                        compat.release_process(load_guard); load_guard = None
                    session = None; discovery = None; current = pid; attempted = None; previous = None
                    detected_at = time.monotonic() if pid else None
                    if pid:
                        log("检测到游戏进程，等待 30 秒后加载随机人格")
                    else:
                        log("未检测到游戏进程，等待游戏启动")
                if not pid:
                    continue
                if session is not None and getattr(session, 'closed', False):
                    log('shared section closed; rebuilding injection link')
                    session = None; attempted = None; pid_misses = 0
                    continue
                if session:
                    if attempted != pid:
                        raise RuntimeError("Incomplete injection session")
                    desired = int(not stopped_by_flag())
                    # Publish the two aligned DWORDs independently. Repacking the
                    # live header can briefly clear enabled during a linked coin.
                    try:
                        C.c_uint32.from_buffer(session, 16).value = K.GetTickCount()
                        flag = C.c_uint32.from_buffer(session, 12)
                        if flag.value != desired:
                            flag.value = desired
                        del flag
                    except (ValueError, OSError):
                        log('shared section lost; rebuilding injection link')
                        try:
                            session.close()
                        except (ValueError, OSError):
                            pass
                        session = None; attempted = None; pid_misses = 0
                        continue
                    if discovery:
                        discovery.poll()
                    stamp = probability_stamp()
                    if stamp != pool_stamp:
                        # Publish the revision only after a complete atomic snapshot.
                        import hashlib
                        rows = prepare_native_pools()
                        published_config = prepare_native_pools.config_revision
                        revision = (revision + 1) & 0xffffffff or 1
                        mode, skins, clash = prewarm_settings()
                        struct.pack_into('<II', session, OFF_TUNABLE, mode, skins)
                        struct.pack_into('<I', session, OFF_TUNABLE + 20, clash)
                        struct.pack_into('<I', session, OFF_TUNABLE + 8, revision)
                        pool_stamp = prepare_native_pools.source_stamp
                        published_at = time.monotonic()
                        publish_retries = 0
                        applied_warned = False
                        log('Probability update published revision=%d rows=%d' % (revision, rows))
                    applied = struct.unpack_from('<I', session, OFF_TUNABLE + 12)[0]
                    now = time.monotonic()
                    if revision and applied != revision:
                        if published_at is None:
                            published_at = now
                        if now - published_at >= POOL_APPLY_TIMEOUT and publish_retries < POOL_RETRY_LIMIT:
                            previous_revision = revision
                            revision = (revision + 1) & 0xffffffff or 1
                            struct.pack_into('<I', session, OFF_TUNABLE + 8, revision)
                            publish_retries += 1
                            published_at = now
                            log('Native did not confirm revision=%d; republishing revision=%d'
                                % (previous_revision, revision))
                        elif now - published_at >= 5 and not applied_warned:
                            log('Native still reports applied=%d for revision=%d; keeping last valid pool'
                                % (applied, revision))
                            applied_warned = True
                    else:
                        published_at = None
                        publish_retries = 0
                        applied_warned = False
                    pool_status = {'pid':pid,'published':revision,'applied':applied, 'config_revision':published_config}
                    if pool_status != getattr(worker, 'pool_status', None):
                        tmp = DATA_ROOT / 'pool_update_status.tmp'
                        tmp.write_text(json.dumps(pool_status), encoding='utf8')
                        tmp.replace(DATA_ROOT / 'pool_update_status.json')
                        worker.pool_status = pool_status
                    previous = report(session, previous)
                    continue
                if attempted == pid:
                    continue
                if not _delay_ready(detected_at, time.monotonic()):
                    continue
                mods = modules(pid)
                if 'gameassembly.dll' not in mods:
                    continue
                # Import by absolute addon path; launcher does not have to add it
                # to sys.path, and another addon's module cannot shadow this one.
                import importlib.util
                spec = importlib.util.spec_from_file_location('_sinners_release_compat', ROOT / 'release_compatibility.py')
                compat = importlib.util.module_from_spec(spec); spec.loader.exec_module(compat)
                try:
                    load_guard = compat.claim_process(pid)
                    compat.validate(ROOT, pathlib.Path(mods['gameassembly.dll'].path).parent, mods, DLL_NAME, allow_existing=any(name.lower().startswith('sinnersnative') and name.lower().endswith('.dll') for name in mods))
                except compat.CompatibilityError as exc:
                    if load_guard:
                        compat.release_process(load_guard); load_guard = None
                    attempted = pid
                    log('安全停止：' + str(exc))
                    continue
                # WarpHook owns the export mapping cache and its refresh policy.
                import warphook
                result = {'mapping': warphook.resolve_exports()}
                result['ok'] = bool(result['mapping'])
                if not result.get('ok'):
                    raise RuntimeError(result.get('reason', 'il2cpp API mapping failed'))
                try:
                    compat.validate_aliases(result, API_NAMES)
                except compat.CompatibilityError as exc:
                    if load_guard:
                        compat.release_process(load_guard); load_guard = None
                    attempted = pid
                    log('安全停止：' + str(exc))
                    continue
                existing = any(name.lower().startswith('sinnersnative') and name.lower().endswith('.dll') for name in mods)
                if existing:
                    # Plugin reloads while a game is already running must adopt
                    # the existing native session instead of injecting a second
                    # module. The old Python host is gone, but the DLL still
                    # owns this named section.
                    try:
                        session = mmap.mmap(-1, SIZE, tagname=SESSION_NAME % pid, access=mmap.ACCESS_WRITE)
                        magic, version, size = struct.unpack_from('<III', session, 0)
                        if magic != MAGIC or version != VERSION or size != SIZE:
                            raise RuntimeError('existing native section has a different protocol')
                    except Exception as exc:
                        if session is not None:
                            try: session.close()
                            except Exception: pass
                        session = None; attempted = pid
                        log('游戏内已有随机人格Native模块，但无法接管共享内存；请完整退出游戏后重启')
                        continue
                    nonce = struct.unpack_from('<I', session, OFF_TUNABLE + 16)[0] or 1
                    mode, skins, clash = prewarm_settings()
                    struct.pack_into('<II', session, OFF_TUNABLE, mode, skins)
                    struct.pack_into('<I', session, OFF_TUNABLE + 20, clash)
                    C.c_uint32.from_buffer(session, 16).value = K.GetTickCount()
                    C.c_uint32.from_buffer(session, 12).value = 0 if stopped_by_flag() else 1
                    spec = importlib.util.spec_from_file_location('_sinners_auto_discovery', ROOT / 'auto_discovery.py')
                    auto_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(auto_module)
                    discovery = auto_module.Discovery(DATA_ROOT, pathlib.Path(mods['gameassembly.dll'].path).parent, pid, nonce, log, VERSION)
                    log('Native pool snapshot rows='+str(prepare_native_pools()))
                    pool_stamp = prepare_native_pools.source_stamp
                    published_config = prepare_native_pools.config_revision
                    previous_revision = struct.unpack_from('<I', session, OFF_TUNABLE + 8)[0]
                    revision = (previous_revision + 1) & 0xffffffff or 1
                    struct.pack_into('<I', session, OFF_TUNABLE + 8, revision)
                    published_at = time.monotonic(); publish_retries = 0; applied_warned = False
                    attempted = pid
                    log('Attached existing native session in %d; republished revision=%d' % (pid, revision))
                    previous = report(session, None)
                    continue
                session = mmap.mmap(-1, SIZE,
                                    tagname=SESSION_NAME % pid,
                                    access=mmap.ACCESS_WRITE)
                session[:] = b'\0' * SIZE
                struct.pack_into('<5I', session, 0, MAGIC, VERSION, SIZE, 0 if stopped_by_flag() else 1, K.GetTickCount())
                mode, skins, clash = prewarm_settings()
                struct.pack_into('<II', session, OFF_TUNABLE, mode, skins)
                struct.pack_into('<I', session, OFF_TUNABLE + 20, clash)
                import secrets
                nonce = secrets.randbits(32) or 1
                struct.pack_into('<I', session, OFF_TUNABLE + 16, nonce)
                spec = importlib.util.spec_from_file_location('_sinners_auto_discovery', ROOT / 'auto_discovery.py')
                auto_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(auto_module)
                discovery = auto_module.Discovery(DATA_ROOT, pathlib.Path(mods['gameassembly.dll'].path).parent, pid, nonce, log, VERSION)
                for index, name in enumerate(API_NAMES):
                    alias = result['mapping'].get('il2cpp_' + name, 'il2cpp_' + name).encode('ascii')
                    if len(alias) >= 64:
                        raise RuntimeError('Invalid export alias')
                    session[32 + index * 64:32 + (index + 1) * 64] = alias.ljust(64, b'\0')
                log("Native pool snapshot rows="+str(prepare_native_pools()))
                prepare_fx_for_injection(ROOT, pathlib.Path(mods['gameassembly.dll'].path).parent, log, STOP.is_set)
                pool_stamp = prepare_native_pools.source_stamp
                published_config = prepare_native_pools.config_revision
                revision = 0
                published_at = None
                publish_retries = 0
                applied_warned = False
                inject_if_running(STOP, inject, pid, mods)
                attempted = pid
                log(f'Native DLL loaded in {pid}')
                previous = report(session, None)
            except Exception as exc:
                if load_guard and attempted != pid:
                    compat.release_process(load_guard); load_guard = None
                if session is not None and attempted != pid:
                    session.close(); session = None
                if isinstance(exc, WarpHookLoadError):
                    attempted = pid
                    log(str(exc) + '。本次游戏已停止加载，请检查 WarpHook 后重新启动游戏。')
                    continue
                if isinstance(exc, OSError) and (getattr(exc, 'winerror', None) == 5 or exc.errno == 5):
                    message = ('游戏进程访问被拒绝（错误 5），原生插件尚未加载。'
                               '请关闭游戏和启动器，以管理员身份运行 FaustLauncher.exe 后重新启动游戏。'
                               '当前会继续等待重试；无需修改概率或重新安装 DLL。')
                else:
                    message = traceback.format_exc()
                if message != last_error:
                    log(message)
                    last_error = message
                STOP.wait(2)
    finally:
        if session:
            struct.pack_into('<I', session, 12, 0)
            session.close()
        if load_guard:
            compat.release_process(load_guard)



# Reloads share one lock because FaustLauncher keeps the same host PID.
_PANEL_LOCK = getattr(MANAGER, '_sinners_panel_lock', None)
if _PANEL_LOCK is None:
    _PANEL_LOCK = threading.RLock()
    MANAGER._sinners_panel_lock = _PANEL_LOCK
_GAME_STATE = (0, None)
_PANEL_EPOCH = 0
_WORKBENCH_URL = None
_WORKBENCH_WINDOW = None
_WEBVIEW_HOOKED = False
_WEEKLY_STOP = threading.Event()
_weekly = None
_weekly_thread = None
_URL_PATTERN = r'http://127\.0\.0\.1:\d{1,5}/[A-Za-z0-9_-]+/'


def _panel_request(url, route, **payload):
    if not url or not re.fullmatch(_URL_PATTERN, url):
        return {}
    request = urllib.request.Request(url + 'api/' + route)
    if payload:
        request.data = json.dumps(payload).encode('utf8')
        request.add_header('Content-Type', 'application/json')
        request.add_header('X-Workbench', url.rstrip('/').rsplit('/', 1)[-1])
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.load(response)
    except (OSError, ValueError):
        return {}


def _release_workbench():
    global _WORKBENCH_URL
    if _WORKBENCH_URL:
        _panel_request(_WORKBENCH_URL, 'instance-release', host_pid=os.getpid())
        _WORKBENCH_URL = None
        if _WORKBENCH_WINDOW is not None:
            try:
                _WORKBENCH_WINDOW.hide()
            except Exception:
                pass


def _sync_panel():
    with _PANEL_LOCK:
        if STOP.is_set() or not _WORKBENCH_URL:
            return
        epoch, pid = _GAME_STATE
        if epoch != _PANEL_EPOCH:
            _release_workbench()
        elif pid:
            reply = _panel_request(_WORKBENCH_URL, 'instance-attach', host_pid=os.getpid(), game_pid=pid)
            if not reply.get('attached'):
                _release_workbench()


def _start_weekly():
    global _weekly_thread, _WEEKLY_STOP
    if _weekly is None or STOP.is_set():
        return
    _WEEKLY_STOP = threading.Event()
    _weekly_thread = threading.Thread(target=_weekly.loop, args=(ROOT, _WEEKLY_STOP, log),
                                      name='SinnersWeeklyDiscovery', daemon=True)
    _weekly_thread.start()


def _workbench_game_changed(pid):
    global _GAME_STATE
    epoch, previous = _GAME_STATE
    _GAME_STATE = (epoch + int(bool(previous)), pid)
    if previous:
        _WEEKLY_STOP.set()
    if pid and _WEEKLY_STOP.is_set():
        _start_weekly()
    threading.Thread(target=_sync_panel, name='SinnersPanelSession', daemon=True).start()


def on_unload(*unused):
    STOP.set()
    with _PANEL_LOCK:
        if getattr(MANAGER, '_sinners_panel_owner', None) is not STOP:
            return
        _release_workbench()
        item = getattr(MANAGER, '_sinners_warp_workers', {}).get(NAME)
        if item and item[0] is STOP and item[1] is not threading.current_thread():
            item[1].join(timeout=2)
        _WEEKLY_STOP.set()
        if _weekly_thread is not None:
            _weekly_thread.join(timeout=3)
        try:
            _DATA_MODULE.remove_legacy_links(ROOT)
        except Exception:
            pass


disabled = deleted = on_unload


def _wrapper_args():
    return ['powershell.exe', '-NoProfile', '-STA', '-WindowStyle', 'Hidden',
            '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'Workbench/ui/open_workbench.ps1')]


def _start_workbench_server(game_pid):
    args = _wrapper_args() + ['-ServerOnly', '-HostProcessId', str(os.getpid())]
    if game_pid:
        args.extend(['-GameProcessId', str(game_pid)])
    try:
        # A private output file keeps cancellation independent of inherited pipes.
        deadline = time.monotonic() + 45
        with tempfile.TemporaryFile() as output:
            wrapper = subprocess.Popen(args, cwd=str(ROOT), stdout=output, stderr=subprocess.STDOUT,
                                       env=dict(os.environ, FAUST_MOS_DATA_ROOT=str(DATA_ROOT)),
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            while wrapper.poll() is None:
                if STOP.is_set() or _GAME_STATE[0] != _PANEL_EPOCH or time.monotonic() >= deadline:
                    wrapper.terminate()
                    wrapper.wait(timeout=2)
                    break
                STOP.wait(.15)
            output.seek(0)
            message = output.read().decode('utf8', 'replace')
        match = re.search(_URL_PATTERN, message)
        if wrapper.returncode == 0 and match:
            return match.group(0)
        if not STOP.is_set():
            log('workbench server start produced no URL: ' + message[:300])
    except (OSError, subprocess.TimeoutExpired):
        log('workbench server start failed: ' + traceback.format_exc())
    # A wrapper may exit after binding the host but before printing its URL.
    try:
        state = json.loads((DATA_ROOT / 'workbench-instance.json').read_text(encoding='utf-8-sig'))
        _panel_request(state.get('url'), 'instance-release', host_pid=os.getpid())
    except (OSError, ValueError):
        pass
    return None


def _reload_workbench_window(window):
    if not _WORKBENCH_URL or window is None:
        return
    try:
        window.load_url(_WORKBENCH_URL)
        return
    except Exception:
        pass
    try:
        import json
        window.evaluate_js('location.replace(' + json.dumps(_WORKBENCH_URL) + ')')
    except Exception:
        pass


def _show_workbench_window():
    global _WORKBENCH_WINDOW
    try:
        import webview
    except Exception:
        return False
    if _WORKBENCH_WINDOW is None:
        for window in list(getattr(webview, 'windows', []) or []):
            try:
                if getattr(window, 'title', '') == '镜像幻化':
                    _WORKBENCH_WINDOW = window
                    break
            except Exception:
                continue
    if _WORKBENCH_WINDOW is None:
        return False
    try:
        _WORKBENCH_WINDOW.show()
        try:
            _WORKBENCH_WINDOW.restore()
        except Exception:
            pass
        _reload_workbench_window(_WORKBENCH_WINDOW)
        return True
    except Exception:
        return False


def _workbench_window_bounds():
    screen_w = screen_h = 0
    screen_x = screen_y = 0
    try:
        import webview
        screens = list(getattr(webview, 'screens', []) or [])
        if screens:
            screen = screens[0]
            screen_w, screen_h = int(screen.width), int(screen.height)
            screen_x, screen_y = int(getattr(screen, 'x', 0)), int(getattr(screen, 'y', 0))
    except Exception:
        pass
    if screen_w <= 0 or screen_h <= 0:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            screen_w = int(user32.GetSystemMetrics(0) or 0)
            screen_h = int(user32.GetSystemMetrics(1) or 0)
        except Exception:
            screen_w = screen_h = 0
    if screen_w <= 0 or screen_h <= 0:
        screen_w, screen_h = 1536, 864
    width = max(1100, min(1400, int(screen_w * 0.82)))
    height = max(760, min(1200, screen_h - 40))
    x = screen_x + max(0, (screen_w - width) // 2)
    y = screen_y + max(0, (screen_h - height) // 2)
    return width, height, x, y


def _install_workbench_webview():
    global _WEBVIEW_HOOKED
    if _WEBVIEW_HOOKED:
        return True
    try:
        import webview
    except Exception:
        log('pywebview unavailable; workbench falls back to launcher window')
        return False
    original = getattr(webview, 'start', None)
    if not callable(original):
        return False
    original = getattr(original, '_mos_workbench_original', original)

    def start(*args, **kwargs):
        global _WORKBENCH_WINDOW
        try:
            if _WORKBENCH_URL and not STOP.is_set():
                existing = None
                for window in list(getattr(webview, 'windows', []) or []):
                    try:
                        if getattr(window, 'title', '') == '镜像幻化':
                            existing = window
                            break
                    except Exception:
                        continue
                if existing is not None:
                    _WORKBENCH_WINDOW = existing
                    try:
                        existing.show()
                    except Exception:
                        pass
                    _reload_workbench_window(existing)
                else:
                    width, height, x, y = _workbench_window_bounds()
                    _WORKBENCH_WINDOW = webview.create_window(
                        '镜像幻化', _WORKBENCH_URL, width=width, height=height,
                        x=x, y=y, min_size=(1000, 650),
                        background_color='#17191d', text_select=True,
                    )
                    try:
                        def _closing(window=_WORKBENCH_WINDOW):
                            try:
                                window.hide()
                            except Exception:
                                pass
                            return False
                        _WORKBENCH_WINDOW.events.closing += _closing
                    except Exception:
                        pass
                    log('workbench pywebview window registered')
        except Exception:
            log('workbench pywebview window failed: ' + traceback.format_exc())
        return original(*args, **kwargs)

    start._mos_workbench_original = original
    webview.start = start
    _WEBVIEW_HOOKED = True
    return True


def _fallback_open_workbench():
    subprocess.Popen(_wrapper_args() + ['-ExistingUrl', _WORKBENCH_URL], cwd=str(ROOT),
                     env=dict(os.environ, FAUST_MOS_DATA_ROOT=str(DATA_ROOT)),
                     creationflags=subprocess.CREATE_NO_WINDOW)


def open_workbench(*unused, from_menu=False):
    global _WORKBENCH_URL, _PANEL_EPOCH
    with _PANEL_LOCK:
        if STOP.is_set():
            return
        epoch, game_pid = _GAME_STATE
        if _WORKBENCH_URL and _PANEL_EPOCH != epoch:
            _release_workbench()
        if not _panel_request(_WORKBENCH_URL, 'instance-ping').get('workbench'):
            _PANEL_EPOCH = epoch
            _WORKBENCH_URL = _start_workbench_server(game_pid)
        if not _WORKBENCH_URL:
            log('workbench server unavailable')
            return
        if STOP.is_set() or _PANEL_EPOCH != _GAME_STATE[0]:
            _release_workbench()
            return
        _sync_panel()
        if not _WORKBENCH_URL or STOP.is_set():
            return
        if _install_workbench_webview():
            import webview
            if not from_menu and getattr(webview, 'guilib', None) is None:
                return
            if _show_workbench_window():
                return
        _fallback_open_workbench()


def open_settings(*unused):
    open_workbench(from_menu=True)


_registry = getattr(MANAGER, '_sinners_warp_workers', None)
if _registry is None:
    _registry = {}
    MANAGER._sinners_warp_workers = _registry
_old = _registry.get(NAME)
if _old:
    _old[0].set()
    if len(_old) > 2:
        _old[2]()
    _old[1].join(timeout=2)
    if _old[1].is_alive():
        STOP.set()
        raise RuntimeError('旧随机人格后台尚未退出，本次不启动第二个后台；请重启启动器')
with _PANEL_LOCK:
    MANAGER._sinners_panel_owner = STOP
try:
    MANAGER.del_funcs.append({'name': NAME, 'func': deleted})
    MANAGER.disabled_funcs.append({'name': NAME, 'func': disabled})
except Exception:
    pass


try:
    import pystray
    menu=pystray.MenuItem('镜像幻化',pystray.Menu(
        pystray.MenuItem('人格、概率与演出设置',open_settings),
        pystray.MenuItem('原生随机已启用',None,enabled=False)))
    register=getattr(MANAGER,'register_tray_item',None)
    if callable(register):register(menu)
    else:
        MANAGER.menu_items.append(menu)
        refresh=getattr(MANAGER,'_refresh_tray_menu',None)
        if callable(refresh):refresh()
except Exception:
    log('tray registration failed: '+traceback.format_exc())
try:
    import importlib.util as _diag_import
    _spec = _diag_import.spec_from_file_location('_sinners_diagnostic', ROOT / 'diagnostic_log.py')
    _diag = _diag_import.module_from_spec(_spec); _spec.loader.exec_module(_diag)
    _diagnostic_logger = _diag.start(DATA_ROOT, STOP)
except Exception:
    log('diagnostic logger failed: '+traceback.format_exc())
log('Sinners Native host loaded; protocol '+str(VERSION))

try:
    if addon_settings().get('是否自动打开调整面板', True):
        threading.Thread(target=open_workbench, name='SinnersWorkbenchOpen', daemon=True).start()
        log('workbench opening in background')
    else:
        log('自动打开调整面板已关闭；可从启动器托盘打开调整菜单')
except Exception:
    log('workbench open failed: '+traceback.format_exc())
# Enabled plugin owns weekly discovery; opening a separate workbench does not.
try:
    import importlib.util as _weekly_import
    _weekly_spec = _weekly_import.spec_from_file_location('_sinners_weekly', ROOT / 'weekly_discovery.py')
    _weekly = _weekly_import.module_from_spec(_weekly_spec); _weekly_spec.loader.exec_module(_weekly)
    _start_weekly()
except Exception:
    log('每周自动检测调度启动失败：'+traceback.format_exc())

_worker_thread = threading.Thread(target=worker, name='SinnersWarpBridge', daemon=True)
_registry[NAME] = (STOP, _worker_thread, on_unload)
_worker_thread.start()
