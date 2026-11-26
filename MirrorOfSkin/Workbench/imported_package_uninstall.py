"""Remove registered appearances when their package folder is deleted."""
import json
import hashlib
import os
import re
import stat
from contextlib import nullcontext
from pathlib import Path, PurePosixPath

from delete_imported import delete_many, rule_paths
from import_packages import (MARKER, encode_index, ensure_library, index_path, locator_path, managed_root,
                             read_index, read_library, relative_model_path, valid_identity)

CATALOG = 'Assets/runtime/all_sinners_pools.json'
BUNDLE_NAME = re.compile(r'(?:[a-f0-9]{64}|BRoland)\.bundle')


def _safe_stat(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
        raise ValueError('管理目录包含链接或重解析点，暂未处理')
    return info


def _index_update(root, index):
    path = index_path(root)
    if path.exists():
        _safe_stat(path)
    if not path.parent.resolve().is_relative_to(root):
        raise ValueError('外观包记录路径无效')
    return {path: encode_index(index)}


def _bundle_path(addon, locator):
    if not locator.exists():
        return None
    _safe_stat(locator)
    content = locator.read_text(encoding='utf8')
    parts = PurePosixPath(content).parts
    if (len(parts) != 3 or parts[0] != '外来外观'
            or not BUNDLE_NAME.fullmatch(parts[2])
            or any(part in ('.', '..') or any(c in part for c in '\\:') for part in parts)):
        raise ValueError('外观模型位置无效')
    folder = addon / parts[0] / parts[1]
    bundle = folder / parts[2]
    for path in (addon / parts[0], folder, bundle):
        try:
            _safe_stat(path)
        except FileNotFoundError:
            return None
    if bundle.is_file():
        return bundle
    return None


def _files(root, addon, identities):
    wanted = {locator_path(root, identity) for identity in identities if valid_identity(identity)}
    present = {path for path in wanted if path.exists() or path.is_symlink()}
    paths = present.copy()
    # A remaining appearance may point at the same named file. Hard links in
    # other package folders hold a different pathname and remain usable.
    models = {_bundle_path(addon, path) for path in present}
    others = {_bundle_path(addon, path) for path in (root/'Assets/ImportedSkins').glob('*.loc')
              if path not in wanted} if models - {None} else set()
    paths.update(models - others - {None})
    return sorted(paths)


def _owns_package_folder(addon, index, package):
    try:
        if read_library(addon) != index['library']:
            return False
        folder = managed_root(addon) / package['directory']
        if not stat.S_ISDIR(_safe_stat(folder).st_mode):
            return False
        marker = folder / MARKER
        if not stat.S_ISREG(_safe_stat(marker).st_mode):
            return False
        value = json.loads(marker.read_bytes())
        return isinstance(value, dict) and value.get('id') == package['id']
    except (OSError, ValueError):
        return False


def delete_identity(root, addon, identity, *, lock_factory, replace=os.replace):
    """Implement the existing workbench delete command using the same transaction."""
    root, addon = Path(root).resolve(), Path(addon).resolve()
    with lock_factory(root/'workbench-save.lock'):
        index = read_index(root)
        package = next((p for p in index['packages'] if identity in p['identities']), None)
        loc = locator_path(root, identity)
        managed = package is not None or loc.exists() or loc.is_symlink()
        extra = []
        if loc.exists() or loc.is_symlink():
            if not stat.S_ISREG(_safe_stat(loc).st_mode):
                raise ValueError('外观定位文件无效')
            extra.append(loc)
        if package is not None:
            owns_folder = _owns_package_folder(addon, index, package)
            missing = package.get('missing_identities', [])
            if owns_folder and identity not in missing and extra:
                relative = loc.read_text(encoding='utf8')
                filename = PurePosixPath(relative).name
                if relative == relative_model_path(package, filename):
                    extra = _files(root, addon, [identity])
            package['identities'].remove(identity)
            if identity in missing:
                missing.remove(identity)
                if not missing:
                    package.pop('missing_identities')
            if not package['identities'] and not owns_folder:
                index['packages'].remove(package)
        # A grouped locator addresses a model only inside its verified package.
        # The legacy Roland mirror belongs to the old, ungrouped removal path.
        return delete_many(root, [identity], addon=None if managed else addon,
                           lock_factory=lambda _: nullcontext(), replace=replace,
                           index_updates=_index_update(root, index) if package is not None else None,
                           extra_files=extra)[0]


def prune_old_stock(root, addon, source, selected, obsolete):
    """After a successful reimport, retire unused stock siblings under the caller's save lock."""
    index = read_index(root)
    selected = set(selected)
    package = next((p for p in index['packages'] if p['source'].casefold() == source.casefold()
                    and selected.intersection(p['identities'])), None)
    if not package:
        return []
    candidates = (set(obsolete) & set(package['identities'])) - selected
    if not candidates or not _owns_package_folder(addon, index, package):
        return sorted(candidates)
    catalog = json.loads((root/CATALOG).read_bytes())
    protected = {e['identity_id'] for pool in catalog.values() for e in pool['entries']
                 if e.get('weight', 0) != 0 or e.get('enabled')}
    names = root / 'Workbench/appearance_names.json'
    if names.is_file():
        protected.update(json.loads(names.read_bytes()))
    for path in rule_paths(root):
        if path.is_file():
            body = path.read_bytes()
            protected.update(i for i in candidates if i.encode('ascii') in body)
    for identity in sorted(candidates - protected):
        portrait = root/'Workbench/user_portraits'/(hashlib.sha256(identity.encode()).hexdigest()+'.png')
        if portrait.exists():
            protected.add(identity)
            continue
        try:
            delete_identity(root, addon, identity, lock_factory=lambda _: nullcontext())
        except (ValueError, OSError):
            protected.add(identity)
    return sorted(candidates & protected)


def _snapshot(directory):
    """Only trust a stable, readable listing of the management root."""
    root_stat = _safe_stat(directory)
    visible = {}
    found_ids = {}
    untracked_directory = False
    for child in directory.iterdir():
        info = _safe_stat(child)
        visible[child.name.casefold()] = child
        if not stat.S_ISDIR(info.st_mode):
            continue
        marker = child/MARKER
        try:
            info = _safe_stat(marker)
        except FileNotFoundError:
            untracked_directory = True
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('外观包标识文件无效')
        marker_value = json.loads(marker.read_bytes())
        marker_id = marker_value.get('id') if isinstance(marker_value, dict) else None
        if not isinstance(marker_id, str) or marker_id in found_ids:
            raise ValueError('外观包标识文件无效')
        found_ids[marker_id] = child
    if not os.path.samestat(root_stat, _safe_stat(directory)):
        raise ValueError('外来外观目录在检查期间发生变化')
    return visible, found_ids, untracked_directory


def _find_missing(directory, entries):
    visible, found_ids, untracked = _snapshot(directory)
    missing = [package for package in entries
               if not (package.get('missing_identities') and
                       set(package['identities']) == set(package['missing_identities']))
               and package['directory'].casefold() not in visible
               and package['id'] not in found_ids]
    # An unmarked folder may be an existing package with its marker removed.
    if missing and untracked:
        raise ValueError('外来外观目录有未登记的子文件夹，暂时无法区分删除与改名')
    return missing


def _follow_renames(root, addon, directory, index):
    _, marker_paths, _ = _snapshot(directory)
    packages = index['packages']
    reserved = {p['directory'].casefold() for p in packages}
    previously_available = set(index.get('library_history', {}).get(index['library'], []))
    for package in packages:
        found = marker_paths.get(package['id'])
        if (found is None or (found.name.casefold() != package['directory'].casefold()
                    and found.name.casefold() in reserved)):
            continue
        renamed = found.name != package['directory']
        pending = set(package.get('missing_identities', []))
        if not renamed and not pending:
            continue
        moved = {**package, 'directory': found.name}
        if renamed:
            relative_model_path(moved, 'BRoland.bundle')  # Validate the new directory name.
        values = {}
        for identity in sorted(set(package['identities']) - pending) if renamed else []:
            locator = locator_path(root, identity)
            _safe_stat(locator)
            old = locator.read_bytes()
            filename = PurePosixPath(old.decode('utf8')).name
            if old != relative_model_path(package, filename).encode('utf8'):
                raise ValueError('改名外观包中包含不匹配的模型记录')
            new = relative_model_path(moved, filename).encode('utf8')
            model = addon / new.decode('utf8')
            _safe_stat(model)
            if not model.is_file():
                raise ValueError('改名外观包中的模型不完整')
            values[locator] = new
        for identity in sorted(pending & previously_available):
            locator = locator_path(root, identity)
            try:
                if not stat.S_ISREG(_safe_stat(locator).st_mode):
                    continue
                old = locator.read_text(encoding='utf8')
                parts = old.split('/')
                if len(parts) != 3:
                    continue
                _, old_directory, filename = parts
                if old != relative_model_path({'directory': old_directory}, filename):
                    continue
                new = relative_model_path(moved, filename)
                if not stat.S_ISREG(_safe_stat(addon / new).st_mode):
                    continue
            except (FileNotFoundError, ValueError):
                continue
            pending.remove(identity)
            if old != new:
                values[locator] = new.encode('utf8')
        if pending:
            moved['missing_identities'] = sorted(pending)
        else:
            moved.pop('missing_identities', None)
        if moved == package:
            continue
        revised = {**index, 'packages':[moved if p is package else p for p in packages]}
        values.update(_index_update(root, revised))
        # Reuse the deletion transaction's rollback without touching rules,
        # tombstones or voice state when a filename is the only change.
        delete_many(root, [], lock_factory=lambda _: nullcontext(), index_updates=values)
        reserved.discard(package['directory'].casefold())
        reserved.add(found.name.casefold())
        package.clear()
        package.update(moved)


def refresh_packages(root, addon, *, lock_factory):
    """Synchronize missing package folders, unless another safe explanation exists."""
    root, addon = Path(root).resolve(), Path(addon).resolve()
    report = {'removed': [], 'blocked': []}
    with lock_factory(root/'workbench-save.lock'):
        try:
            ensure_library(root, addon)
            index = read_index(root)
            if not index['packages']:
                return report
            directory = managed_root(addon, create=False)
            _follow_renames(root, addon, directory, index)
            absent = _find_missing(directory, index['packages'])
        except FileNotFoundError:
            return report
        except (OSError, ValueError) as error:
            report['blocked'].append({'directory': '外来外观', 'error': str(error)})
            return report
        for package in absent:
            if all(current['id'] != package['id'] for current in index['packages']):
                continue
            try:
                if read_library(addon) != index['library']:
                    raise ValueError('外来外观管理目录在检查期间发生变化')
                if not any(p['id'] == package['id'] for p in _find_missing(directory, [package])):
                    continue
                remaining = [p for p in index['packages'] if p['id'] != package['id']]
                missing = set(package.get('missing_identities', []))
                if missing:
                    remaining.insert(index['packages'].index(package), {**package, 'identities': sorted(missing)})
                catalog = json.loads((root/CATALOG).read_bytes())
                existing_ids = {entry['identity_id'] for group in catalog.values() for entry in group['entries']}
                identities = sorted((set(package['identities']) - missing) & existing_ids)
                revised = {**index, 'packages': remaining}
                delete_many(root, identities, addon=addon,
                            lock_factory=lambda _: nullcontext(),
                            index_updates=_index_update(root, revised),
                            extra_files=_files(root, addon, identities))
                index = revised
                report['removed'].append({'directory': package['directory'], 'identities': identities})
            except (OSError, ValueError) as error:
                report['blocked'].append({'directory': package['directory'], 'error': str(error)})
    return report
