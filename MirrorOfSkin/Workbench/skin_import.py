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
from file_lock import FileLock

CATALOG = 'Assets/runtime/all_sinners_pools.json'
LOCAL = 'Assets/ImportedSkins'
BUILTIN = 'story_BRolandBaseAppearance'


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
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
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as dest, src.open('rb') as source:
            shutil.copyfileobj(source, dest)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def config(record, checksum):
    def field(key, pattern, limit):
        value = record[key]
        if (len(value)>=limit or not re.fullmatch(pattern, value, re.ASCII)
                or any(part in ('','.','..') for part in value.split('/'))):
            raise ValueError('模型包含不支持的资源标识：'+key)
        return value
    dependency = field('dependency', r'(?:SD_Personality|SD_Enemy)/[A-Za-z0-9_./-]+\.prefab',512)
    asset = field('asset', r'(?i:assets)/[a-zA-Z0-9_ ./-]+\.prefab',1024)
    layout = field('layout', r'[a-zA-Z0-9_]+',256)
    actions = record['actions']
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
    return ('\n'.join(('WBMOD1', dependency, asset, checksum+'.bundle', layout,
                       ''.join(roles), ''.join(animator)))+'\n').encode('ascii')


def mirror_import_assets(data_root, addon_root):
    """Publish runtime resources atomically, including same-sized updates."""
    for rel in ('Assets/Roland', 'Assets/ImportedSkins', 'Assets/ImportedVoices'):
        src, dst = Path(data_root) / rel, Path(addon_root) / rel
        if not src.is_dir():
            continue
        for path in src.rglob('*'):
            if not path.is_file():
                continue
            target = dst / path.relative_to(src)
            if target.resolve() == path.resolve():
                continue
            try:
                write_bundle(target, path, digest(path))
            except OSError as exc:
                raise OSError('无法同步导入资源：' + str(target)) from exc


def import_skin(archive, addon, *, name=None, unity=None):
    from mod_archive import normalized
    from carra_import import expanded
    from zipfile import ZipFile,BadZipFile
    from bank_mod import import_banks
    from skin_assets import _members
    addon_root=Path(addon).resolve()
    root=addon_root
    if json.loads((root/'compatibility.json').read_bytes()).get('local_skin_import')!=1:
        raise ValueError('请选择支持本地外观导入的工作台。')
    root=mos_data.prepare(root)
    with normalized(archive) as container, expanded(container,root,unity) as path:
        with ZipFile(path) as z:
            has_banks=any(i.filename.lower().endswith('.bank') for i in z.infolist())
            has_models=bool(_members(z))
        rows=_import_normalized(path,root,name=name,unity=unity) if has_models or not has_banks else []
        included=[r['identity_id'][6:] for r in rows if r['identity_id'].startswith('story_WBImp_')]
        if has_banks:
            rows.append(import_banks(path,root,name,source=Path(archive).stem,included=included))
        from voice_binding import companion_archive,reconcile
        if included and not has_banks:
            try:
                companion=companion_archive(Path(archive).resolve())
                if companion:
                    with normalized(companion) as voice_path:
                        voice=import_banks(voice_path,root,source=companion.stem)
                    if voice:
                        for row in rows:row['voice_companion']=companion.name
            except (OSError,ValueError,RuntimeError,BadZipFile) as error:
                for row in rows:row['voice_warning']=str(error)
        mapped=reconcile(root)
        mirror_import_assets(root, addon_root)
        for row in rows:
            if row.get('kind')=='voice':
                row['connected_to']=[label for rev,label in mapped.values() if rev==row['revision']]
            else:
                row['voice_connected']=row['identity_id'].removeprefix('story_') in mapped
        return rows


def install_roland_bundles(archive, root):
    """Build the unified model from the user's original three-bundle archive."""
    from roland_merge import build_roland_bundle
    root = Path(root)
    bundle, metadata = build_roland_bundle(archive)
    expected = root / 'Assets/runtime/story_native/story_BRolandBaseAppearance.bin'
    if not expected.is_file() or expected.read_bytes() != metadata:
        raise ValueError('生成的罗兰动作数据与工作台不匹配，未替换现有模型')
    write_atomic(root / 'Assets/Roland/BRoland.bundle', bundle)


