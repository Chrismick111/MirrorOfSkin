"""Validate and locate portraits supplied by a local appearance package."""
import json
from pathlib import Path
import re
import stat
from zipfile import ZipFile

from scan.custom_portraits import MAX_BYTES, validate_png


MANIFEST = 'mos-portraits.json'
IDENTITY = re.compile(r'story_(?:WBImp_[0-9a-f]{24}|BRolandBaseAppearance)')
MEMBER = re.compile('mos_portraits/' + IDENTITY.pattern + r'\.png', re.IGNORECASE | re.ASCII)
MAX_MANIFEST = 16 * 1024
MAX_PORTRAITS = 64
MAX_TOTAL = 16 * 1024 * 1024


def member_limit(name):
    if name.casefold() == MANIFEST:
        return MAX_MANIFEST
    if MEMBER.fullmatch(name):
        return MAX_BYTES
    return 0


def _unique_keys(items):
    result = dict(items)
    if len(result) != len(items):
        raise ValueError('外观头像清单中存在重复名称')
    return result


def _read(archive, entries, name, limit):
    matches = entries.get(name.casefold(), ())
    if len(matches) != 1 or matches[0].filename != name:
        raise ValueError('外观包中的头像文件不存在或名称重复：' + name)
    entry = matches[0]
    if (entry.is_dir() or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)
            or not 0 < entry.file_size <= limit):
        raise ValueError('外观头像文件格式或大小无效：' + name)
    return archive.read(entry)


def read_archive(path):
    with ZipFile(path) as archive:
        members = {}
        for entry in archive.infolist():
            if member_limit(entry.filename):
                members.setdefault(entry.filename.casefold(), []).append(entry)
        if MANIFEST not in members:
            return {}
        try:
            manifest = json.loads(_read(archive, members, MANIFEST, MAX_MANIFEST), object_pairs_hook=_unique_keys)
        except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise ValueError('外观头像清单无效') from exc
        if not isinstance(manifest, dict) or type(manifest.get('schema')) is not int or manifest['schema'] != 1:
            raise ValueError('外观头像清单版本无效')
        mapping = manifest.get('portraits')
        if not isinstance(mapping, dict) or len(mapping) > MAX_PORTRAITS:
            raise ValueError('外观头像数量无效')
        portraits = {}
        size = 0
        for identity, name in mapping.items():
            if not IDENTITY.fullmatch(identity) or name != 'mos_portraits/' + identity + '.png':
                raise ValueError('外观头像名称与声明的人格不一致')
            data = _read(archive, members, name, MAX_BYTES)
            size += len(data)
            if size > MAX_TOTAL:
                raise ValueError('外观头像总大小超出上限')
            validate_png(data, max_dimension=512)
            portraits[identity] = data
        return portraits


def folder_for(root):
    root = Path(root).resolve()
    folder = root / 'Workbench/imported_portraits'
    if folder.resolve() != folder:
        raise ValueError('导入头像目录无效')
    return folder


def path_for(root, identity):
    if not IDENTITY.fullmatch(identity):
        raise ValueError('导入头像的人格标识无效')
    path = folder_for(root) / (identity + '.png')
    if path.is_symlink():
        raise ValueError('导入头像文件路径无效')
    return path


def get(root, identity):
    if isinstance(identity, str) and IDENTITY.fullmatch(identity):
        path = path_for(root, identity)
        try:
            if path.is_file():
                return path.read_bytes()
        except FileNotFoundError:
            pass
    return None


def identities(root):
    try:
        return {path.stem for path in folder_for(root).iterdir()
                if path.suffix == '.png' and IDENTITY.fullmatch(path.stem)
                and not path.is_symlink() and path.is_file()}
    except FileNotFoundError:
        return set()
