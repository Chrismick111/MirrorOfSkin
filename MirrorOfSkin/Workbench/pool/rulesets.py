import hashlib, json, pathlib
from file_lock import FileLock
import group_entries

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


def catalog(root, pool_data=None):
    result = {}
    for pool in (pools(root) if pool_data is None else pool_data).values():
        for entry in pool.get('entries', []):
            identity = str(entry.get('identity_id', ''))
            if identity:
                result.setdefault(identity, entry)
    return result


def identity_file(root, identity):
    return pathlib.Path(root) / DIR / ('人格-%s.json' % identity)


def global_file(root):
    return pathlib.Path(root) / DIR / '全局.json'


def _default_entries(pool, sinner):
    result = []
    for entry in pool.get('entries', []):
        identity = str(entry.get('identity_id', ''))
        if not identity.isdigit() or len(identity) != 5 or identity[:3] != str(sinner):
            continue
        if entry.get('story_metadata') or entry.get('category') == 'humanoid_boss':
            continue
        weight = float(entry.get('weight', 1))
        if weight > 0:
            result.append({'identity_id': identity, 'weight': weight})
    return result[:MAX_ENTRIES]


def _all_default_entries(pool_data):
    result = []
    seen = set()
    for pool in pool_data.values():
        for entry in pool.get('entries', []):
            identity = str(entry.get('identity_id', ''))
            if not identity.isdigit() or len(identity) != 5 or identity in seen:
                continue
            if entry.get('story_metadata') or entry.get('category') == 'humanoid_boss':
                continue
            weight = float(entry.get('weight', 1))
            if weight > 0:
                seen.add(identity)
                result.append({'identity_id': identity, 'weight': weight})
    return result[:MAX_ENTRIES]


def _saved_appearances(entries):
    result = []
    for entry in entries or []:
        try: value = group_entries.normalize_entry(entry)
        except (TypeError, ValueError): continue
        if value['entry_kind'] == 'appearance':
            result.append(value)
    return result[:MAX_ENTRIES]


def _portrait(root, identity, portrait_ok):
    return bool(identity) and portrait_ok(identity)


