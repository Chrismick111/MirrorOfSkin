"""Read ZIP directly and normalize RAR and 7z containers without extracting paths."""
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import os
import shutil
import stat
import subprocess
import tarfile
from model_workspace import model_tempdir
from zipfile import ZipFile, is_zipfile, ZIP_STORED
from bundle_migration import assets, builtin_recipe
from custom_asset_manifest import (MAX_BUNDLE, MAX_MANIFEST, UNITY_BUNDLE_MAGIC,
                                   bundle_directory, is_manifest, read_manifest, relative_path)
from appearance_dialogue import AUDIO_EXTENSIONS, subtitle_file
from appearance_authors import MAX_METADATA as AUTHOR_METADATA_LIMIT, metadata_member
from imported_portraits import member_limit as portrait_member_limit
from framepack_manifest import skin_member_roots


def _supported_member(path, size=1):
    folders = {part.casefold() for part in path.parts[:-1]}
    # These are game asset directories. Their internal notes do not credit the skin.
    asset_dirs = {'custom_sprites', 'custom_sounds', 'custom_limbus_locale', 'custom_buffs'}
    if not folders.intersection(asset_dirs) and metadata_member(path) and 0 < size <= AUTHOR_METADATA_LIMIT:
        return True
    if portrait_member_limit(str(path)):
        return True
    suffix = path.suffix.casefold()
    if next(skin_member_roots(path), None) is not None and suffix in (
            AUDIO_EXTENSIONS | {'.json', '.png', '.atlas', '.skel', '.bank'}):
        return True
    if suffix in ('.bank', '.carra2'):
        return True
    if suffix in AUDIO_EXTENSIONS:
        return 'custom_sounds' in folders and not folders.intersection({'sfx', 'bgm', 'music', 'effects'})
    if bundle_directory(path) is None:
        if suffix in ('.json', '.bundle') or path.name == '__data':
            return True
    else:
        from skin_assets import _legacy_member
        if _legacy_member(path) or is_manifest(path):
            return True
        if suffix == '.json':
            return bool(folders & {'custom_limbus_data', 'custom_limbus_locale', 'custom_motions', 'custom_sounds'}
                        or path.name.casefold() in ('mos-skin.json', 'mirrorofskin-migration.json')
                        or subtitle_file(path))
    if suffix != '.png':
        return False
    parts = [part.casefold() for part in path.parts]
    return ('custom_sprites' in folders or
            (len(parts) >= 5 and parts[-5] in ('custom_motions', 'motion_appearances') and parts[-3] == 'motions'))


