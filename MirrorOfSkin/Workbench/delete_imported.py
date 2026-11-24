"""Build a deletion plan for one locally imported appearance.

The caller holds workbench-save.lock while planning and applying the plan.
Shared bundles and imported voice libraries belong to all their users.
"""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

IDENTITY = re.compile(r'story_(WBImp_[0-9a-f]{24})\Z')
BUNDLE = re.compile(r'[0-9a-f]{64}\.bundle\Z')


def plan(root, identity):
    root = Path(root).resolve()
    match = IDENTITY.fullmatch(identity)
    if not match:
        raise ValueError('只能删除本地导入的外观')
    look = match.group(1)
    assets = root / 'Assets' / 'ImportedSkins'
    catalog_path = root / 'Assets' / 'runtime' / 'all_sinners_pools.json'
    catalog = json.loads(catalog_path.read_bytes())
    found = []
    for group in catalog.values():
        for entry in group.get('entries', []):
            if entry.get('identity_id') == identity:
                found.append(entry)
    if len(found) != 1 or found[0].get('appearance_name') != look:
        raise ValueError('导入外观不存在或记录不唯一')

    cfg = assets / (look + '.cfg')
    lines = cfg.read_text(encoding='ascii').splitlines()
    if len(lines) != 7 or lines[0] != 'WBMOD1' or not BUNDLE.fullmatch(lines[3]):
        raise ValueError('外观资源记录无效')
    bundle = lines[3]
    timings = list(assets.glob(look + '-*.sst'))
    candidates = {bundle}
    for timing in timings:
        suffix = timing.name[len(look) + 1:-4]
        if re.fullmatch(r'[0-9a-f]{64}', suffix):
            candidates.add(suffix + '.bundle')
    referenced = set()
    for other in assets.glob('WBImp_*.cfg'):
        if other == cfg:
            continue
        parts = other.read_text(encoding='ascii').splitlines()
        if len(parts) != 7 or parts[0] != 'WBMOD1' or not BUNDLE.fullmatch(parts[3]):
            raise ValueError('其他外观资源记录无效，无法确认共享资源')
        referenced.add(parts[3])
    for timing in assets.glob('WBImp_*-*.sst'):
        if not timing.name.startswith(look + '-'):
            match = re.fullmatch(r'WBImp_[0-9a-f]{24}-([0-9a-f]{64})\.sst', timing.name)
            if match:
                referenced.add(match.group(1) + '.bundle')
    shared = bundle in referenced
    files = [cfg, *timings, *(assets / name for name in sorted(candidates - referenced))]
    for path in files:
        if path.parent.resolve() != assets.resolve() or path.is_symlink():
            raise ValueError('外观资源路径无效')
    portrait_dir = root / 'Workbench' / 'user_portraits'
    portrait = portrait_dir / (hashlib.sha256(identity.encode('utf8')).hexdigest() + '.png')
    if portrait.is_file():
        if portrait.is_symlink() or not portrait.resolve().is_relative_to(root):
            raise ValueError('头像路径无效')
        files.append(portrait)
    return {'identity': identity, 'appearance': look, 'catalog': catalog_path,
            'files': files, 'bundle_shared': shared}


