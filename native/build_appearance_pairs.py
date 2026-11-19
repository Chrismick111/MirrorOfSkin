"""Build the portable counterpart registry from an installed pool and authoring databases.

The registry names exact appearances. A shared weapon, rank or reused timeline
is insufficient to identify the character who owns it. Reviewed actor/role
matches below are supplemented with matching attacks and sound cues from the
two sides. LimbusArchive is a build input only.
"""
import argparse
import collections
import gzip
import json
import re
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent

# Each numeric selector is a complete prefab ID, never a string prefix.
# Every form sharing an ID must refer to the same actor. Deliberately use the
# full prefab if an ID is reused for different characters or props.
COUNTERPARTS = {
    10104: ('8044', 'Dongbaek wielding Effloresced E.G.O Spicebush'),
    10107: ('8104', 'Starbuck, first mate of the Pequod'),
    10111: ('8058', 'Faelantern, source of the FairyLantern LCE identity and its root attacks'),
    10113: ('1136 8630', 'Fell Bullet: Gubo wielding the E.G.O and its source Der Fluchschütze share its firing sequence'),
    10116: ('8550', 'Dimension Shredder uses Wayward Passenger dimensional cuts'),
    10204: ('8029 8030', 'Kromer, the One Who Grips, including her second encounter form'),
    10209: ('90126_Butler_W_1Appearance 90126_Butler_W_1_v1Appearance', 'Wuthering Heights butler with Interloper Reception'),
    10210: ('91018', 'MultiCrack Office representative Sasha; bloodbag encounter'),
    10211: ('400007 8577', 'LCE researcher Alyssa using Ardor Blossom Star and the Ardor Blossom Moth supplying its E.G.O'),
    10212: ('1126 1133', 'Zilu, Mao branch adept, including both encounter prefabs'),
    10309: ('90143', 'Class 3 collector with T Corp. Accelerated Amputator'),
    10310: ('8380 1079', 'Sancho and berserk Sancho; the DarkSancho identity assumes management of La Manchaland'),
    10312: ('400003', 'Queen of Hatred: the magical girl E.G.O identity uses her Arcana attack'),
    10315: ('1506', 'Le Noir brand manager; Cometh the Nail and Summoneth the Nail'),
    10408: ('8171', 'Nelly, chief butler of the Edgar family'),
    10412: ('1135', 'Jia Huan wielding Contempt, Awe'),
    10413: ('400002', 'Lin Daiyu, drifting blade of Hongyuan'),
    10416: ('1483', 'Le Noir Footwear Hall: One-leg uses the matching couture kick sequence'),
    10504: ('91005 91006', 'Guido the Persistent, N Corp. Großhammer'),
    10505: ('90051', 'Rosespanner fixer with the same Meursault hammer attack recordings'),
    10508: ('8153 30501 40501 400040', 'Bamboo-hatted Kim; Blade Lineage mentor, original combat forms and LCD appearance'),
    10509: ('91016', 'Dead Rabbits Boss: same rank and Smackdown'),
    10511: ('8371 8375', 'Camille of Cinq West Section 3 and his bloodbag form'),
    10512: ('1145', 'Lei Heng, Thumb East Capo IIII'),
    10513: ('8350', 'Cassetti, Prince of La Manchaland'),
    10515: ('91043 91044', 'Bear variant of the Ring Fauvist students'),
    10603: ('91003', 'Tingtang boss and his three knife attacks'),
    10605: ('8501 8502', 'K Corp. Class 3 Excision Staff; ordinary and empowered forms'),
    10610: ('90156 90157', 'Fanghunt Office fixers wielding the same Slam attack'),
    10613: ('1137', 'Jia Qiu, the Lord of Hongyuan'),
    10615: ('1448 1449', 'S Corp. Ch’unokkun: Incapacitate and Bind share distinct attacks with this identity'),
    10617: ('1481', '3F floor manager in the Le Noir public address room'),
    10704: ('90032', 'N Corp. Kleinhammer using the matching mace recordings'),
    10701: ('8164', 'Heathcliff in the Dead Rabbits disguise performs all three LCB Heathcliff attacks'),
    10705: ('8043 8046', 'Dongbaek wearing Sunshower and the Drifting Fox supplying its umbrella E.G.O'),
    10707: ('8103', 'Queequeg, Pequod harpooneer'),
    10710: ('8172 8173_MaouHeathclif_Main2Appearance 8173_MaouHeathclif_RideAppearance', 'Erlking Heathcliff and his mounted Wild Hunt form'),
    10715: ('8099_MiddleFinger_RicardoAppearance 8099_MiddleFinger_Ricardo_2Appearance', 'Ricardo, Middle Big Brother, including his second encounter'),
    10717: ('1496', 'Le Rouge King of Needleworks'),
    10805: ('90058', 'Lobotomy E.G.O Sloshing wielder in Canto IV'),
    10808: ('8105 8106_Ahab_AwakenAppearance 8582', 'Ahab, captain of the Pequod; ordinary and awakened appearances'),
    10809: ('90122', 'Veteran Edgar Family Butler using Housekeeping and Restraining Technique'),
    10812: ('400001 400005', 'Jia Xichun, including her cultivation form'),
    10814: ('400037', 'Kira, the allied form of the Middle Apprentice'),
    10815: ('400038', 'Aeng-du, LCD OSIR agent'),
    10816: ('1466', 'Le Rouge high domestic, L’Inamovible'),
    10904: ('90035', 'N Corp. Mittelhammer using the matching Rodion attacks'),
    10905: ('91008', 'Rosespanner representative Niko and Vibration Compression'),
    10909: ('90142', 'T Corp. Class 2 Collection Staff: matching rank and collector equipment'),
    10911: ('8381', 'Dulcinea, Princess of La Manchaland'),
    10913: ('1223', 'The Knight of Despair: Arcana: Tear and Pierce'),
    10915: ('1422 1423', 'Rufo, the Ring Fauvist docent, including his wolf form'),
    10917: ('1495', 'Annette the Alterationist, Le Rouge alteration shop'),
    11001: ('91026', 'Training opponent Sinclair uses the LCB base appearance and belongs to Limbus Company LCB'),
    11004: ('91004', 'Aida, Los Mariachis jefe; enemy plays Sinclair’s mariachi skill recordings'),
    11006: ('91009 90059', 'Marile and Canto IV wearers of the same Red Sheet E.G.O equipment'),
    11009: ('1582 1587', 'Philip of Dawn Office and his awakened Waxen Pinion'),
    11012: ('91020', 'Werner, the Little Brother, with shared Middle attack recordings'),
    11016: ('1484 1517', 'The Crimson God of Le Rouge, inchoate and adult combat forms'),
    11103: ('91001 91002', 'Old G Corp. head manager and festered head manager; both use Onslaught Command'),
    11108: ('91014 90136', 'Josephine, Wuthering Heights chief butler, and her Wild Hunt appearance'),
    11111: ('8372', 'Nicolina, the Barber of La Manchaland'),
    11205: ('90053', 'Rosespanner saw wielder with the Rev Up attack and enemy_sawhuman sound cues'),
    11207: ('91012', 'Smee, first mate of the Twinhook Pirates'),
    11209: ('90138', 'Linton, heir to the Edgar family; Wild Hunt appearance'),
    11210: ('8378', 'Priest of La Manchaland, Sacrifice for the Family'),
    11215: ('8045', 'Shock Centipede, source of AEDD, with Electric Release'),
    11216: ('1580', 'Salvador, Dawn Office representative'),
    10216: ('1581', 'Yuna, Dawn Office fixer'),
}

