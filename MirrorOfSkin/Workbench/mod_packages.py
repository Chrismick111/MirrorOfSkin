"""Read self-describing appearance packages from the launcher's ``mods`` folder.

A package is a directory that carries two manifests:

* ``mod_info.json`` is the launcher-facing manifest.  The launcher owns
  ``settings.enable`` and lists the package there, so MOS only imports a
  package that the user enabled in the launcher.
* ``mos-mod.json`` describes how MOS turns the package payload into an
  ordinary local appearance archive.  Version one understands the ``bundles``
  strategy: declared UnityFS bundles are copied into ``custom_appearance/``
  and the package icon becomes the imported portrait.

The importer never gets a caller-supplied path.  Every entry point resolves a
package key against a fresh scan, and every payload path is confined to the
package directory.
"""
from collections import namedtuple
from contextlib import contextmanager
import json
from pathlib import Path, PurePosixPath
import re
import stat
from zipfile import ZipFile, ZIP_STORED

from bundle_migration import MANIFEST as RECIPE_MANIFEST, MAX_RECIPE
from custom_asset_manifest import MAX_BUNDLE, UNITY_BUNDLE_MAGIC
import imported_portraits
from model_workspace import import_workspace, model_tempdir
from scan.custom_portraits import validate_png


MANIFEST = 'mos-mod.json'
INFO = 'mod_info.json'
MAX_MANIFEST = 64 * 1024
MAX_ICON = 1024 * 1024
MAX_BUNDLES = 16
MAX_AUTHORS = 32
MAX_TEXT = 500
MOS = 'MOS'
_ID = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}\Z', re.ASCII)
_REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)


class _Manifest(namedtuple('Manifest', 'data bundles icon recipe')):
    """Manifest payload plus the resolved payload paths."""

    __slots__ = ()

    def __getitem__(self, key):
        return self.data[key] if isinstance(key, str) else tuple.__getitem__(self, key)

    def get(self, key, default=None):
        return self.data.get(key, default)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('清单包含重复字段：' + str(key))
        result[key] = value
    return result


def _plain_file(path):
    try:
        info = path.lstat()
    except OSError:
        return False
    return (stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
            and not getattr(info, 'st_file_attributes', 0) & _REPARSE)


def _plain_directory(path):
    try:
        info = path.lstat()
    except OSError:
        return False
    return (stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)
            and not getattr(info, 'st_file_attributes', 0) & _REPARSE)


