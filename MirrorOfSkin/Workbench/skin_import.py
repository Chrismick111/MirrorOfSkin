"""Import local appearance artwork into the current workbench's catalog."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _module_paths
import mos_data
from import_progress import progress_range
from file_lock import FileLock
import imported_portraits

CATALOG = 'Assets/runtime/all_sinners_pools.json'
LOCAL = 'Assets/ImportedSkins'
BUILTIN = 'story_BRolandBaseAppearance'
# This verified native build resolves imported skins/voices from APPDATA.
# Seed or standalone builds without that exact capability keep the old mirror.
NATIVE_USER_ASSETS = frozenset({
    '564a4728e8a39cb5e2688f6f1bd95ba919f800ebba1e97a6d170b70b14c3da10',
})


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path=path.parent.resolve()/path.name
    fd, candidate = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(candidate, path)
    finally:
        Path(candidate).unlink(missing_ok=True)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def write_bundle(path, src, checksum):
    if path.is_file() and digest(path) == checksum:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path=path.parent.resolve()/path.name
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as dest, src.open('rb') as source:
            shutil.copyfileobj(source, dest)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def config(record, checksum, *, plugin_version=None):
    def field(key, pattern, limit):
        value = record[key]
        if (len(value)>=limit or not re.fullmatch(pattern, value, re.ASCII)
                or any(part in ('','.','..') for part in value.split('/'))):
            raise ValueError('模型包含不支持的资源标识：'+key)
        return value
    dependency = field('dependency', r'SD_(?:Personality|Enemy|Abnormality)/[A-Za-z0-9_./-]+\.prefab',512)
    asset = field('asset', r'(?i:assets)/[a-zA-Z0-9_ ./-]+\.prefab',1024)
    layout = field('layout', r'[a-zA-Z0-9_]+',256)
    actions = record['actions']
    attack_policy = None
    if record.get('policy') is not None:
        from generic_skin_policy import apply_action_policy, encode_policy
        verified = record['entry'].get('verified_attack_details', [])
        policy = record['policy']
        attack_policy = encode_policy(policy, verified, plugin_version=plugin_version)
        actions = apply_action_policy(policy, actions, verified)
    roles = ['0']*128
    animator = ['0']*128
    for key, value in actions['runtime_roles'].items():
        index = int(key)
        if not 0 <= index < 128 or not 1 <= value <= 7:
            raise ValueError('拼点动作编号无效')
        roles[index] = str(value)
    for index in actions['runtime_animator']:
        index = int(index)
        if not 0 <= index < 128:
            raise ValueError('守备动作编号无效')
        animator[index] = '1'
    values=['WBMOD1', dependency, asset, checksum+'.bundle', layout, ''.join(roles), ''.join(animator)]
    if attack_policy is not None:
        values[0]='WBMOD2'
        values.append(attack_policy)
    if record.get('coin_routes'):
        routes = record['coin_routes']
        seen = set()
        if len(routes) > 128:
            raise ValueError('逐币外观的技能映射超过 128 条')
        for route in routes:
            if len(route) != 5 or any(type(n) is not int for n in route):
                raise ValueError('逐币技能映射包含无效字段')
            skill, tier, count, slot, priority = route
            if not (0 < skill <= 2147483647 and tier in (1, 2, 3) and 1 <= count <= 128
                    and (7 <= slot <= 16 or 24 <= slot <= 34) and 0 <= priority <= 255):
                raise ValueError(f'逐币技能映射超出可播放范围：{route}')
            if (skill, tier, count) in seen:
                raise ValueError(f'逐币技能映射重复：技能 {skill}，阶 {tier}，硬币数 {count}')
            seen.add((skill, tier, count))
        slots = sorted({route[3] for route in routes})
        if attack_policy is not None or set(slots) - set(record['entry']['verified_attack_details']):
            raise ValueError('逐币映射与已验证的攻击槽不一致')
        values[0] = 'WBMOD3'
        values.extend(['R|0|' + ','.join(map(str, slots)),
                       'S|' + ';'.join(','.join(map(str, route)) for route in routes)])
    return ('\n'.join(values)+'\n').encode('ascii')


def _native_default_data_root(data_root):
    appdata = os.environ.get('APPDATA')
    if not appdata:
        return False
    native_root = Path(appdata) / 'FaustLauncher' / 'MOS_data'
    try:
        return native_root.is_absolute() and native_root.resolve() == Path(data_root).resolve()
    except (OSError, RuntimeError, ValueError):
        return False


def _native_reads_imports_in(data_root, addon_root):
    if not _native_default_data_root(data_root):
        return False
    try:
        return digest(Path(addon_root) / 'SinnersNative-v64.dll') in NATIVE_USER_ASSETS
    except (OSError, RuntimeError, ValueError):
        return False


def mirror_import_assets(data_root, addon_root, *, reads_user_assets=False):
    """Publish only resources that the installed runtime loads from the add-on."""
    folders = ('Assets/Roland',)
    if not reads_user_assets and not _native_reads_imports_in(data_root, addon_root):
        folders += ('Assets/ImportedSkins', 'Assets/ImportedVoices')
    for rel in folders:
        src, dst = Path(data_root) / rel, Path(addon_root) / rel
        if not src.is_dir():
            continue
        for path in src.rglob('*'):
            if not path.is_file() or path.suffix == '.loc' or path.name == 'import-packages.json':
                continue
            if (rel == 'Assets/Roland' and path.name == 'BRoland.bundle'
                    and (Path(data_root) / LOCAL / 'BRolandBaseAppearance.loc').is_file()):
                continue
            target = dst / path.relative_to(src)
            if target.resolve() == path.resolve():
                continue
            try:
                write_bundle(target, path, digest(path))
            except OSError as exc:
                raise OSError('无法同步导入资源：' + str(target)) from exc


def import_skin(archive, addon, *, name=None, unity=None, progress=None, check_cancelled=None,
                default_portrait=None, source=None, source_kind=None, source_name=None,
                source_version=None):
    from contextlib import ExitStack
    from appearance_dialogue import scan_archive
    from dialogue_status import apply_binding, runtime_bindings
    from voice_binding import companion_archive, reconcile, signal_runtime
    from mod_archive import normalized
    from carra_import import expanded
    from zipfile import ZipFile,BadZipFile
    from bank_mod import import_banks
    from model_workspace import import_workspace
    from skin_assets import _members
    from custom_asset_manifest import read_bindings
    def report(percent, message):
        if check_cancelled is not None:
            check_cancelled()
        if progress is not None:
            progress(percent, message)
    report(0, '正在检查插件和导入文件')
    addon_root=Path(addon).resolve()
    root=addon_root
    manifest = json.loads((root/'compatibility.json').read_bytes())
    if manifest.get('local_skin_import')!=1:
        raise ValueError('请选择支持本地外观导入的工作台。')
    grouped = manifest.get('import_package_folders') == 1
    if grouped:
        dll = manifest.get('dll', 'SinnersNative-v64.dll')
        expected = manifest.get('package_files', {}).get(dll)
        if (dll != 'SinnersNative-v64.dll' or not expected or not (root/dll).is_file()
                or digest(root/dll) != expected):
            raise ValueError('外来外观目录需要此版本的完整游戏核心，请重新安装插件')
    root=mos_data.prepare(root)
    report(3, '正在读取压缩包')
    with import_workspace(addon_root), normalized(archive) as container, ExitStack() as companions:
        portraits = imported_portraits.read_archive(container)
        expanded_members = {}
        path = companions.enter_context(expanded(container, root, unity, source_members=expanded_members))
        with ZipFile(path) as z:
            has_banks=any(i.filename.lower().endswith('.bank') for i in z.infolist())
            workflow = None
            has_models = not has_banks or bool(_members(z) or read_bindings(z))
            if not has_models:
                from framepack_manifest import read_framepacks
                has_models = bool(read_framepacks(z))
            if not has_models:
                from private_appearance_workflow import PrivateAppearanceWorkflow
                workflow = PrivateAppearanceWorkflow.discover(z, unity)
                has_models = bool(workflow.motions or workflow.coin_recipes or
                                  any(d.has_motions or d.appearance.startswith('!') for d in workflow.remaining))
            if portraits and not has_models:
                raise ValueError('外观头像需要与相应的战斗外观一起导入')
        scans = []
        companion = voice_path = None
        companion_warning = ''
        if has_models:
            report(4, '正在检查外观包中的战斗语音和气泡')
            scans.append(scan_archive(path))
            if not has_banks:
                try:
                    companion = companion_archive(Path(archive).resolve())
                    if companion:
                        voice_path = companions.enter_context(normalized(companion))
                        scans.append(scan_archive(voice_path))
                except (OSError, ValueError, RuntimeError, BadZipFile) as error:
                    companion_warning = str(error)
        rows = (_import_normalized(path, root, name=name, unity=unity, dialogue_scans=scans,
                                   package_addon=addon_root if grouped else None,
                                   package_source=source or Path(archive).name, progress=progress_range(report, 5, 94),
                                   check_cancelled=check_cancelled, workflow=workflow, portraits=portraits,
                                   author_archive=container, expanded_members=expanded_members,
                                   default_portrait=default_portrait,
                                   package_kind=source_kind, package_name=source_name,
                                   package_version=source_version,
                                   framepack_dialogue=grouped and manifest.get('framepack_dialogue') == 1)
                if has_models else [])
        included=[r['identity_id'][6:] for r in rows if r['identity_id'].startswith('story_WBImp_')]
        declared=[r['identity_id'][6:] for r in rows if r.get('voice_declared')]
        report(95, '正在检查配套语音')
        if has_banks:
            if check_cancelled is not None:
                check_cancelled(committing=True)
            try:
                bank_row = import_banks(path,root,name,source=Path(archive).stem,included=included,scoped=bool(declared))
                if bank_row:
                    rows.append(bank_row)
            except (OSError,ValueError,BadZipFile) as error:
                if not rows:
                    raise
                companion_warning = str(error)
        if included and voice_path is not None:
            try:
                voice=import_banks(voice_path,root,source=companion.stem,included=declared,scoped=bool(declared))
                if voice:
                    for row in rows:row['voice_companion']=companion.name
            except (OSError,ValueError,RuntimeError,BadZipFile) as error:
                companion_warning = str(error)
        if companion_warning:
            for row in rows:
                row['voice_warning']='；'.join(filter(None, (row.get('voice_warning'), companion_warning)))
        report(98, '正在同步外观库')
        mapped=reconcile(root)
        bindings=runtime_bindings(root, addon_root)
        mirror_import_assets(root, addon_root, reads_user_assets=grouped)
        signal_runtime(root)
        for row in rows:
            if row.get('kind')=='voice':
                row['connected_to']=[label for rev,label in mapped.values() if rev==row['revision']]
            else:
                identity = row['identity_id']
                row['voice_connected'] = (identity.removeprefix('story_') in mapped
                                          or bindings.get(identity, {}).get('voice') == 'connected')
                apply_binding(row, bindings)
    report(100, '导入完成')
    return rows


def install_roland_bundles(archive, root, *, destination=None):
    """Build the unified model from the user's original three-bundle archive."""
    from roland_merge import build_roland_bundle
    root = Path(root)
    bundle, metadata, model_voice_evidence = build_roland_bundle(archive, with_voice=True)
    expected = root / 'Assets/runtime/story_native/story_BRolandBaseAppearance.bin'
    if not expected.is_file() or expected.read_bytes() != metadata:
        raise ValueError('生成的罗兰动作数据与工作台不匹配，未替换现有模型')
    path = destination if destination is not None else root / 'Assets/Roland/BRoland.bundle'
    if path.is_symlink():
        raise ValueError('外观模型文件不是普通文件')
    if not path.is_file() or digest(path) != hashlib.sha256(bundle).hexdigest():
        write_atomic(path, bundle)
    return model_voice_evidence