# Source ordering follows the pool's native base/alternate appearance order.
# 8173 Main2 is a walking alternate: keep its ordinary skill mapping, while the
# mounted transition goes specifically to the Ride appearance.
NATIVE_FORMS = {
    10710: ('8172_MaouHeathclif_MainAppearance', '8173_MaouHeathclif_RideAppearance'),
    10915: ('1422_RingFinger_FauvismeDocent_WolfAppearance', '1423_RingFinger_FauvismeDocent_Wolf2pAppearance'),
    11009: ('1582_PhilipAppearance', '1587_Philip_AwakenAppearance'),
    11016: ('1484_Buffet_ImmatureAppearance', '1517_Buffet_PerfectAppearance'),
}


def database(data, name):
    files = list((data / name).glob('*.json.gz'))
    if not files:
        raise FileNotFoundError(f'Missing {name} snapshot')
    with gzip.open(max(files, key=lambda p: p.name), 'rt', encoding='utf-8') as stream:
        return json.load(stream)


def skill_names(skill):
    return {up['name'].casefold(): up['name'] for up in skill.get('up', {}).values() if up.get('name')}


def enemy_skills(variant):
    result = set(variant.get('skills', []))
    for part in variant.get('parts', []):
        if isinstance(part, dict):
            result.update(enemy_skills(part))
    return result


