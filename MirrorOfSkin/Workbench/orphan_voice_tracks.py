"""Verify dangling voice entries against the original game timelines."""

from addressable_materials import _reachable


def _track_ids(tree):
    return [(ref['m_FileID'], ref['m_PathID']) for ref in tree['m_Tracks']]


def verified_orphans(original, timeline_id, tracks, stock):
    """Only certify absent original voice tracks with the exact same track list."""
    donor = stock.get(timeline_id)
    if donor is None or donor.type.name != 'MonoBehaviour':
        return set()
    game_timeline = donor.read_typetree()
    if ('m_Tracks' not in game_timeline or game_timeline['m_Name'] != original['m_Name']
            or _track_ids(game_timeline) != _track_ids(original)):
        return set()
    verified = set()
    for pid in tracks:
        track = stock.get(pid)
        if track is None or track.type.name != 'MonoBehaviour':
            continue
        tree = track.read_typetree()
        if (tree['m_Name'].casefold() == 'fmod custom track_voice'
                and tree.get('m_Parent') == {'m_FileID': 0, 'm_PathID': timeline_id}
                and tree.get('m_Clips')):
            verified.add(pid)
    return verified


def resolve_orphan_voice_tracks(env, root_pid, unity):
    from skin_assets import _roots
    from scan.resource_catalog import build_index, load_index, resolve_roots

    file, = env.assets
    orphans = {}
    for obj, tree in _reachable(file, root_pid):
        if obj.type.name != 'MonoBehaviour' or 'm_Tracks' not in tree or 'm_FixedDuration' not in tree:
            continue
        missing = {pid for f, pid in _track_ids(tree) if not f and pid and pid not in file.objects}
        if missing:
            orphans[obj.path_id] = tree, missing
    if not orphans:
        return {}

    roots = resolve_roots()
    root, index_dir = roots['resource_root'], roots['index_dir']
    if root is None:
        return {}
    index, _ = load_index(index_dir, root, auto_build=False)
    if index is None:
        index = build_index(root, index_dir, unity_py=unity)
    published = {(address.casefold(), pid) for address, pid, _ in _roots(env)}
    addresses = {address for address, _ in published}
    paths = {root / rel for rel, entry in index['entries'].items()
             if addresses.intersection(a.replace('\\', '/').casefold()
                                       for a in entry.get('prefabs', {}).values())}
    result = {}
    for path in sorted(paths):
        path = path.resolve()
        if not path.is_relative_to(root) or not path.is_file():
            continue
        base = unity.load(path.read_bytes())
        if len(base.assets) != 1 or not any((a.casefold(), p) in published or p == root_pid
                                           for a, p, _ in _roots(base)):
            continue
        objects = base.assets[0].objects
        for pid, (timeline, missing) in orphans.items():
            tracks = verified_orphans(timeline, pid, missing, objects)
            if tracks:
                result.setdefault(pid, set()).update(tracks)
    return result
