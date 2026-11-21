"""Weekly automatic discovery, separate from manual workbench scans."""
import datetime, importlib.util, json, os, pathlib, subprocess, sys, tempfile, time
import importlib.util as _ilu

ZONE = datetime.timezone(datetime.timedelta(hours=8))

def _data_module():
    path=pathlib.Path(__file__).resolve().parent/'Workbench'/'core'/'mos_data.py'
    spec=_ilu.spec_from_file_location('_weekly_mos_data',path);module=_ilu.module_from_spec(spec);spec.loader.exec_module(module);return module

_DATA=_data_module()
_DATA_ROOT=_DATA.prepare(pathlib.Path(__file__).resolve().parent)

def weekly_slot(now):
    if now.tzinfo is None: raise ValueError('timezone-aware datetime required')
    local = now.astimezone(ZONE)
    days = (local.weekday() - 3) % 7
    start = (local - datetime.timedelta(days=days)).date()
    if local.weekday() == 3 and local.time() < datetime.time(11):
        start -= datetime.timedelta(days=7)
    return start.isoformat()

def _lock(root, filename='weekly_scan.lock', timeout=15):
    base=root/'Workbench';lock_path=base/'core'/'file_lock.py'
    if not lock_path.is_file():lock_path=next((p for p in base.rglob('file_lock.py') if p.is_file()),base/'file_lock.py')
    spec=importlib.util.spec_from_file_location('_weekly_file_lock',lock_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.FileLock(_DATA_ROOT/'Workbench'/filename, timeout=timeout)

def _write(path, data):
    tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8');os.replace(tmp,path)

def claim(root, now):
    root=pathlib.Path(root);path=_DATA_ROOT/'Workbench'/'weekly_scan_status.json';slot=weekly_slot(now)
    with _lock(root):
        try: previous=json.loads(path.read_text(encoding='utf8'))
        except (OSError,ValueError): previous={}
        # Fresh installs before Thursday 11 do not run last week's missed slot.
        local=now.astimezone(ZONE)
        if not previous and local.weekday()==3 and local.time()<datetime.time(11): return None
        if not isinstance(previous,dict):previous={}
        if previous.get('slot')==slot:
            if previous.get('status')=='success':return None
            if previous.get('status')=='failed':
                try:
                    finished=datetime.datetime.fromisoformat(previous['finished'])
                    elapsed=now-finished
                except (KeyError,ValueError,TypeError):
                    pass
                else:
                    if datetime.timedelta(0)<=elapsed<datetime.timedelta(minutes=15):return None
        _write(path,{'slot':slot,'status':'running','started':now.isoformat()})
    return slot

def finish(root, slot, code, detail):
    root=pathlib.Path(root);path=_DATA_ROOT/'Workbench'/'weekly_scan_status.json'
    with _lock(root):
        try: state=json.loads(path.read_text(encoding='utf8'))
        except (OSError,ValueError): return
        if state.get('slot')!=slot:return
        state.update(status='success' if code==0 else 'failed',finished=datetime.datetime.now(ZONE).isoformat(),exit_code=code,detail=detail[-2000:]);_write(path,state)

def run(root, stop, log):
    root=pathlib.Path(root)
    # A crashed launcher releases this OS lock even if the status stays "running".
    import contextlib
    with contextlib.ExitStack() as held:
        try:
            held.enter_context(_lock(root,'weekly_scan_owner.lock',timeout=0))
        except TimeoutError:
            return
        if not stop.is_set():
            _run_owned(root,stop,log)

def _run_owned(root,stop,log):
    slot=claim(root,datetime.datetime.now(ZONE))
    if not slot:return
    if stop.is_set():
        finish(root,slot,-1,'插件关闭，自动检测未执行')
        return
    python=root.parent.parent/'resources/mod_loader/_internal/venv/Bins/python.exe'
    try:
        if not python.is_file():raise FileNotFoundError('启动器自带 Python 不存在: '+str(python))
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0)
        env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
        # Redirect to temporary files: a verbose scanner must not block on a full pipe.
        with tempfile.TemporaryFile() as out:
            base=root/'Workbench';scan_script=base/'scan'/'scan_units.py'
            if not scan_script.is_file():scan_script=next((p for p in base.rglob('scan_units.py') if p.is_file()),base/'scan_units.py')
            proc=subprocess.Popen([str(python),str(scan_script),'--addon',str(_DATA_ROOT),'--weekly','--owner-pid',str(os.getpid())],cwd=str(root),stdout=out,stderr=subprocess.STDOUT,creationflags=flags,env=env)
            deadline=time.monotonic()+3600
            try:
                while proc.poll() is None:
                    if stop.wait(.2):
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError('每周自动检测超时')
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=3)
            out.seek(0,2);length=out.tell();out.seek(max(0,length-4000));detail=out.read().decode('utf8','replace')
            code=proc.returncode if proc.returncode is not None else -1
        finish(root,slot,code,detail);log('每周自动检测%s（%s）'%('完成' if code==0 else '未完成，见检测状态',slot))
    except Exception as exc:
        finish(root,slot,-1,str(exc));log('每周自动检测失败：'+str(exc))

def loop(root, stop, log):
    while not stop.is_set():
        try: run(root,stop,log)
        except Exception as exc: log('每周自动检测调度失败：'+str(exc))
        stop.wait(60)
