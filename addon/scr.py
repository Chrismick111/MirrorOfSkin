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



ROW = struct.Struct('<IIII d 64s 128s 64s')

def stopped_by_flag():
    try:
        saved = json.loads((ROOT / '随机设置.json').read_text(encoding='utf-8-sig'))
        return not bool(saved.get('enabled', True))
    except (OSError, ValueError):
        return (ROOT / '停止随机运行.flag').exists()


def max_cached_skins():
    # User-selected full-pool prewarm; the old small-cache field is retained
    # in user settings but is not used by this strategy.
    return 256

_CUSTOM_POOLS=json.loads((ROOT/'自定义人格池.json').read_text(encoding='utf-8-sig'))

_pool_history = {}

def prepare_native_pools():
    import importlib.util, hashlib
    lock=getattr(prepare_native_pools,'lock',None)
    if lock is None:
        spec=importlib.util.spec_from_file_location('_sinners_pool_file_lock',ROOT/'Workbench'/'file_lock.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        lock=module.FileLock(ROOT/'workbench-save.lock');prepare_native_pools.lock=lock
    with lock:
        rows=_prepare_native_pools_unlocked()
        prepare_native_pools.config_revision=hashlib.sha256((ROOT/'自定义人格池.json').read_bytes()).hexdigest()
        return rows

def _prepare_native_pools_unlocked():
    global _pool_history
    import math
    pools=json.loads((ROOT/'Assets/runtime/all_sinners_pools.json').read_text(encoding='utf-8-sig'))
    import importlib.util as _cp_import
    _spec = _cp_import.spec_from_file_location('_sinners_custom_pools',ROOT/'custom_pools.py')
    _cp = _cp_import.module_from_spec(_spec);_spec.loader.exec_module(_cp)
    selected = _cp.apply_custom_pools(pools, json.loads((ROOT/'自定义人格池.json').read_text(encoding='utf-8-sig')))
    _hot_spec = _cp_import.spec_from_file_location('_sinners_hot_pool',ROOT/'hot_pool.py')
    _hot = _cp_import.module_from_spec(_hot_spec);_hot_spec.loader.exec_module(_hot)
    pools = _hot.complete_snapshot(pools, selected, _pool_history)
    settings=json.loads((ROOT/'随机设置.json').read_text(encoding='utf-8-sig'))
    rows=[]
    for key,pool in pools.items():
        sinner=int(key)
        if sinner<101 or sinner>112:raise ValueError('Invalid sinner')
        ids=set()
        for entry in pool['entries']:
            identity=str(entry['identity_id']);raw=identity.encode('ascii')
            asset=str(entry['asset_key']).encode('ascii');look=str(entry['appearance_name']).encode('ascii')
            weight=float(entry.get('weight',1))
            if not math.isfinite(weight) or weight<0 or weight>1000000:raise ValueError('Invalid weight')
            if not raw or len(raw)>=64 or identity in ids:raise ValueError('Invalid/duplicate identity')
            if not asset or len(asset)>=128:raise ValueError('Invalid asset key')
            if not look or len(look)>=64:raise ValueError('Invalid appearance name')
            ids.add(identity)
            enabled=bool(settings.get('enabled',True) and settings.get('characters',{}).get(key,True))
            actions={'evade':1,'attack':2,'attack-preparation':4,'clash':8,'clash-preparation':16}
            excluded=entry.get('excluded_actions',[])
            if any(x not in actions for x in excluded):raise ValueError('Unknown excluded action')
            mask=sum(actions[x] for x in set(excluded))
            if entry.get('auto_discovered'):mask|=0x80000000
            story=1 if entry.get('story_metadata') else 0
            rows.append(ROW.pack(sinner,enabled,mask,story,weight,raw,asset,look))
    if len(rows)>4096:raise ValueError('Too many identities')
    candidate=next((e for k,pool in pools.items() for e in pool['entries'] if settings.get('characters',{}).get(k,True) and float(e.get('weight',1))>0 and not e.get('story_metadata')),None)
    if candidate:
        (ROOT/'probe_asset.txt').write_text(candidate['asset_key'],encoding='utf8')
    # Preserve multi-form metadata separately without changing the stable SRP4 ABI.
    form_data={'version':1,'policy':'donor follows current unit sanity/state','identities':{}}
    for sinner,pool in pools.items():
        for entry in pool['entries']:
            forms=entry.get('forms') or [entry['appearance_name']]
            if len(forms)>1:
                form_data['identities'][str(entry['identity_id'])]={'sinner':int(sinner),'asset_key':entry['asset_key'],'base':entry['appearance_name'],'forms':forms}
    form_path=ROOT/'native_forms.json';form_temp=form_path.with_suffix('.tmp')
    form_temp.write_text(json.dumps(form_data,ensure_ascii=False,indent=2),encoding='utf8');form_temp.replace(form_path)
    dest=ROOT/'native_pools.bin';temp=dest.with_suffix('.tmp')
    temp.write_bytes(struct.pack('<4sIII',b'SRP4',3,len(rows),ROW.size)+b''.join(rows));temp.replace(dest)
    _pool_history = {k:p['entries'] for k,p in pools.items()}
    return len(rows)

def probability_stamp():
    paths = [ROOT/'随机设置.json', ROOT/'Assets/runtime/all_sinners_pools.json', ROOT/'自定义人格池.json']
    return tuple((p.stat().st_mtime_ns, p.stat().st_size) for p in paths)

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
                        struct.pack_into('<I', session, OFF_TUNABLE + 4, max_cached_skins())
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
                struct.pack_into('<II', session, OFF_TUNABLE, 1, max_cached_skins())
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
        subprocess.Popen(['powershell.exe','-NoProfile','-STA','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',str(ROOT/'Workbench'/'打开工作台.ps1')],cwd=str(ROOT),creationflags=subprocess.CREATE_NO_WINDOW)
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


