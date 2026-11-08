import hashlib, json, pathlib
from file_lock import FileLock

SINNER_NAMES = ['李箱', '浮士德', '堂吉诃德', '良秀', '默尔索', '鸿璐', '希斯克利夫', '以实玛利', '罗佳', '辛克莱', '奥提斯', '格里高尔']
DIR = '规则集'
STATE = '规则集状态.json'
CUSTOM = '自定义人格池.json'
POOLS = 'Assets/runtime/all_sinners_pools.json'
DEFAULT_STATE = {'schema': 1, 'global': False, 'active': {}, 'selected': None}
MAX_ENTRIES = 256


def _read(path, default):
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        return data if isinstance(data, dict) else default
    except (OSError, ValueError):
        return default


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.ruleset.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    temp.replace(path)


def state(root):
    data = _read(pathlib.Path(root) / STATE, DEFAULT_STATE)
    active = data.get('active') if isinstance(data.get('active'), dict) else {}
    selected = data.get('selected') if isinstance(data.get('selected'), dict) else None
    return {'schema': 1, 'global': bool(data.get('global')), 'active': {str(k): str(v) for k, v in active.items()}, 'selected': selected}


def save_state(root, data):
    _write(pathlib.Path(root) / STATE, data)


def settings(root):
    return _read(pathlib.Path(root) / '随机设置.json', {'enabled': True, 'characters': {}})


def custom(root):
    return _read(pathlib.Path(root) / CUSTOM, {'schema': 1, 'characters': {}})


def pools(root):
    return _read(pathlib.Path(root) / POOLS, {})


def catalog(root):
    result = {}
    for pool in pools(root).values():
        for entry in pool.get('entries', []):
            identity = str(entry.get('identity_id', ''))
            if identity:
                result.setdefault(identity, entry)
    return result


def identity_file(root, identity):
    return pathlib.Path(root) / DIR / ('人格-%s.json' % identity)


def global_file(root):
    return pathlib.Path(root) / DIR / '全局.json'


def _default_entries(pool):
    return [{'identity_id': str(entry['identity_id']), 'weight': float(entry.get('weight', 1))} for entry in pool.get('entries', []) if float(entry.get('weight', 1)) > 0][:MAX_ENTRIES]


def _positive(entries):
    result = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        identity = str(entry.get('identity_id', ''))
        try:
            weight = float(entry.get('weight', 1))
        except (TypeError, ValueError):
            continue
        if identity and 0 < weight <= 1000000:
            result.append({'identity_id': identity, 'weight': weight})
    return result[:MAX_ENTRIES]


def _portrait(root, identity, portrait_ok):
    return bool(identity) and portrait_ok(identity)


def list_rulesets(root, portrait_ok):
    root = pathlib.Path(root)
    st = state(root)
    pool_data = pools(root)
    cat = catalog(root)
    items = []
    any_active = bool(st['active'])
    items.append({
        'id': 'global', 'kind': 'global', 'name': '所有角色', 'icon': None, 'sinner': None, 'identity': None,
        'active': st['global'], 'conflict': not st['global'] and any_active,
    })
    for index, name in enumerate(SINNER_NAMES):
        sinner = str(101 + index)
        icon = None
        for entry in pool_data.get(sinner, {}).get('entries', []):
            identity = str(entry.get('identity_id', ''))
            if identity and not entry.get('story_metadata') and _portrait(root, identity, portrait_ok):
                icon = identity
                break
        state_value = st['active'].get(sinner, 'none')
        items.append({
            'id': 'sinner:' + sinner, 'kind': 'sinner', 'name': name + ' · 全部人格',
            'icon': icon, 'sinner': sinner, 'identity': None,
            'active': not st['global'] and state_value == 'sinner',
            'conflict': st['global'] or state_value not in ('none', 'sinner'),
        })
    directory = root / DIR
    if directory.is_dir():
        for path in sorted(directory.glob('人格-*.json')):
            data = _read(path, None)
            if not data or data.get('scope') != 'identity':
                continue
            identity = str(data.get('identity', ''))
            sinner = str(data.get('sinner', ''))
            entry = cat.get(identity, {})
            state_value = st['active'].get(sinner, 'none')
            items.append({
                'id': 'identity:' + identity, 'kind': 'identity',
                'name': (SINNER_NAMES[int(sinner) - 101] if sinner.isdigit() and 101 <= int(sinner) <= 112 else sinner) + ' · ' + str(entry.get('name') or identity),
                'icon': identity if _portrait(root, identity, portrait_ok) else None,
                'sinner': sinner, 'identity': identity,
                'active': not st['global'] and state_value == 'identity:' + identity,
                'conflict': st['global'] or state_value not in ('none', 'identity:' + identity),
            })
    return st, items


def selected_rule(root):
    root = pathlib.Path(root)
    st, items = list_rulesets(root, lambda identity: False)
    selected = st.get('selected') or {}
    wanted = selected.get('id')
    if not wanted and selected.get('kind'):
        if selected['kind'] == 'global':
            wanted = 'global'
        elif selected['kind'] == 'sinner':
            wanted = 'sinner:' + str(selected.get('sinner', ''))
        elif selected['kind'] == 'identity':
            wanted = 'identity:' + str(selected.get('identity', ''))
    for item in items:
        if item['id'] == wanted:
            return st, item
    return st, None


