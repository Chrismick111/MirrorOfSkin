"""Read CustomAssetLoader battle-model bindings without running its loader."""
from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import PurePosixPath


MAX_MANIFEST = 8 * 1024**2
MAX_BUNDLE = 512 * 1024**2
MAX_MODELS = 4 * 1024**3
UNITY_BUNDLE_MAGIC = b'UnityFS\0'
_LABELS = {'sd_personality': 'SD_Personality', 'sd_enemy': 'SD_Enemy'}
_SCRIPT_SUFFIXES = {'.dll', '.exe', '.com', '.msi', '.scr', '.bat', '.cmd', '.ps1',
                    '.js', '.vbs', '.py', '.lua', '.cs', '.sh', '.jar'}


@dataclass(frozen=True)
class Binding:
    label: str
    resource_id: str
    address: str


def bundle_directory(path):
    return next((PurePosixPath(*path.parts[:i+1]) for i, part in enumerate(path.parts[:-1])
                 if part.casefold() == 'custom_bundles'), None)


def is_manifest(path):
    return path.name.casefold() == 'asset_manifest.json' and path.parent == bundle_directory(path)


def relative_path(value, limit):
    if not isinstance(value, str) or not 0 < len(value) < limit:
        raise ValueError('CustomAssetLoader 清单包含无效路径')
    value = value.replace('\\', '/')
    parts = value.split('/')
    if any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in parts) or any(
            ch in ':<>"|?*' or ord(ch) < 32 for ch in value):
        raise ValueError('CustomAssetLoader 清单包含无效路径：' + value)
    return PurePosixPath(value)


def read_manifest(archive):
    wanted, resources, manifests = {}, {}, set()
    for info in archive.infolist():
        path = PurePosixPath(info.filename.replace('\\', '/'))
        if info.is_dir() or not is_manifest(path):
            continue
        relative_path(info.filename, 2048)
        folder = path.parent
        key = str(folder).casefold()
        if key in manifests or len(manifests) >= 8192 or info.file_size > MAX_MANIFEST:
            raise ValueError('CustomAssetLoader 清单重复或超出读取上限：' + info.filename)
        manifests.add(key)
        try:
            data = json.loads(archive.read(info).decode('utf-8-sig'))
        except (ValueError, RecursionError) as error:
            raise ValueError('无法读取 CustomAssetLoader 清单：' + info.filename) from error
        rows = data.get('overrides') if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) > 8192:
            raise ValueError('CustomAssetLoader 清单的 overrides 无效：' + info.filename)
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('label'), str):
                continue
            label = _LABELS.get(row['label'].casefold())
            kind = row.get('assetType', 'GameObject')
            if label is None or not isinstance(kind, str) or kind.casefold() != 'gameobject':
                continue
            bundle = relative_path(row.get('bundle'), 512)
            address = relative_path(row.get('assetPath'), 1024)
            resource_id = str(relative_path(row.get('resourceId'), 512))
            if bundle.suffix.casefold() in _SCRIPT_SUFFIXES or is_manifest(folder / bundle):
                raise ValueError('CustomAssetLoader 清单指定的文件不是模型资源包：' + str(bundle))
            if address.suffix.casefold() != '.prefab':
                raise ValueError('CustomAssetLoader 战斗外观必须指向预制体：' + str(address))
            member = str(folder / bundle).casefold()
            target = member, str(address).casefold()
            resource = key, label, resource_id.casefold()
            previous = resources.get(resource)
            if previous is not None:
                if previous != target:
                    raise ValueError('CustomAssetLoader 资源标识指向多个预制体：' + resource_id)
                continue
            if len(resources) >= 8192:
                raise ValueError('CustomAssetLoader 战斗资源数量超出读取上限')
            resources[resource] = target
            wanted.setdefault(member, []).append(Binding(label, resource_id, str(address)))
    return wanted


def read_bindings(archive):
    wanted = read_manifest(archive)
    found = {}
    total = 0
    for info in archive.infolist():
        path = PurePosixPath(info.filename.replace('\\', '/'))
        key = str(path).casefold()
        if info.is_dir() or key not in wanted:
            continue
        relative_path(info.filename, 2048)
        total += info.file_size
        if key in found or not 8 <= info.file_size <= MAX_BUNDLE or total > MAX_MODELS:
            raise ValueError('CustomAssetLoader 模型包重复或超出读取上限：' + info.filename)
        found[key] = info, path, wanted[key]
    missing = wanted.keys() - found.keys()
    if missing:
        raise ValueError('CustomAssetLoader 清单指定的模型包不存在：' + min(missing))
    return [found[key] for key in wanted]


def resolve_prefabs(path, bindings, published):
    by_address = defaultdict(list)
    for prefab in published:
        by_address[prefab[0].replace('\\', '/').casefold()].append(prefab)
    selected = {}
    for binding in bindings:
        matches = by_address[binding.address.casefold()]
        if len(matches) != 1:
            raise ValueError(f'CustomAssetLoader 模型包 {path} 内找不到唯一的战斗预制体：{binding.address}')
        selected.setdefault(matches[0], []).append(binding)
    return [(aliases, prefab) for prefab, aliases in selected.items()]