def _read_json(path, label):
    if not _plain_file(path):
        raise ValueError(label + '不存在或不是普通文件')
    try:
        size = path.stat().st_size
        if not 0 < size <= MAX_MANIFEST:
            raise ValueError(label + '大小超出上限')
        return json.loads(path.read_bytes().decode('utf-8-sig'), object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(label + '无法读取') from exc


def _text(value, label, limit=MAX_TEXT):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(label + '无效')
    return value.strip()


def _relative(folder, value, label, *, suffix=None):
    if not isinstance(value, str) or not 0 < len(value) < 260:
        raise ValueError(label + '路径无效')
    relative = PurePosixPath(value.replace('\\', '/'))
    if relative.is_absolute() or any(
            part in ('', '.', '..') or ':' in part for part in relative.parts):
        raise ValueError(label + '路径无效')
    if suffix is not None and relative.suffix.casefold() != suffix:
        raise ValueError(label + '扩展名无效')
    base = folder.resolve()
    path = folder.joinpath(*relative.parts)
    try:
        if not path.resolve().is_relative_to(base):
            raise ValueError(label + '路径无效')
    except (OSError, RuntimeError) as exc:
        raise ValueError(label + '路径无效') from exc
    return relative, path


def _requirements(raw):
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or len(raw) > 32:
        raise ValueError('依赖声明无效')
    result = []
    for item in raw:
        name = _text(item, '依赖名称', 64)
        if name.casefold() not in {value.casefold() for value in result}:
            result.append(name)
    return result


def _mod_info(folder):
    info = _read_json(folder / INFO, INFO)
    if not isinstance(info, dict):
        raise ValueError(INFO + '格式无效')
    name = info.get('name')
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError(INFO + '缺少有效的显示名称')
    version = info.get('version', '')
    if not isinstance(version, str) or len(version) > 64:
        raise ValueError(INFO + '版本号无效')
    authors = info.get('authors', {})
    if not isinstance(authors, dict) or len(authors) > MAX_AUTHORS:
        raise ValueError(INFO + '作者信息无效')
    for key, value in authors.items():
        if not isinstance(key, str) or not isinstance(value, str) or len(key) > 64 or len(value) > 512:
            raise ValueError(INFO + '作者信息无效')
    settings = info.get('settings', {})
    if not isinstance(settings, dict):
        raise ValueError(INFO + '中的 settings 无效')
    if not isinstance(settings.get('enable', False), bool):
        raise ValueError(INFO + '中的 settings.enable 无效')
    required = _requirements(info.get('requires'))
    if MOS.casefold() not in {value.casefold() for value in required}:
        raise ValueError(INFO + ' 的 requires 未声明依赖 ' + MOS)
    return info


def _bundles(folder, values):
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_BUNDLES:
        raise ValueError('bundles 必须声明 1 到 %d 个模型文件' % MAX_BUNDLES)
    result = []
    names = set()
    for value in values:
        relative, path = _relative(folder, value, '模型文件')
        if len(relative.parts) != 2 or relative.parts[0].casefold() != 'bundles':
            raise ValueError('模型文件必须直接放在 bundles 目录中：' + value)
        name = relative.parts[1]
        if name.casefold() in names:
            raise ValueError('模型文件重复：' + name)
        names.add(name.casefold())
        if not _plain_file(path):
            raise ValueError('模型文件不存在或不是普通文件：' + name)
        size = path.stat().st_size
        if not 8 <= size <= MAX_BUNDLE:
            raise ValueError('模型文件大小超出上限：' + name)
        try:
            with path.open('rb') as stream:
                magic = stream.read(8)
        except OSError as exc:
            raise ValueError('模型文件无法读取：' + name) from exc
        if magic != UNITY_BUNDLE_MAGIC:
            raise ValueError('模型文件不是 UnityFS 模型包：' + name)
        result.append((name, path))
    return result


def _icon(folder, value):
    if value is None:
        return None
    relative, path = _relative(folder, value, '图标文件', suffix='.png')
    if len(relative.parts) != 1:
        raise ValueError('图标必须直接放在包目录中：' + value)
    if not _plain_file(path):
        raise ValueError('图标文件不存在或不是普通文件')
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError('图标文件无法读取') from exc
    if not 0 < len(data) <= MAX_ICON:
        raise ValueError('图标文件大小超出上限')
    validate_png(data, max_dimension=4096)
    return path


def _recipe(folder, value):
    if value is None:
        return None
    relative, path = _relative(folder, value, '合并配方', suffix='.json')
    if len(relative.parts) != 1:
        raise ValueError('合并配方必须直接放在包目录中：' + value)
    if not _plain_file(path):
        raise ValueError('合并配方不存在或不是普通文件')
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError('合并配方无法读取') from exc
    if not 0 < len(raw) <= MAX_RECIPE:
        raise ValueError('合并配方大小超出上限')
    try:
        data = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('合并配方无法读取') from exc
    if not isinstance(data, dict) or data.get('schema') != 1:
        raise ValueError('合并配方版本无效')
    return path


def _manifest(folder):
    data = _read_json(folder / MANIFEST, MANIFEST)
    if not isinstance(data, dict):
        raise ValueError(MANIFEST + '格式无效')
    allowed = {'schema', 'id', 'name', 'version', 'authors', 'description',
               'strategy', 'icon', 'identity', 'bundles', 'recipe', 'requires'}
    if not set(data) <= allowed:
        raise ValueError('清单包含不支持的字段：' + ', '.join(sorted(set(data) - allowed)))
    if type(data.get('schema')) is not int or data['schema'] != 1:
        raise ValueError('清单版本无效')
    package_id = data.get('id')
    if not isinstance(package_id, str) or not _ID.fullmatch(package_id):
        raise ValueError('包标识无效，只允许小写字母、数字、下划线和连字符')
    if data.get('strategy') != 'bundles':
        raise ValueError('暂不支持的外观包导入策略')
    name = data.get('name')
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError('清单缺少有效的显示名称')
    version = data.get('version', '')
    if not isinstance(version, str) or len(version) > 64:
        raise ValueError('清单版本号无效')
    description = data.get('description', '')
    if not isinstance(description, str) or len(description) > 2000:
        raise ValueError('清单描述无效')
    authors = data.get('authors', {})
    if not isinstance(authors, dict) or len(authors) > MAX_AUTHORS:
        raise ValueError('清单作者信息无效')
    for key, value in authors.items():
        if not isinstance(key, str) or not isinstance(value, str) or len(key) > 64 or len(value) > 512:
            raise ValueError('清单作者信息无效')
    identity = data.get('identity')
    if identity is not None and (not isinstance(identity, str)
                                 or not imported_portraits.IDENTITY.fullmatch(identity)):
        raise ValueError('清单 identity 不是受支持的人格标识')
    _requirements(data.get('requires'))
    bundles = _bundles(folder, data.get('bundles'))
    icon = _icon(folder, data.get('icon', 'icon.png'))
    recipe = _recipe(folder, data.get('recipe'))
    return _Manifest(dict(data), bundles, icon, recipe)


def _inspect(folder):
    manifest = _manifest(folder)
    info = _mod_info(folder)
    item = {
        'key': folder.name,
        'id': manifest['id'],
        'name': info['name'],
        'version': info.get('version') or manifest.get('version', ''),
        'description': info.get('desc') or manifest.get('description', ''),
        'authors': dict(info.get('authors') or manifest.get('authors') or {}),
        'icon': manifest.icon is not None,
        'identity': manifest.data.get('identity'),
        'status': 'ready',
        'error': '',
        '_folder': folder,
        '_manifest': manifest,
    }
    settings = info.get('settings') or {}
    if settings.get('enable') is not True:
        item['status'] = 'disabled'
        item['error'] = '请在启动器中启用该 Mod 后再导入'
    return item


def packages_folder(addon_root):
    return Path(addon_root).resolve().parent.parent / 'mods'


def _public(item):
    return {key: value for key, value in item.items() if not key.startswith('_')}


def scan(addon_root):
    """List every directory package under the launcher's ``mods`` folder."""
    folder = packages_folder(addon_root)
    if not _plain_directory(folder):
        return []
    packages = []
    ids = {}
    try:
        entries = sorted(folder.iterdir(), key=lambda path: path.name.casefold())
    except OSError:
        return []
    for entry in entries:
        if not _plain_directory(entry) or not _plain_file(entry / MANIFEST):
            continue
        try:
            item = _inspect(entry)
        except ValueError as exc:
            item = {'key': entry.name, 'id': '', 'name': entry.name, 'version': '',
                    'description': '', 'authors': {}, 'icon': False, 'identity': None,
                    'status': 'invalid', 'error': str(exc), '_folder': entry}
        if item['id']:
            previous = ids.get(item['id'])
            if previous is not None:
                item['status'] = 'invalid'
                item['error'] = '包标识与其他包重复：' + item['id']
            else:
                ids[item['id']] = entry.name
        packages.append(_public(item))
    return packages


def find(addon_root, key):
    """Return the inspected package for a public key, or ``None``."""
    if not isinstance(key, str) or not key or key in ('.', '..'):
        return None
    if Path(key).name != key:
        return None
    folder = packages_folder(addon_root)
    directory = folder / key
    if not _plain_directory(directory) or not _plain_file(directory / MANIFEST):
        return None
    try:
        item = _inspect(directory)
    except ValueError as exc:
        return {'key': key, 'id': '', 'name': key, 'version': '', 'description': '',
                'authors': {}, 'icon': False, 'identity': None, 'status': 'invalid',
                'error': str(exc), '_folder': directory}
    try:
        siblings = [entry for entry in folder.iterdir()
                    if entry != directory and _plain_directory(entry)
                    and _plain_file(entry / MANIFEST)]
    except OSError:
        siblings = []
    for sibling in siblings:
        try:
            other = _manifest(sibling).data.get('id')
        except ValueError:
            continue
        if other == item['id']:
            item['status'] = 'invalid'
            item['error'] = '包标识与其他包重复：' + str(item['id'])
            break
    return item


def icon_bytes(addon_root, key):
    item = find(addon_root, key)
    if item is None or not item.get('icon'):
        return None
    manifest = item.get('_manifest')
    if manifest is not None and manifest.icon is not None:
        try:
            return manifest.icon.read_bytes()
        except OSError:
            return None
    try:
        return (item['_folder'] / 'icon.png').read_bytes()
    except (KeyError, OSError):
        return None


def _portrait(path):
    from io import BytesIO
    from PIL import Image

    with Image.open(path) as source:
        image = source.convert('RGBA')
        image.thumbnail((512, 512), getattr(Image, 'Resampling', Image).LANCZOS)
        output = BytesIO()
        image.save(output, 'PNG', optimize=True)
    data = output.getvalue()
    validate_png(data, max_dimension=512)
    return data


Prepared = namedtuple('Prepared', 'archive portrait source')


def _owner_source(identity):
    """Return the registered archive name that already owns ``identity``.

    An explicit identity is the primary key of an imported package.  When a
    user previously imported the same appearance from another archive, the new
    package adopts that archive name so the importer updates the existing
    package instead of rejecting the transfer as an accidental rename.
    """
    if not identity:
        return None
    try:
        import import_packages
        import mos_data
        index = import_packages.read_index(mos_data.data_dir(create=False))
    except (OSError, ValueError, RuntimeError):
        return None
    for package in index['packages']:
        if identity in package.get('identities', ()):
            return package.get('source')
    return None


@contextmanager
def prepared_archive(addon_root, key, *, progress=None):
    """Build a stable-named normalized ZIP for the importer and clean it up."""
    item = find(addon_root, key)
    if item is None:
        raise ValueError('未找到外观包')
    if item['status'] != 'ready':
        raise ValueError(item['error'] or '外观包不可导入')
    manifest = item['_manifest']
    bundles = manifest.bundles
    source = _owner_source(manifest.data.get('identity')) or (manifest['id'] + '.zip')
    total = sum(path.stat().st_size for _, path in bundles)
    reported = -1

    def advance(written):
        nonlocal reported
        if progress is None:
            return
        percent = min(2, written * 3 // total) if total else 2
        if percent != reported:
            reported = percent
            progress(percent, '正在准备外观包')

    with import_workspace(addon_root), model_tempdir(prefix='workbench-mod-') as tmp:
        archive_path = Path(tmp) / (manifest['id'] + '.zip')
        portrait = None
        written = 0
        advance(0)
        with ZipFile(archive_path, 'w', ZIP_STORED, allowZip64=True) as archive:
            for name, path in bundles:
                archive.write(path, 'custom_appearance/' + name)
                written += path.stat().st_size
                advance(written)
            if manifest.recipe is not None:
                archive.writestr(RECIPE_MANIFEST, manifest.recipe.read_bytes())
            if manifest.icon is not None:
                image = _portrait(manifest.icon)
                identity = manifest.data.get('identity')
                if identity:
                    archive.writestr('mos-portraits.json', json.dumps({
                        'schema': 1, 'portraits': {identity: 'mos_portraits/' + identity + '.png'}
                    }, ensure_ascii=False))
                    archive.writestr('mos_portraits/' + identity + '.png', image)
                else:
                    portrait = image
        yield Prepared(archive_path, portrait, source)