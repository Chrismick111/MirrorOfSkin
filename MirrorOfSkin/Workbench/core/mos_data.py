"""Resolve the launcher-owned MOS_data directory and migrate legacy addon data.

FaustLauncher stores per-user data under ``%APPDATA%/FaustLauncher``.  This
module uses the launcher's public path helper when available, with a plain
APPDATA fallback for the standalone workbench and tests.
"""
import os
import pathlib
import shutil
import subprocess

DATA_NAME = 'MOS_data'
LAUNCHER_NAME = 'FaustLauncher'

# Files that live directly in MOS_data instead of the add-on directory.
ROOT_FILES = (
    '随机设置.json', '自定义人格池.json', '演出编排.json', '规则集状态.json',
    '停止随机运行.flag',
    'native_pools.bin', 'native_forms.json', 'native_stage_groups.bin',
    'pool_update_status.json', 'warmup_status.json', 'probe_asset.txt',
    'auto_forms.bin', 'auto_form_annotations.json', 'auto_internal_forms.jsonl',
    'auto_registry.json', 'identity_catalog.json', 'workbench_rules.bin',
    'workbench_forms.bin', 'fx-active.bin', '特效启用状态.json',
    'native.log', 'native_runtime.log', '诊断日志.txt', '诊断日志-上一份.txt',
    'stage_director.json',
)
ROOT_DIRS = ('规则集', '方案', '特效方案')
WORKBENCH_FILES = (
    'portrait_manifest.json', 'portrait_hashes.json', 'weekly_scan_status.json',
    'weekly_scan.lock', 'auto_translation_cache.json', 'scan_progress.json',
    'scan_state.json', 'scan.lock', 'discovered_units.json',
    'scan_last_error.txt', 'images_disabled.flag', 'image_resources.lock',
    'name_translations.json', 'resource-paths.json', 'workbench_gateway.json', 'server_build.json',
    'webview-window.json',
)
WORKBENCH_DIRS = ('portraits', 'local_portraits', 'user_portraits', 'chapter_art', 'resource-cache')
ANIMATION_PREFIXES = ('animation-times-',)


def _fallback_appdata():
    return os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming')


def data_dir(create=True):
    """Return ``%APPDATA%/FaustLauncher/MOS_data`` without touching add-on files."""
    override = os.environ.get('FAUST_MOS_DATA_ROOT')
    if override:
        root = pathlib.Path(override).resolve()
        if create:
            root.mkdir(parents=True, exist_ok=True)
        return root
    try:
        from functions.base.common import get_launcher_data_dir
        path = pathlib.Path(get_launcher_data_dir(DATA_NAME, create=create))
    except Exception:
        path = pathlib.Path(_fallback_appdata()) / LAUNCHER_NAME / DATA_NAME
        if create:
            path.mkdir(parents=True, exist_ok=True)
    return path


def _is_junction(path):
    try:
        return bool(os.lstat(path).st_file_attributes & 0x400) or path.is_symlink()
    except (OSError, AttributeError):
        return False


def _junction(link, target):
    link = pathlib.Path(link); target = pathlib.Path(target)
    if _is_junction(link):
        if link.resolve() == target.resolve():
            return link.is_dir()
        if not target.is_dir():
            return False
        os.rmdir(str(link))
    elif link.exists():
        return False
    link.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_dir():
        return False
    try:
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return link.is_dir()
    except Exception:
        try:
            os.symlink(target, link, target_is_directory=True)
            return link.is_dir()
        except Exception:
            return False


def _merge_move(src, dst):
    """Move legacy data to MOS_data, or merge missing files if both exist."""
    src = pathlib.Path(src); dst = pathlib.Path(dst)
    if not src.exists():
        return
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return
    if src.is_dir() and dst.is_dir():
        for child in list(src.iterdir()):
            target = dst / child.name
            if not target.exists():
                shutil.move(str(child), str(target))
            elif child.is_dir() and target.is_dir():
                _merge_move(child, target)
    elif src.is_file() and (not dst.exists() or dst.stat().st_size == 0):
        shutil.copy2(src, dst)
        try:
            src.unlink()
        except OSError:
            pass


def _migrate_file(addon, rel):
    src = pathlib.Path(addon) / rel
    dst = data_dir() / rel
    if src.is_file() and not dst.exists():
        _merge_move(src, dst)


def _migrate_dir(addon, rel):
    src = pathlib.Path(addon) / rel
    dst = data_dir() / rel
    if _is_junction(src):
        return
    if src.exists():
        _merge_move(src, dst)


