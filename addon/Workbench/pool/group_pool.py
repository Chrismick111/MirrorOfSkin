"""SRP5 pool assembly. Isolated until the host and runtime use the protocol."""
import group_entries

def build_rows(catalog, groups, rules, previous=()):
    """Merge active weighted rules with zero-weight catalog and prior rows.

    rules are (sinner, base_identity, entries); IDs in previous preserve native
    cache indices during hot reload. Invalid active references fail explicitly.
    """
    known = {}
    active = []
    def add(row, enabled):
        row = dict(row)
        key = group_entries.row_key(row)
        if enabled:
            if key in {group_entries.row_key(x) for x in active}:
                raise ValueError('duplicate active pool row')
            active.append(row)
        else:
            row['weight'] = 0
            row['enabled'] = 0
            known.setdefault(key, row)
    for sinner, base, entries in rules:
        normalized = group_entries.validate_entries(entries, catalog, groups)
        for item in normalized:
            row = group_entries.resolve_entry(item, catalog, groups)
            row.update(sinner=int(sinner), base_identity=str(base), enabled=1)
            add(row, True)
    for row in previous:
        add(row, False)
    # Runtime caches retain old keys; active rows have priority over zero rows.
    seen = {group_entries.row_key(x) for x in active}
    return active + [row for key, row in known.items() if key not in seen]

def encode_rows(rows):
    return group_entries.pack_rows(rows)
