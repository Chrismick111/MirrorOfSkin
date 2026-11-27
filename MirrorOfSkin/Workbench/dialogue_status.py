"""Combine evidence from the author archive with current, wearer-specific bindings."""
import re


def detected_status(record, scans, records):
    from appearance_dialogue import for_record

    reports = [for_record(scan, record, records=records) for scan in scans]
    model = record.get('model_voice_evidence') or {}
    states = {}
    for kind in ('voice', 'bubble'):
        evidence = [item.get(kind, 'unknown') for item in reports]
        if kind == 'voice':
            evidence.append(model.get('state', 'unknown'))
        states[kind] = next((s for s in ('found', 'text_only', 'found_unattributed', 'unassigned', 'inherited', 'unknown')
                             if s in evidence), 'none')
    return states


def runtime_bindings(root, addon=None):
    """Read the appearance-local WAV and legacy bank maps used by the game."""
    library = root / 'Assets/ImportedVoices'
    try:
        lines = (library / 'bindings.tsv').read_text(encoding='ascii').splitlines()
    except (OSError, UnicodeError):
        lines = []
    from framepack_dialogue import installed_states
    bindings = installed_states(root, addon or root)
    subtitles = {}
    for line in lines:
        fields = line.split('\t')
        if len(fields) != 4:
            continue
        look, owner, revision, bank = fields
        if not (re.fullmatch(r'WBImp_[0-9a-f]{24}', look)
                and re.fullmatch(r'[1-9][0-9]{2,7}', owner)
                and re.fullmatch(r'[a-f0-9]{64}', revision)
                and re.fullmatch(r'[A-Za-z0-9_-]+(?:\.assets)?\.bank', bank, re.I)):
            continue
        folder = library / revision
        if not (folder / bank).is_file():
            continue
        if revision not in subtitles:
            owners = set()
            try:
                with (folder / 'bubbles.tsv').open(encoding='utf8') as stream:
                    for row in stream:
                        parts = row.rstrip('\r\n').split('\t', 2)
                        if len(parts) == 3 and parts[1].startswith('battle') and parts[2].strip():
                            owners.add(parts[0])
            except (OSError, UnicodeError):
                pass
            subtitles[revision] = owners
        status = bindings.setdefault('story_' + look, {})
        status['voice'] = 'connected'
        if owner in subtitles[revision]:
            status['bubble'] = 'connected'
    return bindings


def apply_binding(entry, bindings):
    bound = bindings.get(entry.get('identity_id'))
    if bound:
        entry['dialogue_detection'] = {'voice': 'unknown', 'bubble': 'unknown',
                                       **(entry.get('dialogue_detection') or {}), **bound}
