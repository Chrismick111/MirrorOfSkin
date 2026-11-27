"""Read Mod Spec v2 skin declarations and their scoped archive resources."""
from collections import defaultdict
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import PurePosixPath, PureWindowsPath
import stat
from typing import Optional
from zipfile import ZipInfo

from custom_asset_manifest import relative_path
from scan.custom_portraits import validate_png


MAX_METADATA = 1024 * 1024
MAX_SKINS = 64
MAX_MEMBERS = 8192


@dataclass(frozen=True, eq=False)
class FrameSkin:
    pack_root: PurePosixPath
    package_root: PurePosixPath
    skin_id: str
    personality: str
    label: str
    manifest: dict
    members: dict
    frames_dir: Optional[PurePosixPath]
    illust_dir: Optional[PurePosixPath]
    spine_dir: Optional[PurePosixPath]
    voice_dir: Optional[PurePosixPath]
    locale_exclusive_dir: Optional[PurePosixPath]
    portrait: Optional[ZipInfo]

    @property
    def visual(self):
        return self.manifest.get('visual', {})

    @property
    def audio(self):
        return self.manifest.get('voice', {})

    @property
    def locale(self):
        return self.manifest.get('locale', {})

    @property
    def combo(self):
        return self.manifest.get('combo', {})


def _key(path):
    return str(path).casefold()


def _path(name):
    try:
        path = relative_path(name, 2048)
    except ValueError as error:
        raise ValueError(f'Mod Spec v2 声明或压缩包包含无效路径：{name!r}') from error
    if any(PureWindowsPath(part).is_reserved() for part in path.parts):
        raise ValueError('Mod Spec v2 声明或压缩包包含系统保留路径：' + str(path))
    return path


def _check_file(info):
    _path(info.orig_filename)
    if stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG):
        raise ValueError('Mod Spec v2 资源必须是普通文件：' + info.filename)


def _unique_keys(items):
    result = {}
    for name, value in items:
        if name in result:
            raise ValueError('Mod Spec v2 声明包含重复字段：' + name)
        result[name] = value
    return result


def _read_json(archive, info):
    if not 0 < info.file_size <= MAX_METADATA:
        raise ValueError('Mod Spec v2 声明大小无效：' + info.filename)
    try:
        return json.loads(archive.read(info).decode('utf-8-sig'), object_pairs_hook=_unique_keys)
    except (ValueError, RecursionError) as error:
        raise ValueError('无法读取 Mod Spec v2 声明：' + info.filename) from error


def _object(data, name):
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ValueError('Mod Spec v2 声明字段必须是对象：' + name)
    return value


def _single_part(name):
    path = _path(name)
    if len(path.parts) != 1:
        raise ValueError('Mod Spec v2 标识必须是单个名称：' + str(path))
    return path


def _declared_path(folder, data, field):
    value = data.get(field)
    return folder / _path(value) if value not in (None, '') else None


def _select_portrait(folder, meta, illust_dir, manifest, members):
    preview = _declared_path(folder, meta, 'preview')
    if preview is not None and preview.suffix.casefold() == '.png':
        if _key(preview) in members:
            return members[_key(preview)]
    normal = _object(manifest, 'private_server').get('vanilla_normal_cg_key')
    if normal and illust_dir is not None:
        stem = _single_part(normal).name
        return members.get(_key(illust_dir / (stem + '_profile.png')))
    return None


