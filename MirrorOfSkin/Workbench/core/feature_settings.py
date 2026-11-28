"""Versioned feature switches stored in MOS_data and mirrored to the native DLL.

The Workbench edits ``MOS_data/settings.json``.  A shipped ``settings.example.json``
defines the current schema, so a data file written by an older build is
upgraded automatically (new keys get defaults, existing user values survive).
The native module never parses JSON: it polls the tiny ``native_ui.bin`` mirror
written here, which lets the panel toggle overrides without a game restart.
"""
import json
import os
import pathlib
import struct

SCHEMA_VERSION = 1
FILE_NAME = 'settings.json'
EXAMPLE_NAME = 'settings.example.json'
NATIVE_NAME = 'native_ui.bin'
NATIVE_MAGIC = b'SRUI'
NATIVE_VERSION = 1

DEFAULT = {
    'version': SCHEMA_VERSION,
    'cosmetic_ui': {
        'enabled': False,
        'skill_name': True,
        'skill_icon': True,
        'portrait': True,
        'buff': True,
    },
}
FLAG_BITS = (
    ('enabled', 1 << 0),
    ('skill_name', 1 << 1),
    ('skill_icon', 1 << 2),
    ('portrait', 1 << 3),
    ('buff', 1 << 4),
)


def _read(path):
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path, data):
    path = pathlib.Path(path)
    temp = path.with_name(path.name + '.settings.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    os.replace(temp, path)


def _version(data):
    try:
        return int(data.get('version', 0))
    except (TypeError, ValueError):
        return 0


def _copy_default():
    return {'version': SCHEMA_VERSION,
            'cosmetic_ui': dict(DEFAULT['cosmetic_ui'])}


def _normalize(raw):
    """Merge a stored document over the shipped defaults, key by key."""
    settings = _copy_default()
    if not isinstance(raw, dict):
        return settings
    version = _version(raw)
    if version > 0:
        settings['version'] = version
    ui = raw.get('cosmetic_ui')
    if isinstance(ui, dict):
        for key in DEFAULT['cosmetic_ui']:
            if isinstance(ui.get(key), bool):
                settings['cosmetic_ui'][key] = ui[key]
    return settings


def native_flags(settings):
    ui = settings.get('cosmetic_ui') or {}
    flags = 0
    for key, bit in FLAG_BITS:
        if ui.get(key) is True:
            flags |= bit
    return flags


def write_native(data_root, settings):
    """Publish the flags for the native DLL. Returns True when bytes changed."""
    blob = struct.pack('<4sII', NATIVE_MAGIC, NATIVE_VERSION, native_flags(settings))
    path = pathlib.Path(data_root) / NATIVE_NAME
    try:
        if path.read_bytes() == blob:
            return False
    except OSError:
        pass
    temp = path.with_name(path.name + '.settings.tmp')
    temp.write_bytes(blob)
    os.replace(temp, path)
    return True


def _example(addon_root):
    raw = _read(pathlib.Path(addon_root) / EXAMPLE_NAME)
    settings = _normalize(raw)
    if raw is not None and _version(raw) > settings['version']:
        settings['version'] = _version(raw)
    return settings


def load(data_root, addon_root, log=None, persist=True):
    """Return the current settings, upgrading an older data file in place.

    ``persist=False`` is for read-only previews: it upgrades the document in
    memory but never creates or rewrites anything under the data directory.
    """
    data_root = pathlib.Path(data_root)
    example = _example(addon_root)
    path = data_root / FILE_NAME
    current = _read(path)
    reason = ''
    if current is None:
        settings = example
        settings['version'] = max(settings['version'], SCHEMA_VERSION)
        if persist:
            _write_json(path, settings)
            reason = 'initialized'
    else:
        settings = _normalize(current)
        current_version = _version(current)
        if current_version < SCHEMA_VERSION:
            # Keep the user's values, add any new defaults, and stamp the schema.
            settings['version'] = SCHEMA_VERSION
            if persist:
                _write_json(path, settings)
                reason = 'upgraded %d->%d' % (current_version, SCHEMA_VERSION)
        elif settings != current and persist:
            _write_json(path, settings)
            reason = 'normalized'
    changed = write_native(data_root, settings) if persist else False
    if log and (reason or changed):
        detail = reason or 'native mirror refreshed'
        log('feature settings %s version=%d cosmetic_ui=%s'
            % (detail, settings['version'],
               'on' if settings['cosmetic_ui']['enabled'] else 'off'))
    return settings


def save(data_root, addon_root, incoming, log=None):
    """Validate and persist the panel payload. Returns the fresh snapshot."""
    if not isinstance(incoming, dict):
        raise ValueError('设置内容无效')
    ui = incoming.get('cosmetic_ui')
    if not isinstance(ui, dict):
        raise ValueError('外观覆盖设置无效')
    for key in DEFAULT['cosmetic_ui']:
        if key in ui and not isinstance(ui[key], bool):
            raise ValueError('外观覆盖开关必须是布尔值')
    current = load(data_root, addon_root, log)
    merged = _normalize(current)
    for key in DEFAULT['cosmetic_ui']:
        if key in ui:
            merged['cosmetic_ui'][key] = ui[key]
    merged['version'] = max(_version(current), SCHEMA_VERSION)
    _write_json(pathlib.Path(data_root) / FILE_NAME, merged)
    write_native(data_root, merged)
    if log:
        log('feature settings saved cosmetic_ui=%s'
            % ('on' if merged['cosmetic_ui']['enabled'] else 'off'))
    return merged