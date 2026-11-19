"""Read and publish the JSON and binary stage definitions used by the workbench and launcher."""
import hashlib
import json
import os
import struct
import zlib

FILE = 'stage_director.json'

def snapshot(root):
 path = root / FILE
 data = path.read_bytes() if path.exists() else b''
 return {'revision': hashlib.sha256(data).hexdigest(), 'config': json.loads(data.decode('utf-8-sig')) if data else {'schema': 1, 'groups': []}}

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

def publish(root, config):
 # Publish the binary first. An interrupted legacy migration can then retry from the old JSON.
 blobs = {'native_stage_groups.bin': binary(config), FILE: json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False).encode('utf8')}
 originals = {name: (root / name).read_bytes() if (root / name).exists() else None for name in blobs}
 written = []
 try:
  for name, data in blobs.items():
   tmp = root / (name + '.tmp'); tmp.write_bytes(data); os.replace(tmp, root / name); written.append(name)
 except Exception:
  for name in reversed(written):
   if originals[name] is None: (root / name).unlink(missing_ok=True)
   else:
    tmp = root / (name + '.rollback'); tmp.write_bytes(originals[name]); os.replace(tmp, root / name)
  raise
 return snapshot(root)

def migrate(root, upgrade):
 """Caller holds workbench-save.lock across the read, compare and publication."""
 try:
  current = snapshot(root)['config']
 except (ValueError, UnicodeError):
  return
 updated = upgrade(current)
 if updated is not current:
  publish(root, updated)
