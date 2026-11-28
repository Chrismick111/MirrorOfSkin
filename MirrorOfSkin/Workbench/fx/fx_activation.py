"""Choose and prepare one effect scheme; preparation never injects into a game."""
import json,os,pathlib,tempfile,importlib.util
import effect_schemes,effect_timelines,prepare_plan,scan_units
import resource_catalog

STATE='fx_active.json'
ACTIVE='fx-active.bin'

def read_selection(root):
    p=pathlib.Path(root)/STATE
    if not p.is_file():return {'enabled':False,'name':''}
    obj=json.loads(p.read_text(encoding='utf-8-sig'))
    if not isinstance(obj,dict) or type(obj.get('enabled')) is not bool or not isinstance(obj.get('name'),str):raise ValueError('特效启用状态无效')
    return {'enabled':obj['enabled'],'name':obj['name']}

def atomic_bytes(path,data):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=str(path.parent),prefix='.fx-',suffix='.tmp')
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def select(root,name,enabled):
    if type(enabled) is not bool or not isinstance(name,str):raise ValueError('方案设置无效')
    if enabled:effect_schemes.get(root,name)
    elif name:effect_schemes._path(root,name)
    selection={'enabled':enabled,'name':name}
    atomic_bytes(pathlib.Path(root)/STATE,json.dumps(selection,ensure_ascii=False).encode('utf8'))
    return selection

def prepare_start(root, game_dir, log):
    """Discard stale data first; fail closed for effects but keep plugin startup."""
    root=pathlib.Path(root);active=root/ACTIVE
    try:
        if active.exists():active.unlink()
        selection=read_selection(root)
        if not selection['enabled']:
            log('特效方案未启用');return False
        plan=effect_schemes.get(root,selection['name'])
        roots=resource_catalog.resolve_roots(game_dir=game_dir)
        cache=roots.get('resource_root')
        if not cache:raise ValueError('未找到游戏资源缓存')
        looks=list(dict.fromkeys(item.get('appearance') for item in plan['effects']))
        if not looks or any(not isinstance(x,str) or not x for x in looks):raise ValueError('方案缺少外观')
        for look in looks:
            snapshot=effect_timelines.lookup(look,roots=roots)
            effect_timelines._read_live(look,snapshot,roots=roots)
            state=effect_timelines.state(look)
            if state.get('status')!='done':raise ValueError('读取外观资源失败：'+str(state.get('message','未知错误')))
        compiled=__import__('effect_plan').preview_workbench(plan,effect_timelines.state)
        addon=pathlib.Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('_fx_release_compatibility',addon/'release_compatibility.py')
        compatibility=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(compatibility)
        manifest=json.loads((addon/'compatibility.json').read_text(encoding='utf-8-sig'))
        expected=compatibility.select_game_files(game_dir,manifest)['GameAssembly.dll']
        binary=prepare_plan.prepare(compiled,cache,pathlib.Path(game_dir)/'GameAssembly.dll',expected,effect_timelines.state)
        atomic_bytes(active,binary)
        log('特效方案已准备：'+selection['name']);return True
    except Exception as exc:
        try:
            if active.exists():active.unlink()
        except OSError:pass
        log('特效方案准备失败：'+str(exc));return False

