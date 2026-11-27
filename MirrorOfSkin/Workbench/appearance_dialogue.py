"""Identify battle dialogue materials without treating detection as playback support."""
from collections import defaultdict
from dataclasses import dataclass, field
import json
from pathlib import PurePosixPath
import re
from unicodedata import normalize
from zipfile import BadZipFile, ZipFile


AUDIO_EXTENSIONS = frozenset(('.wav', '.ogg', '.mp3', '.flac', '.opus', '.m4a'))
_MAX_JSON = 16 * 1024**2
_OWNER = r'[1-9][0-9]{2,7}'
_BATTLE = re.compile(r'battle[A-Za-z0-9_-]{0,185}', re.I)
_FRAMEPACK_BATTLE = re.compile(r'battle[a-z0-9]*(?:_[a-z][a-z0-9]*)*_(%s)(?:_[0-9]+)*(?:-[0-9]+)?' % _OWNER, re.I)
_VOICE = re.compile(r'(?:[a-z]{2,3}(?:[-_][a-z]{2,4})?_)?voice_[\w-]+\.json', re.I)
_BUBBLE = re.compile(r'(?:[a-z]{2,3}(?:[-_][a-z]{2,4})?_)?battlespeechbubbledlg(?:[-_][\w-]+)?\.json', re.I)
_BATTLE_DIRS = {'battlespeechbubbletext', 'battlespeechbubbledlg'}
_STORY_DIRS = {'story', 'stories', 'storydlg', 'storydialogue', 'storytext', 'cutscenes', 'cutscene'}
_EFFECT_DIRS = {'sfx', 'bgm', 'music', 'effects'}
_SCOPE_DIRS = {'custom_sounds', 'custom_limbus_locale', 'motion_appearances', 'custom_appearance'}


@dataclass(frozen=True)
class Evidence:
    kind: str
    state: str
    scope: tuple
    owner: str = ''
    label: str = ''
    bank: str = ''
    scope_exact: bool = False


@dataclass
class Scan:
    evidence: set = field(default_factory=set)
    aliases: dict = field(default_factory=lambda: defaultdict(set))
    skill_owners: dict = field(default_factory=lambda: defaultdict(set))
    sounds: dict = field(default_factory=lambda: defaultdict(set))
    unreadable: bool = False


def _path(value):
    path = PurePosixPath(str(value).replace('\\', '/').casefold())
    if not path.is_absolute() and '..' not in path.parts and ':' not in str(path):
        return path
    return None


def _scope(path):
    return next((path.parts[:i] for i, name in enumerate(path.parts) if name in _SCOPE_DIRS),
                path.parent.parts)


def _key(value):
    return ''.join(c for c in normalize('NFKC', str(value)).casefold() if c.isalnum())


def _owner(value):
    return str(value) if re.fullmatch(_OWNER, str(value)) else ''


def _event_owner(event):
    match = re.search(r'_(%s)_[0-9]+$' % _OWNER, event)
    return match[1] if match else ''


def subtitle_file(path):
    """Identify supported locale documents even when they carry a language prefix."""
    path = _path(path)
    if path is None or path.suffix != '.json' or _STORY_DIRS.intersection(path.parts[:-1]):
        return None
    if _VOICE.fullmatch(path.name):
        return 'voice'
    if _BUBBLE.fullmatch(path.name) or _BATTLE_DIRS.intersection(path.parts[:-1]):
        return 'bubble'
    return None


def subtitle_owner(path):
    if subtitle_file(path) == 'voice':
        return _owner(PurePosixPath(path).stem.rsplit('_', 1)[-1])
    return ''


def battle_dialogue(data, path):
    """Yield valid battle event, owner, text triples from a game locale document."""
    rows = data.get('dataList') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return
    owner = subtitle_owner(path)
    for row in rows:
        if not isinstance(row, dict):
            continue
        event = row.get('id')
        line = row.get('dlg')
        if not isinstance(event, str) or not _BATTLE.fullmatch(event) or not isinstance(line, str):
            continue
        event_owner = _event_owner(event)
        if not event_owner:
            ids = {part for part in event.split('_') if part == owner or re.fullmatch('[1-9][0-9]{4}', part)}
            if len(ids) == 1:
                event_owner = next(iter(ids))
            elif ids:
                continue
        line = _battle_line(line)
        if line and not (owner and event_owner and owner != event_owner):
            yield event, owner or event_owner, line


