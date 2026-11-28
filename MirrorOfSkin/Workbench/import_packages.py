"""Names and durable ownership records for files under a plug-in's import folder."""
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import tempfile
from uuid import uuid4


DIRECTORY = 'imported-appearance'
LEGACY_DIRECTORY = '外来外观'
MARKER = '.mos-package.json'
LIBRARY_MARKER = '.mos-library.json'
BUILTIN = 'story_BRolandBaseAppearance'
_IDENTITY = re.compile(r'story_(WBImp_[0-9a-f]{24})\Z')
_MEDIADATA = re.compile(r'[0-9a-f]{64}\.bundle\Z')
_INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_DEVICES = {'CON', 'PRN', 'AUX', 'NUL', *(f'{kind}{i}' for kind in ('COM', 'LPT') for i in '123456789¹²³')}


def _safe_name(name):
    return (isinstance(name, str) and 0 < len(name) <= 70 and name not in ('.', '..')
            and not _INVALID_NAME.search(name) and name.rstrip(' .') == name
            and name.split('.', 1)[0].upper() not in _DEVICES
            and PureWindowsPath(name).name == name)


def _package_name(source):
    name = _INVALID_NAME.sub('_', Path(source).stem).strip().rstrip('.')
    if name.split('.', 1)[0].upper() in _DEVICES:
        name = '_' + name
    return name[:55].rstrip(' .') or '未命名压缩包'


