"""Prepare fresh effect snapshot in a separate interpreter before injection."""
import json,os,pathlib,subprocess,time,importlib.util

def _mos_data():
    path=pathlib.Path(__file__).resolve().parents[1]/"core"/"mos_data.py"
    spec=importlib.util.spec_from_file_location("_fx_mos_data",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

mos_data=_mos_data()

def launcher_python(root):
    base=pathlib.Path(root).parent.parent/'resources/mod_loader/_internal/venv'
    for relative in ('Bins/python.exe','Scripts/python.exe'):
        path=base/relative
        if path.is_file():return path
    raise RuntimeError('找不到启动器 Python，请检查启动器安装')

def prepare(root,game_dir,log,python_exe=None,timeout=600,cancelled=None):
    addon=pathlib.Path(root);data=mos_data.data_dir();active=mos_data.path(addon,'fx-active.bin')
    try:active.unlink(missing_ok=True)
    except OSError as exc:raise RuntimeError('无法清除旧特效快照，停止加载原生插件') from exc
    runner=addon/'Workbench/fx_prepare_runner.py'
    try:
        state_file=mos_data.path(addon,'特效启用状态.json')
        if not state_file.is_file():log('特效方案未启用');return False
        state=json.loads(state_file.read_text(encoding='utf-8-sig'))
        if not isinstance(state,dict) or type(state.get('enabled')) is not bool or not isinstance(state.get('name'),str):raise ValueError('特效启用状态无效')
        if not state['enabled']:log('特效方案未启用');return False
        if cancelled and cancelled():raise RuntimeError('特效准备已取消')
        exe=pathlib.Path(python_exe) if python_exe else launcher_python(addon)
        log('正在读取游戏资源并准备特效方案，首次建立索引可能需要几分钟')
        process=subprocess.Popen([str(exe),'-B',str(runner),str(data),str(game_dir)],cwd=str(addon),
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1'))
        deadline=time.monotonic()+timeout
        try:
            while True:
                if cancelled and cancelled():raise RuntimeError('特效准备已取消')
                left=deadline-time.monotonic()
                if left<=0:raise RuntimeError('特效准备超时')
                try:stdout,stderr=process.communicate(timeout=min(.25,left));break
                except subprocess.TimeoutExpired:continue
        except BaseException:
            process.kill();process.communicate();raise
        if cancelled and cancelled():raise RuntimeError('特效准备已取消')
        if process.returncode==0 and active.is_file():
            log('特效方案快照已准备');return True
        raise RuntimeError((stderr or stdout or ('退出码 %d'%process.returncode)).strip()[-1000:])
    except Exception as exc:
        try:active.unlink(missing_ok=True)
        except OSError as cleanup:raise RuntimeError('无法清除特效快照，停止加载原生插件') from cleanup
        log('特效未启用：'+str(exc));return False
