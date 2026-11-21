"""Build the internal stage table for automatic appearance matching."""

import json
import os
import struct
import zlib

def binary(config):
 groups = []
 types = {'health': 1, 'sanity': 2, 'defense': 3, 'native': 4, 'chapter_phase': 5}
 for group in config['groups']:
  blob = struct.pack('<4I', int(group['enabled']), len(group['stages']), int(group.get('hold', False)), 0)
  for i in range(8):
   if i >= len(group['stages']):
    blob += bytes(144)
    continue
   stage = group['stages'][i]; conditions = stage.get('conditions', [])
   blob += struct.pack('<64s4I', stage['identity_id'].encode('ascii'), stage.get('form', 0), stage.get('priority', i), len(conditions), int(stage.get('match', 'all') == 'any'))
   for j in range(4):
    if j < len(conditions):
     c = conditions[j]
     blob += struct.pack('<IIiI', types[c['metric']], int(c['op'] == 'lte'), c['value'], 0)
    else: blob += bytes(16)
  groups.append(blob)
 payload = b''.join(group['id'].encode('ascii').ljust(64,b'\0') + blob for group,blob in zip(config['groups'],groups))
 return struct.pack('<4I', 0x3247534e, 2, zlib.crc32(payload) & 0xffffffff, len(groups)) + payload

def automatic_groups(root):
 path=root/'Workbench/data/chapter_nine_profiles.json'
 profiles=json.loads(path.read_bytes()) if path.exists() else []
 groups=[]
 for row in profiles:
  key='ch9_'+row['identity']
  group=dict(id=key,enabled=True,hold=row.get('hold',False),stages=row['stages'])
  groups.append(group)
  alternate={'10314':['story_1355_Index_Disciple_NormalAppearance','story_1355_Index_DiscipleAppearance'],
             '10215':['story_1354_RingFinger_DiscipleAppearance','story_1336_RingFinger_Disciple_CastoffAppearance'],
             '11015':['story_1353_Pinky_DiscipleAppearance']}.get(row['identity'])
  if alternate:
   stages=[dict(stage,identity_id=identity) for stage,identity in zip(group['stages'],alternate)]
   groups.append(dict(group,id=key+'_alt',stages=stages))
 pair_path = root / 'Workbench/data/appearance_pairs.json'
 if pair_path.exists():
  groups.extend(_paired_form_groups(json.loads(pair_path.read_bytes())))
 return groups


def _paired_form_groups(registry):
    def key(value):
        return isinstance(value, str) and 0 < len(value) < 64 and value.isascii() and '\0' not in value

    def two_keys(values):
        return (isinstance(values, list) and len(values) == 2 and
                all(key(value) for value in values) and values[0] != values[1])

    verified = set()
    for pair in registry.get('pairs', []):
        base = pair.get('personality')
        for variant in pair.get('aliases', []):
            verified.add((pair.get('identity'), base, variant, pair.get('pool_id')))
    groups = []
    seen = set()
    for mapping in registry.get('native_forms', []):
        identity = mapping.get('identity')
        player, looks = mapping.get('player'), mapping.get('appearances')
        if type(identity) is not int or identity in seen or not two_keys(player) or not two_keys(looks):
            continue
        if not all((identity, player[0], player[1], look) in verified for look in looks):
            continue
        seen.add(identity)
        groups.append({
            'id': 'pair' + str(identity), 'enabled': True, 'hold': False,
            'stages': [
                {'identity_id': looks[0], 'conditions': []},
                {'identity_id': looks[1], 'conditions': [{'metric': 'native', 'op': 'gte', 'value': 1}]},
            ],
        })
    return groups

def runtime_binary(root):
 return binary({'groups': automatic_groups(root)})

def ensure_runtime(root):
 path = root / 'native_stage_groups.bin'
 data = runtime_binary(root)
 if not path.is_file() or path.read_bytes() != data:
  temp = path.with_suffix('.stage-tmp')
  temp.write_bytes(data)
  os.replace(temp, path)
