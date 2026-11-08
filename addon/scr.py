"""FaustLauncher host for the native Sinners Random addon.

The launcher resolves the obfuscated il2cpp export names, writes them into a
shared section with a heartbeat, injects the versioned native DLL, and mirrors the
DLL status into native.log. No Frida, no bundled Python.
"""
import ctypes as C
from ctypes import wintypes as W
import json, mmap, pathlib, struct, threading, time, traceback

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
DLL_NAME = 'SinnersNative-v63.dll'
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
bind('OpenProcess', W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
bind('VirtualAllocEx', P, W.HANDLE, P, C.c_size_t, W.DWORD, W.DWORD)
bind('VirtualFreeEx', W.BOOL, W.HANDLE, P, C.c_size_t, W.DWORD)
bind('WriteProcessMemory', W.BOOL, W.HANDLE, P, P, C.c_size_t, P)
bind('CreateRemoteThread', W.HANDLE, W.HANDLE, P, C.c_size_t, P, P, W.DWORD, P)
bind('WaitForSingleObject', W.DWORD, W.HANDLE, W.DWORD)
bind('GetModuleHandleW', W.HMODULE, W.LPCWSTR)
bind('GetProcAddress', P, W.HMODULE, C.c_char_p)
bind('GetTickCount', W.DWORD)
bind('VirtualQuery', C.c_size_t, P, P, C.c_size_t)
bind('GetModuleFileNameW', W.DWORD, W.HMODULE, W.LPWSTR, W.DWORD)


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


def log(message):
    try:
        import warphook
        warphook.log(str(message), prefix='[' + str(NAME) + ']')
    except Exception:
        pass
    with (ROOT / 'native.log').open('a', encoding='utf8') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + str(message) + '\n')


def modules(pid):
    return {m.name.lower(): m for m in _snapshot(0x18, pid, Module, 'Module32')}


def _inject_remote_loader(pid, mods):
    dll = ROOT / DLL_NAME
    if dll.name.lower() in mods:
        return
    process = K.OpenProcess(0x43a, False, pid)
    if not process:
        raise C.WinError(C.get_last_error())
    remote = thread = None
    try:
        path = str(dll).encode('utf-16le') + b'\0\0'
        remote = K.VirtualAllocEx(process, None, len(path), 0x3000, 4)
        if not remote:
            raise C.WinError(C.get_last_error())
        buf = C.create_string_buffer(path)
        if not K.WriteProcessMemory(process, remote, buf, len(path), None):
            raise C.WinError(C.get_last_error())
        address = K.GetProcAddress(K.GetModuleHandleW('kernel32.dll'), b'LoadLibraryW')

        class Memory(C.Structure):
            _fields_ = [('base', P), ('allocation', P), ('protection', W.DWORD),
                        ('partition', W.WORD), ('size', C.c_size_t), ('state', W.DWORD),
                        ('protect', W.DWORD), ('type', W.DWORD)]

        info = Memory(); K.VirtualQuery(address, C.byref(info), C.sizeof(info))
        text = C.create_unicode_buffer(32768)
        K.GetModuleFileNameW(info.allocation, text, len(text))
        module = mods[pathlib.Path(text.value).name.lower()]
        loader = module.base + address - info.allocation
        thread = K.CreateRemoteThread(process, None, 0, loader, remote, 0, None)
        if not thread:
            raise C.WinError(C.get_last_error())
        if K.WaitForSingleObject(thread, 20000) != 0:
            def finish(h, t, p):
                K.WaitForSingleObject(t, 0xffffffff)
                K.VirtualFreeEx(h, p, 0, 0x8000)
                K.CloseHandle(t); K.CloseHandle(h)
            threading.Thread(target=finish, args=(process, thread, remote), daemon=True).start()
            process = thread = remote = None
            raise RuntimeError('DLL load timed out')
        if dll.name.lower() not in modules(pid):
            raise RuntimeError('DLL not present after load')
    finally:
        if remote:
            K.VirtualFreeEx(process, remote, 0, 0x8000)
        if thread:
            K.CloseHandle(thread)
        if process:
            K.CloseHandle(process)