def _battle_line(line):
    if not isinstance(line, str):
        return ''
    line = ' '.join(re.sub(r'[\x00-\x1f\x7f]', ' ', line).split())
    if (not any(0xD800 <= ord(char) <= 0xDFFF for char in line)
            and len(line.encode('utf8')) <= 4095):
        return line
    return ''


def _framepack_owner(event):
    match = _FRAMEPACK_BATTLE.fullmatch(event) if _BATTLE.fullmatch(event) else None
    return match[1] if match else ''


def _scan_framepack(archive, skin, scan):
    voice_dir = _path(skin.voice_dir) if skin.voice_dir else None
    locale_dir = _path(skin.locale_exclusive_dir) if skin.locale_exclusive_dir else None
    scope = _path(skin.package_root).parts
    owner = skin.personality
    lines = defaultdict(set)
    for name, info in skin.members.items():
        path = PurePosixPath(name)
        if (voice_dir is not None and path.is_relative_to(voice_dir) and path.suffix == '.wav'
                and _framepack_owner(path.stem) == owner):
            try:
                valid = _audio_valid(archive, info, path)
            except (BadZipFile, OSError, RuntimeError, NotImplementedError):
                valid = False
            scan.evidence.add(Evidence('voice', 'found' if valid else 'unknown', scope, owner, scope_exact=True))
        if (locale_dir is None or not path.is_relative_to(locale_dir)
                or not _BATTLE_DIRS.intersection(path.relative_to(locale_dir).parts[:-1])
                or subtitle_file(path) != 'bubble'):
            continue
        try:
            data = json.loads(archive.read(info)) if info.file_size <= _MAX_JSON else None
        except (BadZipFile, OSError, ValueError, RuntimeError, NotImplementedError, RecursionError):
            data = None
        if not isinstance(data, dict):
            scan.evidence.add(Evidence('bubble', 'unknown', scope, owner, scope_exact=True))
            continue
        rows = data.get('dataList')
        entries = ((row.get('id'), row) for row in rows if isinstance(row, dict)) if isinstance(rows, list) else data.items()
        for event, row in entries:
            if (isinstance(event, str) and isinstance(row, dict) and row.get('id') == event
                    and _framepack_owner(event) == owner):
                line = _battle_line(row.get('dlg'))
                if line:
                    lines[event.casefold()].add(line)
    if lines:
        state = 'found' if any(len(choices) == 1 for choices in lines.values()) else 'unknown'
        scan.evidence.add(Evidence('bubble', state, scope, owner, scope_exact=True))


def _audio_valid(archive, info, path):
    if info.file_size < 12:
        return False
    with archive.open(info) as stream:
        head = stream.read(64)
    if path.suffix == '.wav':
        return head[:4] in (b'RIFF', b'RF64') and head[8:12] == b'WAVE' and info.file_size > 44
    return (head.startswith((b'OggS', b'fLaC', b'ID3'))
            or (path.suffix == '.mp3' and head[0] == 255 and head[1] & 224 == 224)
            or (path.suffix == '.m4a' and head[4:8] == b'ftyp'))


def _root_aliases(scan, path, data):
    if not data or 'custom_limbus_data' not in path.parts:
        return
    index = path.parts.index('custom_limbus_data')
    if path.parts[index + 1:index + 2] != ('personality',):
        return
    rows = data.get('list')
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        owner = _owner(row.get('id'))
        appearance = row.get('appearance', '')
        if owner and isinstance(appearance, str):
            parts = re.sub(r'^!(?:motions|custom)_', '', appearance, flags=re.I).split('_')
            aliases = {_key(path.stem), _key(parts[0])} - {''}
            scope = path.parts[:index]
            scan.aliases[scope, owner].update(aliases)
            ids = set()
            for key in ('attributeList', 'skillIdList', 'defenseSkillIDList'):
                values = row.get(key)
                if isinstance(values, list):
                    ids.update(str(x.get('skillId') if isinstance(x, dict) else x) for x in values)
            for skill in ids:
                if skill.isascii() and skill.isdecimal():
                    scan.skill_owners[scope, skill].add(owner)


