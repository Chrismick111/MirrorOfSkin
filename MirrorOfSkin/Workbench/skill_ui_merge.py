"""Combine confirmed visual resources for one imported appearance."""
from pathlib import PurePosixPath
import re


def merge_external(rows, external, keep, *, address=None):
    from skill_ui import STATUS, _identifier, _name

    target, skills, statuses, portrait = external
    declared = next((int(row[1]) for row in rows if row[0] == 'T'), None)
    target = _identifier(target)
    if target and declared and target != declared:
        return rows
    if target and not declared:
        rows.append(('T', str(target)))
    if target and address:
        prefab = PurePosixPath(str(address).replace('\\', '/'))
        if (prefab.suffix.casefold() == '.prefab' and prefab.stem.startswith(str(target) + '_')
                and re.fullmatch(r'[A-Za-z0-9_-]{1,127}', prefab.stem)):
            rows.append(('A', prefab.stem))
    if portrait and not any(row[0] == 'P' for row in rows):
        if filename := keep(portrait):
            rows.append(('P', filename))
    known_statuses = {row[1] for row in rows if row[0] == 'B'}
    for key, blob in sorted(statuses.items()):
        if key not in known_statuses and STATUS.fullmatch(key) and (filename := keep(blob)):
            rows.append(('B', key, filename))

    # The runtime requires a single role per skill, including all upgrades.
    roles = {row[1]: row[2] for row in rows if row[0] == 'S'}
    slots = {(row[1], row[3]): i for i, row in enumerate(rows) if row[0] == 'S'}
    declared_names = {}
    for row in rows:
        if row[0] == 'S' and row[4]:
            declared_names[row[1]] = min(int(row[3]), declared_names.get(row[1], 33))
    for identifier, role, level, name, blob in skills:
        if (_identifier(identifier) is None or type(level) is not int or not 0 <= level <= 32
                or role not in ('unknown', 'attack1', 'attack2', 'attack3', 'defense', 'conditional')):
            continue
        skill = str(identifier)
        old_role = roles.get(skill)
        if old_role and role != 'unknown' and old_role not in ('unknown', role):
            continue
        if old_role == 'unknown' and role != 'unknown':
            for (slot_skill, _), index in slots.items():
                if slot_skill == skill:
                    row = rows[index]
                    rows[index] = (*row[:2], role, *row[3:])
        effective_role = role if old_role in (None, 'unknown') else old_role
        roles[skill] = effective_role
        key = (skill, str(level))
        index = slots.get(key)
        existing_name, existing_icon = rows[index][4:] if index is not None else ('', '')
        text = existing_name or _name(name)
        icon = existing_icon or keep(blob)
        # A higher sync level can explicitly return to the vanilla name, while
        # an independent authored localization and the icon retain their own scopes.
        restore_name = name is None and level < declared_names.get(skill, 33) and not text
        if text or icon or restore_name:
            row = ('R' if restore_name else 'S', skill, effective_role, key[1], text, icon)
            if index is None:
                slots[key] = len(rows)
                rows.append(row)
            else:
                rows[index] = row
    return rows