def _animation_dirs(addon):
    root = pathlib.Path(addon)
    for path in root.iterdir():
        if path.is_dir() and path.name.startswith(ANIMATION_PREFIXES):
            yield path.name
    if (root / 'archive-times-candidate').is_dir():
        yield 'archive-times-candidate'


def _copy_shared(addon, data, rel):
    src = pathlib.Path(addon) / rel
    dst = pathlib.Path(data) / rel
    if not src.is_file():
        return
    try:
        if dst.is_file() and dst.read_bytes() == src.read_bytes():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    except OSError:
        pass


def _remove_junction(path):
    try:
        if _is_junction(path):
            os.rmdir(str(path))
    except OSError:
        pass


def remove_legacy_links(addon_root):
    """Remove old add-on junctions so uninstalling never traverses MOS_data."""
    addon = pathlib.Path(addon_root)
    for rel in ROOT_DIRS + tuple('Workbench/' + x for x in WORKBENCH_DIRS):
        _remove_junction(addon / rel)
    if addon.is_dir():
        for path in addon.iterdir():
            if path.is_dir() and path.name.startswith(ANIMATION_PREFIXES):
                _remove_junction(path)


def _atomic_copy(source, dest):
    from tempfile import NamedTemporaryFile
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest = dest.parent.resolve() / dest.name
    with NamedTemporaryFile(dir=dest.parent, delete=False) as stream:
        temp = pathlib.Path(stream.name)
    try:
        shutil.copy2(source, temp)
        os.replace(temp, dest)
    finally:
        temp.unlink(missing_ok=True)


def _prepare_workbench_tables(addon, data):
    source, dest = addon / 'Workbench/data', data / 'Workbench/data'
    if _junction(dest, source) or not source.is_dir():
        return
    if _is_junction(dest):
        raise OSError('无法连接新版工作台数据目录：' + str(dest))
    for table in source.glob('*.json'):
        if table.name.endswith('.local.json'):
            continue
        target = dest / table.name
        if not target.is_file() or target.read_bytes() != table.read_bytes():
            _atomic_copy(table, target)


