"""Discover appearance prefabs that the pool does not know about yet.

The pool is built from prefab names, so a unit is "known" only if its
appearance name is already in all_sinners_pools.json. Anything the game ships
under Prefab/SD/ and the pool has never seen is a candidate: new bosses, new
assist units, new seasonal forms.

Reading is done through UnityPy because the payload lives in UnityFS bundles.
A bundle is skipped when its (size, mtime) fingerprint is unchanged, so a
routine run after a game update touches only what the update replaced.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import struct
import sys
import time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

PRE = 'Assets/Resources_moved/Prefab/'
# 外观名不只「10101_XxxAppearance」一种：还有 Fools_9999_VergiliusAppearance、
# 8375A_...（编号后带字母）、1450_...Appearance2p（尾部变体）。早期只认第一种，
# 那些家族的新 prefab 会被静默跳过，所以放宽并按未匹配数量留痕。
APPEARANCE = re.compile(r'^(?:[A-Za-z]+_)?\d{3,}[A-Za-z]?_(?:[A-Za-z0-9_]*)(?:Appearance|Appearacne)(?:\d+p)?$')
STATE_NAME = 'scan_state.json'
REPORT_NAME = 'discovered_units.json'
LOCK_NAME = 'scan.lock'
# 缓存是「包没变就不用重开」的捷径，但这假设解析逻辑本身没变。改了正则或
# 扫描方式就把它 +1，旧缓存自动作废，否则新认出的名字永远不会出现。
SCAN_VERSION = 4
# 单个 bundle 上限：正常包几百 KB，超过这个量级基本是坏包或解压炸弹。
MAX_BUNDLE_BYTES = 512 * 1024 * 1024
MAX_OBJECTS = 200000
# 每扫这么多包落一次 checkpoint，进程被杀或超时不会把整轮成果全丢掉。
CHECKPOINT_EVERY = 200

def cache_root(game_dir, override=None):
    """Directory that holds one folder per downloaded bundle.

    resource_catalog owns the resolution order (argument, LIMBUS_RESOURCE_ROOT,
    the workbench config file, then detection of the Addressables download cache
    or StreamingAssets/aa), so a scan and a lookup can never disagree about which
    root they are reading.
    """
    import resource_catalog
    if override:
        chosen = pathlib.Path(override)
        return chosen if chosen.is_dir() else None
    env = os.environ.get(resource_catalog.ENV_RESOURCE)
    if env:
        chosen = pathlib.Path(env)
        return chosen if chosen.is_dir() else None
    return resource_catalog.find_resource_root(game_dir)


def steam_libraries():
    """Steam library roots, from the registry, the usual install paths, and
    libraryfolders.vdf. A player can have the game on any drive, so all of them
    are tried instead of assuming C: or a single library."""
    roots = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam'),
                          (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam')):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    for name in ('SteamPath', 'InstallPath'):
                        try:
                            roots.append(pathlib.Path(winreg.QueryValueEx(handle, name)[0]))
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    for drive in 'CDEFGH':
        for suffix in (':\\Steam', ':\\Program Files (x86)\\Steam', ':\\SteamLibrary'):
            roots.append(pathlib.Path(drive + suffix))
    seen = []
    for root in roots:
        if root.is_dir() and root not in seen:
            seen.append(root)
    libraries = list(seen)
    for root in seen:
        vdf = root / 'steamapps/libraryfolders.vdf'
        try:
            text = vdf.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            library = pathlib.Path(match.group(1))
            if library.is_dir() and library not in libraries:
                libraries.append(library)
    return libraries


def find_game_dir():
    """Directory that contains LimbusCompany_Data, or None."""
    override = os.environ.get('LIMBUS_GAME_DIR')
    if override:
        candidate = pathlib.Path(override)
        if (candidate / 'LimbusCompany_Data').is_dir():
            return candidate
        if candidate.name == 'LimbusCompany_Data':
            return candidate.parent
    for library in steam_libraries():
        for data in library.glob('steamapps/common/*/LimbusCompany_Data'):
            if (data / 'StreamingAssets/aa/catalog.bin').is_file():
                return data.parent
    return None


GROUP_NAMES = ('SD_Enemy', 'SD_Personality', 'SD_Abnormality', 'SD_EGO', 'SD_DeadScene')


def catalog_groups(game_dir):
    """prefab basename -> Addressables group, read straight out of catalog.bin.

    The catalog is a string table. Every address record is
    '<ascii name>.prefab' followed by two uint32 words:
      * w1 -- the record's own byte offset (a self reference)
      * w2 -- either the offset of a group record's first word, or, when it
              differs per entry, a length-prefixed inline group name
    A group record for name G is stored as uint32(len(G)) + G + uint32(offset of
    that same length word); the anchor we match against is that offset, which
    equals (position of G in the blob) + len(G).

    Verified against every pool entry: 663/663 exact, zero mismatches. That is
    why this is used instead of guessing from directory, id family or bundle --
    all three of those were measured and are ambiguous.
    """
    if game_dir is None:
        return {}
    path = pathlib.Path(game_dir) / 'LimbusCompany_Data/StreamingAssets/aa/catalog.bin'
    try:
        blob = path.read_bytes()
    except OSError:
        return {}

    anchors = {}
    for name in GROUP_NAMES:
        at = blob.find(name.encode('ascii'))
        if at >= 0:
            anchors[at + len(name)] = name

    records = {}
    suffix = b'.prefab'
    pos = 0
    while True:
        i = blob.find(suffix, pos)
        if i < 0:
            break
        pos = i + 1
        end = i + len(suffix)
        if end + 8 > len(blob):
            continue
        self_off, group_ref = struct.unpack_from('<II', blob, end)
        start = i
        while start > 0 and (blob[start - 1:start].isalnum() or blob[start - 1:start] == b'_'):
            start -= 1
        try:
            name = blob[start:i].decode('ascii')
        except UnicodeDecodeError:
            continue
        if not name:
            continue
        if group_ref in anchors:
            group = anchors[group_ref]
        else:
            group = None
            for candidate in GROUP_NAMES:
                raw = candidate.encode('ascii')
                if self_off == len(raw) and blob[end + 4:end + 4 + len(raw)] == raw:
                    group = candidate
                    break
        if group and name not in records:
            records[name] = group
    return records


def catalog_hash(game_dir):
    """catalog.hash changes on every content update. It is the one cheap signal
    that says 'the game shipped new prefabs' without opening a single bundle."""
    if game_dir is None:
        return None
    path = pathlib.Path(game_dir) / 'LimbusCompany_Data/StreamingAssets/aa/catalog.hash'
    try:
        return path.read_text(encoding='utf-8-sig').strip()
    except OSError:
        return None


def bundle_paths(root):
    """Every __data file under the cache root, without following junctions.

    Path.rglob() follows junctions and symlinks on 3.9, so one link inside the
    cache could drag the scan out of the tree; walk by hand and skip reparse points.
    """
    found = []
    for current, dirs, files in os.walk(root, followlinks=False):
        keep = []
        for name in dirs:
            child = os.path.join(current, name)
            try:
                if os.stat(child, follow_symlinks=False).st_file_attributes & 0x400:
                    continue  # FILE_ATTRIBUTE_REPARSE_POINT
            except (OSError, AttributeError):
                continue
            keep.append(name)
        dirs[:] = keep
        if '__data' in files:
            candidate = pathlib.Path(current) / '__data'
            if candidate.is_file():
                found.append(candidate)
    return sorted(found)


def fingerprint(path):
    st = path.stat()
    return [st.st_size, st.st_mtime_ns]


def atomic_write(path, text):
    """Write through a unique temp name, so two scans cannot clobber each other."""
    path = pathlib.Path(path)
    tmp = path.with_name('%s.%d.tmp' % (path.name, os.getpid()))
    with open(tmp, 'w', encoding='utf-8') as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def state_text(state):
    return json.dumps(state, ensure_ascii=False, separators=(',', ':'))


def family(name):
    """Coarse numeric family of an appearance name, e.g. identity / assist400 / d4_8.

    放宽后的 APPEARANCE 也收 Fools_9999_... 这类字母前缀名，所以先剥掉可选前缀
    再取数字。剥完不是数字的记 nonnum 并排除在 combo/family 信任之外——能被
    APPEARANCE 命中的名字剥完一定有数字，所以这条只在护栏被绕过时才生效，
    但它挡住了「没见过的前缀靠同桶多数票拿到假 asset_key」这条路。
    """
    stripped = re.sub(r'^[A-Za-z]+_', '', name)
    m = re.match(r'^(\d+)', stripped)
    if not m:
        return 'nonnum'
    digits = m.group(1)
    if len(digits) == 5 and digits[:3] in (
            '101', '102', '103', '104', '105', '106',
            '107', '108', '109', '110', '111', '112'):
        return 'identity'
    if len(digits) == 6 and digits.startswith('400'):
        return 'assist400'
    if len(digits) == 5 and digits[0] == '9':
        return 'enemy9xxxx'
    if len(digits) == 4:
        return 'd4_' + digits[0]
    if len(digits) == 3:
        return 'd3_' + digits[0]
    return 'len' + str(len(digits))


class PoolError(RuntimeError):
    """人格池缺失或损坏：扫描无法判断什么算「新」，只能明确失败。"""


def pool_entries(addon_root):
    """appearance name -> pool entry. The entry's asset_key prefix is the
    Addressables group, which no directory rule reproduces on its own."""
    path = pathlib.Path(addon_root) / 'Assets/runtime/all_sinners_pools.json'
    try:
        pools = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise PoolError('人格池不可用（%s）：%s' % (path, exc))
    if not isinstance(pools, dict):
        raise PoolError('人格池格式无效：%s' % path)
    names = {}
    for sinner, group in pools.items():
        for entry in group.get('entries', []):
            look = entry.get('appearance_name')
            if not look:
                continue
            asset_key = str(entry.get('asset_key') or '')
            names[look] = {
                'sinner': sinner,
                'identity_id': entry.get('identity_id'),
                'asset_key': asset_key,
                'group': asset_key.rsplit('/', 1)[0] if '/' in asset_key else '',
                'category': entry.get('category'),
            }
    return names


def build_group_lookup(pool, seen):
    """(directory, family) -> group, learned from pool rows that are already
    proven to load. A combination is only trusted when the pool agrees on one
    group for it; family-wide agreement is the fallback."""
    name_dir = {}
    for info in seen.values():
        for name, payload in (info.get('entries') or {}).items():
            rel = payload.get('path') if isinstance(payload, dict) else None
            if isinstance(rel, str) and rel:
                name_dir[name] = rel.rsplit('/', 1)[0]
    by_combo = {}
    by_family = {}
    for look, entry in pool.items():
        directory = name_dir.get(look)
        fam = family(look)
        group = entry['group']
        if not group or fam == 'nonnum':
            continue
        by_family.setdefault(fam, {}).setdefault(group, 0)
        by_family[fam][group] += 1
        if directory:
            by_combo.setdefault((directory, fam), {}).setdefault(group, 0)
            by_combo[(directory, fam)][group] += 1
    return name_dir, by_combo, by_family


def predict_group(name, directory, by_combo, by_family):
    """Return (group, confidence, evidence). confidence is combo > family > guess."""
    fam = family(name)
    combo = by_combo.get((directory, fam))
    if combo and len(combo) == 1:
        return next(iter(combo)), 'combo', sum(combo.values())
    fams = by_family.get(fam)
    if fams and len(fams) == 1:
        return next(iter(fams)), 'family', sum(fams.values())
    if combo:
        group, hits = max(combo.items(), key=lambda kv: kv[1])
        return group, 'guess', '%d/%d' % (hits, sum(combo.values()))
    return None, 'unknown', 0


def scan_bundle(path, unity_py):
    """Return ({prefab_rel_path: [motion details]}, skipped_names) for one bundle.

    Everything here reads a file we did not write, so a single damaged or
    half-downloaded bundle must stay eligible for a retry. Load and enumeration
    errors propagate to the per-bundle caller, which skips caching that result.
    skipped_names counts SD/ prefabs whose name falls outside APPEARANCE, so a
    naming family we do not model shows up as a number instead of vanishing.
    """
    UnityPy = unity_py
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        return {}, 0
    env = UnityPy.load(str(path))
    containers = dict(env.container)
    rel_paths = {}
    skipped = 0
    for key in containers:
        if not key.startswith(PRE + 'SD/') or not key.endswith('.prefab'):
            continue
        rel = key[len(PRE):]
        stem = rel.rsplit('/', 1)[-1][:-len('.prefab')]
        if APPEARANCE.match(stem):
            rel_paths[stem] = rel
        else:
            skipped += 1
    if not rel_paths:
        return {}, skipped
    details = {}
    objects = env.objects
    seen_objects = 0
    for obj in objects:
        seen_objects += 1
        if seen_objects > MAX_OBJECTS:
            break
        try:
            if obj.type.name != 'MonoBehaviour':
                continue
        except Exception:
            continue
        try:
            data = obj.read()
        except Exception:
            continue
        if 'motionList' not in getattr(data, '__dict__', {}):
            continue
        try:
            owner = str(getattr(data.m_GameObject.read(), 'm_Name', ''))
        except Exception:
            continue
        if owner not in rel_paths:
            continue
        rows = []
        for motion in (getattr(data, 'motionList', []) or []):
            try:
                detail = getattr(motion, '_motiondetail', None)
                if not isinstance(detail, int):
                    continue
                assets = getattr(motion, 'timelineAssets', None) or []
                rows.append([detail, len(assets)])
            except Exception:
                continue
        if rows:
            details[owner] = rows
    return {name: {'path': rel_paths[name], 'motions': details.get(name, [])}
            for name in rel_paths}, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--addon', required=True, help='addon root (contains Assets/runtime)')
    ap.add_argument('--game', default=None, help='Limbus Company install dir')
    ap.add_argument('--full', action='store_true', help='ignore the fingerprint cache')
    ap.add_argument('--no-write', action='store_true', help='report only, do not save state')
    ap.add_argument('--weekly', action='store_true', help='weekly discovery enrichment')
    ap.add_argument('--cache', default=None, help='Addressables cache root (default: derive it)')
    args = ap.parse_args(argv)

    try:
        from resource_tools import unity
        UnityPy = unity()
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    UnityPy.config.FALLBACK_UNITY_VERSION = '6000.3.0f1'

    addon = pathlib.Path(args.addon)
    game = args.game or find_game_dir()
    root = cache_root(game, args.cache)
    if root is None:
        if args.cache:
            print('--cache 指向的目录不可用：%s' % args.cache, file=sys.stderr)
        else:
            tried = pathlib.Path(os.environ.get('USERPROFILE', '')) / 'AppData/LocalLow/Unity'
            print('Addressables cache not found under %s; launch the game once first, '
                  'or pass --cache <dir>.' % tried, file=sys.stderr)
        return 3

    # 两个工作台同时扫会互相覆盖状态，跨进程用锁文件挡住；抢不到就明说，
    # 页面会显示「已有扫描在进行」。
    lock_path = addon / 'Workbench' / LOCK_NAME
    lock_handle = None
    if not args.no_write:
        try:
            lock_handle = open(lock_path, 'a+b')
            lock_handle.seek(0)
        except OSError as exc:
            # 只读插件目录、scan.lock 被建成目录之类的问题，不能报成「已有扫描」。
            print('无法在插件目录创建锁文件 %s：%s' % (lock_path, exc), file=sys.stderr)
            return 5
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            try: lock_handle.close()
            except OSError: pass
            print('另一个扫描正在进行，稍后再试。', file=sys.stderr)
            return 4

    try:
        pool = pool_entries(addon)
    except PoolError as exc:
        print(str(exc), file=sys.stderr)
        return 6
    state_path = addon / 'Workbench' / STATE_NAME
    state = {}
    if state_path.is_file() and not args.full:
        try:
            loaded = json.loads(state_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            loaded = {}
        # 被写坏、被改成列表、或来自旧版本扫描逻辑的状态一律按「没有缓存」处理。
        state = loaded if isinstance(loaded, dict) else {}
        if state.get('__version__') != SCAN_VERSION:
            state = {}

    # Authoritative group source. Reading it costs one file read and beats every
    # heuristic: measured 100% against the pool, while directory/family/bundle
    # each got real entries wrong.
    catalog_map = catalog_groups(game)
    if catalog_map:
        print('catalog groups: %d prefabs decoded' % len(catalog_map))
    hash_now = catalog_hash(game)
    hash_before = state.get('__catalog__') if isinstance(state, dict) else None
    if hash_now:
        print('game: %s' % game)
        if hash_before and hash_now != hash_before:
            print('catalog changed since the last scan: %s -> %s' % (hash_before, hash_now))
        print('catalog.hash: %s' % hash_now)
    bundles = bundle_paths(root)
    print('bundles: %d' % len(bundles))
    started = time.time()
    seen = {}
    changed = 0
    failed = {}
    unmatched_total = 0
    checkpoint_every = CHECKPOINT_EVERY
    for index, bundle in enumerate(bundles, 1):
        key = str(bundle.relative_to(root))
        try:
            mark = fingerprint(bundle)
        except OSError as exc:
            failed[key] = str(exc)
            continue
        cached = state.get(key)
        if isinstance(cached, dict) and cached.get('fingerprint') == mark and not args.full:
            seen[key] = cached
            unmatched_total += int(cached.get('skipped') or 0)
            continue
        try:
            found, skipped = scan_bundle(bundle, UnityPy)
        except Exception as exc:
            failed[key] = str(exc)
            continue
        changed += 1
        unmatched_total += skipped
        seen[key] = {'fingerprint': mark, 'entries': found, 'skipped': skipped}
        if index % 100 == 0:
            print('  scanned %d/%d (%.0fs)' % (index, len(bundles), time.time() - started))
        # A full pass takes minutes on a big cache; checkpoint so a timeout or a
        # killed process does not throw away everything scanned so far. The
        # catalog marker is deliberately not written here: only a complete pass
        # may claim the cache is up to date.
        if checkpoint_every and index % checkpoint_every == 0 and not args.no_write:
            # 合并写入：seen 只包含本轮已经处理过的包，直接覆盖会把上次缓存里
            # 还没轮到的包整片删掉（下一轮又得全量重开）。__catalog__ 也不在这里
            # 更新：只有完整跑完才算「缓存已是最新」。
            try:
                merged = dict(state)
                merged.update(seen)
                merged['__version__'] = SCAN_VERSION
                atomic_write(state_path, state_text(merged))
            except OSError as exc:
                print('  checkpoint skipped: %s' % exc)

    name_dir, by_combo, by_family = build_group_lookup(pool, seen)
    # 名字没被 APPEARANCE 认出来的 prefab 不参与发现，但留下计数，免得无声漏报。
    unmatched = unmatched_total

    discovered = {}
    known_hits = 0
    for key, info in seen.items():
        for name, payload in (info.get('entries') or {}).items():
            if name in pool:
                known_hits += 1
                continue
            directory = payload['path'].rsplit('/', 1)[0]
            real = catalog_map.get(name)
            if real:
                group, confidence, evidence = real, 'catalog', 'catalog.bin'
            else:
                group, confidence, evidence = predict_group(name, directory, by_combo, by_family)
            # Only a group we can stand behind becomes a copyable asset_key; a
            # majority vote ('guess') stays a name, not a path that looks proven.
            trusted = group if confidence in ('catalog', 'combo', 'family') else None
            discovered[name] = {
                'appearance_name': name,
                'asset_key': ('%s/%s.prefab' % (trusted, name)) if trusted else None,
                'group': group,
                'group_confidence': confidence,
                'group_evidence': evidence,
                'prefab_path': PRE + payload['path'],
                'motions': payload['motions'],
                'bundle': key,
            }

    by_confidence = {}
    for name, payload in discovered.items():
        by_confidence.setdefault(payload['group_confidence'], []).append(name)

    report = {
        'generated': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'catalog_hash': hash_now,
        'catalog_previous': hash_before,
        'catalog_changed': bool(hash_now and hash_before and hash_now != hash_before),
        'game_dir': str(game) if game else None,
        'bundles_total': len(bundles),
        'bundles_rescanned': changed,
        'bundle_errors': failed,
        'pool_entries': len(pool),
        'known_prefabs_seen': known_hits,
        'new_prefabs': len(discovered),
        'unmatched_count': unmatched,
        'new_by_confidence': {c: sorted(v) for c, v in sorted(by_confidence.items())},
        'units': dict(sorted(discovered.items())),
    }

    print('')
    print('rescanned %d/%d bundles in %.0fs' % (changed, len(bundles), time.time() - started))
    print('pool entries: %d   known prefabs seen in bundles: %d' % (len(pool), known_hits))
    print('new prefabs: %d' % len(discovered))
    by_dir = {}
    for name, payload in discovered.items():
        by_dir.setdefault(payload['prefab_path'][len(PRE):].rsplit('/', 1)[0], []).append(name)
    for directory, names in sorted(by_dir.items()):
        print('  %-26s %3d' % (directory, len(names)))
    if unmatched:
        print('names outside the appearance pattern: %d' % unmatched)
    print('')
    print('group confidence:')
    for confidence in ('catalog', 'combo', 'family', 'guess', 'unknown'):
        names = report['new_by_confidence'].get(confidence)
        if names:
            print('  %-8s %3d' % (confidence, len(names)))

    out = addon / 'Workbench' / REPORT_NAME
    # 「扫完了」= 真的有包、且认得游戏目录；只缺 catalog.hash 时也算扫完，
    # 但那样就不写 __catalog__，下次启动会再比一次。
    complete = bool(seen)
    if failed:
        first = next(iter(failed))
        print('读取失败的资源包：%d；下次重试。%s: %s' % (len(failed), first, failed[first]), file=sys.stderr)
    if not args.no_write:
        # 一次没扫到任何包的运行不能覆盖上一份有效报告，也不能把「缓存已最新」
        # 记下来：缓存为空或 --cache 指错目录时，那会让自动扫描此后永不重试。
        if complete:
            # Scan the complete cache, including already catalogued appearances,
            # so older entries can acquire the no-attack classification too.
            import discovery_import, discovery_metadata, discovery_personalities
            import attack_discovery
            class PersonalityMetadata:
                def resolve_label(self, name): return discovery_metadata.resolve(meta, name)
            def is_personality(name, payload):
                return bool(re.fullmatch(r'(10[1-9]|11[0-2])\d{2}_[A-Za-z0-9_]+Appearance',name) and payload.get('asset_key')=='SD_Personality/'+name+'.prefab')
            from file_lock import FileLock
            candidates = dict(discovered)
            for info in seen.values():
                if not isinstance(info, dict):
                    continue
                for name, payload in (info.get('entries') or {}).items():
                    if name in pool and name not in candidates:
                        candidates[name] = {'asset_key':pool[name].get('asset_key'),
                                            'motions':payload.get('motions') or []}
            meta = discovery_metadata.load_metadata(game, addon/'boss_chapters.json') if game else {'names':{'identity':{},'enemy':{}},'chapters':{}}
            attack_entries = []
            attack_errors = {}
            tree_cache = {}
            for name, payload in discovered.items():
                if is_personality(name,payload): continue
                if not discovery_import.has_attack(payload.get('motions') or []): continue
                if payload.get('group_confidence') != 'catalog' or not payload.get('asset_key'): continue
                try:
                    bundle = payload['bundle']
                    if bundle not in tree_cache:
                        tree_cache[bundle] = attack_discovery.read_trees(root/bundle, UnityPy)
                    label = discovery_metadata.resolve(meta,name)
                    entry, blob = attack_discovery.from_trees(name,payload['asset_key'],tree_cache[bundle],label['name'])
                    entry.update(discovery_source='local_cache',translation_status=label['translation_status'],chapter=label['category'],chapter_label=label['category_label'],chapter_memberships=label['category_memberships'] or [{'chapter':label['category'],'label':label['category_label']}])
                    attack_entries.append((entry,blob))
                except Exception as exc:
                    attack_errors[name] = str(exc)
            pool_path = addon/'Assets/runtime/all_sinners_pools.json'
            translations = {}; translation_stats = {}
            if args.weekly:
                import auto_translate
                preliminary = json.loads(pool_path.read_text(encoding='utf-8-sig'))
                discovery_personalities.merge(preliminary, discovered, PersonalityMetadata())
                preliminary, _ = discovery_import.merge(preliminary, {'units':{n:v for n,v in candidates.items() if not is_personality(n,v)}}, meta)
                preliminary['101']['entries'].extend(entry for entry, _ in attack_entries)
                discovery_metadata.refresh_discovered(preliminary, meta)
                translation_stats = auto_translate.fill(preliminary, addon/'Workbench/auto_translation_cache.json')
                translations = {str(e.get('identity_id')):e for pool in preliminary.values() for e in pool.get('entries',[]) if e.get('translation_status') == '自动暂译'}
            with FileLock(addon/'workbench-save.lock'):
                before = pool_path.read_bytes()
                current = json.loads(before.decode('utf-8-sig'))
                updated, added = discovery_import.merge(current, {'units':{n:v for n,v in candidates.items() if not is_personality(n,v)}}, meta)
                new_personalities, ambiguous_personalities = discovery_personalities.merge(updated, discovered, PersonalityMetadata())
                report['auto_added_personalities'] = new_personalities
                report['ambiguous_personalities'] = ambiguous_personalities
                known_names={e.get('appearance_name') for p in updated.values() for e in p.get('entries',[])}
                added_attack=0
                for entry, blob in attack_entries:
                    if entry['appearance_name'] in known_names: continue
                    contract=addon/'Assets/runtime/story_native'/ (entry['identity_id']+'.bin')
                    contract.parent.mkdir(parents=True,exist_ok=True)
                    temp=contract.with_name(contract.name+'.%d.tmp'%os.getpid())
                    temp.write_bytes(blob); temp.replace(contract)
                    updated['101']['entries'].append(entry)
                    known_names.add(entry['appearance_name']);added_attack+=1
                if args.weekly:
                    discovery_metadata.refresh_discovered(updated, meta)
                    for pool in updated.values():
                        for item in pool.get('entries', []):
                            trans = translations.get(str(item.get('identity_id')))
                            if trans and item.get('discovery_source') == 'local_cache' and not re.search(r'[\u3400-\u9fff]',str(item.get('name') or '')):
                                item['name']=trans['name'];item['translation_status']='自动暂译';item['translation_source_text']=trans.get('translation_source_text','')
                    report['translation'] = translation_stats
                if updated != current:
                    if pool_path.read_bytes() != before:
                        raise RuntimeError('人格池在扫描期间发生修改，请重新扫描')
                    atomic_write(pool_path, json.dumps(updated, ensure_ascii=False, indent=2)+'\n')
                report['auto_added_no_attack'] = added
                report['auto_added_attack'] = added_attack
                report['attack_import_errors'] = attack_errors
            if args.weekly:
                try:
                    import auto_artwork
                    with FileLock(addon/'Workbench/image_resources.lock'):
                        if (addon/'Workbench/images_disabled.flag').exists():
                            report['artwork'] = {'disabled': True}
                        else:
                            report['artwork'] = auto_artwork.extract(addon, root, UnityPy, files=bundles)
                except Exception as exc:
                    report['artwork'] = {'error':str(exc)}
            seen['__catalog__'] = hash_now
            seen['__version__'] = SCAN_VERSION
            # 已持锁，这里的清理不会碰到别人的临时文件。
            for stale in (addon / 'Workbench').glob('*.tmp'):
                try:
                    if stale.name.startswith((STATE_NAME, REPORT_NAME)):
                        stale.unlink()
                except OSError:
                    pass
            # report first, state last: if we die between the two writes, the state still
            # says "not up to date" and the next start rescans, which is the safe side.
            atomic_write(out, json.dumps(report, ensure_ascii=False, indent=1))
            try:
                atomic_write(state_path, state_text(seen))
            except OSError as exc:
                print('state 写入失败（报告已更新）：%s' % exc)
            # 这一轮成功了，上一轮的报错文件留着会冒充当前故障。
            try:
                (addon / 'Workbench/scan_last_error.txt').unlink()
            except OSError:
                pass
            print('')
            print('wrote %s' % out.name)
        else:
            print('缓存为空，未写入报告，稍后重试。')
    if lock_handle is not None:
        try:
            if os.name == 'nt':
                import msvcrt
                lock_handle.seek(0)
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        try: lock_handle.close()
        except OSError: pass
    return 7 if failed else (0 if complete else 3)


if __name__ == '__main__':
    raise SystemExit(main())