def _plain_directory(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISDIR(info.st_mode) and not (
        getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def migrate_legacy(addon, *roots):
    """Rename the old Chinese import folder and repair locator prefixes.

    Older builds stored imported appearances under ``外来外观/`` and wrote that
    prefix into every ``.loc`` pointer.  Renaming the folder alone would orphan
    those pointers, so the locator text is rewritten as well.
    """
    addon = Path(addon)
    old, new = addon / LEGACY_DIRECTORY, addon / DIRECTORY
    if _plain_directory(old) and not new.exists():
        try:
            old.rename(new)
        except OSError:
            pass
    prefix = LEGACY_DIRECTORY + '/'
    for base in (addon, *[Path(root) for root in roots]):
        assets = base / 'Assets' / 'ImportedSkins'
        if not assets.is_dir():
            continue
        for locator in assets.glob('*.loc'):
            if locator.is_symlink():
                continue
            try:
                text = locator.read_text(encoding='utf8')
            except OSError:
                continue
            if text.startswith(prefix):
                try:
                    locator.write_text(DIRECTORY + text[len(LEGACY_DIRECTORY):], encoding='utf8')
                except OSError:
                    pass


def managed_root(addon, *, create=False):
    addon = Path(addon).resolve(strict=True)
    migrate_legacy(addon)
    path = addon / DIRECTORY
    if create:
        path.mkdir(exist_ok=True)
    if not _plain_directory(path):
        raise ValueError('外来外观目录不存在或不是普通文件夹')
    return path


def index_path(root):
    return Path(root) / 'Assets/ImportedSkins/import-packages.json'


def locator_path(root, identity):
    if identity == BUILTIN:
        return index_path(root).parent / 'BRolandBaseAppearance.loc'
    match = _IDENTITY.fullmatch(identity)
    if not match:
        raise ValueError('导入外观编号无效')
    return index_path(root).parent / (match[1] + '.loc')


def read_index(root):
    path = index_path(root)
    try:
        if path.is_symlink() or path.parent.resolve() != path.parent.absolute():
            raise ValueError('导入包索引路径无效')
        index = json.loads(path.read_bytes())
    except FileNotFoundError:
        return {'schema': 1, 'packages': []}
    if not isinstance(index, dict) or index.get('schema') != 1 or not isinstance(index.get('packages'), list):
        raise ValueError('导入包索引格式无效')
    if (index.get('library') is not None and not _valid_uuid(index['library'])) or (
        index['packages'] and not _valid_uuid(index.get('library'))
    ):
        raise ValueError('导入包库编号格式无效')
    history = index.get('library_history', {})
    if (not isinstance(history, dict) or not all(_valid_uuid(value) for value in history)
            or any(not isinstance(ids, list) or not all(valid_identity(value) for value in ids)
                   or len(ids) != len(set(ids)) for ids in history.values())
            or not isinstance(index.get('creating_library', False), bool)):
        raise ValueError('导入包库编号格式无效')
    seen, names, identities = set(), set(), set()
    for item in index['packages']:
        if (not isinstance(item, dict) or not isinstance(item.get('source'), str)
                or not isinstance(item.get('identities'), list) or not _safe_name(item.get('directory'))
                or not _valid_uuid(item.get('id'))
                or item['id'] in seen or item['directory'].casefold() in names):
            raise ValueError('导入包索引格式无效')
        for identity in item['identities']:
            if not valid_identity(identity) or identity in identities:
                raise ValueError('导入包外观编号重复或无效')
            identities.add(identity)
        missing = item.get('missing_identities', [])
        if (not isinstance(missing, list) or not all(valid_identity(value) for value in missing)
                or len(missing) != len(set(missing)) or set(missing) - set(item['identities'])):
            raise ValueError('导入包待恢复外观编号无效')
        seen.add(item['id'])
        names.add(item['directory'].casefold())
    return index


def valid_identity(identity):
    return isinstance(identity, str) and (identity == BUILTIN or bool(_IDENTITY.fullmatch(identity)))


def _valid_uuid(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[0-9a-f]{32}', value))


def read_library(addon):
    """Check that the installed directory belongs to the current import library."""
    path = Path(addon).resolve(strict=True) / DIRECTORY
    if not _plain_directory(path):
        return None
    marker = path / LIBRARY_MARKER
    if marker.is_symlink():
        raise ValueError('外观库目录标识不是普通文件')
    try:
        value = json.loads(marker.read_bytes())
    except FileNotFoundError:
        return None
    if not isinstance(value, dict) or not _valid_uuid(value.get('id')):
        raise ValueError('外观库目录标识格式无效')
    return value['id']


def ensure_library(root, addon):
    """Resume a recorded library, or rebuild an empty one while retaining package metadata."""
    index = read_index(root)
    observed = read_library(addon)
    current = index.get('library')
    if observed is not None and current == observed:
        if index.pop('creating_library', False):
            write_index(root, index)
        return observed

    history = index.get('library_history', {})
    parent = managed_root(addon, create=True)
    known_library = observed is not None and (current is None or observed in history)
    if not known_library:
        marker = parent / LIBRARY_MARKER if observed is not None else None
        if any(child != marker for child in parent.iterdir()):
            raise ValueError('当前安装目录与外观库索引不匹配，请确认原外来外观文件夹还在')

    if observed is not None or not index.get('creating_library'):
        library = observed or uuid4().hex
        if current and not index.get('creating_library'):
            known = set(history.get(current, []))
            history[current] = sorted(
                identity for package in index['packages'] for identity in package['identities']
                if identity in known or identity not in package.get('missing_identities', [])
            )
        index['library'] = library
        if history:
            index['library_history'] = history
        for package in index['packages']:
            if package['identities']:
                package['missing_identities'] = sorted(package['identities'])
        if observed is None:
            index['creating_library'] = True
        else:
            index.pop('creating_library', None)
        # Persist protection before writing a new marker. An interrupted
        # rebuild resumes with the same library identifier on the next call.
        write_index(root, index)
    if observed is None:
        if any(parent.iterdir()):
            raise ValueError('外来外观目录在检查期间发生变化')
        _write_marker(parent / LIBRARY_MARKER, index['library'])
        index.pop('creating_library')
        write_index(root, index)
    return index['library']


def _write_marker(path, owner):
    # Stage beside the managed folder so a crash leaves the recovery root empty
    # and the next attempt can safely resume. Never replace an observed marker.
    fd, staging = tempfile.mkstemp(dir=path.parent.parent, prefix='.mos-marker-')
    try:
        with os.fdopen(fd, 'wb') as marker:
            marker.write(encode_index({'id': owner}))
        if os.name == 'nt':
            os.rename(staging, path)  # Windows rename refuses to replace an existing file.
        else:
            os.link(staging, path)
    finally:
        Path(staging).unlink(missing_ok=True)


def _marked_package(folder, package_id):
    if not _safe_name(folder.name) or not _plain_directory(folder):
        return False
    path = folder / MARKER
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or (
            getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            return False
        value = json.loads(path.read_bytes())
    except FileNotFoundError:
        return False
    return isinstance(value, dict) and value.get('id') == package_id


def encode_index(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def write_index(root, index):
    path = index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, staging = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(encode_index(index))
        os.replace(staging, path)
    finally:
        Path(staging).unlink(missing_ok=True)


def prepare_package(root, addon, source, identities):
    """Reserve a folder. The caller holds the data save lock and commits the index."""
    library = ensure_library(root, addon)
    directory = managed_root(addon)
    index = read_index(root)
    index['library'] = library
    identities = set(identities)
    matches = [item for item in index['packages']
               if item['source'].casefold() == source.casefold() and identities.intersection(item['identities'])]
    if len(matches) > 1:
        raise ValueError('压缩包同时匹配多个已导入包，请在工作台中先确认对应外观')
    if any(item not in matches and identities.intersection(item['identities']) for item in index['packages']):
        raise ValueError('压缩包中的外观已归属其他包，请使用已登记的压缩包名称更新')
    created = False
    if matches:
        package = matches[0]
        folder = directory / package['directory']
        if not _marked_package(folder, package['id']):
            if set(package['identities']) != set(package.get('missing_identities', [])):
                raise ValueError('已导入包目录已移动或无法访问，请先刷新工作台')
            previous = [child for child in directory.iterdir() if _marked_package(child, package['id'])]
            if len(previous) > 1:
                raise ValueError('已导入包目录标识重复')
            folder = previous[0] if previous else None
            if folder is not None:
                if any(item is not package and item['directory'].casefold() == folder.name.casefold()
                       for item in index['packages']):
                    raise ValueError('已导入包目录与另一个登记目录重名')
                package['directory'] = folder.name
    else:
        folder = None
        package = {'id': uuid4().hex, 'source': source, 'identities': []}
        index['packages'].append(package)
    if folder is None:
        base = package.get('directory', _package_name(source))
        reserved = {p.name.casefold() for p in directory.iterdir()}
        reserved.update(item['directory'].casefold() for item in index['packages'] if item is not package)
        name, sequence = base, 2
        while name.casefold() in reserved:
            suffix = f' ({sequence})'
            name = base[:70 - len(suffix)].rstrip(' .') + suffix
            sequence += 1
        folder = directory / name
        folder.mkdir()
        package['directory'] = name
        try:
            _write_marker(folder / MARKER, package['id'])
        except OSError:
            try:
                folder.rmdir()
            except OSError:
                pass
            raise
        created = True
    package['identities'] = sorted(set(package['identities']) | identities)
    missing = set(package.pop('missing_identities', [])) - identities
    if missing:
        package['missing_identities'] = sorted(missing)
    return package, folder, encode_index(index), created


def discard_failed_package(folder, package_id, generated):
    """Roll back only files created by this attempt in its own new folder."""
    marker = folder / MARKER
    try:
        if not _plain_directory(folder) or marker.is_symlink():
            return
        if json.loads(marker.read_bytes()).get('id') != package_id:
            return
    except (OSError, ValueError, AttributeError):
        return
    for path in (*generated, marker):
        try:
            if path.parent == folder and not path.is_symlink():
                path.unlink(missing_ok=True)
        except OSError:
            continue
    try:
        folder.rmdir()
    except OSError:
        pass


def relative_model_path(package, filename):
    if not _safe_name(package['directory']) or (filename != 'BRoland.bundle' and not _MEDIADATA.fullmatch(filename)):
        raise ValueError('导入模型路径无效')
    return f"{DIRECTORY}/{package['directory']}/{filename}"


def clean_replaced_models(assets, previous, digest):
    """Reclaim previously located, verified models after a successful update."""
    if not previous:
        return
    references = set()
    try:
        for locator in assets.glob('*.loc'):
            if locator.is_symlink():
                return
            references.add(locator.read_text(encoding='utf-8').strip().casefold())
    except (OSError, UnicodeError):
        return
    for path, relative, checksum in previous:
        if relative.casefold() in references:
            continue
        try:
            if (_plain_directory(path.parent.parent) and _plain_directory(path.parent)
                    and not path.is_symlink() and path.is_file() and digest(path) == checksum):
                path.unlink()
        except OSError:
            # Unity or another reader may temporarily still hold the old model.
            continue


def share_model(path, filename):
    """Find a potential hard link source, never through a directory link."""
    for folder in path.parent.parent.iterdir():
        if folder == path.parent or not _plain_directory(folder):
            continue
        source = folder / filename
        if source.is_file() and not source.is_symlink():
            yield source
