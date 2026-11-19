"""Human-readable, session-scoped preparation evidence."""
import ctypes, os, re, hashlib

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

def config_digest(root):
    paths=[root/'stage_director.json',root/'随机设置.json',root/'自定义人格池.json',root/'规则集状态.json',root/'Assets/runtime/all_sinners_pools.json']
    directory=root/'规则集'
    if directory.exists():paths.extend(sorted(directory.glob('*.json')))
    h=hashlib.sha256()
    for path in paths:
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

def read_tail(path):
    try:
        with path.open('rb') as f:
            f.seek(0,2);size=f.tell();f.seek(max(0,size-4*1024*1024));return f.read().decode('utf8','replace')
    except OSError:return ''