def _sound_reference(base, value):
    path = _path(value) if isinstance(value, str) else None
    if path is not None and path.suffix in AUDIO_EXTENSIONS:
        candidate = base / path
        if not _EFFECT_DIRS.intersection(path.parts[:-1]) and not _STORY_DIRS.intersection(path.parts[:-1]):
            return candidate
    return None


def _add_audio(archive, items, scan, path, ref, *, owner='', label=''):
    if ref is None or ref not in items:
        return
    try:
        valid = _audio_valid(archive, items[ref], ref)
    except (OSError, BadZipFile, RuntimeError, NotImplementedError):
        valid = False
    scan.evidence.add(Evidence('voice', 'found' if valid else 'unknown', _scope(path), owner, label))


def _audio_manifest(archive, items, scan, path, data, mapped):
    rows = data.get('lines')
    manifest_owner = _owner(data.get('personalityId'))
    if manifest_owner and isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            ref = _sound_reference(path.parent, row.get('file'))
            if ref is not None:
                mapped.add(ref)
            event = row.get('voiceId')
            if not isinstance(event, str) or not _BATTLE.fullmatch(event):
                continue
            owner = _event_owner(event)
            if owner and owner != manifest_owner:
                continue
            _add_audio(archive, items, scan, path, ref, owner=manifest_owner)
            if isinstance(row.get('text'), str) and row['text'].strip():
                scan.evidence.add(Evidence('bubble', 'text_only', _scope(path), manifest_owner))
    if path.name != 'audio.json' or not isinstance(data.get('sounds'), list):
        return
    for row in data['sounds']:
        if not isinstance(row, dict) or str(row.get('soundType')).casefold() != 'voice':
            continue
        ref = _sound_reference(path.parent, row.get('file'))
        name = row.get('name')
        if ref is not None and isinstance(name, str):
            scan.sounds[_scope(path), name.casefold()].add(ref)
            role = re.match(r'^(.*?)(?:battle(?:voice)?|combat(?:voice)?|voice[_ -]?battle)[_ -]*[0-9]+$', name, re.I)
            if role:
                _add_audio(archive, items, scan, path, ref, label=_key(role[1]))


def _skill_dialogue(archive, items, scan, path, data):
    rows = data.get('list')
    if not isinstance(rows, list):
        return
    scope = path.parts[:path.parts.index('custom_limbus_data')]
    for row in rows:
        if not isinstance(row, dict):
            continue
        owners = scan.skill_owners.get((scope, str(row.get('id'))), ())
        if not owners:
            continue
        pending = [row]
        while pending:
            node = pending.pop()
            if isinstance(node, list):
                pending.extend(node)
                continue
            if not isinstance(node, dict):
                continue
            pending.extend(node.values())
            script = node.get('scriptName')
            if not isinstance(script, str) or not re.match(r'^Modular/TIMING:', script, re.I):
                continue
            lines = re.findall(r'\bbattledialogline\(\s*(Self|id[0-9]+)\s*,([^()]+)\)', script, re.I)
            sounds = re.findall(r'\bplaycustomsound\(\s*([^(),]+?)\s*\)', script, re.I)
            speakers = set()
            for speaker, text in lines:
                if text.strip(' _'):
                    target = _owner(speaker[2:])
                    speakers.update(owners if speaker.casefold() == 'self' else {target} if target else ())
            for speaker in speakers:
                scan.evidence.add(Evidence('bubble', 'found', scope, speaker))
            for name in sounds:
                refs = scan.sounds.get((scope, name.casefold()), ())
                if len(refs) == 1:
                    ref = next(iter(refs))
                    # A summon or ally skill can ask a different author unit to speak.
                    alias = re.match(r'^(.*?)(?:battle(?:voice)?|combat(?:voice)?|voice[_ -]?battle)[_ -]*[0-9]+$', name, re.I)
                    named = {uid for (root, uid), names in scan.aliases.items()
                             if root == scope and alias and _key(alias[1]) in names}
                    candidates = named or speakers or set(owners)
                    if len(candidates) == 1:
                        _add_audio(archive, items, scan, ref, ref, owner=next(iter(candidates)))
                    elif candidates:
                        _add_audio(archive, items, scan, ref, ref)