def _import_normalized(archive, addon, *, name=None, unity=None):
    from skin_assets import build_assets
    root, archive = Path(addon).resolve(), Path(archive).resolve()
    manifest = json.loads((root/'compatibility.json').read_bytes())
    if manifest.get('local_skin_import') != 1:
        raise ValueError('请选择支持本地外观导入的工作台。')
    if not archive.is_file():
        raise ValueError('找不到所选压缩包')
    if unity is None:
        import resource_tools
        unity = resource_tools.unity()
    results = []
    with tempfile.TemporaryDirectory(prefix='faust-skin-') as tmp:
        records = list(build_assets(archive, Path(tmp), unity, name=name))
        if not records:
            raise ValueError('压缩包内没有可加入池的战斗外观')
        pending = {}
        assets = {}
        seen = set()
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
            pending[root/LOCAL/(look+'.cfg')] = config(rec,sha)
        with FileLock(root/'workbench-save.lock'):
            catalog_file = root/CATALOG
            catalog = json.loads(catalog_file.read_bytes())
            by_id = {r['identity_id']: r for group in catalog.values() for r in group['entries']}
            for rec in records:
                if rec.get('builtin') == 'roland':
                    install_roland_bundles(archive, root)
                    if BUILTIN not in by_id or not (root/'Assets/Roland/BRoland.bundle').is_file():
                        raise ValueError('该工作台缺少配套的统一罗兰模型')
                    actions = json.loads((root/'Assets/Roland/import-actions.json').read_bytes())
                    results.append(dict(identity_id=BUILTIN, name=by_id[BUILTIN]['name'], status='existing', actions=actions))
                    continue
                entry = rec['entry'].copy()
                entry['import_source']=archive.stem
                identity = entry['identity_id']
                old = by_id.get(identity)
                entry['imported_actions'] = rec['actions']
                if old:
                    if old.get('appearance_name') != rec['look'] or old.get('sinner') != entry['sinner']:
                        raise ValueError('已有不同的同名条目：'+identity)
                    for k in ('enabled','weight'):
                        if k in old:
                            entry[k] = old[k]
                    if name is None:
                        from imported_catalog import display_name
                        entry['name']=display_name(old.get('name') or entry['name'],archive.stem)
                    pointer = root/LOCAL/(rec['look']+'.cfg')
                    changed = old != entry or not pointer.is_file() or pointer.read_bytes()!=pending[pointer]
                    old.update(entry)
                    status = 'updated' if changed else 'existing'
                else:
                    catalog[entry['sinner']]['entries'].append(entry)
                    status = 'added'
                results.append(dict(identity_id=identity,name=entry['name'],status=status,actions=rec['actions']))

            # Stage immutable art and timing first. Existing instances continue
            # reading the timing associated with their own bundle revision.
            for dst,(src,sha) in assets.items():
                write_bundle(dst,src,sha)
            for rec in records:
                if 'timing_path' in rec:
                    path,data = rec['timing_path'],rec['timing']
                    if not path.exists() or path.read_bytes()!=data:
                        write_atomic(path,data)
            if seen:
                pending[catalog_file] = encode(catalog)
                tombstone = root/'imported-skin-deletions.json'
                if tombstone.is_file():
                    deleted = json.loads(tombstone.read_bytes())
                    if not isinstance(deleted, list):
                        raise ValueError('导入外观删除记录无效')
                    pending[tombstone] = encode([value for value in deleted if value not in {'story_'+look for look in seen}])
            before = {}
            try:
                for path,data in pending.items():
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
    return results


def main():
    parser = argparse.ArgumentParser(description='识别并加入本地战斗外观')
    parser.add_argument('archive',type=Path)
    parser.add_argument('--addon',type=Path,default=HERE.parent)
    parser.add_argument('--name',help='工作台中的显示名称')
    parser.add_argument('--json',action='store_true')
    args = parser.parse_args()
    try:
        rows = import_skin(args.archive,args.addon,name=args.name)
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
                if row['voice_connected']:print('  已自动接通此外观的语音。')
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
