"""Install portraits from the pinned standalone source in portrait_source.json.

The portrait archive is version-independent from the core plugin, so this path
must never consult the GitHub release API or compare its tag with the installed
core version. The pinned URL and SHA-256 in the local config are the root of
trust. ``portrait_source.local.json`` may override the packaged config and is
excluded from core updates.
"""
import hashlib, io, json, pathlib, re, urllib.error, urllib.request, zipfile
from urllib.parse import urlparse
from file_lock import FileLock
from github_update import UpdateError

SOURCE = 'Workbench/portrait_source.json'
LOCAL_SOURCE = 'Workbench/portrait_source.local.json'
PORTRAIT_PATH = re.compile(r'Workbench/portraits/[0-9a-f]{24}\.png')
MAX_ZIP = 200 * 1024 * 1024
MAX_TOTAL = 300 * 1024 * 1024


def _read_json(path, label):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise UpdateError(label + '无法读取：' + path.name) from exc


def _optional_json(path, default):
    return _read_json(path, '头像校验清单') if path.is_file() else default


def _load_source(root):
    local = root / LOCAL_SOURCE
    path = local if local.is_file() else root / SOURCE
    if not path.is_file():
        raise UpdateError('缺少头像包直链配置：' + SOURCE)
    data = _read_json(path, '头像包直链配置')
    if not isinstance(data, dict) or data.get('schema') != 1:
        raise UpdateError('头像包直链配置格式无效')
    url = data.get('url')
    digest = data.get('sha256')
    size = data.get('size')
    if not isinstance(url, str) or not url:
        raise UpdateError('头像包直链配置缺少 url')
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.netloc:
        raise UpdateError('头像包直链必须是 HTTPS 地址')
    if not isinstance(digest, str):
        raise UpdateError('头像包直链配置缺少 sha256')
    digest = digest.lower()
    if digest.startswith('sha256:'):
        digest = digest[7:]
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise UpdateError('头像包直链配置的 sha256 无效')
    if size is not None and (isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_ZIP):
        raise UpdateError('头像包直链配置的 size 无效')
    return url, digest, size


def _fetch_direct(url, limit):
    request = urllib.request.Request(url, headers={'User-Agent': 'FaustRandomIdentity-Portraits', 'Accept': '*/*'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            blob = response.read(limit + 1)
            if len(blob) > limit:
                raise UpdateError('头像包下载内容过大')
            return blob
    except UpdateError:
        raise
    except urllib.error.HTTPError as exc:
        raise UpdateError('头像包下载失败：HTTP ' + str(exc.code)) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError('无法下载头像包，请检查网络或直链配置') from exc


def download(root):
    root = pathlib.Path(root).resolve()
    with FileLock(root / 'github-update.lock'):
        return _download_locked(root)


def _download_locked(root):
    url, digest, expected_size = _load_source(root)
    blob = _fetch_direct(url, MAX_ZIP)
    if expected_size is not None and len(blob) != expected_size:
        raise UpdateError('头像包大小与直链配置不符')
    if hashlib.sha256(blob).hexdigest() != digest:
        raise UpdateError('头像包 SHA-256 与直链配置不符')

    manifest = _optional_json(root / 'Workbench/portrait_manifest.json', {})
    if not isinstance(manifest, dict):
        raise UpdateError('头像清单格式无效')
    names = {value.get('file') for value in manifest.values() if isinstance(value, dict) and isinstance(value.get('file'), str)}

    hashes = _optional_json(root / 'Workbench/portrait_hashes.json', None)
    if hashes is not None:
        if not isinstance(hashes, dict) or any(
            not PORTRAIT_PATH.fullmatch(key)
            or not isinstance(value, str)
            or not re.fullmatch(r'[0-9a-fA-F]{64}', value)
            or (names and key.rsplit('/', 1)[-1] not in names)
            for key, value in hashes.items()
        ):
            raise UpdateError('头像校验清单无效')

    compat = _optional_json(root / 'compatibility.json', {})
    tracked = compat.get('package_files', {}) if isinstance(compat, dict) else {}
    if not isinstance(tracked, dict):
        raise UpdateError('插件校验清单无效')

    files = {}
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                if name == 'portrait-hashes.json':
                    if info.file_size > 1024 * 1024:
                        raise UpdateError('头像包清单过大')
                    embedded = json.loads(archive.read(info).decode('utf8'))
                    if not isinstance(embedded, dict):
                        raise UpdateError('头像包清单格式无效')
                    if hashes is not None and embedded != hashes:
                        raise UpdateError('头像包清单与核心不符')
                    continue
                if not PORTRAIT_PATH.fullmatch(name) or (names and name.rsplit('/', 1)[-1] not in names) or name in files:
                    raise UpdateError('头像包包含未声明的文件')
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise UpdateError('头像包不能包含符号链接')
                total += info.file_size
                if total > MAX_TOTAL:
                    raise UpdateError('头像包解压内容过大')
                data = archive.read(info)
                if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise UpdateError('头像图片格式无效')
                if hashes is not None:
                    if name not in hashes or hashlib.sha256(data).hexdigest() != hashes[name].lower():
                        raise UpdateError('头像包与校验清单不符')
                if name in tracked and hashlib.sha256(data).hexdigest() != tracked[name].lower():
                    raise UpdateError('头像不符合当前插件校验清单')
                destination = root.joinpath(*name.split('/'))
                if not destination.resolve().is_relative_to(root):
                    raise UpdateError('头像路径无效')
                files[name] = data
    except UpdateError:
        raise
    except (zipfile.BadZipFile, RuntimeError, ValueError) as exc:
        raise UpdateError('头像资源包损坏') from exc

    if not files:
        raise UpdateError('头像资源包为空')
    if hashes is not None and set(files) != set(hashes):
        raise UpdateError('头像包不完整')

    written = []
    before = {}
    try:
        for name, data in files.items():
            path = root.joinpath(*name.split('/'))
            path.parent.mkdir(parents=True, exist_ok=True)
            before[name] = path.read_bytes() if path.exists() else None
            tmp = path.with_name(path.name + '.portrait-tmp')
            tmp.write_bytes(data)
            tmp.replace(path)
            written.append(name)
    except Exception:
        for name in reversed(written):
            path = root.joinpath(*name.split('/'))
            old = before[name]
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old)
        raise
    return {'count': len(files), 'message': '头像资源已下载，请刷新工作台'}
