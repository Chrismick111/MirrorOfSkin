"""Package the reviewed native core over the matching Workbench release."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
import sys
import tempfile
import zipfile

BASE_VERSION = '0.78.0'
VERSION = '0.79.0'
FLAGS = ('wedge-borrow-native.enable', 'wedge-component-borrow.enable')
ADDON_SOURCE = Path(__file__).resolve().parent.parent / 'addon'
CATALOG = 'Assets/runtime/all_sinners_pools.json'
WORKBENCH_UPDATES = ('Workbench/index.html', 'Workbench/merged_appearances.py',
                     'Workbench/schemes.py', 'Workbench/stage_director.py', 'Workbench/workbench.py',
                     'Workbench/stage_files.py', 'Workbench/chapter_nine.py',
                     'Workbench/chapter_nine_profiles.json', 'Workbench/story_defaults.py',
                     'Assets/runtime/story_defaults.zip')
STORY_TIMINGS = {
    'Assets/runtime/story_native/story_' + look + '.bin' for look in (
        '1306_Thumb_DiscipleAppearance', '1314_Thumb_FatherAppearance', '1318_Pinky_DiscipleAppearance',
        '1319_RingFinger_DiscipleAppearance', '1322_Pinky_FatherAppearance', '1322_Pinky_Father2pAppearance',
        '1325_Index_Disciple_NormalAppearance', '1325_Index_discipleAppearance',
        '1327_MiddleFinger_fatherAppearance', '1327_MiddleFinger_father_Phase4Appearance',
        '1328_MiddleFinger_discipleAppearance', '1331_RingFinger_FatherAppearance',
        '1336_RingFinger_Disciple_CastoffAppearance', '1347_Index_fatherAppearance',
        '1348_Index_father_Phase2Appearance', '1353_Pinky_DiscipleAppearance',
        '1354_RingFinger_DiscipleAppearance', '1355_Index_DiscipleAppearance', '1355_Index_Disciple_NormalAppearance',
    )
}


def repair_catalog(data, timings=None):
    """Correct two shipped addresses verified against the game address catalog."""
    fixes = {'1450_Distorted_ChoiAppearance': ('SD_Enemy', 'SD_Abnormality'),
             '1501_4F_AlriuneAppearance': ('SD_Abnormality', 'SD_Enemy')}
    pools = json.loads(data)
    for look, (old, new) in fixes.items():
        old_key, new_key = (f'{group}/{look}.prefab' for group in (old, new))
        if any(row.get('appearance_name') == look and row.get('asset_key') == old_key
               for pool in pools.values() for row in pool.get('entries', [])):
            # Replace this exact prefab address and retain the local file's formatting.
            data = data.replace(json.dumps(old_key).encode(), json.dumps(new_key).encode())
    pools = json.loads(data)
    verified_clashes = set(json.loads(Path(__file__).with_name('clash_catalog_repairs.json').read_bytes()))
    changed = False
    for pool in pools.values():
        for entry in pool['entries']:
            if entry['identity_id'] in verified_clashes and entry.get('excluded_actions') == ['evade','clash']:
                entry['excluded_actions'] = ['evade']
                changed = True
            # The base Blueprint prefab has an authored parry but all five
            # attack references are null. Its other two forms have real attacks.
            if (entry.get('appearance_name')=='1525_JeanneBlueprint_DefaultAppearance'
                    and not (entry.get('story_metadata') or {}).get('motionList') and not entry.get('no_attack')):
                entry.update(no_attack=True,motion_status='no_attack_observed')
                changed=True
    if not timings:
        return encode(pools) if changed else data
    updates = {}
    timing_row = struct.Struct('<iii128s')
    for path, blob in timings.items():
        magic, version, count, size = struct.unpack_from('<4sIII', blob)
        offset = 16 + timing_row.size * count
        if magic != b'SST1' or version != 1 or len(blob) != offset + size:
            raise ValueError(f'Invalid chapter timing file: {path}')
        metadata = json.loads(blob[offset:])
        names = {}
        for detail, index, parts, label in timing_row.iter_unpack(blob[16:offset]):
            group = names.setdefault(str(detail), ['']*parts)
            group[index] = label.rstrip(b'\0').decode('ascii')
        updates['story_' + metadata['AppearanceName']] = metadata, names
    matched = set()
    for pool in pools.values():
        for entry in pool['entries']:
            identity = entry.get('identity_id')
            if identity in updates:
                metadata, names = updates[identity]
                entry.update(story_metadata=metadata, story_timeline_names=names,
                             verified_attack_details=[int(k) for k in names],
                             metadata_evidence='Game timeline Hit Cheaker / End Cheaker / Give Damage markers where present; see original timeline for remaining fields.')
                matched.add(identity)
    if matched != updates.keys():
        raise ValueError('Chapter timing data has no corresponding catalog appearance')
    return encode(pools)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(doc):
    return (json.dumps(doc, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('addon', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.addon / 'Workbench'))
    from package_release import package
    native = Path(__file__).with_name('SinnersNative.dll').read_bytes()
    manifest = json.loads((args.addon / 'compatibility.json').read_bytes())
    if manifest['version'] != BASE_VERSION or manifest['protocol'] != 75:
        raise ValueError(f'Select the reviewed {BASE_VERSION} / protocol 75 installation')
    expected = manifest['package_files']
    if digest(native) == expected[manifest['dll']].lower() or any(
        marker not in native for marker in (
            b'link coin director adopted', b'heldCameraUpdates=', b'wedge short body scene=', b'GetSpritesWithNameScripting',
            b'submittedPoses=', b'11116_S6_Link_03', b'link donor audio scene=',
            b'link pending handoff scene=', b'form defense sinner=', b'link timed donor sound scene=', b'coinVariant=',
            b'chapter native look=', b'chapter form visible identity=', b'clash fallback look=',
            b'CheckVoiceIndex', b'AddMultiVoice'
        )
    ):
        raise ValueError('Build the updated native core before packaging')
    with tempfile.TemporaryDirectory() as folder:
        stage = Path(folder)
        for name, checksum in expected.items():
            data = (args.addon / name).read_bytes()
            if digest(data) != checksum.lower():
                raise ValueError(f'Installed release changed: {name}')
            path = stage / name
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_bytes(data)
        catalog = Path(CATALOG)
        (stage / catalog).parent.mkdir(parents=True, exist_ok=True)
        info = json.loads((stage / 'addon_info.json').read_bytes())
        info['version'] = manifest['version'] = VERSION
        changes = {manifest['dll']: native, 'addon_info.json': encode(info),
                   'scr.py': (ADDON_SOURCE / 'scr.py').read_bytes()}
        changes.update({name: (ADDON_SOURCE / name).read_bytes() for name in WORKBENCH_UPDATES})
        timings = {}
        for name in sorted(STORY_TIMINGS):
            timings[name] = (ADDON_SOURCE / name).read_bytes()
            if not timings[name].startswith(b'SST1'):
                raise ValueError(f'Missing or invalid chapter timing data: {name}')
        if not (ADDON_SOURCE / 'Assets/runtime/story_native/story_1318_Pinky_DiscipleAppearance.bin').is_file():
            raise ValueError('Missing the rebuilt Pinky S7 timing data')
        changes.update(timings)
        (stage / catalog).write_bytes(repair_catalog((args.addon / catalog).read_bytes(), timings))
        changes.update({flag:b'' for flag in FLAGS})
        for name, data in changes.items():
            (stage / name).parent.mkdir(parents=True, exist_ok=True)
            (stage / name).write_bytes(data)
            expected[name] = digest(data)
        (stage / 'compatibility.json').write_bytes(encode(manifest))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=args.output.parent) as build:
            candidate = Path(build) / args.output.name
            count = package(stage, candidate)
            with zipfile.ZipFile(candidate) as archive:
                if archive.testzip() or set(archive.namelist()) != set(expected) | {'compatibility.json', catalog.as_posix()}:
                    raise ValueError('Archive inventory mismatch')
                for name, checksum in expected.items():
                    if digest(archive.read(name)) != checksum:
                        raise ValueError(f'Archive digest mismatch: {name}')
            candidate.replace(args.output)
    print('RELEASE_OK', VERSION, count, digest(args.output.read_bytes()), 'DLL', digest(native))


if __name__ == '__main__':
    main()