def _clean_entries(obj, identity):
    """Remove appearance references from rule entry lists only."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == 'entries' and isinstance(value, list):
                obj[key] = [item for item in value if not (
                    isinstance(item, dict) and item.get('identity_id') == identity
                )]
            else:
                _clean_entries(value, identity)
    elif isinstance(obj, list):
        for item in obj:
            _clean_entries(item, identity)


def _has_stage_reference(obj, identity):
    if isinstance(obj, dict):
        stages = obj.get('stages')
        if isinstance(stages, list) and any(isinstance(stage, dict) and stage.get('identity_id') == identity for stage in stages):
            return True
        return any(_has_stage_reference(value, identity) for value in obj.values())
    if isinstance(obj, list):
        return any(_has_stage_reference(value, identity) for value in obj)
    return False


def delete(root, identity, *, lock_factory, replace=os.replace):
    """Delete catalog entry and references. The caller supplies FileLock.

    Files are moved to a private staging folder before commit and restored on
    failure. Voice banks remain available to other appearances.
    """
    root = Path(root).resolve()
    with lock_factory(root / 'workbench-save.lock'):
        item = plan(root, identity)
        catalog = json.loads(item['catalog'].read_bytes())
        for group in catalog.values():
            group['entries'] = [entry for entry in group['entries']
                                if entry.get('identity_id') != identity]
        changed = {item['catalog']: catalog}
        rules = [root / '自定义人格池.json', root / '演出编排.json', root / 'stage_director.json']
        rules_dir = root / '规则集'
        if rules_dir.is_dir():
            rules.extend(rules_dir.glob('*.json'))
        schemes = root / '方案'
        if schemes.is_dir():
            rules.extend(schemes.rglob('*.json'))
        for path in rules:
            if path.is_file():
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise ValueError('规则文件路径无效')
                data = json.loads(path.read_bytes())
                if _has_stage_reference(data, identity):
                    raise ValueError('此外观仍用于形态组，请先在形态组中移除后再删除')
                before = json.dumps(data, ensure_ascii=False, sort_keys=True)
                _clean_entries(data, identity)
                if json.dumps(data, ensure_ascii=False, sort_keys=True) != before:
                    changed[path] = data
        updates = {path: (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf8')
                   for path, data in changed.items()}
        tombstone = root / 'imported-skin-deletions.json'
        deleted = json.loads(tombstone.read_bytes()) if tombstone.is_file() else []
        if not isinstance(deleted, list) or not all(isinstance(value, str) and IDENTITY.fullmatch(value) for value in deleted):
            raise ValueError('导入外观删除记录无效')
        updates[tombstone] = (json.dumps(sorted(set(deleted) | {identity}), ensure_ascii=False) + '\n').encode('utf8')
        binding = root / 'Assets/ImportedVoices/bindings.tsv'
        if binding.is_file():
            lines = binding.read_bytes().splitlines(keepends=True)
            updates[binding] = b''.join(line for line in lines
                                        if line.split(b'\t', 1)[0] != item['appearance'].encode('ascii'))
        for metadata in (root / 'Assets/ImportedVoices').glob('*/voice.json'):
            if not metadata.resolve().is_relative_to((root / 'Assets/ImportedVoices').resolve()) or metadata.is_symlink():
                raise ValueError('语音资源路径无效')
            record = json.loads(metadata.read_bytes())
            looks = record.get('included_looks', [])
            if not isinstance(looks, list):
                raise ValueError('语音资源记录无效')
            if item['appearance'] in looks:
                record['included_looks'] = [look for look in looks if look != item['appearance']]
                updates[metadata] = (json.dumps(record, ensure_ascii=False, indent=2) + '\n').encode('utf8')
        originals = {path: path.read_bytes() if path.exists() else None for path in updates}
        moved = []
        written = []
        temp = Path(tempfile.mkdtemp(prefix='delete-import-', dir=root))
        try:
            recovery = {path: temp / ('original-' + str(index))
                        for index, path in enumerate(originals)}
            for path, backup in recovery.items():
                if originals[path] is not None:
                    backup.write_bytes(originals[path])
            (temp / 'recovery.json').write_text(json.dumps({
                backup.name: {'path': str(path.relative_to(root)), 'existed': originals[path] is not None}
                for path, backup in recovery.items()
            }, ensure_ascii=False), encoding='utf8')
            asset_map = {}
            for index, source in enumerate(item['files']):
                if source.exists():
                    fd, name = tempfile.mkstemp(prefix='.mos-delete-', dir=source.parent.resolve())
                    os.close(fd)
                    os.unlink(name)
                    asset_map[str(source.relative_to(root))] = name
            (temp / 'assets.json').write_text(json.dumps(asset_map, ensure_ascii=False), encoding='utf8')
            for source in item['files']:
                name = asset_map.get(str(source.relative_to(root)))
                if name:
                    target = Path(name)
                    physical_source=source.parent.resolve()/source.name
                    replace(physical_source, target)
                    moved.append((physical_source, target))
            for index, (path, data) in enumerate(updates.items()):
                fd, name = tempfile.mkstemp(prefix='.mos-write-', dir=path.parent.resolve())
                staged = Path(name)
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(data)
                    replace(staged, path.parent.resolve()/path.name)
                finally:
                    staged.unlink(missing_ok=True)
                written.append(path)
        except BaseException:
            try:
                for index, path in enumerate(reversed(written)):
                    if originals[path] is None:
                        path.unlink(missing_ok=True)
                    else:
                        fd, name = tempfile.mkstemp(prefix='.mos-restore-', dir=path.parent.resolve())
                        staged = Path(name)
                        try:
                            with os.fdopen(fd, 'wb') as stream:
                                stream.write(recovery[path].read_bytes())
                            os.replace(staged, path.parent.resolve()/path.name)
                        finally:
                            staged.unlink(missing_ok=True)
                for source, target in reversed(moved):
                    os.replace(target, source)
            except BaseException as recovery_error:
                raise RuntimeError('回滚未完成，资源保留在 ' + str(temp)) from recovery_error
            for path in temp.iterdir():
                path.unlink()
            temp.rmdir()
            raise
        for source, target in moved:
            target.unlink(missing_ok=True)
        for path in temp.iterdir():
            path.unlink()
        temp.rmdir()
        return {'identity_id': identity, 'bundle_shared': item['bundle_shared']}