def _import_normalized(archive, addon, *, name=None, unity=None, package_addon=None, package_source=None,
                       progress=None, check_cancelled=None, workflow=None, dialogue_scans=(), portraits=None,
                       framepack_dialogue=False, author_archive=None, expanded_members=None,
                       default_portrait=None, package_kind=None, package_name=None, package_version=None):
    from contextlib import ExitStack
    from zipfile import ZipFile
    from appearance_authors import read_attribution
    from skin_assets import build_assets
    from model_workspace import model_tempdir
    from private_identity import PrivateIdentities
    root, archive = Path(addon).resolve(), Path(archive).resolve()
    manifest = json.loads((root/'compatibility.json').read_bytes())
    if manifest.get('local_skin_import') != 1:
        raise ValueError('请选择支持本地外观导入的工作台。')
    if not archive.is_file():
        raise ValueError('找不到所选压缩包')
    if portraits is None:
        portraits = {}
    report = progress_range(progress)
    report(0, '正在准备模型读取组件')
    if unity is None:
        import resource_tools
        unity = resource_tools.unity()
    results = []
    source_name = package_source or archive.name
    source_stem = Path(source_name.casefold()).stem
    registered = json.loads((root/CATALOG).read_bytes())
    registered = [entry for group in registered.values() for entry in group['entries']]
    if package_addon is not None:
        from import_packages import read_index

        other_sources = {identity for package in read_index(root)['packages']
                         if package['source'].casefold() != source_name.casefold()
                         for identity in package['identities']}
        registered = [entry for entry in registered if entry['identity_id'] not in other_sources]
    with model_tempdir(prefix='faust-skin-') as tmp:
        records = list(build_assets(archive, Path(tmp), unity, name=name,
                                    progress=progress_range(report, 3, 90),
                                    registered=registered, source_name=source_name, workflow=workflow,
                                    framepack_dialogue=framepack_dialogue))
        if not records:
            raise ValueError('压缩包内没有可加入池的战斗外观')
        with ZipFile(author_archive or archive) as authors:
            author_credits = read_attribution(authors, records, expanded_members=expanded_members)
        from dialogue_status import detected_status
        for rec in records:
            portrait = rec.pop('portrait', None)
            if portrait is not None:
                portraits.setdefault(rec['entry']['identity_id'], portrait)
            if dialogue_scans:
                rec['dialogue_detection'] = detected_status(rec, dialogue_scans, records)
        if default_portrait is not None:
            from scan.custom_portraits import validate_png
            validate_png(default_portrait, max_dimension=512)
            produced = {'story_' + rec['look'] for rec in records if rec.get('builtin') != 'roland'}
            if any(rec.get('builtin') == 'roland' for rec in records):
                produced.add(BUILTIN)
            if len(produced) != 1:
                raise ValueError('外观包包含多个外观，无法自动确定图标对应的人格；'
                                 '请在 mos-mod.json 中声明 identity')
            portraits.setdefault(produced.pop(), default_portrait)
        if package_addon is not None:
            from skill_ui import HEADER, SUFFIX, collect, icon_names, obsolete_icons
            from skill_ui_import import collect_external
            with ExitStack() as archive_files:
                skin_archive = archive_files.enter_context(ZipFile(author_archive or archive))
                model_archive = (archive_files.enter_context(ZipFile(archive))
                                 if author_archive and Path(author_archive).resolve() != archive else skin_archive)
                external = collect_external(skin_archive, records, model_archive=model_archive,
                                            expanded_members=expanded_members, unity=unity)
                skill_ui = collect(skin_archive, records, portraits, external=external)
        report(91, '正在校验外观与动作')
        pending = {}
        assets = {}
        seen = set()
        restored_builtin = False
        builtin_author_changed = False
        package = folder = None
        for rec in records:
            if rec.get('builtin') == 'roland':
                continue
            look, entry = rec['look'], rec['entry']
            if (not re.fullmatch(r'WBImp_[a-f0-9]{24}', look) or entry['identity_id'] != 'story_'+look
                    or entry['appearance_name'] != look or look in seen):
                raise ValueError('外观标识重复或无效')
            seen.add(look)
            bundle = rec['bundle']
            if isinstance(bundle, bytes):
                bundle_path = Path(tmp)/(look+'.bundle')
                bundle_path.write_bytes(bundle)
            else:
                bundle_path = Path(bundle)
            sha = digest(bundle_path)
            assets[root/LOCAL/(sha+'.bundle')] = (bundle_path,sha)
            rec['timing_path'] = root/LOCAL/(look+'-'+sha+'.sst')
            plugin_version = None
            if 'plugin_version' in (rec.get('policy') or {}):
                try:
                    info = json.loads((Path(package_addon or root)/'addon_info.json').read_text(encoding='utf-8-sig'))
                    plugin_version = info['version']
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    raise ValueError('无法读取当前插件版本') from exc
            pending[root/LOCAL/(look+'.cfg')] = config(rec, sha, plugin_version=plugin_version)
        appearance_ids = {'story_' + look for look in seen}
        if any(rec.get('builtin') == 'roland' for rec in records):
            appearance_ids.add(BUILTIN)
        if portraits.keys() - appearance_ids:
            raise ValueError('外观头像声明的人格不在本次导入的战斗外观中')
        report(94, '正在写入模型和人格池')
        if check_cancelled is not None:
            check_cancelled(committing=True)
        with FileLock(root/'workbench-save.lock'), ExitStack() as rollback:
            pending.update((imported_portraits.path_for(root, identity), data)
                           for identity, data in portraits.items())
            generated = set()
            replaced = set()
            previous_audio = set()
            previous_icons = set()
            skill_ui_changed = set()
            dialogue_changed = set()
            catalog_file = root/CATALOG
            catalog = json.loads(catalog_file.read_bytes())
            by_id = {r['identity_id']: r for group in catalog.values() for r in group['entries']}
            if package_addon is not None:
                from import_packages import (clean_replaced_models, discard_failed_package, index_path,
                                             locator_path, prepare_package, relative_model_path)
                identities = {rec['entry']['identity_id'] if rec.get('builtin') != 'roland' else BUILTIN
                              for rec in records}
                package, folder, index, created = prepare_package(
                    root, package_addon, package_source, identities, source_kind=package_kind,
                    source_name=package_name, source_version=package_version)
                if created:
                    rollback.callback(discard_failed_package, folder, package['id'], generated)
                pending[index_path(root)] = index

                for old, data in tuple(assets.items()):
                    assets[folder / old.name] = data
                    del assets[old]
                for rec, (skill_data, icons) in zip(records, skill_ui):
                    identity = BUILTIN if rec.get('builtin') == 'roland' else rec['entry']['identity_id']
                    filename = ('BRoland.bundle' if identity == BUILTIN else
                                pending[root/LOCAL/(rec['look']+'.cfg')].decode('ascii').splitlines()[3])
                    loc = locator_path(root, identity)
                    pending[loc] = relative_model_path(package, filename).encode('utf-8')
                    from framepack_dialogue import plain_file
                    sidecar = folder / (identity.removeprefix('story_') + SUFFIX)
                    if sidecar.exists() or sidecar.is_symlink():
                        previous_icons.update(icon_names(sidecar))
                        skill_data = skill_data or (HEADER + '\n').encode('ascii')
                    if skill_data:
                        pending[sidecar] = skill_data
                        if not sidecar.exists() or sidecar.read_bytes() != skill_data:
                            skill_ui_changed.add(identity)
                    for name, image in icons.items():
                        destination = folder / name
                        if destination.exists() or destination.is_symlink():
                            if not plain_file(destination) or digest(destination) != name[:-4]:
                                raise ValueError('战斗外观图标已存在但内容不匹配')
                            continue
                        write_atomic(destination, image)
                        generated.add(destination)
                        rollback.callback(destination.unlink, missing_ok=True)
                        skill_ui_changed.add(identity)
                    if identity != BUILTIN:
                        if framepack_dialogue:
                            from framepack_dialogue import audio_names
                            path = folder / (rec['look'] + '.voice.tsv')
                            data, audio = rec.get('framepack_dialogue', (b'', {}))
                            exists = path.exists() or path.is_symlink()
                            if exists:
                                previous_audio.update(audio_names(path))
                            if data or exists:
                                pending[path] = data
                                if not exists or path.read_bytes() != data:
                                    dialogue_changed.add(identity)
                            for wav, source in audio.items():
                                destination = folder / wav
                                if destination.exists() or destination.is_symlink():
                                    if not plain_file(destination) or digest(destination) != wav[:-4]:
                                        raise ValueError('外观语音文件已存在但内容不匹配')
                                    continue
                                write_bundle(destination, source, wav[:-4])
                                rollback.callback(destination.unlink, missing_ok=True)
                                dialogue_changed.add(identity)
                        try:
                            old_cfg = root / LOCAL / (rec['look'] + '.cfg')
                            previous = old_cfg.read_text(encoding='ascii').splitlines()[3]
                            if (previous != filename and re.fullmatch(r'[a-f0-9]{64}\.bundle', previous)
                                    and loc.read_text(encoding='utf-8') == relative_model_path(package, previous)):
                                replaced.add((folder / previous, relative_model_path(package, previous), previous[:-7]))
                        except (OSError, IndexError, UnicodeError):
                            pass
            for rec, attribution in zip(records, author_credits):
                author_fields = ('author', 'imported_author_source', 'author_links')
                if rec.get('builtin') == 'roland':
                    old_bundle = folder/'BRoland.bundle' if folder is not None else root/'Assets/Roland/BRoland.bundle'
                    already_present = old_bundle.is_file()
                    if BUILTIN not in by_id:
                        template = json.loads((HERE.parent/CATALOG).read_bytes())
                        matches = [(role, entry) for role, group in template.items() for entry in group['entries'] if entry.get('identity_id') == BUILTIN]
                        if len(matches) != 1 or matches[0][0] not in catalog:
                            raise ValueError('该工作台缺少罗兰外观定义')
                        role, entry = matches[0]
                        catalog[role]['entries'].append(entry)
                        by_id[BUILTIN] = entry
                        restored_builtin = True
                    if folder is not None:
                        model_evidence = install_roland_bundles(archive, root, destination=old_bundle)
                        if not already_present:
                            generated.add(old_bundle)
                    else:
                        model_evidence = install_roland_bundles(archive, root)
                    if model_evidence and dialogue_scans:
                        rec['model_voice_evidence'] = model_evidence
                        rec['dialogue_detection'] = detected_status(rec, dialogue_scans, records)
                    if not old_bundle.is_file():
                        raise ValueError('该工作台缺少配套的统一罗兰模型')
                    actions = json.loads((root/'Assets/Roland/import-actions.json').read_bytes())
                    entry = by_id[BUILTIN]
                    previous = {key: entry[key] for key in author_fields if key in entry}
                    if 'imported_author_source' in previous:
                        entry.pop('author', None)
                        entry.pop('imported_author_source', None)
                    entry.pop('author_links', None)
                    entry.update(attribution)
                    builtin_author_changed = previous != {key: entry[key] for key in author_fields if key in entry}
                    status = ('added' if restored_builtin else
                              'updated' if not already_present or builtin_author_changed or BUILTIN in skill_ui_changed else 'existing')
                    results.append(dict(identity_id=BUILTIN, name=entry['name'], status=status, actions=actions,
                                        **attribution))
                    if 'dialogue_detection' in rec:
                        by_id[BUILTIN]['dialogue_detection'] = rec['dialogue_detection']
                        results[-1]['dialogue_detection'] = rec['dialogue_detection']
                    continue
                entry = rec['entry'].copy()
                entry.update(attribution)
                if 'dialogue_detection' in rec:
                    entry['dialogue_detection'] = rec['dialogue_detection']
                entry['import_source']=archive.stem
                identity = entry['identity_id']
                old = by_id.get(identity)
                entry['imported_actions'] = rec['actions']
                if rec.get('presentation_warning'):
                    entry['presentation_warning'] = rec['presentation_warning']
                voice = (rec.get('policy') or {}).get('voice')
                if voice is not None:
                    from voice_binding import validate_voice_policy
                    entry['imported_voice'] = validate_voice_policy(voice)
                if old:
                    if old.get('appearance_name') != rec['look'] or old.get('sinner') != entry['sinner']:
                        raise ValueError('已有不同的同名条目：'+identity)
                    owner = entry.get('private_declaration')
                    if owner and not PrivateIdentities.can_replace(
                            old, owner, source_stem, legacy=rec.get('_uses_legacy_private_id', False)):
                        raise ValueError('已导入外观属于不同的私服人格或压缩包，请刷新后重试')
                    for k in ('enabled','weight'):
                        if k in old:
                            entry[k] = old[k]
                    old_default = rec.get('legacy_name') is not None and old.get('name') == rec['legacy_name']
                    if name is None and not old_default:
                        from imported_catalog import display_name
                        entry['name']=display_name(old.get('name') or entry['name'],archive.stem)
                    pointer = root/LOCAL/(rec['look']+'.cfg')
                    before_entry = dict(old, private_declaration=owner) if owner and 'private_declaration' not in old else old
                    changed = before_entry != entry or not pointer.is_file() or pointer.read_bytes()!=pending[pointer]
                    changed = changed or identity in dialogue_changed or identity in skill_ui_changed
                    if identity in portraits:
                        changed = changed or imported_portraits.get(root, identity) != portraits[identity]
                    if folder is not None:
                        loc = locator_path(root, identity)
                        changed = (changed or not loc.is_file() or loc.read_bytes() != pending[loc]
                                   or not (folder / pending[loc].decode('utf-8').rsplit('/', 1)[-1]).is_file())
                    if 'imported_voice' not in entry:
                        old.pop('imported_voice',None)
                    if 'presentation_warning' not in entry:
                        old.pop('presentation_warning', None)
                    for key in author_fields:
                        if key not in attribution:
                            old.pop(key, None)
                    old.update(entry)
                    status = 'updated' if changed else 'existing'
                else:
                    catalog[entry['sinner']]['entries'].append(entry)
                    status = 'added'
                results.append(dict(identity_id=identity, name=entry['name'], status=status, actions=rec['actions'],
                                    **attribution))
                if 'dialogue_detection' in entry:
                    results[-1]['dialogue_detection'] = entry['dialogue_detection']
                if rec.get('voice_warning'):
                    results[-1]['voice_warning'] = rec['voice_warning']
                if rec.get('presentation_warning'):
                    results[-1]['presentation_warning'] = rec['presentation_warning']
                if voice is not None:
                    results[-1]['voice_declared'] = True

            # Stage immutable art and timing first. Existing instances continue
            # reading the timing associated with their own bundle revision.
            for dst,(src,sha) in assets.items():
                if folder is not None:
                    from import_packages import share_model
                    if dst.is_symlink():
                        raise ValueError('外观模型文件不是普通文件')
                    if dst.exists() and (not dst.is_file() or digest(dst) != sha):
                        raise ValueError('模型文件已存在但内容不匹配')
                    if not dst.exists():
                        for candidate in share_model(dst, dst.name):
                            if digest(candidate) != sha:
                                continue
                            try:
                                os.link(candidate, dst)
                                generated.add(dst)
                                break
                            except OSError:
                                continue
                new_file = not dst.exists()
                write_bundle(dst,src,sha)
                if new_file:
                    generated.add(dst)
            for rec in records:
                if 'timing_path' in rec:
                    path,data = rec['timing_path'],rec['timing']
                    if not path.exists() or path.read_bytes()!=data:
                        write_atomic(path,data)
            if (seen or restored_builtin or builtin_author_changed
                    or (dialogue_scans and any(rec.get('builtin') == 'roland' for rec in records))):
                pending[catalog_file] = encode(catalog)
            if seen or any(rec.get('builtin') == 'roland' for rec in records):
                tombstone = root/'imported-skin-deletions.json'
                if tombstone.is_file():
                    deleted = json.loads(tombstone.read_bytes())
                    if not isinstance(deleted, list):
                        raise ValueError('导入外观删除记录无效')
                    restored = {'story_'+look for look in seen}
                    if any(rec.get('builtin') == 'roland' for rec in records): restored.add(BUILTIN)
                    pending[tombstone] = encode([value for value in deleted if value not in restored])
            before = {}
            try:
                for path,data in pending.items():
                    if path.is_symlink():
                        raise ValueError('导入配置文件不是普通文件')
                    prior = path.read_bytes() if path.exists() else None
                    if prior != data:
                        write_atomic(path,data)
                        before[path] = prior
            except BaseException:
                for path,prior in reversed(list(before.items())):
                    if prior is None:
                        path.unlink(missing_ok=True)
                    else:
                        write_atomic(path,prior)
                raise
            if package is not None:
                rollback.pop_all()
                clean_replaced_models(root / LOCAL, replaced, digest)
                if previous_audio:
                    from framepack_dialogue import obsolete_audio
                    for path in obsolete_audio(folder, previous_audio):
                        try:
                            path.unlink()
                        except OSError:
                            continue
                if previous_icons:
                    for path in obsolete_icons(folder, previous_icons):
                        try:
                            path.unlink()
                        except OSError:
                            continue
                for row in results:
                    row['package_directory'] = str(folder)
                obsolete = {i for rec in records for i in rec.get('_obsolete_stock_ids', [])}
                if obsolete:
                    from imported_package_uninstall import prune_old_stock
                    try:
                        kept = prune_old_stock(root, package_addon, package_source, identities, obsolete)
                        if kept:
                            results[0]['cleanup_warning'] = '已保留有个人设置或无法安全清理的旧外观，可在添加人格中手动管理'
                    except (ValueError, OSError):
                        results[0]['cleanup_warning'] = '新版外观已导入，旧条目未能全部清理'
    return results


