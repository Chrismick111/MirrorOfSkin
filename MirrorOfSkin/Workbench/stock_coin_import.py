"""Build a wearable appearance from the stock models referenced by a mod's coins."""
from pathlib import Path, PurePosixPath
import re
from import_progress import progress_range


def _locate(names, unity, progress=None):
    from resource_catalog import build_index, fingerprint, load_index, resolve_roots

    roots = resolve_roots()
    root, index_dir = roots['resource_root'], roots['index_dir']
    if root is None:
        raise ValueError('找不到已下载的游戏模型，请在工作台确认游戏资源目录。')

    def resolve(index):
        found = {name: [] for name in names}
        for relative, entry in index['entries'].items():
            matches = names.intersection(entry.get('prefabs', {}))
            if not matches:
                continue
            path = (root / relative).resolve()
            if not path.is_relative_to(root) or not path.is_file() or fingerprint(path) != entry.get('fingerprint'):
                continue
            for name in matches:
                address = entry['prefabs'][name].replace('\\', '/')
                if PurePosixPath(address).stem == name and '/SD/' in address:
                    found[name].append((path, address))
        return found

    report = progress_range(progress)
    report(0, '正在查找所需的游戏外观')
    index, _ = load_index(index_dir, root, auto_build=False)
    found = resolve(index) if index is not None else None
    if found is None or any(len(matches) != 1 for matches in found.values()):
        last_percent = -1

        def scanned(done, total, changed):
            nonlocal last_percent
            percent = done * 99 // max(total, 1)
            if percent != last_percent or done == total:
                report(percent, f'正在索引游戏资源（{done}/{total}）')
                last_percent = percent

        report(0, '正在建立游戏资源索引')
        found = resolve(build_index(root, index_dir, unity_py=unity, progress=scanned))
    for name, matches in sorted(found.items()):
        if len(matches) != 1:
            raise ValueError(f'逐币外观 {name} 在已下载游戏资源中有 {len(matches)} 个匹配，请核对游戏资源目录。')
    return {name: matches[0] for name, matches in found.items()}


def _motion_detail(name):
    match = re.fullmatch(r'S([1-9][0-9]?)', name or '')
    if match:
        number = int(match[1])
        if 1 <= number <= 10:
            return number + 6
        if 11 <= number <= 21:
            return number + 13
    raise ValueError(f'不能确认逐币攻击动作槽位：{name}')


def _attack_sequences(recipe):
    if recipe['issues']:
        issue = recipe['issues'][0]
        raise ValueError(f"逐币演出配置缺少可验证的数据：{issue['code']}（技能 {issue.get('skillId', '未知')}）")
    sequences = []
    for skill in recipe['skills']:
        level = max(skill['levels'], key=lambda item: item['gaksungLevel'])
        coins = level['coins']
        if skill['role'] == 'defense':
            if any(c['appearance'] != recipe['appearance'] or c['motion'] not in ('Default', 'Guard', 'Evade') for c in coins):
                raise ValueError('此包声明了单独的守备换形，尚不能完整转换。')
            continue
        if not coins or len(coins) > 128 or skill['skillTier'] not in (1, 2, 3):
            raise ValueError(f"逐币技能的阶或硬币数无法转换：{skill['skillId']}")
        parts = []
        for coin in coins:
            if not coin['appearance'] or type(coin['fragment']) is not int or coin['fragment'] < 1:
                raise ValueError(f"逐币技能缺少身体或动作片段：{skill['skillId']}，硬币 {coin['coinIndex']}")
            parts.append((coin['appearance'], _motion_detail(coin['motion']), coin['fragment'] - 1))
        sequences.append((skill, tuple(parts)))
    return sequences


def _allocate_groups(sequences, occupied):
    free = iter(d for d in (*range(7, 17), *range(24, 35)) if d not in occupied)
    slots, routes = {}, []
    for skill, parts in sequences:
        if parts not in slots:
            slot = next(free, None)
            if slot is None:
                raise ValueError('可用攻击动作槽不足，无法容纳所有逐币演出。')
            slots[parts] = slot
        routes.append([skill['skillId'], skill['skillTier'], len(parts), slots[parts],
                       0 if skill['role'] == 'attack' else 1])
    if not slots or len(routes) > 128:
        raise ValueError('工作台支持每个逐币外观包含 1 至 128 条攻击技能映射。')
    return {slot: parts for parts, slot in slots.items()}, routes


def build_coin_record(declaration, recipe, work, unity, name, keys, archive_name, identity, *, progress=None):
    from imported_catalog import display_name
    from skin_assets import _roots
    from skin_motions import analyze_motion
    from stock_appearance_composite import build

    report = progress_range(progress)
    base = recipe['appearance']
    sequences = _attack_sequences(recipe)
    assets = _locate({base} | {part[0] for _, parts in sequences for part in parts}, unity, progress_range(report, 0, 35))
    report(35, '正在读取基础外观：' + base)
    path, address = assets[base]
    env = unity.load(str(path))
    root, = [item for item in _roots(env) if item[0] == address]
    objects = env.assets[0].objects
    app, = [tree for component in objects[root[1]].read_typetree()['m_Component']
            for obj in [objects.get(component['component']['m_PathID'])]
            if obj and obj.type.name == 'MonoBehaviour'
            for tree in [obj.read_typetree()] if 'motionList' in tree]
    groups, routes = _allocate_groups(sequences, {m['_motiondetail'] for m in app['motionList']})
    del env, objects, app
    look = identity.look
    dependency = 'SD_' + address.split('/SD/', 1)[1]
    if dependency not in keys:
        raise ValueError('游戏资源目录中缺少逐币外观的基础人格：' + dependency)
    encoded, published, layout = build(assets, base, groups, look, unity, progress=progress_range(report, 38, 92))
    report(92, '正在回读模型并检查逐币动作')
    env = unity.load(encoded)
    root, = _roots(env)
    reader = env.assets[0].objects[root[1]]
    if root[0] != published or reader.peek_name() != look:
        raise ValueError('逐币模型读回时未找到唯一的已发布外观。')
    label = display_name(declaration.package_root.name or archive_name, archive_name)
    if declaration.label:
        label += ' · ' + declaration.label
    label = name or label
    entry, timing, actions = analyze_motion(env, reader, look, 'Imported/' + look + '.prefab', label, stock_only=True)
    verified = {item['detail']: len(item['parts']) for item in actions['attack']}
    if any(verified.get(slot) != len(parts) for slot, parts in groups.items()):
        raise ValueError('合成后有逐币攻击缺少可播放的画面或命中时序，已取消导入。')
    actions['coin_routes'] = routes
    entry['private_declaration'] = identity.owner
    work.mkdir(parents=True, exist_ok=True)
    bundle = work / (look + '.bundle')
    bundle.write_bytes(encoded)
    return dict(look=look, name=label, asset=published, layout=layout, dependency=dependency,
                bundle=bundle, entry=entry, timing=timing, actions=actions, coin_routes=routes,
                model_voice_evidence=actions.pop('model_voice_evidence', dict(state='unknown', count=0)),
                _uses_legacy_private_id=identity.uses_legacy)
