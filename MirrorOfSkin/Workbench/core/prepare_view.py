"""Human-readable, session-scoped preparation evidence."""
import ctypes, os, re, hashlib, threading

def process_alive(pid):
    if not isinstance(pid,int) or pid<=0:return False
    if os.name!='nt':
        try:os.kill(pid,0);return True
        except OSError:return False
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32];kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=[ctypes.c_void_p];kernel.CloseHandle.restype=ctypes.c_int
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return False
    try:
        kernel.QueryFullProcessImageNameW.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_uint32)]
        kernel.QueryFullProcessImageNameW.restype=ctypes.c_int
        size=ctypes.c_uint32(32768);buffer=ctypes.create_unicode_buffer(size.value)
        return bool(kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size))) and os.path.basename(buffer.value).lower()=='limbuscompany.exe'
    finally:kernel.CloseHandle(handle)

def config_paths(root):
    paths=[root/'random_settings.json',root/'custom_pools.json',root/'ruleset_state.json',root/'Assets/runtime/all_sinners_pools.json']
    directory=root/'rulesets'
    if directory.exists():paths.extend(sorted(directory.glob('*.json')))
    return paths

def config_digest(root):
    h=hashlib.sha256()
    for path in config_paths(root):
        try:h.update(path.read_bytes())
        except OSError:pass
        h.update(b'\0')
    return h.hexdigest()

def session_lines(log,pid):
    if not isinstance(pid,int):return []
    lines=log.splitlines();tag='pid=%d '%pid
    starts=[i for i,line in enumerate(lines) if tag in line and 'native worker started' in line]
    return [line for line in lines[starts[-1]:] if tag in line] if starts else []

def summarize(log,pid,alive,catalog):
    if not alive:return {'connected':False,'loaded':[],'shown':[]}
    lines=session_lines(log,pid)
    if not lines:return {'connected':True,'loaded':[],'shown':[],'evidence_missing':True}
    by_identity={str(e.get('identity_id','')):e for e in catalog}
    by_look={str(e.get('appearance_name','')):e for e in catalog}
    loaded={};shown={}
    def add(dest,key,kind):
        item=(by_identity.get(key) if kind=='identity' else by_look.get(key)) or {}
        label=str(item.get('name') or '未识别名称的外观')
        canonical=str(item.get('identity_id') or key)
        if key:dest.setdefault(canonical,{'name':label})
    for line in lines:
        m=re.search(r'skin ready .*?look=(\S+)',line)
        if m:add(loaded,m.group(1),'look')
        m=re.search(r'battle start appearance .*?identity=(\S+)',line)
        if m:add(shown,m.group(1),'identity')
        m=re.search(r'visual event .*?selected=(\S+) shown=1',line)
        if m:add(shown,m.group(1),'identity')
        m=re.search(r'apply look=(\S+)',line)
        if m:add(shown,m.group(1),'look')
    return {'connected':True,'ready':any('hooks installed' in line for line in lines),'loaded':list(loaded.values()),'shown':list(shown.values()),'evidence_missing':False}

_MARKERS = re.compile(r'\] (hooks installed|pool rows=|workbench draw rules applied revision=|workbench forms loaded revision=|skin ready |battle start appearance |visual event |apply look=)')
_APPEARANCE = re.compile(r'\b(?:look|identity|selected)=(\S+)')

class SessionEvidence:
    """Keep only the most recent session's preparation events, across log polls."""
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.key = None
        self.position = 0
        self.events = {}

    def read(self, pid):
        if type(pid) is not int or pid <= 0:
            return ''
        tag = (' pid=%d ' % pid).encode()
        with self.lock:
            try:
                with self.path.open('rb') as stream:
                    stat = os.fstat(stream.fileno())
                    key = (pid, stat.st_dev, stat.st_ino)
                    if self.key != key or stat.st_size < self.position:
                        self.events.clear()
                        self.position = 0
                        self.key = key
                    stream.seek(self.position)
                    while stream.tell() < stat.st_size:
                        raw = stream.readline()
                        if not raw.endswith(b'\n'):
                            break
                        self.position = stream.tell()
                        if tag not in raw:
                            continue
                        if b'] native worker started' in raw:
                            self.events = {'start': raw.decode('utf8','replace').rstrip()}
                            continue
                        if not self.events:
                            continue
                        line = raw.decode('utf8','replace').rstrip()
                        mark = _MARKERS.search(line)
                        if not mark:
                            continue
                        event = mark.group(1)
                        if event in ('skin ready ', 'battle start appearance ', 'visual event ', 'apply look='):
                            match = _APPEARANCE.search(line)
                            if not match or (event=='visual event ' and ' shown=1' not in line):
                                continue
                            event = (event, match.group(1))
                        self.events[event] = line
            except OSError:
                self.key = None
                return ''
            return '\n'.join(self.events.values())

def pool_status(pool, evidence, root):
    if not evidence or pool.get('config_revision') != config_digest(root):
        return '等待运行中的插件读取'
    published, applied = pool.get('published'), pool.get('applied')
    if (isinstance(published,int) and applied == published and
            (published > 0 or published == 0 and re.search(r'\] pool rows=\d+', evidence))):
        return '核心已读取成员与权重'
    return '已发布，等待核心读取'