def entries(root, rule):
    root = pathlib.Path(root)
    if not rule:
        return []
    kind, sinner, identity = rule.get('kind'), str(rule.get('sinner') or ''), rule.get('identity')
    if kind == 'global':
        data = _read(global_file(root), {})
        profile = (data.get('pools') or {}).get(sinner)
        if isinstance(profile, dict):
            return _positive(profile.get('entries', []))
        return _default_entries(pools(root).get(sinner, {}))
    if kind == 'sinner':
        profile = (custom(root).get('characters') or {}).get(sinner)
        return _positive(profile.get('entries', [])) if isinstance(profile, dict) else []
    if kind == 'identity':
        data = _read(identity_file(root, identity), {})
        return _positive(data.get('entries', [])) if isinstance(data, dict) else []
    return []


def revision(root, rule):
    root = pathlib.Path(root)
    if not rule:
        return hashlib.sha256(b'').hexdigest()
    kind, identity = rule.get('kind'), rule.get('identity')
    if kind == 'global':
        path = global_file(root)
    elif kind == 'sinner':
        path = root / CUSTOM
    else:
        path = identity_file(root, identity)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return hashlib.sha256(b'').hexdigest()


def save_entries(root, rule, entries, expected_revision, known, validate):
    root = pathlib.Path(root)
    if not rule:
        raise ValueError('未选择规则集')
    entries = _positive(entries)
    validate(str(rule.get('sinner') or '101'), {'enabled': True, 'entries': entries}, known)
    with FileLock(root / 'workbench-save.lock'):
        if revision(root, rule) != expected_revision:
            raise ValueError('规则集已在其他窗口更改，请重新载入')
        kind, sinner, identity = rule.get('kind'), str(rule.get('sinner') or ''), rule.get('identity')
        if kind == 'sinner':
            data = custom(root)
            data.setdefault('characters', {})[sinner] = {'enabled': True, 'entries': entries}
            _write(root / CUSTOM, data)
        elif kind == 'identity':
            path = identity_file(root, identity)
            data = _read(path, None)
            if not data:
                raise ValueError('单人格规则集不存在')
            data['entries'] = entries
            _write(path, data)
        elif kind == 'global':
            path = global_file(root)
            data = _read(path, {'schema': 1, 'scope': 'global', 'name': '所有角色', 'pools': {}})
            data.setdefault('pools', {})[sinner] = {'enabled': True, 'entries': entries}
            _write(path, data)
        else:
            raise ValueError('未知规则集类型')
    return revision(root, rule)


def activate(root, rule):
    root = pathlib.Path(root)
    if not rule:
        raise ValueError('未选择规则集')
    st = state(root)
    kind, sinner, identity = rule.get('kind'), rule.get('sinner'), rule.get('identity')
    cfg = settings(root)
    cfg['enabled'] = True
    cfg.setdefault('characters', {})
    if kind == 'global':
        st['global'] = True
        st['active'] = {}
        for index in range(101, 113):
            cfg['characters'][str(index)] = True
    elif kind == 'sinner':
        st['global'] = False
        st['active'][str(sinner)] = 'sinner'
        cfg['characters'][str(sinner)] = True
    elif kind == 'identity':
        st['global'] = False
        st['active'][str(sinner)] = 'identity:' + str(identity)
        cfg['characters'][str(sinner)] = True
    else:
        raise ValueError('未知规则集类型')
    st['selected'] = {'id': rule['id'], 'kind': kind, 'sinner': sinner, 'identity': identity}
    with FileLock(root / 'workbench-save.lock'):
        save_state(root, st)
        _write(root / '随机设置.json', cfg)
    return st


def create_identity(root, sinner, identity, known):
    root = pathlib.Path(root)
    identity = str(identity)
    sinner = str(sinner)
    if identity not in known:
        raise ValueError('未知人格')
    if identity_file(root, identity).exists():
        raise ValueError('该人格规则集已存在')
    entry = known[identity]
    entry_sinner = str(entry.get('source', ''))
    if entry_sinner not in ('', sinner):
        raise ValueError('该人格不属于当前角色')
    entries = _default_entries(pools(root).get(sinner, {}))
    data = {
        'schema': 1, 'scope': 'identity', 'sinner': int(sinner), 'identity': identity,
        'name': str(entry.get('name') or identity), 'entries': entries,
    }
    with FileLock(root / 'workbench-save.lock'):
        _write(identity_file(root, identity), data)
    return data

def only(root, rule):
    root = pathlib.Path(root)
    if not rule:
        raise ValueError('未选择规则集')
    sinner = str(rule.get('sinner') or '')
    st = state(root)
    current = st['active'].get(sinner, 'none')
    if current == 'none':
        current = 'sinner'
    st['global'] = False
    st['active'] = {sinner: current}
    st['selected'] = {'id': rule.get('id'), 'kind': rule.get('kind'), 'sinner': rule.get('sinner'), 'identity': rule.get('identity')}
    cfg = settings(root)
    cfg['enabled'] = True
    cfg['characters'] = {str(i): str(i) == sinner for i in range(101, 113)}
    with FileLock(root / 'workbench-save.lock'):
        save_state(root, st)
        _write(root / '随机设置.json', cfg)
    return st