def inject(pid, mods):
    import warphook
    if DLL_NAME.lower() in mods:
        return
    ok, message = warphook.inject_dll(pid, str((ROOT / DLL_NAME).resolve()))
    if not ok:
        if 'winerror=87' in str(message):
            log('WarpHook加载地址错误87，使用按目标进程模块地址计算的兼容加载路径')
            _inject_remote_loader(pid, mods)
        else:
            raise RuntimeError('WarpHook加载失败: ' + str(message))
    if DLL_NAME.lower() not in modules(pid):
        raise RuntimeError('WarpHook加载后未发现目标DLL')


def enable_debug_privilege():
    class Luid(C.Structure):
        _fields_ = [('low', W.DWORD), ('high', W.LONG)]

    class Privilege(C.Structure):
        _fields_ = [('count', W.DWORD), ('luid', Luid), ('attributes', W.DWORD)]

    adv = C.WinDLL('advapi32', use_last_error=True)
    adv.OpenProcessToken.argtypes = [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)]
    adv.LookupPrivilegeValueW.argtypes = [W.LPCWSTR, W.LPCWSTR, C.POINTER(Luid)]
    adv.AdjustTokenPrivileges.argtypes = [W.HANDLE, W.BOOL, C.POINTER(Privilege), W.DWORD, P, P]
    bind('GetCurrentProcess', W.HANDLE)
    token = W.HANDLE()
    if not adv.OpenProcessToken(K.GetCurrentProcess(), 0x28, C.byref(token)):
        return
    privilege = Privilege(); privilege.count = 1; privilege.attributes = 2
    if adv.LookupPrivilegeValueW(None, 'SeDebugPrivilege', C.byref(privilege.luid)):
        C.set_last_error(0)
        adv.AdjustTokenPrivileges(token, False, C.byref(privilege), 0, None, None)
        log('SeDebugPrivilege result=' + str(C.get_last_error()))
    K.CloseHandle(token)


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



ROW = struct.Struct('<IIII d 64s 128s 64s 64s')
ROW3 = struct.Struct('<IIII d 64s 128s 64s')
RULESET_DIR = ROOT / '规则集'
RULESET_STATE = ROOT / '规则集状态.json'

DEFAULT_SETTINGS = {'max_cached_skins': 3, 'prewarm_full_pool': False, 'enabled': True, 'characters': {str(i): False for i in range(101, 113)}}
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
        path = ROOT / name
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
    path = ROOT / name
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
        saved = json.loads((ROOT / '随机设置.json').read_text(encoding='utf-8-sig'))
        return not bool(saved.get('enabled', True))
    except (OSError, ValueError):
        return (ROOT / '停止随机运行.flag').exists()


def prewarm_settings():
    settings = load_user_json('随机设置.json', DEFAULT_SETTINGS)
    try:
        skins = int(settings.get('max_cached_skins', 3))
    except (TypeError, ValueError):
        skins = 3
    skins = max(2, min(256, skins))
    mode = 1 if settings.get('prewarm_full_pool', False) else 0
    return mode, skins

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
    if not data or data.get('scope') != 'global' or not isinstance(data.get('pools'), dict):
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
    rows = []
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
        identity = str(item.get('identity_id', ''))
        source = catalog.get(identity)
        if not source:
            continue
        row = dict(source)
        row['weight'] = weight
        row['base_identity'] = base
        rows.append(row)
    return rows


def _rule_paths():
    paths = [ROOT / '随机设置.json', ROOT / '自定义人格池.json', RULESET_STATE, ROOT / 'Assets/runtime/all_sinners_pools.json']
    if RULESET_DIR.exists():
        paths.extend(sorted(RULESET_DIR.glob('*.json')))
    return paths


def _config_digest():
    import hashlib
    digest = hashlib.sha256()
    for path in _rule_paths():
        try:
            digest.update(path.read_bytes())
        except OSError:
            pass
        digest.update(b'\0')
    return digest.hexdigest()


