import copy, datetime, json, os, pathlib, re, tempfile
from contextlib import contextmanager
import director
import rulesets
import chapter_nine

DIR = 'schemes'
BACKUP = '读取前自动备份'
_NAME = re.compile(r'^[^\\/:*?"<>|\x00-\x1f]{1,40}$')
_RULE_FILE = re.compile(r'^(全局|persona-\d+)\.json$')


def _path(root, name):
    name = str(name or '').strip()
    if not _NAME.match(name) or name.startswith('.') or name.endswith('.'):
        raise ValueError('方案名无效：1-40 个字符，不能包含 \\ / : * ? " < > |')
    return pathlib.Path(root) / DIR / (name + '.json'), name


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    os.replace(temp, path)


def capture(root):
    root = pathlib.Path(root)
    files = {}
    folder = root / rulesets.DIR
    if folder.is_dir():
        for path in sorted(folder.glob('*.json')):
            data = rulesets._read(path, None)
            if data is not None and _RULE_FILE.match(path.name):
                files[path.name] = data
    return {'schema': 3, 'pools': rulesets.custom(root), 'director': director.snapshot(root)['config'],
            'rulesets': {'state': rulesets.state(root), 'files': files}, 'settings': _switches(rulesets.settings(root))}


def _switches(cfg):
    chars = cfg.get('characters') if isinstance(cfg.get('characters'), dict) else {}
    return {'enabled': bool(cfg.get('enabled', True)), 'characters': {str(k): bool(v) for k, v in chars.items()}}


def normalize(doc, root=None):
    if not isinstance(doc, dict):
        raise ValueError('方案格式不支持')
    doc = copy.deepcopy(doc)
    legacy = doc.pop('stage_director', None)
    if doc.get('schema') == 1 and isinstance(doc.get('characters'), dict):
        doc = {'schema': 3, 'pools': doc, 'director': None, 'rulesets': None}
    elif doc.get('schema') == 2 and isinstance(doc.get('pools'), dict):
        doc = {'schema': 3, 'pools': doc['pools'], 'director': doc.get('director'), 'rulesets': None}
    if doc.get('schema') != 3 or not isinstance(doc.get('pools'), dict):
        raise ValueError('方案格式不支持')
    def check_profiles(profiles):
        if not isinstance(profiles, dict) or any(
            not isinstance(p, dict) or not isinstance(p.get('entries', []), list)
            for p in profiles.values()
        ):
            raise ValueError('方案中的人格池条目无效')
    check_profiles(doc['pools'].get('characters', {}))
    rules = doc.get('rulesets')
    if rules is not None:
        if not isinstance(rules, dict) or not isinstance(rules.get('files', {}), dict):
            raise ValueError('方案中的规则集格式无效')
        for name, data in rules.get('files', {}).items():
            if not _RULE_FILE.match(name) or not isinstance(data, dict):
                raise ValueError('方案中的规则集文件无效：' + str(name))
            if name == 'global.json':
                check_profiles(data.get('pools', {}))
            elif not isinstance(data.get('entries', []), list):
                raise ValueError('方案中的专属规则条目无效')
        state = rules.get('state')
        if state is not None and (not isinstance(state, dict) or not isinstance(state.get('active', {}), dict)):
            raise ValueError('方案中的规则启用状态无效')
    settings = doc.get('settings')
    if settings is not None and not isinstance(settings, dict):
        raise ValueError('方案中的随机开关格式无效')
    normalized = {'schema': 3, 'pools': doc['pools'], 'director': doc.get('director'), 'rulesets': rules, 'settings': settings}
    return chapter_nine.clean_document(normalized, chapter_nine.defaults(root) if root is not None else {}, legacy)


def _names(root):
    return {identity: str(entry.get('name') or entry.get('appearance_name') or identity)
            for identity, entry in rulesets.catalog(root).items()}


def _items(entries, names):
    items = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        try:
            weight = float(entry.get('weight', 1))
        except (TypeError, ValueError):
            continue
        if weight > 0:
            identity = str(entry.get('identity_id', ''))
            items.append(names.get(identity, identity))
    return items


def _who(sinner):
    try:
        return rulesets.SINNER_NAMES[int(sinner) - 101]
    except (TypeError, ValueError, IndexError):
        return str(sinner)


def summary(root, doc, names=None):
    if names is None:
        names = _names(root)
    groups = []
    rules = doc.get('rulesets') or {}
    state = rules.get('state') or {}
    active = state.get('active') or {}
    for sinner, profile in sorted((doc['pools'].get('characters') or {}).items()):
        items = _items((profile or {}).get('entries'), names)
        if items:
            groups.append({'label': _who(sinner) + ' · 罪人池', 'active': active.get(str(sinner)) == 'sinner', 'items': items})
    for name, data in sorted((rules.get('files') or {}).items()):
        if name == 'global.json':
            for sinner, profile in sorted((data.get('pools') or {}).items()):
                items = _items((profile or {}).get('entries'), names)
                if items:
                    groups.append({'label': '全局 · ' + _who(sinner), 'active': bool(state.get('global')), 'items': items})
        else:
            identity = str(data.get('identity', ''))
            items = _items(data.get('entries'), names)
            if items:
                groups.append({'label': _who(data.get('sinner')) + ' · ' + names.get(identity, identity) + ' 专属',
                               'active': active.get(str(data.get('sinner'))) == 'identity:' + identity, 'items': items})
    return {'groups': groups, 'count': sum(len(g['items']) for g in groups)}