def resources(addon, archive):
    pools = json.loads((addon / 'Assets/runtime/all_sinners_pools.json').read_bytes())
    source, target = {}, {}
    for pool in pools.values():
        for row in pool['entries']:
            key = row['identity_id']
            if key.isdecimal():
                source[int(key)] = row
            elif key.startswith('story_'):
                target[row['appearance_name']] = row
    units = {u['id']: u for u in database(archive, 'unit_db')['ids']}
    enemy = database(archive, 'enemy_db')
    enemy_labels = collections.defaultdict(set)
    attacks = collections.defaultdict(dict)
    for row in enemy['list']:
        app = row['app']
        enemy_labels[app].add(row['name'])
        for variant in row['variants']:
            for number in enemy_skills(variant):
                attacks[app].update(skill_names(enemy['skills'].get(str(number), {})))
    sound = {}
    for path in (addon / 'Workbench/timeline_data').glob('*.json.z'):
        row = json.loads(zlib.decompress(path.read_bytes()))
        sound[row['appearance']] = {
            e['label'] for r in row['records'] if r.get('detail') in range(7, 17)
            for m in r.get('matches', []) for e in m.get('events', [])
            if e.get('kind') == 'sound' and e.get('label')}
    return source, target, units, enemy_labels, attacks, sound


def expected_contracts():
    text = (ROOT / 'chapter_nine_playback.h').read_text(encoding='utf-8')
    records = []
    for line in text.splitlines():
        match = re.match(r'\s*\{"(\d{5}_[^"]+)",(?:NULL|"[^"]+"),\{([^}]+)\}\}', line)
        if match:
            records.extend((int(match[1][:5]), app, 'chapter9', 'Chapter IX actor and phase contract')
                           for app in re.findall(r'"([^"]+)"', match[2]))
    text = (ROOT / 'wedge_identity.h').read_text(encoding='utf-8')
    records += [(int(key[:5]), app, 'wedge', 'Wedge Office role and authentic link timeline')
                for key, app in re.findall(r'\{"(\d{5}_[^"]+)","story_([^"]+)",\d+\}', text)]
    if len(records) != 22:
        raise ValueError('The chapter IX or Wedge contract changed; review counterpart ownership')
    return records


def build(addon, archive):
    source, target, units, enemy_labels, attacks, sound = resources(addon, archive)
    specs = expected_contracts()
    for ident, (selectors, reason) in COUNTERPARTS.items():
        for selector in selectors.split():
            names = [k for k in target if k == selector or k.split('_', 1)[0] == selector]
            if len(names) != 1:
                raise ValueError(f'Expected a unique appearance for {ident} / {selector}: {names}')
            specs.extend((ident, app, 'named', reason) for app in names)
    pairs = []
    seen = set()
    for ident, app, family, reason in sorted(specs):
        if (ident, app) in seen:
            raise ValueError(f'Duplicate {ident}/{app}')
        seen.add((ident, app))
        player = source[ident]
        unit = units[ident]
        forms = list(dict.fromkeys(player.get('forms', [])))
        base = player['appearance_name']
        evidence = [reason, 'Identity title: ' + unit['title']]
        labels = sorted(enemy_labels[app])
        if labels:
            evidence.append('Encounter names: ' + ' / '.join(labels))
        common = sorted({label for s in unit['skills'] for label in skill_names(s)} & attacks[app].keys())
        if common:
            evidence.append('Shared attack names: ' + ' / '.join(attacks[app][label] for label in common))
        cues = sorted(set.union(set(), *(sound.get(f, set()) for f in [base, *forms])) & sound.get(app, set()))
        if cues:
            evidence.append('Shared attack sound cues: ' + ' / '.join(cues[:4]))
        pairs.append(dict(identity=ident, personality=base, aliases=[f for f in forms if f != base],
                          appearance='story_' + app, pool_id=target[app]['identity_id'],
                          family=family, evidence=evidence))
    native = []
    for ident, looks in NATIVE_FORMS.items():
        player = source[ident]
        forms = player['forms']
        if len(set(forms)) != 2 or len(forms) != 2 or forms[0] != player['appearance_name']:
            raise ValueError(f'Unexpected native player forms: {ident}/{forms}')
        if any((ident, look) not in seen for look in looks):
            raise ValueError(f'Missing counterpart for a native form of {ident}')
        native.append(dict(identity=ident, player=forms,
                           appearances=[target[look]['identity_id'] for look in looks]))
    return dict(schema=1, pairs=pairs, native_forms=native)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('addon', type=Path)
    parser.add_argument('archive_data', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'addon/Workbench/appearance_pairs.json')
    args = parser.parse_args()
    data = build(args.addon, args.archive_data)
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"{len(data['pairs'])} exact appearance pairs")