def _old_pool_rows():
    path = ROOT / 'native_pools.bin'
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    if len(raw) < 16:
        return []
    magic, version, count, size = struct.unpack_from('<4sIII', raw, 0)
    if magic != b'SRP4' or count > 4096:
        return []
    if version == 4 and size == ROW.size:
        fmt, has_base = ROW, True
    elif version == 3 and size == ROW3.size:
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
            'weight': 0,
            '_mask': excluded,
            '_story': bool(story),
        })
    return rows


def prepare_native_pools():
    import importlib.util
    lock = getattr(prepare_native_pools, 'lock', None)
    if lock is None:
        spec = importlib.util.spec_from_file_location('_sinners_pool_file_lock', ROOT / 'Workbench' / 'file_lock.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        lock = module.FileLock(ROOT / 'workbench-save.lock')
        prepare_native_pools.lock = lock
    with lock:
        rows = _prepare_native_pools_unlocked()
        prepare_native_pools.config_revision = _config_digest()
        return rows


def _prepare_native_pools_unlocked():
    import math
    pools = json.loads((ROOT / 'Assets/runtime/all_sinners_pools.json').read_text(encoding='utf-8-sig'))
    catalog = _catalog_by_identity(pools)
    custom = load_user_json('自定义人格池.json', DEFAULT_CUSTOM_POOLS)
    state = ruleset_state()
    settings = load_user_json('随机设置.json', DEFAULT_SETTINGS)

    known = {}

    def add(sinner, row):
        row = dict(row)
        row['sinner'] = int(sinner)
        row['weight'] = 0
        key = (int(sinner), str(row.get('base_identity', '')), str(row.get('identity_id', '')))
        if key[2]:
            known.setdefault(key, row)

    # Keep every catalog identity at zero weight so changing rule sets never
    # has to remove native rows (the hot reload path requires old rows).
    for sinner, pool in pools.items():
        for entry in pool.get('entries', []):
            row = dict(entry)
            row['weight'] = 0
            row['base_identity'] = ''
            add(sinner, row)

    for target, profile in (custom.get('characters') or {}).items():
        if not isinstance(profile, dict):
            continue
        for row in _resolve_rows(profile.get('entries', []), '', catalog, include_zero=True):
            add(target, row)

    global_rule = _global_ruleset()
    if global_rule:
        for target, profile in global_rule.get('pools', {}).items():
            if str(target) not in pools or not isinstance(profile, dict):
                continue
            for row in _resolve_rows(profile.get('entries', []), '', catalog, include_zero=True):
                add(target, row)

    if RULESET_DIR.exists():
        for path in sorted(RULESET_DIR.glob('人格-*.json')):
            data = _json_file(path)
            if not data or data.get('scope') != 'identity':
                continue
            identity = str(data.get('identity', ''))
            sinner = str(data.get('sinner', ''))
            if sinner not in pools or identity not in catalog:
                continue
            for row in _resolve_rows(data.get('entries', []), identity, catalog, include_zero=True):
                add(sinner, row)

    for row in _old_pool_rows():
        sinner = str(row.get('sinner', ''))
        if sinner in pools:
            add(sinner, row)

    active_rows = []

    def activate(sinner, rows):
        for row in rows:
            weight = float(row.get('weight', 0))
            if weight <= 0:
                continue
            row = dict(row)
            row['sinner'] = int(sinner)
            key = (int(sinner), str(row.get('base_identity', '')), str(row.get('identity_id', '')))
            known[key] = row
            active_rows.append(row)

    if state['global']:
        for sinner in range(101, 113):
            key = str(sinner)
            entries = None
            if global_rule:
                profile = global_rule.get('pools', {}).get(key)
                if isinstance(profile, dict):
                    entries = profile.get('entries', [])
            if entries is None:
                entries = pools[key].get('entries', [])
            activate(key, _resolve_rows(entries, '', catalog))
    else:
        for sinner in range(101, 113):
            key = str(sinner)
            active = state['active'].get(key, 'none')
            if active == 'sinner':
                profile = (custom.get('characters') or {}).get(key)
                entries = profile.get('entries', []) if isinstance(profile, dict) else pools[key].get('entries', [])
                activate(key, _resolve_rows(entries, '', catalog))
            elif active.startswith('identity:'):
                identity = active.split(':', 1)[1]
                rule = _identity_ruleset(identity)
                if rule and str(rule.get('sinner')) == key:
                    activate(key, _resolve_rows(rule.get('entries', []), identity, catalog))

    rows = []
    written = set()
    for row in active_rows:
        key = (int(row['sinner']), str(row.get('base_identity', '')), str(row['identity_id']))
        if key in written:
            continue
        written.add(key)
        rows.append(row)
    for key, row in known.items():
        if key in written:
            continue
        written.add(key)
        rows.append(row)
    if len(rows) > 4096:
        raise ValueError('Too many identities')

    actions = {'evade': 1, 'attack': 2, 'attack-preparation': 4, 'clash': 8, 'clash-preparation': 16}
    packed = []
    seen = set()
    for row in rows:
        sinner = int(row['sinner'])
        if sinner < 101 or sinner > 112:
            raise ValueError('Invalid sinner')
        identity = str(row['identity_id'])
        raw = identity.encode('ascii')
        asset = str(row['asset_key']).encode('ascii')
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
        key = (sinner, base, raw)
        if key in seen:
            continue
        seen.add(key)
        excluded = row.get('excluded_actions', [])
        if any(x not in actions for x in excluded):
            raise ValueError('Unknown excluded action')
        if '_mask' in row:
            mask = int(row['_mask'])
        else:
            mask = sum(actions[x] for x in set(excluded))
        if row.get('auto_discovered'):
            mask |= 0x80000000
        story = 1 if row.get('_story') or row.get('story_metadata') else 0
        enabled = 1 if weight > 0 and settings.get('enabled', True) else 0
        packed.append(ROW.pack(sinner, enabled, mask, story, weight, raw, asset, look, base))

    candidate = next((row for row in active_rows if float(row.get('weight', 0)) > 0 and not row.get('story_metadata')), None)
    if candidate:
        (ROOT / 'probe_asset.txt').write_text(str(candidate['asset_key']), encoding='utf8')

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
    form_path = ROOT / 'native_forms.json'
    form_temp = form_path.with_suffix('.tmp')
    form_temp.write_text(json.dumps(form_data, ensure_ascii=False, indent=2), encoding='utf8')
    form_temp.replace(form_path)

    dest = ROOT / 'native_pools.bin'
    temp = dest.with_suffix('.tmp')
    temp.write_bytes(struct.pack('<4sIII', b'SRP4', 4, len(packed), ROW.size) + b''.join(packed))
    temp.replace(dest)
    return len(packed)


def probability_stamp():
    return tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else (0, 0) for p in _rule_paths())


