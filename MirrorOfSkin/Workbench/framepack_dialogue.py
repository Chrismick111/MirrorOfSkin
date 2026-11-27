"""Read and publish battle dialogue from a declared Mod Spec v2 skin."""
from collections import defaultdict
import hashlib
import json
from pathlib import PurePosixPath
import re
import stat
import struct
from zipfile import BadZipFile

from appearance_dialogue import _BATTLE_DIRS, _battle_line, _framepack_owner, _path, subtitle_file
from framepack_manifest import _unique_keys
from import_packages import DIRECTORY, _plain_directory, _safe_name


MAX_WAV = 16 * 1024**2
MAX_MANIFEST = 2 * 1024**2
MAX_LOCALE = 16 * 1024**2
WAV_NAME = re.compile(r'[0-9a-f]{64}\.wav')
LOOK = re.compile(r'WBImp_[0-9a-f]{24}')
MANIFEST_NAME = re.compile(LOOK.pattern + r'\.voice\.tsv')
BUNDLE_NAME = re.compile(r'[0-9a-f]{64}\.bundle')
_READ_ERRORS = (BadZipFile, OSError, ValueError, RuntimeError, NotImplementedError, RecursionError)


def _valid_wav(data):
    if (len(data) < 44 or data[:4] != b'RIFF' or data[8:12] != b'WAVE'
            or int.from_bytes(data[4:8], 'little') != len(data) - 8):
        return False
    offset, alignment, sample_size = 12, 0, 0
    while offset + 8 <= len(data):
        kind, size = struct.unpack_from('<4sI', data, offset)
        offset += 8
        if offset + size > len(data):
            return False
        if kind == b'fmt ':
            if size < 16 or alignment:
                return False
            encoding, channels, rate, byte_rate, alignment, bits = struct.unpack_from('<HHIIHH', data, offset)
            valid_format = (encoding == 1 and bits in (8, 16, 24, 32)) or (encoding == 3 and bits == 32)
            if (not valid_format or channels not in (1, 2) or not 8000 <= rate <= 192000
                    or alignment != channels * (bits // 8) or byte_rate != alignment * rate):
                return False
        elif kind == b'data':
            if sample_size or not size or not alignment or size % alignment:
                return False
            sample_size = size
        offset += size + (size & 1)
    return offset == len(data) and sample_size > 0


def _subtitle_rows(data):
    if isinstance(data, dict):
        rows = data.get('dataList')
        if isinstance(rows, list):
            yield from ((row.get('id'), row) for row in rows if isinstance(row, dict))
        else:
            yield from data.items()


def collect(archive, skin, stage):
    """Stage valid PCM by content hash and serialize only the declared skin's events."""
    voice = _path(skin.voice_dir) if skin.voice_dir else None
    locale = _path(skin.locale_exclusive_dir) if skin.locale_exclusive_dir else None
    owner = skin.personality
    audio, event_audio = {}, defaultdict(set)
    lines = defaultdict(set)
    for name, info in skin.members.items():
        path = PurePosixPath(name)
        if (voice is not None and path.is_relative_to(voice) and path.suffix == '.wav'
                and _framepack_owner(path.stem) == owner and 0 < info.file_size <= MAX_WAV):
            try:
                data = archive.read(info)
            except _READ_ERRORS:
                continue
            if _valid_wav(data):
                filename = hashlib.sha256(data).hexdigest() + '.wav'
                event_audio[path.stem].add(filename)
                if filename not in audio:
                    audio[filename] = stage / filename
                    if not audio[filename].exists():
                        audio[filename].write_bytes(data)
        if (locale is None or not path.is_relative_to(locale)
                or not _BATTLE_DIRS.intersection(path.relative_to(locale).parts[:-1])
                or subtitle_file(path) != 'bubble' or not 0 < info.file_size <= MAX_LOCALE):
            continue
        try:
            data = json.loads(archive.read(info), object_pairs_hook=_unique_keys)
        except _READ_ERRORS:
            continue
        for event, row in _subtitle_rows(data):
            if (isinstance(event, str) and isinstance(row, dict) and row.get('id') == event
                    and _framepack_owner(event) == owner):
                line = _battle_line(row.get('dlg'))
                if line:
                    lines[event.casefold()].add(line)
    rows = []
    used_audio = {}
    for event in sorted(event_audio.keys() | lines.keys()):
        filenames, texts = event_audio[event], lines[event]
        filename = next(iter(filenames)) if len(filenames) == 1 else ''
        text = next(iter(texts)) if len(texts) == 1 else ''
        if filename or text:
            rows.append(f'{owner}\t{event}\t{filename}\t{text}\n')
            if filename:
                used_audio[filename] = audio[filename]
    manifest = ''.join(rows).encode('utf8')
    if len(manifest) > MAX_MANIFEST:
        raise ValueError('Mod Spec v2 战斗语音和气泡映射过大：' + skin.label)
    return manifest, used_audio


def plain_file(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISREG(info.st_mode) and not (
        getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def read_manifest(path):
    """Read the package-local protocol without following links or guessing ownership."""
    if not plain_file(path) or path.stat().st_size > MAX_MANIFEST:
        raise ValueError('无效的外观语音映射：' + str(path))
    rows = []
    keys = set()
    for row in path.read_text(encoding='utf8').split('\n'):
        if not row:
            continue
        owner, event, filename, line = row.split('\t')
        if (not owner or owner != _framepack_owner(event) or event != event.casefold() or event in keys
                or (rows and owner != rows[0][0]) or (filename and not WAV_NAME.fullmatch(filename))
                or (line and _battle_line(line) != line) or not (filename or line)):
            raise ValueError('无效的外观语音映射：' + str(path))
        keys.add(event)
        rows.append((owner, event, filename, line))
    return rows


def audio_names(path):
    return {filename for _, _, filename, _ in read_manifest(path) if filename}


def content_hash(path):
    checksum = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024**2), b''):
            checksum.update(block)
    return checksum.hexdigest()


def obsolete_audio(folder, candidates, *, excluding=()):
    """Find audio that no remaining sidecar in this package refers to."""
    candidates = set(candidates)
    if not candidates:
        return set()
    try:
        for path in folder.glob('*.voice.tsv'):
            if path not in excluding and MANIFEST_NAME.fullmatch(path.name):
                candidates.difference_update(audio_names(path))
        return {folder / name for name in candidates
                if WAV_NAME.fullmatch(name) and plain_file(folder / name)
                and content_hash(folder / name) == name[:-4]}
    except (OSError, ValueError):
        return set()


def supported(addon):
    manifest = json.loads((addon / 'compatibility.json').read_bytes())
    if manifest.get('framepack_dialogue') != 1 or manifest.get('import_package_folders') != 1:
        return False
    dll = 'SinnersNative-v64.dll'
    expected = manifest.get('package_files', {}).get(dll)
    return (manifest.get('dll', dll) == dll and bool(expected) and plain_file(addon / dll)
            and content_hash(addon / dll) == expected)


def _usable_wav(path):
    try:
        if not plain_file(path) or not 44 <= path.stat().st_size <= MAX_WAV:
            return False
        data = path.read_bytes()
        return hashlib.sha256(data).hexdigest() == path.stem and _valid_wav(data)
    except OSError:
        return False


def installed_states(root, addon):
    """Report connections only for installed resources and a compatible core."""
    try:
        imported = addon / DIRECTORY
        if not _plain_directory(imported) or not supported(addon):
            return {}
        assets = root / 'Assets/ImportedSkins'
        if assets.resolve() != assets.absolute():
            return {}
    except (OSError, ValueError, AttributeError):
        return {}
    statuses = {}
    for loc in assets.glob('WBImp_*.loc'):
        if not LOOK.fullmatch(loc.stem):
            continue
        try:
            if not plain_file(loc):
                continue
            parts = loc.read_text(encoding='utf8').split('/')
            if (len(parts) != 3 or parts[0] != DIRECTORY or not _safe_name(parts[1])
                    or not BUNDLE_NAME.fullmatch(parts[2])):
                continue
            folder = imported / parts[1]
            if not _plain_directory(folder) or not plain_file(folder / parts[2]):
                continue
            rows = read_manifest(folder / (loc.stem + '.voice.tsv'))
            status = {}
            if any(filename and _usable_wav(folder / filename) for _, _, filename, _ in rows):
                status['voice'] = 'connected'
            if any(line for _, _, _, line in rows):
                status['bubble'] = 'connected'
            if status:
                statuses['story_' + loc.stem] = status
        except (OSError, ValueError):
            continue
    return statuses
