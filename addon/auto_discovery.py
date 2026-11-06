"""Merge the native game's authoritative identity snapshot; never scrape IDs
from translations or guess a base appearance by filename sorting."""
import json
import pathlib
import re
import struct
import time

FORM = struct.Struct('<64sII256s512s')
NAME = re.compile(r'^[A-Za-z0-9_]{1,63}$')
PREFAB = re.compile(rb'((?:10[1-9]|11[0-2])[0-9]{2}_[A-Za-z0-9_]+(?:Appearance|Appearacne))\.prefab')


def atomic(path, content):
    path = pathlib.Path(path)
    tmp = path.with_name(path.name + '.auto.tmp')
    tmp.write_bytes(content)
    tmp.replace(path)


def json_bytes(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def authoritative_rows(doc, pid, nonce, protocol):
    if doc.get('protocol') != protocol or doc.get('pid') != pid or doc.get('nonce') != nonce:
        return []
    rows = doc.get('rows', [])
    if not isinstance(rows, list) or len(rows) > 4096:
        raise ValueError('Invalid identity snapshot')
    output = []; seen = set()
    for row in rows:
        ident = str(row.get('id', '')); char = row.get('character'); look = row.get('appearance')
        if not re.fullmatch(r'(?:10[1-9]|11[0-2])[0-9]{2}', ident) or type(char) is not int:
            continue
        if str(100 + char) != ident[:3] or not 1 <= char <= 12 or row.get('hidden'):
            continue
        if not isinstance(look, str) or not NAME.fullmatch(look) or not look.startswith(ident + '_'):
            continue
        if ident in seen:
            raise ValueError('Duplicate authoritative identity')
        seen.add(ident); output.append((ident, str(100 + char), look))
    return output


def alternate_prefabs(base, available):
    suffix = 'Appearance' if base.endswith('Appearance') else 'Appearacne' if base.endswith('Appearacne') else None
    if not suffix:
        return []
    stem = base[:-len(suffix)]
    variants = sorted(name for name in available if name != base and name.startswith(stem + '_') and name.endswith(suffix))
    if len(variants) == 1:
        return [base] + variants
    # Multiple forms require an explicit complete stage numbering, not lexical ordering.
    if 1 < len(variants) <= 3:
        indexed = {}
        for name in variants:
            m = re.fullmatch(re.escape(stem) + r'_(?:Stage|Phase)([1-3])' + re.escape(suffix), name)
            if not m or int(m[1]) in indexed:
                return []
            indexed[int(m[1])] = name
        if set(indexed) == set(range(1, len(variants) + 1)):
            return [base] + [indexed[i] for i in range(1, len(variants) + 1)]
    return []


def encode_forms(policies):
    blobs = []
    for ident, p in policies.items():
        names = p['names']; kind = p['kind']
        if not re.fullmatch(r'(?:10[1-9]|11[0-2])[0-9]{2}', ident) or kind not in (1, 2) or not 2 <= len(names) <= 4:
            raise ValueError('Invalid automatic form policy')
        if any(not NAME.fullmatch(n) for n in names):
            raise ValueError('Invalid form name')
        assets = [('SD_Personality/' + n + '.prefab') if kind == 1 else '' for n in names]
        if any(len(a.encode('ascii')) >= 128 for a in assets):
            raise ValueError('Form asset key too long')
        names = names + [''] * (4 - len(names)); assets += [''] * (4 - len(assets))
        blobs.append(FORM.pack(ident.encode('ascii'), kind, len(p['names']), b''.join(n.encode('ascii').ljust(64,b'\0') for n in names), b''.join(a.encode('ascii').ljust(128,b'\0') for a in assets)))
    if len(blobs) > 512:
        raise ValueError('Too many automatic form policies')
    return struct.pack('<4sIII', b'SAF1', 1, len(blobs), FORM.size) + b''.join(blobs)


class Discovery:
    def __init__(self, root, game_dir, pid, nonce, log, protocol):
        self.root = pathlib.Path(root); self.game = pathlib.Path(game_dir)
        self.pid = pid; self.nonce = nonce; self.log = log; self.protocol = protocol
        self.next_poll = 0; self.stamp = None

    def poll(self):
        if time.monotonic() < self.next_poll:
            return False
        self.next_poll = time.monotonic() + 5
        root = self.root
        settings = json.loads((root/'随机设置.json').read_text(encoding='utf-8-sig'))
        if settings.get('auto_discover', True) is False:
            return False
        catalog = self.game/'LimbusCompany_Data/StreamingAssets/aa/catalog.bin'
        exported = root/'identity_catalog.json'
        internal = root/'auto_internal_forms.jsonl'
        paths = [exported, catalog, internal, root/'Assets/runtime/all_sinners_pools.json']
        stamp = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in paths)
        if not exported.exists() or not catalog.exists() or stamp == self.stamp:
            return False
        if exported.stat().st_size > 2*1024*1024 or catalog.stat().st_size > 64*1024*1024:
            raise ValueError('Discovery snapshot/catalog too large')
        doc = json.loads(exported.read_text(encoding='ascii'))
        rows = authoritative_rows(doc, self.pid, self.nonce, self.protocol)
        if not rows:
            return False
        available = {m.decode('ascii') for m in PREFAB.findall(catalog.read_bytes()) if len(m) < 64}
        pool_path = root/'Assets/runtime/all_sinners_pools.json'
        before = pool_path.read_bytes(); pools = json.loads(before.decode('utf-8-sig'))
        localized = {}
        for directory, pattern in [(self.game/'LimbusCompany_Data/Assets/Resources_moved/Localize/en','EN_Personalities*.json'),(self.game/'LimbusCompany_Data/Lang/LLC_zh-CN','Personalities*.json')]:
            for path in directory.glob(pattern):
                try:
                    for item in json.loads(path.read_text(encoding='utf-8-sig')).get('dataList',[]):
                        localized[str(item['id'])] = re.sub(r'<[^>]+>|\s+', ' ', str(item.get('title',''))+' '+str(item.get('name',''))).strip()
                except (OSError, ValueError, KeyError, TypeError):
                    continue
        by_id = {str(e['identity_id']): e for p in pools.values() for e in p['entries']}
        added = []; policies = {}; notes = {}
        source = {i:look for i,_,look in rows}
        registry_path = root/'auto_registry.json'
        registry = json.loads(registry_path.read_text(encoding='utf-8')) if registry_path.exists() else {}
        # Only validated observations from this native session may update the cache.
        if internal.exists() and internal.stat().st_size <= 2*1024*1024:
            for line in internal.read_text(encoding='ascii').splitlines():
                try:
                    item = json.loads(line)
                    if item.get('pid') == self.pid and item.get('nonce') == self.nonce and item.get('protocol') == self.protocol and source.get(item.get('id')) == item.get('appearance'):
                        registry[item['id']] = item
                except (ValueError, TypeError):
                    continue
        for ident, sinner, look in rows:
            # Catalog strings are only a presence filter; the base comes from the game table.
            if sinner not in pools or look not in available:
                continue
            entry = by_id.get(ident)
            if entry is None:
                entry = {'identity_id':ident,'appearance_name':look,'asset_key':'SD_Personality/'+look+'.prefab','forms':[look],'name':localized.get(ident,ident),'weight':1,'auto_discovered':True}
                pools[sinner]['entries'].append(entry);by_id[ident]=entry;added.append(ident)
            if not entry.get('auto_discovered') or entry['appearance_name'] != look:
                continue  # Existing explicit health/sanity policies always take precedence.
            names = alternate_prefabs(look, available)
            item = registry.get(ident, {})
            if names:
                policies[ident] = {'kind':1,'names':names}
            elif item.get('appearance') == look and 2 <= len(item.get('names',[])) <= 4 and all(isinstance(n,str) and NAME.fullmatch(n) for n in item['names']):
                policies[ident] = {'kind':2,'names':item['names']}
            policy = policies.get(ident)
            if policy:
                n = len(policy['names']); label = ' → '.join('外观阶段'+str(i+1) for i in range(n))
                notes[ident] = {'forms':label,'method':'自动识别：每实际使用1次守备（闪避／防御／反击）推进1阶段，最终阶段保持。本场累计；只改变外观。阶段编号为插件标记。','supported':True}
                entry['auto_forms'] = {'kind':policy['kind'],'names':policy['names']}
            else:
                entry.pop('auto_forms',None)
                notes[ident] = {'forms':'新增人格：形态检查','method':'基础外观已入池。首次加载后检查内部形态；复杂组合或无法确认顺序的形态不自动套用。','supported':False}
        binary = encode_forms(policies)
        if pool_path.read_bytes() != before:
            raise RuntimeError('Probability settings changed during discovery; retry later')
        after = json_bytes(pools)
        # All updates are written before the host publishes a reload revision.
        atomic(root/'auto_forms.bin', binary)
        atomic(root/'auto_form_annotations.json', json_bytes({'entries':notes}))
        atomic(registry_path, json_bytes(registry))
        changed = json.loads(before.decode('utf-8-sig')) != pools
        if changed:
            atomic(pool_path, after)
        self.stamp = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in paths)
        if added or changed:
            self.log('Auto discovery: added=%s automatic_forms=%d' % (','.join(added) or 'none', len(policies)))
        return changed