def main():
    parser = argparse.ArgumentParser(description='识别并加入本地战斗外观')
    parser.add_argument('archive',type=Path)
    parser.add_argument('--addon',type=Path,default=HERE.parent)
    parser.add_argument('--name',help='工作台中的显示名称')
    parser.add_argument('--json',action='store_true')
    args = parser.parse_args()
    try:
        def show_progress(percent, message):
            print(f'[{percent:3}%] {message}', flush=True)
        rows = import_skin(args.archive,args.addon,name=args.name,progress=None if args.json else show_progress)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False))
        else:
            for row in rows:
                state={'added':'已加入','updated':'已更新','existing':'已在池中'}[row['status']]
                print(row['name'],state)
                if row.get('kind')=='voice':
                    print('  语音库：'+'、'.join(row['banks']))
                    print('  关联人格：'+('、'.join(row['targets']) or '未标明'))
                    if row['connected_to']:print('  已接通：'+'、'.join(row['connected_to']))
                    elif not row.get('playable_banks'):print('  已入库，缺少配套的 FMOD 事件库或音频素材。')
                    else:print('  已入库，等待可唯一匹配的外观或语音线索。')
                    continue
                for key,label in [('attack','攻击'),('clash','拼点'),('defense','守备')]:
                    slots=[str(item['detail']) for item in row['actions'][key]]
                    print('  '+label+'动作槽：'+('、'.join(slots) or '未识别'))
                if row.get('voice_companion'):print('  已读取同目录语音包：'+row['voice_companion'])
                if row.get('voice_warning'):print('  配套语音读取失败：'+row['voice_warning'])
                if row.get('presentation_warning'):print('  演出说明：'+row['presentation_warning'])
                states={'connected':'已绑定','found':'已检出','unassigned':'包内有材料，归属待确认',
                        'text_only':'有战斗台词，未确认气泡', 'inherited':'沿用基础模型语音',
                        'found_unattributed':'有模型语音，来源未确认',
                        'none':'未检出','unknown':'未能确认'}
                for key, label in (('voice','战斗语音'),('bubble','战斗气泡')):
                    print('  ' + label + '：' + states[row['dialogue_detection'][key]])
            if any(r.get('kind')!='voice' for r in rows):
                print('已写入工作台：'+str(mos_data.data_dir()))
                print('重新打开这份工作台，在“添加人格 → 章节 → 外来人格”中查看。已在运行的游戏请在下次启动时使用。')
    except Exception as exc:
        if args.json:
            print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr)
        else:
            print('导入失败：'+str(exc),file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
