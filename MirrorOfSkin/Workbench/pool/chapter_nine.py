"""Upgrade old appearance-group selections to ordinary appearance entries."""
import importlib.util
import json
import os
import re
from functools import lru_cache
from pathlib import Path


def _read(path):
    return json.loads(path.read_bytes()) if path.is_file() else {}


@lru_cache(maxsize=1)
def _template_appearances():
    # FaustLauncher imports this module by filename without adding Workbench to sys.path.
    path = Path(__file__).with_name('merged_appearances.py')
    spec = importlib.util.spec_from_file_location('_retired_appearance_presets', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = {}
    for key, name, members in module.FAMILIES:
        family = module.family_info(key, name, members)
        for group_id in [family['group_id'], *family['group_ids']]:
            result[group_id] = members[0]
    return result


def _definitions(config):
    result = {}
    if not isinstance(config, dict):
        return result
    for group in (config or {}).get('groups', []):
        stages = group.get('stages') if isinstance(group, dict) else None
        if stages and isinstance(stages[0], dict) and stages[0].get('identity_id'):
            result[group['id']] = (stages[0]['identity_id'], group.get('enabled', True))
    return result


def defaults(root):
    path = Path(root) / 'Workbench/data/chapter_nine_profiles.json'
    return {'ch9_' + row['identity']: row['stages'][0]['identity_id']
            for row in (_read(path) or [])}


def _convert_entries(profile, definitions):
    rows = profile.get('entries', [])
    if not any(isinstance(row, dict) and row.get('entry_kind') == 'group' for row in rows):
        return
    converted, by_identity = [], {}
    for row in rows:
        if not isinstance(row, dict):
            converted.append(row)
            continue
        if row.get('entry_kind') == 'group':
            group_id = row.get('group_id', '')
            if group_id in definitions:
                identity, enabled = definitions[group_id]
            elif isinstance(group_id, str) and group_id.startswith('merged_'):
                identity, enabled = _template_appearances().get(group_id), True
            else:
                identity, enabled = row.get('identity_id'), True
            if not identity:
                # A deleted group with no representative was already skipped by the launcher.
                continue
            row = dict(row, entry_kind='appearance', identity_id=identity)
            row.pop('group_id', None)
            if not enabled:
                row['weight'] = 0
        identity = row.get('identity_id')
        if identity and identity in by_identity:
            first = by_identity[identity]
            first['weight'] = first.get('weight', 1) + row.get('weight', 1)
        else:
            converted.append(row)
            if identity:
                by_identity[identity] = row
    peak = max((row.get('weight', 1) for row in by_identity.values()), default=0)
    if peak > 1000000:
        # Keep the same selection probabilities when merged weights exceed the per-entry limit.
        for row in by_identity.values():
            row['weight'] = 1000000 * (row.get('weight', 1) / peak)
    profile['entries'] = converted


def clean_document(doc, retired, legacy=None):
    definitions = {key: (identity, True) for key, identity in retired.items()}
    definitions.update(_definitions(legacy))
    definitions.update(_definitions(doc.pop('stage_director', None)))
    rules = doc.get('rulesets') or {}
    files = rules.get('files') or {}
    removed = {'chapter:' + key[4:] for key in retired if key.startswith('ch9_')}
    for name, rule in list(files.items()):
        identity = str(rule.get('identity', ''))
        group_id = 'ch9_' + identity
        rows = rule.get('entries') or []
        if (name == 'persona-' + identity + '.json' and len(rows) == 1 and
                rows[0].get('entry_kind') == 'group' and rows[0].get('group_id') == group_id and group_id in retired):
            del files[name]
            removed.add('identity:' + identity)
        else:
            _convert_entries(rule, definitions)
            for profile in rule.get('pools', {}).values():
                _convert_entries(profile, definitions)
    pools = doc.get('pools') or doc
    for profile in pools.get('characters', {}).values():
        _convert_entries(profile, definitions)
    state = rules.get('state') or {}
    for sinner, key in list(state.get('active', {}).items()):
        if key in removed:
            del state['active'][sinner]
    if (state.get('selected') or {}).get('id') in removed:
        state['selected'] = None
    return doc


def _save_if_changed(path, data):
    if data == _read(path):
        return
    tmp = path.with_suffix('.migration-tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    os.replace(tmp, path)


def migrate(root, stage_files):
    """Caller holds the common save lock. Remove definitions only after all live references are migrated."""
    root = Path(root)
    retired = defaults(root)
    old_file = root / 'stage_director.json'
    legacy = _read(old_file)
    for path in (root / 'schemes').glob('*.json'):
        try:
            doc = _read(path)
            if not isinstance(doc, dict) or doc.get('schema') not in (1, 2, 3):
                continue
            clean_document(doc, retired, legacy)
        except (ValueError, TypeError, AttributeError, KeyError):
            # An unreadable preset should stay available for repair without blocking game startup.
            continue
        _save_if_changed(path, doc)
    folder = root / 'rulesets'
    paths = [p for p in folder.glob('*.json') if re.fullmatch(r'global\\.json|persona-\d+\.json', p.name)]
    files = {p.name: _read(p) for p in paths}
    state, pools = root / 'ruleset_state.json', root / 'custom_pools.json'
    doc = clean_document({'pools': _read(pools), 'rulesets': {'files': files, 'state': _read(state)}}, retired, legacy)
    _save_if_changed(state, doc['rulesets']['state'])
    _save_if_changed(pools, doc['pools'])
    for path in paths:
        if path.name in files:
            _save_if_changed(path, files[path.name])
        else:
            path.unlink()
    stage_files.ensure_runtime(root)
    old_file.unlink(missing_ok=True)
