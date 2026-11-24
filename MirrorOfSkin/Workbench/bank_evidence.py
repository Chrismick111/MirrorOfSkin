"""Read FMOD event/sample bank structure and identify changed identity voice clips."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import struct
import sys


_DESKTOP = Path('StreamingAssets/Assets/Sound/FMODBuilds/Desktop')
_BANK = re.compile(r'(?!master(?:\.|$))[\w-]+(?:\.assets)?\.bank\Z', re.ASCII | re.I)
_OWNER = re.compile(rb'^[a-z][a-z0-9_-]*?_([1-9][0-9]{2,7})_[0-9][a-z0-9_-]*$', re.I)
_RATES = (4000, 8000, 11000, 11025, 16000, 22050, 24000, 32000, 44100, 48000, 96000)
_ERRORS = (OSError, ValueError, struct.error, OverflowError)


def _desktop(root):
    for path in (root / 'LimbusCompany_Data' / _DESKTOP, root / _DESKTOP, root):
        if path.is_dir() and (path.name.casefold() == 'desktop' or path != root):
            return path
    return None


def _steam_roots():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            yield Path(winreg.QueryValueEx(key, 'SteamPath')[0])
    except (ImportError, OSError):
        pass
    if os.getenv('ProgramFiles(x86)'):
        yield Path(os.environ['ProgramFiles(x86)']) / 'Steam'


def game_bank_dir(folder: Path):
    override = os.getenv('LIMBUS_GAME_DIR')
    if override:
        return _desktop(Path(override))
    # The installed workbench and its bundled Python both live under the launcher.
    for parent in dict.fromkeys((*Path(__file__).resolve().parents, *Path(sys.executable).parents)):
        config = parent / 'config/settings.json'
        if config.is_file():
            try:
                root = json.loads(config.read_text(encoding='utf-8-sig'))['game_path']['value']
                if isinstance(root, str) and root and (desktop := _desktop(Path(root))):
                    return desktop
            except (OSError, ValueError, KeyError, TypeError):
                pass
    for steam in _steam_roots():
        libraries = [steam]
        try:
            info = (steam / 'steamapps/libraryfolders.vdf').read_text(encoding='utf-8-sig')
            libraries.extend(Path(p.replace('\\\\', '\\')) for p in re.findall(r'"path"\s+"([^"]+)"', info))
        except (OSError, ValueError):
            pass
        for lib in libraries:
            if (desktop := _desktop(lib / 'steamapps/common/Limbus Company')):
                return desktop
    return None


def _chunks(data, start, end):
    while start < end:
        if end - start < 8:
            raise ValueError('short RIFF chunk')
        tag, size = struct.unpack_from('<4sI', data, start)
        body = start + 8
        start = body + size + (size % 2)
        if start > end:
            raise ValueError('chunk exceeds container')
        yield tag, body, size


def _sample_times(data, fsb, end, fingerprints=False):
    version, count, headers, names, audio = struct.unpack_from('<5I', data, fsb + 4)
    base = fsb + 60 + headers
    if (version != 1 or count > 65536 or headers < 8 * count or names < count * 4
            or base + names + audio > end):
        raise ValueError('unsupported FSB5 sample directory')
    pos = fsb + 60
    result = {}
    offsets = []
    for i in range(count):
        nameoff = struct.unpack_from('<I', data, base + 4 * i)[0]
        if not count * 4 <= nameoff < names or pos + 8 > base:
            raise ValueError('bad sample directory offset')
        namepos = base + nameoff
        term = data.find(b'\x00', namepos, min(namepos + 512, base + names))
        if term < 0:
            raise ValueError('unterminated sample name')
        name = data[namepos:term]
        bits = struct.unpack_from('<Q', data, pos)[0]
        pos += 8
        offsets.append((name, ((bits >> 7) & 0x7ffffff) * 32))
        more = bits & 1
        rate_id = (bits >> 1) & 15
        rate = _RATES[rate_id] if rate_id < len(_RATES) else 0
        while more:
            if pos + 4 > base:
                raise ValueError('bad sample extension')
            extra = struct.unpack_from('<I', data, pos)[0]
            pos += 4
            size = (extra >> 1) & 0xffffff
            if pos + size > base:
                raise ValueError('bad sample extension size')
            if extra >> 25 == 2:
                if size != 4:
                    raise ValueError('bad frequency extension')
                rate = struct.unpack_from('<I', data, pos)[0]
            more = extra & 1
            pos += size
        if not rate or not name or name in result:
            raise ValueError('ambiguous sample')
        result[name] = (bits >> 34) / rate
    if fingerprints:
        data_start=base+names
        for i,(name,offset) in enumerate(offsets):
            next_offset=offsets[i+1][1] if i+1<len(offsets) else audio
            if offset>next_offset or next_offset>audio:
                raise ValueError('invalid sample audio offsets')
            view=memoryview(data)[data_start+offset:data_start+next_offset]
            try:sample_hash=hashlib.sha256(view).digest()
            finally:view.release()
            result[name]=(result[name],sample_hash)
    return result


def _read_bank(path, times=False, fingerprints=False):
    with path.open('rb') as stream:
        if not 12 <= os.fstat(stream.fileno()).st_size <= 1024**3:
            raise ValueError('unsupported bank size')
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            sig, size, form = struct.unpack_from('<4sI4s', data)
            if (sig, size, form) != (b'RIFF', len(data) - 8, b'FEV '):
                raise ValueError('unsupported bank')
            events = audio = False
            samples = {}
            for tag, pos, size in _chunks(data, 12, len(data)):
                if tag == b'LIST' and data[pos:pos+4] == b'PROJ':
                    for child, start, length in _chunks(data, pos+4, pos+size):
                        if child == b'LIST' and length > 4 and data[start:start+4] == b'EVTS':
                            events = True
                if tag == b'SND ':
                    # FSB starts at a 32-byte alignment inside its RIFF chunk.
                    fsb = data.find(b'FSB5', pos, min(pos+35, pos+size))
                    if fsb < 0 or fsb+60 > pos+size:
                        raise ValueError('unsupported sound chunk')
                    audio = True
                    if times:
                        clips = _sample_times(data, fsb, pos+size, fingerprints=fingerprints)
                        if samples.keys() & clips.keys():
                            raise ValueError('ambiguous sample bank')
                        samples.update(clips)
            return events, audio, samples


def playable_banks(folder: Path, banks: list[str]) -> list[str]:
    """Return local participants in complete event/audio pairs or integrated banks."""
    game = game_bank_dir(folder)
    families = defaultdict(dict)
    for name in banks:
        if _BANK.fullmatch(name):
            family = name.lower().removesuffix('.bank').removesuffix('.assets')
            families[family][name.lower().endswith('.assets.bank')] = name
    result = []
    for family, local in families.items():
        flags = {}
        exemplar = next(iter(local.values()))
        stem = exemplar[:-len('.assets.bank')] if exemplar.lower().endswith('.assets.bank') else exemplar[:-5]
        for assets, suffix in ((False, '.bank'), (True, '.assets.bank')):
            path = None
            if assets in local:
                path = folder / local[assets]
            elif game:
                path = game / (stem + suffix)
            try:
                flags[assets] = _read_bank(path)[:2] if path else (False, False)
            except _ERRORS:
                flags[assets] = (False, False)
        events, integrated = flags[False]
        if events and (flags[True][1] or integrated):
            if False in local:
                result.append(local[False])
            if flags[True][1] and True in local:
                result.append(local[True])
    return sorted(result, key=str.casefold)


def target_probe_key(folder: Path, banks: list[str]) -> str:
    """Recheck unresolved voice owners only when their evidence changes."""
    game=game_bank_dir(folder)
    def stamp(path):
        try:
            st=path.stat()
            return (st.st_size,st.st_mtime_ns)
        except OSError:return None
    rows=[]
    for name in sorted(banks,key=str.casefold):
        if _BANK.fullmatch(name):
            rows.append((name,stamp(folder/name),stamp(game/name) if game else None))
    data=json.dumps([2,str(game) if game else None,rows],ensure_ascii=True,separators=(',',':'))
    return hashlib.sha256(data.encode('ascii')).hexdigest()


def probe_targets(folder: Path, banks: list[str]) -> set[str]:
    """Compare shared banks against stock, or identify an entirely single-owner new bank."""
    game = game_bank_dir(folder)
    owners = set()
    for name in banks:
        if not _BANK.fullmatch(name):
            continue
        try:
            changed = _read_bank(folder / name, times=True, fingerprints=True)[2]
            if not game or not (game / name).is_file():
                identities = set()
                for key in changed:
                    match = _OWNER.fullmatch(key)
                    if not match:
                        break
                    identities.add(match[1].decode('ascii'))
                else:
                    if len(identities) == 1:
                        owners.update(identities)
                continue
            stock = _read_bank(game / name, times=True, fingerprints=True)[2]
        except _ERRORS:
            continue
        if stock.keys() != changed.keys():
            continue
        duration_owners=set()
        fingerprint_owners=set()
        changed_samples=0
        for key, (duration,sample_hash) in changed.items():
            old_duration,old_hash=stock[key]
            match=_OWNER.fullmatch(key)
            if sample_hash!=old_hash:
                changed_samples+=1
                if match:fingerprint_owners.add(match[1].decode('ascii'))
            if abs(old_duration-duration)>0.05 and match:
                duration_owners.add(match[1].decode('ascii'))
        owners.update(duration_owners)
        # Some tools re-encode every sample in a shared season bank.  Treat
        # broad byte changes as ambiguous, rather than assigning every voice
        # in that bank to the mod.  Sparse or single-owner changes remain useful.
        if len(fingerprint_owners)==1 or changed_samples<=max(1,len(changed)//4):
            owners.update(fingerprint_owners)
    return owners