def _delay_ready(detected_at, now):
    return detected_at is not None and now - detected_at >= 30.0


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
    enable_debug_privilege()
    try:
        while not STOP.wait(.5):
            try:
                import warphook
                pid = warphook.find_game_pid()
                if pid != current:
                    if session:
                        log('game process ended, closing shared section')
                        session.close()
                    if load_guard:
                        compat.release_process(load_guard); load_guard = None
                    session = None; discovery = None; current = pid; attempted = None; previous = None
                    detected_at = time.monotonic() if pid else None
                    if pid:
                        log("检测到游戏进程，等待 30 秒后加载随机人格")
                if not pid:
                    continue
                if session:
                    if attempted != pid:
                        raise RuntimeError("Incomplete injection session")
                    struct.pack_into('<II', session, 12, 0 if stopped_by_flag() else 1, K.GetTickCount())
                    if discovery:
                        discovery.poll()
                    stamp = probability_stamp()
                    if stamp != pool_stamp:
                        # Publish the revision only after a complete atomic snapshot.
                        import hashlib
                        rows = prepare_native_pools()
                        published_config = prepare_native_pools.config_revision
                        revision = (revision + 1) & 0xffffffff or 1
                        mode, skins = prewarm_settings()
                        struct.pack_into('<II', session, OFF_TUNABLE, mode, skins)
                        struct.pack_into('<I', session, OFF_TUNABLE + 8, revision)
                        pool_stamp = stamp
                        log('Probability update published revision=%d rows=%d' % (revision, rows))
                    import hashlib
                    pool_status = {'pid':pid,'published':revision,'applied':struct.unpack_from('<I',session,OFF_TUNABLE+12)[0], 'config_revision':published_config}
                    if pool_status != getattr(worker,'pool_status',None):
                        tmp=ROOT/'pool_update_status.tmp';tmp.write_text(json.dumps(pool_status),encoding='utf8');tmp.replace(ROOT/'pool_update_status.json');worker.pool_status=pool_status
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
                    compat.validate(ROOT, pathlib.Path(mods['gameassembly.dll'].path).parent, mods, DLL_NAME)
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
                session = mmap.mmap(-1, SIZE,
                                    tagname=SESSION_NAME % pid,
                                    access=mmap.ACCESS_WRITE)
                session[:] = b'\0' * SIZE
                struct.pack_into('<5I', session, 0, MAGIC, VERSION, SIZE, 0 if stopped_by_flag() else 1, K.GetTickCount())
                mode, skins = prewarm_settings()
                struct.pack_into('<II', session, OFF_TUNABLE, mode, skins)
                import secrets
                nonce = secrets.randbits(32) or 1
                struct.pack_into('<I', session, OFF_TUNABLE + 16, nonce)
                spec = importlib.util.spec_from_file_location('_sinners_auto_discovery', ROOT / 'auto_discovery.py')
                auto_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(auto_module)
                discovery = auto_module.Discovery(ROOT, pathlib.Path(mods['gameassembly.dll'].path).parent, pid, nonce, log, VERSION)
                for index, name in enumerate(API_NAMES):
                    alias = result['mapping'].get('il2cpp_' + name, 'il2cpp_' + name).encode('ascii')
                    if len(alias) >= 64:
                        raise RuntimeError('Invalid export alias')
                    session[32 + index * 64:32 + (index + 1) * 64] = alias.ljust(64, b'\0')
                log("Native pool snapshot rows="+str(prepare_native_pools()))
                pool_stamp = probability_stamp()
                revision = 0
                inject(pid, mods)
                attempted = pid
                log(f'Native DLL loaded in {pid}')
                previous = report(session, None)
            except Exception as exc:
                if load_guard and attempted != pid:
                    compat.release_process(load_guard); load_guard = None
                if session is not None and attempted != pid:
                    session.close(); session = None
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