def listing(root):
    folder = pathlib.Path(root) / DIR
    result = []
    if not folder.is_dir():
        return result
    names = None
    for path in sorted(folder.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            raw = json.loads(path.read_text(encoding='utf-8-sig'))
            doc = normalize(raw, root)
        except (OSError, ValueError):
            continue
        if names is None:
            names = _names(root)
        result.append(dict(summary(root, doc, names), name=path.stem, saved_at=raw.get('saved_at', '')))
    return result


def get(root, name):
    path, name = _path(root, name)
    if not path.is_file():
        raise ValueError('方案不存在：' + name)
    doc = json.loads(path.read_text(encoding='utf-8-sig'))
    normalize(doc, root)
    return chapter_nine.clean_document(doc, chapter_nine.defaults(root))


def save(root, name, overwrite=False, doc=None):
    path, name = _path(root, name)
    if path.exists() and not overwrite:
        raise ValueError('已存在同名方案：' + name)
    doc = normalize(doc, root) if doc is not None else capture(root)
    doc.update(name=name, saved_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
    _write(path, doc)
    return name


def delete(root, name):
    path, name = _path(root, name)
    path.unlink(missing_ok=True)


def load(store, name, known):
    return load_document(store, name, get(store.root, name), known)


def load_document(store, name, data, known):
    root = pathlib.Path(store.root)
    doc = normalize(data, root)
    pools = doc['pools']
    if pools.get('schema') != 1 or not isinstance(pools.get('characters'), dict):
        raise ValueError('方案中的人格池格式不支持')
    for target, profile in pools['characters'].items():
        store.validate(target, profile, known)
    for filename, data in ((doc.get('rulesets') or {}).get('files') or {}).items():
        if filename == 'global.json':
            for target, profile in (data.get('pools') or {}).items():
                store.validate(str(target), dict(profile, enabled=True), known)
        else:
            store.validate(str(data.get('sinner','')), dict(data, enabled=True), known)
    if doc['director'] is not None:
        director.validate(doc['director'], known)
        if any(k not in store.form_annotations() for k in doc['director'].get('forms', {})):
            raise ValueError('方案包含未确认支持的形态人格')
    with store.lock:
        paths = {root / p for p in ('custom_pools.json', 'custom_pools.workbench.bak')}
        if doc['director'] is not None:
            paths.update(root / p for p in ('director.json', 'director.workbench.bak', 'workbench_rules.bin', 'workbench_forms.bin'))
        if doc['settings'] is not None:
            paths.update((root / 'random_settings.json', root / 'stop_random.flag'))
        if doc['rulesets'] is not None:
            folder = root / rulesets.DIR
            paths.add(root / rulesets.STATE)
            paths.update(p for p in folder.glob('*.json') if _RULE_FILE.fullmatch(p.name))
            paths.update(folder / p for p in doc['rulesets'].get('files', {}))
        with backed_up_switch(root, paths):
            _apply(store, root, doc, pools, known)
    return name


@contextmanager
def backed_up_switch(root, paths):
    paths = set(paths) | {_path(root, BACKUP)[0]}
    before = {p: p.read_bytes() if p.exists() else None for p in paths}
    try:
        save(root, BACKUP, overwrite=True)
        yield
    except Exception:
        for p, content in before.items():
            if content is None:
                p.unlink(missing_ok=True)
            elif not p.exists() or p.read_bytes() != content:
                fd, tmp = tempfile.mkstemp(dir=p.parent)
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(content)
                    os.replace(tmp, p)
                finally:
                    pathlib.Path(tmp).unlink(missing_ok=True)
        raise


def _apply(store, root, doc, pools, known):
    store.replace(pools, store.snapshot()['revision'], known)
    if doc['director'] is not None:
        store.save_director(doc['director'], store.director_snapshot()['revision'], known)
    rules = doc['rulesets']
    if rules is not None:
        folder = root / rulesets.DIR
        files = rules.get('files', {})
        if folder.is_dir():
            for path in folder.glob('*.json'):
                if path.name not in files and _RULE_FILE.match(path.name):
                    path.unlink()
        for file_name, data in files.items():
            rulesets._write(folder / file_name, data)
        rulesets.save_state(root, dict(rulesets.DEFAULT_STATE, **(rules.get('state') or {})))
    if doc['settings'] is not None:
        apply_switches(root, doc['settings'])


def apply_switches(root, settings):
    cfg = rulesets.settings(root)
    saved = _switches(settings)
    cfg['enabled'] = saved['enabled']
    cfg['characters'] = {str(i): saved['characters'].get(str(i), False) for i in range(101, 113)}
    rulesets._write(root / 'random_settings.json', cfg)
    flag = root / 'stop_random.flag'
    if cfg['enabled']:
        flag.unlink(missing_ok=True)
    else:
        flag.touch()