def _read_skin(archive, pack_root, skin_id, file_index, skin_index):
    folder = pack_root / 'skins' / _single_part(skin_id)
    entries = file_index.get(_key(folder / 'manifest.json'), ())
    if len(entries) != 1:
        raise ValueError('找不到唯一的 Mod Spec v2 皮肤清单：' + str(folder))
    members = {}
    for key, info in skin_index[_key(folder)]:
        _check_file(info)
        if key in members or len(members) >= MAX_MEMBERS:
            raise ValueError('Mod Spec v2 皮肤资源重复或超出读取上限：' + info.filename)
        members[key] = info
    data = _read_json(archive, entries[0])
    if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data['schema_version'] != 2:
        raise ValueError('不支持的 Mod Spec 皮肤清单版本：' + str(folder))
    meta = _object(data, 'meta')
    target = _object(data, 'target')
    personality = target.get('personality_id')
    label = meta.get('display_name')
    if (meta.get('skin_id') != skin_id or target.get('kind') != 'personality'
            or type(personality) is not int or not 0 < personality <= 2147483647
            or not isinstance(label, str) or not label.strip()):
        raise ValueError('Mod Spec v2 皮肤的人格或作者名称无效：' + str(folder))
    visual, voice, locale = (_object(data, name) for name in ('visual', 'voice', 'locale'))
    for section, field in (('fx', 'dir'), ('locale', 'shared_optional_dir')):
        _declared_path(folder, _object(data, section), field)
    _object(data, 'combo')
    _object(data, 'private_server')
    illust = _declared_path(folder, visual, 'illust_dir')
    return FrameSkin(
        pack_root, folder, skin_id, str(personality), label.strip(), data, members,
        _declared_path(folder, visual, 'sd_frames_dir'), illust,
        _declared_path(folder, visual, 'spine_dir'), _declared_path(folder, voice, 'dir'),
        _declared_path(folder, locale, 'exclusive_dir'),
        _select_portrait(folder, meta, illust, data, members),
    )


def skin_member_roots(path):
    """Yield each enclosing skins/<id> folder, allowing wrapper folders."""
    for index, part in enumerate(path.parts[:-2]):
        if part.casefold() == 'skins':
            yield PurePosixPath(*path.parts[:index + 2])


def read_framepacks(archive):
    if not any(name.replace('\\', '/').rsplit('/', 1)[-1].casefold() == 'pack.json'
               for name in archive.namelist()):
        return []
    file_index = defaultdict(list)
    skin_index = defaultdict(list)
    candidates = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = PurePosixPath(info.filename.replace('\\', '/'))
        for root in skin_member_roots(path):
            skin_index[_key(root)].append((_key(path), info))
        if path.name.casefold() in ('pack.json', 'manifest.json'):
            file_index[_key(path)].append(info)
        if path.name.casefold() == 'pack.json':
            candidates.append((path, info))

    result = []
    for path, info in candidates:
        try:
            data = _read_json(archive, info)
        except ValueError:
            prefix = _key(path.parent / 'skins') + '/'
            if any(root.startswith(prefix) for root in skin_index):
                raise
            continue
        if not isinstance(data, dict) or not {'pack_id', 'skins'} <= data.keys():
            continue
        _check_file(info)
        if len(file_index[_key(path)]) != 1:
            raise ValueError('Mod Spec v2 包声明重复：' + info.filename)
        if type(data.get('schema_version')) is not int or data['schema_version'] != 2:
            raise ValueError('不支持的 Mod Spec 包声明版本：' + info.filename)
        _single_part(data['pack_id'])
        _declared_path(path.parent, data, 'preview')
        skin_ids = data['skins']
        if not isinstance(skin_ids, list) or not 0 < len(skin_ids) <= MAX_SKINS - len(result):
            raise ValueError('Mod Spec v2 包声明的皮肤数量无效：' + info.filename)
        if len({_key(_single_part(skin_id)) for skin_id in skin_ids}) != len(skin_ids):
            raise ValueError('Mod Spec v2 包声明包含重复皮肤：' + info.filename)
        result.extend(_read_skin(archive, path.parent, skin_id, file_index, skin_index) for skin_id in skin_ids)
    return result


def portrait_png(archive, skin):
    """Return a validated Workbench PNG for this skin."""
    if skin.portrait is None:
        return None
    from PIL import Image

    if not 0 < skin.portrait.file_size <= 16 * 1024**2:
        raise ValueError('Mod Spec v2 皮肤头像大小无效：' + skin.label)
    try:
        with archive.open(skin.portrait) as stream, Image.open(stream, formats=('PNG',)) as image:
            if max(image.size) > 4096:
                raise ValueError('Mod Spec v2 皮肤头像尺寸无效：' + skin.label)
            picture = image.convert('RGBA')
            picture.thumbnail((384, 384), Image.Resampling.LANCZOS)
            output = BytesIO()
            picture.save(output, format='PNG')
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError('无法读取 Mod Spec v2 皮肤头像：' + skin.label) from error
    data = output.getvalue()
    validate_png(data, max_dimension=512)
    return data
