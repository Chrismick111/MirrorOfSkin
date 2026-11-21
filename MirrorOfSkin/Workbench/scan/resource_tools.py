"""Use the launcher's resource readers, or provision the tested Windows wheels once."""
import hashlib
from contextlib import ExitStack
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import uuid4
import zipfile

from file_lock import FileLock

WHEELS = Path(__file__).resolve().parents[1] / 'data/resource-tools-wheels.json'
PROBE = """
import sys,json
sys.path[:]=json.loads(sys.stdin.read())
if sys.platform == "win32":
    from host_lifetime import exit_with_owner
    exit_with_owner(int(sys.argv[1]))
from UnityPy import load
from UnityPy.export.AudioClipConverter import extract_audioclip_samples
from UnityPy.export.Texture2DConverter import get_image_from_texture2d
from PIL import Image
from astc_encoder import ASTCContext
"""
_lock = threading.Lock()
_unity = None


def _check(paths):
    result = subprocess.run([sys.executable,'-B','-c',PROBE,str(os.getpid())], input=json.dumps(paths),
                            capture_output=True, text=True, errors='replace', timeout=90,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise ImportError('资源读取组件不可用：'+result.stderr.strip()[-350:])


def _download(folder, wheels):
    records = {}
    for wheel in wheels:
        url = wheel['url']
        parts = urlsplit(url)
        if parts.scheme!='https' or parts.hostname!='files.pythonhosted.org':
            raise ValueError('无效的资源依赖下载地址')
        with urlopen(url, timeout=45) as response:
            blob=response.read(wheel['size']+1)
        if len(blob)!=wheel['size'] or hashlib.sha256(blob).hexdigest()!=wheel['sha256']:
            raise ValueError('资源依赖校验失败：'+wheel['filename'])
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for member in z.infolist():
                name=member.filename
                if member.is_dir() or (name.startswith('astc_encoder/_encoder_') and name.endswith(('.ipdb','.iobj'))):
                    continue
                z.extract(member,folder)
                records[name]=member.CRC
    return records


def _cached(index):
    try:
        pointer=json.loads(index.read_bytes())
        generation=pointer['generation']
        if not re.fullmatch(r'[0-9a-f]{32}',generation):
            return None
        target=index.parent/(index.stem+'-'+generation)
        records=pointer['files']
        if 'UnityPy/__init__.py' not in records:
            return None
        for name,crc in records.items():
            path=Path(name)
            if path.anchor or '..' in path.parts or zipfile.crc32((target/path).read_bytes())!=crc:
                return None
        return target
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        return None


def _provision():
    if (sys.implementation.name!='cpython' or sys.version_info[:2]!=(3,9)
            or sysconfig.get_platform().lower()!='win-amd64'):
        raise ImportError('请使用 FaustLauncher 的 Windows 64 位 Python 3.9 打开工作台，或在当前解释器中安装 UnityPy')
    raw=WHEELS.read_bytes()
    directory=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData/Local')/'FaustLauncher'/'appearance-resource-tools'
    directory.mkdir(parents=True,exist_ok=True)
    index=directory/('cp39-'+hashlib.sha256(raw).hexdigest()[:16]+'.json')
    lock=FileLock(index.with_suffix('.lock'))
    deadline=time.monotonic()+600
    while True:
        with ExitStack() as held:
            try:
                held.enter_context(lock)
            except TimeoutError:
                if time.monotonic()>=deadline:raise
                continue
            target=_cached(index)
            if target is not None:return target
            with tempfile.TemporaryDirectory(dir=directory) as temp:
                stage=Path(temp)/'packages'
                stage.mkdir()
                files=_download(stage,json.loads(raw))
                _check([str(stage)]+[p for p in sys.path if p])
                generation=uuid4().hex
                target=directory/(index.stem+'-'+generation)
                pointer=Path(temp)/'ready.json'
                pointer.write_text(json.dumps(dict(generation=generation,files=files)),encoding='utf8')
                # An older generation may still have native DLLs in use by another worker.
                stage.rename(target)
                os.replace(pointer,index)
                return target


def unity():
    global _unity
    with _lock:
        if _unity is not None:return _unity
        local=False
        if importlib.util.find_spec('UnityPy') is not None:
            try:
                _check(sys.path)
                local=True
            except (ImportError,subprocess.TimeoutExpired):
                pass
        if not local:
            try:
                cache=_provision()
            except (OSError,ValueError,zipfile.BadZipFile,subprocess.TimeoutExpired) as exc:
                raise ImportError('资源读取组件准备失败，请检查网络后重试：'+str(exc)) from exc
            if str(cache) not in sys.path:sys.path.insert(0,str(cache))
            importlib.invalidate_caches()
        _unity=importlib.import_module('UnityPy')
        return _unity


def prepare_in_background():
    def prepare():
        try:
            unity()
        except (OSError,ImportError) as exc:
            # Resource operations retry and surface the same failure to their caller.
            print(str(exc),file=sys.stderr,flush=True)
    threading.Thread(target=prepare,name='appearance-resource-tools',daemon=True).start()