def _scan_bank(archive, info, path, scan):
    from shutil import copyfileobj
    from pathlib import Path
    from bank_evidence import _read_bank, _ERRORS, probe_targets
    from model_workspace import model_tempdir

    original = PurePosixPath(info.filename.replace('\\', '/')).name
    if (not 12 <= info.file_size <= 1024**3 or not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.assets)?\.bank', original, re.I)
            or path.name.startswith('master.')):
        return
    with archive.open(info) as stream:
        header = stream.read(12)
        if (header[:4], header[8:]) != (b'RIFF', b'FEV '):
            return
        with model_tempdir(prefix='mos-dialogue-bank-') as folder:
            bank = Path(folder) / original
            with bank.open('wb') as out:
                out.write(header)
                copyfileobj(stream, out, 1024*1024)
            try:
                events, audio, clips = _read_bank(bank, times=True)
            except _ERRORS:
                return
            battle = {_event_owner(name.decode('ascii', errors='ignore')) for name in clips
                      if _BATTLE.fullmatch(name.decode('ascii', errors='ignore'))}
            owners = (battle - {''}) & probe_targets(bank.parent, [bank.name])
            for owner in owners:
                scan.evidence.add(Evidence('voice', 'found', _scope(path), owner, bank=path.name))
            if battle and not owners:
                scan.evidence.add(Evidence('voice', 'unassigned', _scope(path), bank=path.name))
            elif not battle and events:
                # An explicitly declared bank can carry audio in its companion asset bank.
                scan.evidence.add(Evidence('voice', 'unknown', _scope(path), bank=path.name))


