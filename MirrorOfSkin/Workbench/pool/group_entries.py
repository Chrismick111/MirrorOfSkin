"""Experimental SRP5/NSG2 codec and rule entries. Not wired into the plugin."""
import math
import re
import struct
import zlib

GROUP_ID = re.compile(r'^[A-Za-z0-9_-]{1,63}$')
ROW = struct.Struct('<IIIId64s128s64s64sI64s')
HEADER = struct.Struct('<4I')
SRP5_MAGIC = int.from_bytes(b'SRP5', 'little')
NSG2_MAGIC = int.from_bytes(b'NSG2', 'little')
GROUP_RECORD = 64 + 1168


def valid_group_id(gid):
    return isinstance(gid, str) and bool(GROUP_ID.fullmatch(gid))


def normalize_entry(raw):
    if not isinstance(raw, dict):
        raise ValueError('entry must be an object')
    kind = raw.get('entry_kind', 'appearance')
    weight = raw.get('weight', 1)
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or not 0 <= weight <= 1000000:
        raise ValueError('invalid weight')
    if kind == 'appearance':
        identity = raw.get('identity_id')
        if not isinstance(identity, str) or not identity:
            raise ValueError('missing appearance identity')
        return {'entry_kind': kind, 'identity_id': identity, 'weight': weight}
    if kind == 'group':
        gid = raw.get('group_id')
        if not valid_group_id(gid):
            raise ValueError('invalid group_id')
        return {'entry_kind': kind, 'group_id': gid, 'weight': weight}
    raise ValueError('unknown entry_kind')


def entry_key(entry):
    entry = normalize_entry(entry)
    return (entry['entry_kind'], entry.get('identity_id', entry.get('group_id')))


def validate_entries(entries, catalog, groups):
    result, seen = [], set()
    for raw in entries:
        e = normalize_entry(raw)
        k = entry_key(e)
        if k in seen: raise ValueError('duplicate entry')
        seen.add(k)
        if e['entry_kind'] == 'appearance':
            if e['identity_id'] not in catalog: raise ValueError('unknown appearance')
        else:
            g = groups.get(e['group_id'])
            if not g or not g.get('enabled') or not g.get('stages'):
                raise ValueError('unknown or disabled group')
            if g['stages'][0]['identity_id'] not in catalog:
                raise ValueError('unknown group representative')
        result.append(e)
    return result


def resolve_entry(entry, catalog, groups):
    e = normalize_entry(entry)
    if e['entry_kind'] == 'group':
        group = groups.get(e['group_id'])
        if not group or not group.get('enabled') or not group.get('stages'):
            raise ValueError('unknown or disabled group')
        identity = group['stages'][0]['identity_id']
    else:
        identity = e['identity_id']
    if identity not in catalog: raise ValueError('unknown appearance')
    return dict(catalog[identity], identity_id=identity, entry_kind=e['entry_kind'],
                group_id=e.get('group_id', ''), weight=e['weight'])


def row_key(row):
    return (int(row['sinner']), str(row.get('base_identity', '')), str(row['identity_id']),
            str(row.get('entry_kind', 'appearance')), str(row.get('group_id', '')))


def _bytes(text, size):
    try: val = text.encode('ascii')
    except (AttributeError, UnicodeEncodeError): raise ValueError('field must be ASCII')
    if b'\0' in val or len(val) >= size: raise ValueError('binary field too long or has NUL')
    return val


def pack_rows(rows):
    rows = list(rows)
    if len(rows) > 4096: raise ValueError('too many rows')
    seen, payload = set(), bytearray()
    for row in rows:
        k = row_key(row)
        if k in seen: raise ValueError('duplicate row')
        seen.add(k)
        kind = row.get('entry_kind', 'appearance')
        gid = row.get('group_id', '')
        if kind == 'appearance' and gid: raise ValueError('appearance cannot have group_id')
        if kind == 'group' and not valid_group_id(gid): raise ValueError('invalid group_id')
        if kind not in ('appearance','group'): raise ValueError('unknown entry_kind')
        weight = row.get('weight', 0)
        if isinstance(weight, bool) or not isinstance(weight, (int,float)) or not math.isfinite(weight) or not 0 <= weight <= 1000000: raise ValueError('invalid weight')
        sinner = int(row['sinner'])
        if not 101 <= sinner <= 112: raise ValueError('invalid sinner')
        payload += ROW.pack(sinner, int(row.get('enabled', 1)), int(row.get('mask', 0)),
                int(row.get('reserved', 0)), weight, _bytes(row['identity_id'], 64),
                _bytes(row['asset_key'], 128), _bytes(row['appearance_name'], 64),
                _bytes(str(row.get('base_identity', '')), 64), int(kind == 'group'), _bytes(gid, 64))
    return HEADER.pack(SRP5_MAGIC, 5, len(rows), ROW.size) + payload


def pack_groups_v2(config, stage_director, catalog):
    """Reuse fully validated NSG1 stage encoding, prepend stable ID to each record."""
    if not isinstance(config, dict) or config.get('schema') != 1 or not isinstance(config.get('groups'), list) or len(config['groups']) > 64:
        raise ValueError('invalid group config')
    groups = config['groups']
    ids = set()
    for group in groups:
        stage_director.validate({'schema': 1, 'groups': [group]}, catalog)
        if not valid_group_id(group['id']) or group['id'] in ids: raise ValueError('invalid or duplicate binary group_id')
        ids.add(group['id'])
    v1 = stage_director.binary(config)
    payload = b''.join(_bytes(g['id'],64).ljust(64,b'\0') + v1[16+i*1168:16+(i+1)*1168]
                       for i, g in enumerate(groups))
    return HEADER.pack(NSG2_MAGIC, 2, zlib.crc32(payload)&0xffffffff, len(groups)) + payload