def list_rulesets(root, portrait_ok, pool_data=None):
    root = pathlib.Path(root)
    st = state(root)
    if pool_data is None:
        pool_data = pools(root)
    cat = catalog(root, pool_data)
    items = []
    any_active = bool(st['active'])
    global_data = _read(global_file(root), {})
    items.append({
        'id': 'global', 'kind': 'global', 'name': '所有角色', 'icon': None, 'sinner': None, 'identity': None,
        'active': st['global'], 'conflict': not st['global'] and any_active,
        'locked': bool(global_data.get('locked')),
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


def entries(root, rule, pool_data=None):
    root = pathlib.Path(root)
    if not rule:
        return []
    kind, sinner, identity = rule.get('kind'), str(rule.get('sinner') or ''), rule.get('identity')
    if kind == 'global':
        data = _read(global_file(root), {})
        if isinstance(data.get('entries'), list):
            return _saved_appearances(data.get('entries', []))
        if isinstance(data.get('pools'), dict):
            merged = []
            seen = set()
            for profile in data['pools'].values():
                if not isinstance(profile, dict):
                    continue
                for entry in _saved_appearances(profile.get('entries', [])):
                    identity = str(entry.get('identity_id', ''))
                    if identity and identity not in seen:
                        seen.add(identity)
                        merged.append(entry)
            return merged[:MAX_ENTRIES]
        return []
    if kind == 'sinner':
        profile = (custom(root).get('characters') or {}).get(sinner)
        return _saved_appearances(profile.get('entries', [])) if isinstance(profile, dict) else []
    if kind == 'identity':
        data = _read(identity_file(root, identity), {})
        return _saved_appearances(data.get('entries', [])) if isinstance(data, dict) else []
    return []


def effective_entries(root, rule, pool_data=None):
    """Return only entries the native pool builder can actually resolve.

    An empty rule set is valid JSON, so it used to be activated silently and
    left the game with zero candidates. Every activation/creation path uses
    this check to fail loudly instead of disabling all appearance replacement.
    """
    root = pathlib.Path(root)
    if pool_data is None:
        pool_data = pools(root)
    cat = catalog(root, pool_data)
    kind = rule.get('kind')
    if kind == 'sinner':
        sinner = str(rule.get('sinner') or '')
        profile = (custom(root).get('characters') or {}).get(sinner)
        if not isinstance(profile, dict):
            # No custom pool yet: the native builder uses this character's
            # default catalog entries, so activating it is still safe.
            return _default_entries(pool_data.get(sinner, {}), sinner)
    result = []
    for entry in entries(root, rule, pool_data):
        if entry.get('entry_kind', 'appearance') != 'appearance':
            continue
        identity = str(entry.get('identity_id', ''))
        try:
            weight = float(entry.get('weight', 1))
        except (TypeError, ValueError):
            continue
        if identity in cat and weight > 0:
            result.append(entry)
    return result


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


def save_entries(root, rule, entries, expected_revision, known, validate, lock=None):
    root = pathlib.Path(root)
    if not rule:
        raise ValueError('未选择规则集')
    if not isinstance(entries,list) or len(entries)>MAX_ENTRIES: raise ValueError('规则池格式无效')
    with (lock or FileLock(root / 'workbench-save.lock')):
        catalog_map = {str(key): {} for key in known}
        entries = group_entries.validate_entries(entries, catalog_map, {})
        validate(str(rule.get('sinner') or '101'), {'enabled': True, 'entries': entries}, known)
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
            data = _read(path, {})
            if data.get('locked'):
                raise ValueError('纯随机默认池不可编辑，请右键清空池子')
            data.update({'schema': 1, 'scope': 'global', 'name': '所有角色', 'entries': entries, 'locked': False})
            data.pop('pools', None)
            _write(path, data)
        else:
            raise ValueError('未知规则集类型')
    return revision(root, rule)


def fill_default(root, rule, pool_data=None):
    root = pathlib.Path(root)
    if not rule:
        raise ValueError('未选择规则集')
    if pool_data is None:
        pool_data = pools(root)
    kind, sinner, identity = rule.get('kind'), str(rule.get('sinner') or ''), rule.get('identity')
    if kind == 'global':
        entries = _all_default_entries(pool_data)
        if not entries:
            raise ValueError('没有可填入的默认外观候选；请先更新资源。')
        with FileLock(root / 'workbench-save.lock'):
            _write(global_file(root), {'schema': 1, 'scope': 'global', 'name': '所有角色', 'entries': entries, 'locked': True})
        return entries
    entries = _default_entries(pool_data.get(sinner, {}), sinner)
    if not entries:
        raise ValueError('该角色没有可填入的默认外观候选；请先更新资源。')
    if kind == 'sinner':
        with FileLock(root / 'workbench-save.lock'):
            data = custom(root)
            data.setdefault('characters', {})[sinner] = {'enabled': True, 'entries': entries}
            _write(root / CUSTOM, data)
        return entries
    if kind == 'identity':
        path = identity_file(root, identity)
        data = _read(path, None)
        if not data:
            raise ValueError('单人格规则集不存在')
        data['entries'] = entries
        with FileLock(root / 'workbench-save.lock'):
            _write(path, data)
        return entries
    raise ValueError('未知规则集类型')


def clear(root, rule):
    root = pathlib.Path(root)
    if not rule:
        raise ValueError('未选择规则集')
    kind, sinner, identity = rule.get('kind'), str(rule.get('sinner') or ''), rule.get('identity')
    if kind == 'global':
        with FileLock(root / 'workbench-save.lock'):
            _write(global_file(root), {'schema': 1, 'scope': 'global', 'name': '所有角色', 'entries': [], 'locked': False})
    elif kind == 'sinner':
        with FileLock(root / 'workbench-save.lock'):
            data = custom(root)
            profile = (data.get('characters') or {}).get(sinner)
            if not isinstance(profile, dict):
                profile = {'enabled': True}
                data.setdefault('characters', {})[sinner] = profile
            profile['entries'] = []
            _write(root / CUSTOM, data)
    elif kind == 'identity':
        path = identity_file(root, identity)
        data = _read(path, None)
        if data:
            data['entries'] = []
            with FileLock(root / 'workbench-save.lock'):
                _write(path, data)
    else:
        raise ValueError('未知规则集类型')
    return []


def activate(root, rule):
    root = pathlib.Path(root)
    if not rule:
        raise ValueError('未选择规则集')
    if not effective_entries(root, rule):
        raise ValueError('该规则集没有可用的外观候选，已拒绝启用；请先点击“填入默认全随机”。')
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


def select(root, rule):
    root = pathlib.Path(root)
    if not rule:
        raise ValueError('未选择规则集')
    kind = rule.get('kind')
    if kind not in ('global', 'sinner', 'identity'):
        raise ValueError('未知规则集类型')
    st = state(root)
    st['selected'] = {
        'id': rule.get('id'),
        'kind': kind,
        'sinner': rule.get('sinner'),
        'identity': rule.get('identity'),
    }
    with FileLock(root / 'workbench-save.lock'):
        save_state(root, st)
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
    # A new rule set is an empty canvas: the user decides which appearances
    # belong in it. Activation still rejects empty pools, so an unfinished rule
    # set cannot silently disable appearance replacement in the game.
    entries = []
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
    if current.startswith('identity:'):
        identity = current.split(':', 1)[1]
        if not effective_entries(root, {'kind': 'identity', 'sinner': sinner, 'identity': identity}):
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

def deactivate(root, rule):
    root = pathlib.Path(root)
    if not rule:
        raise ValueError('未选择规则集')
    st = state(root)
    kind = rule.get('kind')
    sinner = str(rule.get('sinner') or '')
    identity = rule.get('identity')
    if kind == 'global':
        st['global'] = False
        st['active'] = {}
        st['selected'] = None
    else:
        current = st['active'].get(sinner)
        target = 'sinner' if kind == 'sinner' else 'identity:' + str(identity)
        if current == target:
            st['active'][sinner] = 'none'
        selected = st.get('selected') or {}
        if selected.get('id') == rule.get('id'):
            st['selected'] = None
    cfg = settings(root)
    cfg['characters'] = {str(i): False for i in range(101, 113)}
    for key, value in st['active'].items():
        if str(value) != 'none' and str(key).isdigit():
            cfg['characters'][str(key)] = True
    if st['global']:
        for i in range(101, 113):
            cfg['characters'][str(i)] = True
    with FileLock(root / 'workbench-save.lock'):
        save_state(root, st)
        _write(root / '随机设置.json', cfg)
    return st