def _prepare_assets(addon, data):
    """Keep writable catalog, skins, voices and timing outside the installed package."""
    import hashlib
    import json
    import re
    import sys
    # The launcher's scr.py can load this module directly by filename.
    core = str(pathlib.Path(__file__).resolve().parent)
    if core not in sys.path:
        sys.path.insert(0, core)
    from file_lock import FileLock
    from github_update import CATALOG, merge_catalog

    assets = data / 'Assets'
    shipped = addon / 'Assets'
    stamp = data / 'Workbench' / 'asset-seed.sha256'
    if not (addon / CATALOG).is_file():
        return
    manifest = addon / 'compatibility.json'
    fingerprint = hashlib.sha256((manifest.read_bytes() if manifest.is_file() else b'') +
                                 (addon / CATALOG).read_bytes()).hexdigest()
    # Check before taking the save lock, then again under the lock for other processes.
    def ready():
        return (not _is_junction(assets) and (data / CATALOG).is_file() and stamp.is_file()
                and stamp.read_text(encoding='ascii') == fingerprint)

    if ready():
        return
    with FileLock(data / 'workbench-save.lock'):
        if ready():
            return
        staging = data / '.asset-migration'
        if _is_junction(assets):
            # First copy old user files while the previous release still exists.
            old = assets.resolve()
            if old.is_dir():
                shutil.copytree(old, staging, dirs_exist_ok=True)
            os.rmdir(str(assets))
        if staging.is_dir() and not assets.exists():
            staging.rename(assets)
        assets.mkdir(exist_ok=True)
        local_catalog = data / CATALOG
        tombstone = data / 'imported-skin-deletions.json'
        deleted = json.loads(tombstone.read_bytes()) if tombstone.is_file() else []
        if not isinstance(deleted, list) or not all(isinstance(x, str) and re.fullmatch(r'story_WBImp_[0-9a-f]{24}', x) for x in deleted):
            raise ValueError('导入外观删除记录无效')
        looks = {x.removeprefix('story_') for x in deleted}
        source_skins = shipped / 'ImportedSkins'
        deleted_bundles, retained_bundles = set(), set()
        if looks:
            for folder in (source_skins, assets / 'ImportedSkins'):
                for cfg in folder.glob('WBImp_*.cfg'):
                    parts = cfg.read_text(encoding='ascii').splitlines()
                    if len(parts) != 7 or parts[0] != 'WBMOD1' or not re.fullmatch(r'[0-9a-f]{64}\.bundle', parts[3]):
                        raise ValueError('导入外观资源记录无效')
                    (deleted_bundles if cfg.stem in looks else retained_bundles).add(parts[3])
                for timing in folder.glob('WBImp_*-*.sst'):
                    match = re.fullmatch(r'(WBImp_[0-9a-f]{24})-([0-9a-f]{64})\.sst', timing.name)
                    if match:
                        (deleted_bundles if match[1] in looks else retained_bundles).add(match[2] + '.bundle')
        for source in shipped.rglob('*'):
            if not source.is_file():
                continue
            rel = source.relative_to(shipped)
            if rel.parts[0] == 'ImportedSkins':
                if any(rel.name == look + '.cfg' or rel.name.startswith(look + '-') and rel.name.endswith('.sst') for look in looks):
                    continue
                if rel.name in deleted_bundles - retained_bundles:
                    continue
            dest = assets / rel
            if dest == local_catalog:
                continue
            # Imported files are initially seeded and thereafter owned by the user.
            if dest.exists() and rel.parts[0] in ('ImportedSkins', 'ImportedVoices', 'CarraBases'):
                continue
            if (dest.is_file() and source.stat().st_size == dest.stat().st_size
                    and source.stat().st_mtime_ns == dest.stat().st_mtime_ns):
                continue
            _atomic_copy(source, dest)
        if local_catalog.is_file():
            merged = merge_catalog(local_catalog.read_bytes(), (addon / CATALOG).read_bytes())
            if looks:
                decoded = json.loads(merged)
                for group in decoded.values():
                    group['entries'] = [e for e in group['entries'] if e.get('identity_id') not in deleted]
                merged = (json.dumps(decoded, ensure_ascii=False, indent=2) + '\n').encode('utf8')
            temp = local_catalog.with_suffix('.seed.tmp')
            temp.write_bytes(merged)
            os.replace(temp, local_catalog)
        else:
            if looks:
                decoded = json.loads((addon / CATALOG).read_bytes())
                for group in decoded.values():
                    group['entries'] = [e for e in group['entries'] if e.get('identity_id') not in deleted]
                local_catalog.parent.mkdir(parents=True, exist_ok=True)
                temp = local_catalog.with_suffix('.seed.tmp')
                temp.write_text(json.dumps(decoded, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
                os.replace(temp, local_catalog)
            else:
                _atomic_copy(addon / CATALOG, local_catalog)
        temp = stamp.with_suffix('.tmp')
        temp.write_text(fingerprint, encoding='ascii')
        os.replace(temp, stamp)


def prepare(addon_root):
    """Migrate legacy user files once, then return the MOS_data root."""
    addon = pathlib.Path(addon_root).resolve()
    data = data_dir()
    if data.resolve() == addon:
        raise ValueError('工作台数据目录必须与插件安装目录分开')
    data.mkdir(parents=True, exist_ok=True)
    (data / 'Workbench').mkdir(parents=True, exist_ok=True)
    _prepare_assets(addon, data)
    _prepare_workbench_tables(addon, data)
    for name in ('compatibility.json', 'addon_info.json', 'boss_chapters.json'):
        _copy_shared(addon, data, name)
    for rel in ROOT_FILES:
        _migrate_file(addon, rel)
    for rel in ROOT_DIRS:
        _migrate_dir(addon, rel)
    for rel in WORKBENCH_FILES:
        _migrate_file(addon, 'Workbench/' + rel)
    for rel in WORKBENCH_DIRS:
        _migrate_dir(addon, 'Workbench/' + rel)
    for name in list(_animation_dirs(addon)):
        _migrate_dir(addon, name)
    # timeline_data is a shipped audited snapshot, not a user cache. If an old
    # build moved it into MOS_data, restore it before compatibility validation.
    timeline = addon / 'Workbench' / 'timeline_data'
    if not timeline.exists() and (data / 'Workbench' / 'timeline_data').is_dir():
        timeline.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(data / 'Workbench' / 'timeline_data', timeline)
    remove_legacy_links(addon)
    return data


def path(addon_root, rel):
    """Resolve a legacy relative path to its launcher-owned location."""
    rel = pathlib.PurePosixPath(str(rel).replace('\\', '/'))
    text = rel.as_posix()
    if rel.parts and rel.parts[0] == 'Assets':
        return data_dir() / text
    if text in ROOT_FILES or (rel.parts and rel.parts[0] in ROOT_DIRS):
        return data_dir() / text
    if text.startswith('Workbench/'):
        rest = text[len('Workbench/'):]
        if rest in WORKBENCH_FILES or rest.split('/', 1)[0] in WORKBENCH_DIRS:
            return data_dir() / text
    if rel.parts and rel.parts[0].startswith(ANIMATION_PREFIXES):
        return data_dir() / text
    if rel.parts and rel.parts[0] == 'archive-times-candidate':
        return data_dir() / text
    return pathlib.Path(addon_root) / text