def scan_archive(zip_path):
    """Build a reusable index from a normalized archive."""
    scan = Scan()
    mapped = set()
    skills = []
    try:
        with ZipFile(zip_path) as archive:
            from framepack_manifest import read_framepacks

            framepacks = read_framepacks(archive)
            framepack_members = {name for skin in framepacks for name in skin.members}
            for skin in framepacks:
                _scan_framepack(archive, skin, scan)
            grouped = defaultdict(list)
            for info in archive.infolist():
                path = _path(info.filename)
                if path is not None and str(path) not in framepack_members and not info.is_dir():
                    grouped[path].append(info)
            items = {path: infos[0] for path, infos in grouped.items() if len(infos) == 1}
            scan.unreadable = any(len(infos) > 1 and (subtitle_file(path) or path.suffix in AUDIO_EXTENSIONS)
                                  for path, infos in grouped.items())
            for path, info in items.items():
                if path.suffix != '.json':
                    continue
                subtitle = subtitle_file(path)
                sound = 'custom_sounds' in path.parts[:-1]
                persona = 'custom_limbus_data' in path.parts and 'personality' in path.parts
                skill = ('custom_limbus_data' in path.parts
                         and path.parts[path.parts.index('custom_limbus_data') + 1:-1] == ('skill',))
                if not (subtitle or sound or persona or skill):
                    continue
                try:
                    data = json.loads(archive.read(info)) if info.file_size <= _MAX_JSON else None
                except (BadZipFile, ValueError, OSError, RuntimeError, NotImplementedError, RecursionError):
                    data = None
                if not isinstance(data, dict):
                    if subtitle:
                        scan.evidence.add(Evidence('bubble', 'unknown', _scope(path), subtitle_owner(str(path))))
                    continue
                if subtitle:
                    for _, owner, _ in battle_dialogue(data, str(path)):
                        scan.evidence.add(Evidence('bubble', 'found', _scope(path), owner))
                if persona:
                    _root_aliases(scan, path, data)
                if sound:
                    _audio_manifest(archive, items, scan, path, data, mapped)
                if skill:
                    skills.append((path, data))
            for path, data in skills:
                _skill_dialogue(archive, items, scan, path, data)
            for path, info in items.items():
                if (_STORY_DIRS | _EFFECT_DIRS).intersection(path.parts[:-1]):
                    continue
                if path.suffix == '.bank':
                    _scan_bank(archive, info, path, scan)
                elif path.suffix in AUDIO_EXTENSIONS and 'custom_sounds' in path.parts[:-1] and path not in mapped:
                    event = path.stem
                    match = re.fullmatch(r'(?:voice[_ -]?)?(.*?)battle(?:voice)?[_ -]*[0-9]+', event)
                    owner = _event_owner(event) if _BATTLE.fullmatch(event) else ''
                    voice_dir = 'voice' in path.parts[:-1] or 'voices' in path.parts[:-1]
                    if owner or match and (voice_dir or event.startswith('voice_')):
                        _add_audio(archive, items, scan, path, path, owner=owner,
                                   label=_key(match[1]) if match else '')
                    elif voice_dir and event.startswith('voice_'):
                        try:
                            if _audio_valid(archive, info, path):
                                scan.evidence.add(Evidence('voice', 'unassigned', _scope(path)))
                        except (BadZipFile, RuntimeError, OSError, NotImplementedError):
                            scan.evidence.add(Evidence('voice', 'unknown', _scope(path)))
    except (OSError, BadZipFile, RuntimeError, NotImplementedError):
        scan.unreadable = True
    return scan


def _record_info(record):
    private = record.get('entry', {}).get('private_declaration') or {}
    voice = (record.get('policy') or {}).get('voice') or {}
    # A private appearance's replacement target is a different owner's identity.
    fallback = '' if private else _owner(str(record.get('asset', '')).rpartition('/')[2].split('_')[0])
    owners = {_owner(private.get('personality')), _owner(voice.get('owner')), fallback} - {''}
    path = _path(private.get('root', ''))
    return path.parts if path is not None else (), owners, voice.get('bank', '').casefold()


def for_record(scan, record, records=None):
    """Report evidence for one author appearance by declaration, scope and event owner."""
    records = tuple(records) if records is not None else (record,)
    scope, owners, bank = _record_info(record)
    status = dict.fromkeys(('voice', 'bubble'), 'unknown' if scan.unreadable else 'none')
    priority = {'none': 0, 'unknown': 1, 'unassigned': 2, 'text_only': 3, 'found': 4}
    for item in scan.evidence:
        if (item.scope_exact or scope and item.scope) and item.scope != scope:
            continue
        if item.owner:
            if item.owner not in owners:
                continue
            state = item.state
        elif item.label:
            candidates = set().union(*(names for (root, uid), names in scan.aliases.items()
                                       if root == item.scope and uid in owners))
            candidates.update(_key(record.get(key, '')) for key in ('name', 'legacy_name'))
            declared = {uid for (root, uid), names in scan.aliases.items()
                        if root == item.scope and item.label in names}
            if declared and not declared.intersection(owners):
                continue
            if len(declared) > 1 or item.label not in candidates:
                state = 'unassigned'
            else:
                state = item.state
        elif item.bank and item.bank == bank and item.state == 'unknown':
            state = 'unknown'
        elif item.state == 'found':
            local = [other for other in records if _record_info(other)[0] == item.scope]
            declared = [uid for (root, uid) in scan.aliases if root == item.scope]
            state = ('found' if len(declared) == 1 and declared[0] in owners and local == [record]
                     and not item.bank else 'unassigned')
        else:
            state = item.state
        if priority[state] > priority[status[item.kind]]:
            status[item.kind] = state
    return status
