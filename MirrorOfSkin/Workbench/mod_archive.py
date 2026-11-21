"""Read ZIP directly and normalize RAR and 7z containers without extracting paths."""
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import os
import shutil
import subprocess
import tarfile
import tempfile
from zipfile import ZipFile, is_zipfile


@contextmanager
def normalized(archive):
    archive = Path(archive).resolve()
    with archive.open('rb') as source:
        header = source.read(8)
    if header.startswith(b'RIFF') and archive.suffix.casefold()=='.bank':
        with tempfile.TemporaryDirectory(prefix='workbench-bank-') as tmp:
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
    if is_zipfile(archive):
        yield archive
        return
    if not header.startswith((b'7z\xbc\xaf\x27\x1c', b'Rar!\x1a\x07')):
        raise ValueError('无法识别压缩格式，请选择完整的 ZIP、7z 或 RAR 文件。')
    tar = Path(os.environ['SystemRoot'])/'System32/tar.exe'
    with tempfile.TemporaryDirectory(prefix='workbench-archive-') as tmp:
        dest = Path(tmp)/(archive.stem+'.zip')
        # bsdtar decodes Unicode names into a pax stream, including solid RARs.
        with subprocess.Popen([str(tar), '-cf', '-', '--format=pax', '@'+str(archive)],
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE) as proc:
            try:
                with tarfile.open(fileobj=proc.stdout, mode='r|') as members, ZipFile(dest,'w') as out:
                    seen = set()
                    size = 0
                    for entry in members:
                        p = PurePosixPath(entry.name.replace('\\','/'))
                        if not entry.isfile():
                            continue
                        if p.is_absolute() or '..' in p.parts or ':' in str(p):
                            raise ValueError('压缩包包含无效路径')
                        if p.suffix.lower() not in ('.bank','.json','.bundle','.carra2') and p.name!='__data':
                            continue
                        key = str(p).casefold()
                        size += entry.size
                        if key in seen or len(seen)>=8192 or size>4*1024**3:
                            raise ValueError('压缩包包含重复文件或超出读取上限')
                        seen.add(key)
                        with members.extractfile(entry) as src, out.open(str(p),'w',force_zip64=True) as target:
                            shutil.copyfileobj(src,target,1024*1024)
                while proc.stdout.read(65536):
                    pass
                if proc.wait():
                    raise ValueError('压缩包读取失败，请确认分卷完整且已解除加密。')
            finally:
                proc.stdout.close()
                if proc.poll() is None:
                    proc.kill()
        yield dest