def on_unload(): STOP.set()
def disabled(*unused): STOP.set()
def deleted(*unused): STOP.set()
try:
    import pystray
    def open_settings(*unused):
        import subprocess
        subprocess.Popen(['powershell.exe','-NoProfile','-STA','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',str(ROOT/'Workbench'/'open_workbench.ps1')],cwd=str(ROOT),creationflags=subprocess.CREATE_NO_WINDOW)
    menu=pystray.MenuItem('人格演出工作台',pystray.Menu(
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
    _diagnostic_logger = _diag.start(ROOT, STOP)
except Exception:
    log('diagnostic logger failed: '+traceback.format_exc())
log('Sinners Native host loaded; protocol '+str(VERSION))
_registry = getattr(MANAGER, '_sinners_warp_workers', None)
if _registry is None:
    _registry = {}; setattr(MANAGER, '_sinners_warp_workers', _registry)
_old = _registry.get(NAME)
if _old:
    _old[0].set(); _old[1].join(timeout=2)
    if _old[1].is_alive():
        STOP.set()
        raise RuntimeError('旧随机人格后台尚未退出，本次不启动第二个后台；请重启启动器')
_worker_thread = threading.Thread(target=worker,name='SinnersWarpBridge',daemon=True)
_registry[NAME] = (STOP, _worker_thread)
_worker_thread.start()


