"""Catalog presentation for cosmetics published by the local importer."""
import re

CHAPTER = 'imported_skins'
LABEL = '外来人格'


def display_name(current, archive_stem):
    """Recover the archive label when an old importer exposed a cache folder."""
    if current and archive_stem and current!=archive_stem:
        # Legacy ZIP directory names can arrive as CP437. Only use a decoded
        # label when the archive's actual Unicode filename confirms it.
        try:
            if current.encode('cp437').decode('gbk')==archive_stem:
                return archive_stem
        except UnicodeError:
            pass
    cache = re.fullmatch(r'[0-9a-fA-F]{32}( · .+)?', current or '')
    if not cache or not archive_stem:
        return current
    title = re.sub(r'\s+\d{4}-\d{2}-\d{2}T\d{2}-\d{2}Z\s+[A-Za-z0-9_-]+$', '', archive_stem).strip()
    return (title or archive_stem) + (cache[1] or '')


def apply(catalog, root=None, addon=None):
    from dialogue_status import apply_binding, runtime_bindings
    bindings = runtime_bindings(root, addon) if root is not None else {}
    if root is not None:
        from import_packages import read_index
        try:
            packages = read_index(root)['packages']
        except (OSError, ValueError):
            packages = []  # Synchronization reports an unreadable library separately.
        for package in packages:
            for identity in package.get('missing_identities', []):
                if identity in catalog:
                    catalog[identity]['missing_package_source'] = package.get('source_name') or package['source']
    for identity, entry in catalog.items():
        if not (re.fullmatch(r'story_WBImp_[a-f0-9]{24}', identity) or identity == 'story_BRolandBaseAppearance'):
            continue
        if 'dialogue_detection' not in entry and ('import_source' in entry or identity.startswith('story_WBImp_')):
            entry['dialogue_detection'] = {'voice': 'unknown', 'bubble': 'unknown'}
            entry['dialogue_needs_import'] = True
        apply_binding(entry, bindings)
        entry['name'] = display_name(entry.get('name'), entry.get('import_source'))
        memberships = list(entry.get('chapter_memberships') or [])
        old = entry.get('chapter')
        if old and old not in (CHAPTER,'unassigned') and not any(g.get('chapter') == old for g in memberships):
            memberships.append({'chapter':old,'label':entry.get('chapter_label') or old})
        entry.update(chapter=CHAPTER, chapter_rank=-10000, chapter_label=LABEL,
                     chapter_memberships=[{'chapter':CHAPTER,'label':LABEL}]+[g for g in memberships if g.get('chapter')!=CHAPTER])
