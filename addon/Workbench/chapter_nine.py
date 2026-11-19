"""Build the chapter nine identity rules using the installed appearance catalog."""
import json
from pathlib import Path

import schemes
import rulesets
import stage_director

NAME = '第九章 · 五指父辈与子辈'


def profiles(root):
    rows = json.loads((Path(root) / 'Workbench/chapter_nine_profiles.json').read_text(encoding='utf8'))
    for row in rows:
        row['sinner_name'] = rulesets.SINNER_NAMES[int(row['identity'][:3]) - 101]
    return rows


def rule_items(root, state, existing, has_portrait):
    items = []
    for row in profiles(root):
        identity = row['identity']
        sinner = identity[:3]
        key = 'chapter:' + identity
        current = state['active'].get(sinner)
        # 0.77 represented the same presets as editable personal rules. Recognize
        # that exact one-group selection without relabeling custom appearance pools.
        legacy = 'identity:' + identity
        enabled = current == key
        if current == legacy and not state['global']:
            old = next((r for r in existing if r['id'] == legacy), None)
            if old:
                entries = rulesets.entries(root, old)
                enabled = len(entries) == 1 and entries[0].get('group_id') == 'ch9_' + identity
        items.append(dict(id=key, kind='chapter', identity=identity, sinner=sinner,
                          name=row['sinner_name'] + ' → ' + row['enemy'], role=row['role'],
                          condition=row['condition'], icon=identity if has_portrait(identity) else None,
                          active=not state['global'] and enabled))
    return items


def activate(store, identity=None, mode='enable'):
    # The launcher and workbench share this lock. The scheme loader handles
    # backup and rollback for the whole switch, including the native files.
    with store.lock:
        doc = schemes.capture(store.root)
        stage_config = doc['stage_director']
        rules = doc['rulesets']
        active = rules['state'].setdefault('active', {})
        before = json.dumps(doc, ensure_ascii=False, sort_keys=True)
        chapter = profiles(store.root)
        if identity is not None:
            chapter = [row for row in chapter if row['identity'] == identity]
            if not chapter:
                raise ValueError('未知的第九章专属人格')
        if mode not in ('enable', 'only', 'disable') or (mode != 'enable' and identity is None):
            raise ValueError('未知的第九章规则操作')
        if mode == 'only':
            active.clear()
            doc['settings']['characters'] = {str(i): False for i in range(101, 113)}
        for row in chapter:
            identity = str(row['identity'])
            sinner = identity[:3]
            group_id = 'ch9_' + identity
            key = 'chapter:' + identity
            if mode == 'disable':
                current = active.get(sinner)
                personal = rules['files'].get('人格-' + identity + '.json') or {}
                entries = personal.get('entries') or []
                legacy = (current == 'identity:' + identity and len(entries) == 1 and
                          entries[0].get('group_id') == group_id and entries[0].get('weight', 1) > 0)
                if rules['state']['global'] or (current != key and not legacy):
                    return row['enemy']
                active[sinner] = 'none'
                doc['settings']['characters'][sinner] = False
                if (rules['state'].get('selected') or {}).get('id') in (current, key):
                    rules['state']['selected'] = None
                continue
            group = dict(id=group_id, name=row['role'] + ' · ' + row['enemy'], enabled=True,
                         hold=row.get('hold', False), stages=row['stages'])
            groups = stage_config['groups']
            for i, previous in enumerate(groups):
                if previous['id'] == group_id:
                    groups[i] = group
                    break
            else:
                groups.append(group)
            active[sinner] = key
            doc['settings']['characters'][sinner] = True
        if mode != 'disable':
            rules['state']['global'] = False
            first = str(chapter[0]['identity'])
            rules['state']['selected'] = dict(id='chapter:' + first, kind='chapter',
                                              sinner=int(first[:3]), identity=first)
            doc['settings']['enabled'] = True
        if before != json.dumps(doc, ensure_ascii=False, sort_keys=True):
            root = store.root
            stage = stage_director.snapshot(root)
            paths = [root / name for name in (rulesets.STATE, '随机设置.json', '停止随机运行.flag')]
            if stage['config'] != stage_config:
                paths.extend((root / stage_director.FILE, root / 'native_stage_groups.bin'))
            with schemes.backed_up_switch(root, paths):
                if stage['config'] != stage_config:
                    stage_director.save(root, stage_config, stage['revision'], store.data()['catalog'])
                rulesets.save_state(root, rules['state'])
                schemes.apply_switches(root, doc['settings'])
        return NAME