def _is_link(path):
    status = path.lstat()
    return (stat.S_ISLNK(status.st_mode)
            or getattr(status, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _directory_zip(folder, dest):
    files = {}
    selected = set()
    size = 0
    with ZipFile(dest, 'w', ZIP_STORED, allowZip64=True) as out:
        for root, dirs, names in os.walk(folder, followlinks=False):
            dirs[:] = [name for name in dirs if not _is_link(Path(root) / name)]
            for name in names:
                path = Path(root) / name
                if _is_link(path) or not path.is_file():
                    continue
                member = PurePosixPath(path.relative_to(folder).as_posix())
                key = str(member).casefold()
                if key in files:
                    raise ValueError('目录中包含重复文件名：' + str(member))
                files[key] = (path, member)
                entry_size = path.stat().st_size
                if _supported_member(member, entry_size):
                    size += entry_size
                    portrait_limit = portrait_member_limit(str(member))
                    if (len(selected) >= 8192 or size > 4 * 1024**3
                            or (is_manifest(member) and entry_size > MAX_MANIFEST)
                            or (portrait_limit and entry_size > portrait_limit)):
                        raise ValueError('目录超出读取上限')
                    out.write(path, str(member))
                    selected.add(key)
    with ZipFile(dest) as out:
        wanted = read_manifest(out)
    with ZipFile(dest, 'a') as out:
        for key in wanted.keys() - selected:
            if key not in files:
                raise ValueError('CustomAssetLoader 清单指定的模型包不存在：' + key)
            path, member = files[key]
            entry_size = path.stat().st_size
            size += entry_size
            with path.open('rb') as stream:
                if not 8 <= entry_size <= MAX_BUNDLE or stream.read(8) != UNITY_BUNDLE_MAGIC:
                    raise ValueError('CustomAssetLoader 清单指定的文件不是 UnityFS 模型包：' + str(member))
            if len(selected) >= 8192 or size > 4 * 1024**3:
                raise ValueError('目录超出读取上限')
            out.write(path, str(member))
            selected.add(key)
    if not selected:
        raise ValueError('文件夹内未找到可读取的模组文件。')


@contextmanager
def _archive_stream(archive, tmp):
    tar = Path(os.environ['SystemRoot']) / 'System32/tar.exe'
    env = dict(os.environ, TMP=tmp, TEMP=tmp, TMPDIR=tmp)
    # bsdtar decodes Unicode names into a pax stream, including solid RARs.
    with subprocess.Popen([str(tar), '-cf', '-', '--format=pax', '@'+str(archive)],
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, env=env) as proc:
        try:
            with tarfile.open(fileobj=proc.stdout, mode='r|') as members:
                yield members
            while proc.stdout.read(65536):
                pass
            if proc.wait():
                raise ValueError('压缩包读取失败，请确认分卷完整且已解除加密。')
        finally:
            proc.stdout.close()
            if proc.poll() is None:
                proc.kill()


@contextmanager
def normalized(archive):
    archive = Path(archive).resolve()
    if archive.is_dir():
        candidate = archive / builtin_recipe()['source_archive']
        if candidate.is_file():
            yield candidate
            return
        with model_tempdir(prefix='workbench-folder-') as tmp:
            dest = Path(tmp) / (archive.name + '.zip')
            _directory_zip(archive, dest)
            yield dest
        return
    if archive.suffix.casefold() == '.bundle':
        recipe = builtin_recipe()
        members = {asset['member'].casefold() for asset in assets(recipe)}
        if archive.name.casefold() in members:
            siblings = {p.name.casefold(): p for p in archive.parent.iterdir() if p.is_file() and p.name.casefold() in members}
            if set(siblings) != members:
                raise ValueError('罗兰需要三个 .bundle 文件放在同一文件夹；也可以直接选择 '
                                 + recipe['source_archive'] + '。')
            sources = [siblings[key] for key in sorted(members)]
        else:
            sources = [archive]
        with model_tempdir(prefix='workbench-bundle-') as tmp:
            dest = Path(tmp)/(archive.stem+'.zip')
            with ZipFile(dest,'w',ZIP_STORED,allowZip64=True) as z:
                for source in sources:
                    z.write(source,'custom_appearance/'+source.name)
            yield dest
        return
    with archive.open('rb') as source:
        header = source.read(8)
    if header.startswith(b'RIFF') and archive.suffix.casefold()=='.bank':
        with model_tempdir(prefix='workbench-bank-') as tmp:
            dest=Path(tmp)/(archive.stem+'.zip')
            if archive.name.lower().endswith('.assets.bank'):
                sibling=archive.with_name(archive.name[:-len('.assets.bank')]+'.bank')
            else:
                sibling=archive.with_suffix('.assets.bank')
            with ZipFile(dest,'w') as z:
                z.write(archive,archive.name)
                if sibling.is_file():z.write(sibling,sibling.name)
            yield dest
        return
    if not header.startswith((b'7z\xbc\xaf\x27\x1c', b'Rar!\x1a\x07')):
        # A stored Carra2 can expose an inner ZIP trailer in an outer 7z/RAR.
        if is_zipfile(archive):
            yield archive
            return
        raise ValueError('无法识别压缩格式，请选择完整的 ZIP、7z 或 RAR 文件。')
    with model_tempdir(prefix='workbench-archive-') as tmp:
        dest = Path(tmp)/(archive.stem+'.zip')
        seen = set()
        size = 0

        def copy_members(mode, wanted=None):
            nonlocal size
            with _archive_stream(archive, tmp) as members, ZipFile(dest, mode) as out:
                for entry in members:
                    p = PurePosixPath(entry.name.replace('\\','/'))
                    if not entry.isfile():
                        continue
                    if p.is_absolute() or '..' in p.parts or ':' in str(p):
                        raise ValueError('压缩包包含无效路径')
                    key = str(p).casefold()
                    if not (_supported_member(p, entry.size) if wanted is None else key in wanted):
                        continue
                    if is_manifest(p) or wanted is not None:
                        relative_path(entry.name, 2048)
                    size += entry.size
                    portrait_limit = portrait_member_limit(str(p))
                    if (key in seen or len(seen)>=8192 or size>4*1024**3
                            or is_manifest(p) and entry.size > MAX_MANIFEST
                            or portrait_limit and entry.size > portrait_limit
                            or wanted is not None and not 8 <= entry.size <= MAX_BUNDLE):
                        raise ValueError('压缩包包含重复文件或超出读取上限')
                    seen.add(key)
                    with members.extractfile(entry) as src:
                        signature = src.read(8) if wanted is not None else b''
                        if wanted is not None and signature != UNITY_BUNDLE_MAGIC:
                            raise ValueError('CustomAssetLoader 清单指定的文件不是 UnityFS 模型包：' + str(p))
                        with out.open(str(p),'w',force_zip64=True) as target:
                            target.write(signature)
                            shutil.copyfileobj(src,target,1024*1024)

        copy_members('w')
        with ZipFile(dest) as out:
            wanted = read_manifest(out)
        if wanted:
            remaining = wanted.keys() - seen
            if remaining:
                copy_members('a', remaining)
            missing = wanted.keys() - seen
            if missing:
                raise ValueError('CustomAssetLoader 清单指定的模型包不存在：' + min(missing))
        yield dest
