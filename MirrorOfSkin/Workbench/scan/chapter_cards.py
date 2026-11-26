"""Serve default chapter cards and apply the workbench's user chapter settings."""
import base64
import binascii
import hashlib
import json
import pathlib
import re
import uuid

from custom_portraits import validate_png

SETTINGS = 'Workbench/appearance_chapters.json'
USER_ART = 'Workbench/user_chapter_art'
MAX_IMAGE_BYTES = 2 * 1024 * 1024
DEFAULT_RANK = 20000


def _real_chapter(key):
    return bool(isinstance(key, str) and re.fullmatch(r'[a-zA-Z0-9_]{1,128}', key)
                and key != 'unassigned' and not key.startswith('__'))


def settings(root):
    try:
        raw = (root / SETTINGS).read_bytes()
    except FileNotFoundError:
        return {'schema': 1, 'chapters': {}, 'moves': {}}, _revision(b'')
    value = json.loads(raw)
    if (not isinstance(value, dict) or value.get('schema') != 1 or
            not isinstance(value.get('chapters'), dict) or not isinstance(value.get('moves'), dict) or
            any(not _real_chapter(key) or not isinstance(row, dict) or
                not isinstance(row.get('label', ''), str) or not isinstance(row.get('default_label', ''), str)
                for key, row in value['chapters'].items()) or
            any(not _real_chapter(key) for key in value['moves'].values())):
        raise ValueError('自定义章节设置文件无效')
    return value, _revision(raw)


def _revision(raw):
    return hashlib.sha256(raw).hexdigest()


def _check_revision(expected, actual):
    if expected != actual:
        raise ValueError('章节设置已在其他窗口修改，请重新载入')


def _save_settings(root, value):
    from skin_import import encode, write_atomic
    raw = encode(value)
    write_atomic(root / SETTINGS, raw)
    return _revision(raw)


def _user_art_path(root, name):
    if not isinstance(name, str) or not re.fullmatch(r'[0-9a-f]{64}\.png', name):
        return None
    path = root / USER_ART / name
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('章节封面目录无效')
    return path

def _entries(root):
    folder = pathlib.Path(root) / 'Workbench/chapter_art'
    def read_cards(name):
        try:
            data = json.loads((folder/name).read_text(encoding='utf-8-sig'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}
    data = read_cards('chapters.discovered.json')
    discovered_assets={str(name).casefold():row for name,row in read_cards('discovered-assets.json').items() if isinstance(row,dict)}
    try:
        bundled=json.loads((pathlib.Path(root)/'Workbench/data/chapter_cards.json').read_text(encoding='utf-8-sig'))
        if not isinstance(bundled,dict):bundled={}
    except (OSError,ValueError):bundled={}
    bundled.update(read_cards('chapters.json'))
    for key, curated in bundled.items():
        if not isinstance(curated, dict):
            continue
        merged = dict(data.get(key) or {})
        filename = curated.get('image')
        merged.update(curated)
        if not filename or not isinstance(filename, str) or not re.fullmatch(r'[\w.-]+\.png', filename) or not (folder/filename).is_file():
            found=discovered_assets.get(str(filename or '').casefold(),{}).get('file')
            if not isinstance(found,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+\.png',found) or '..' in found or not (folder/found).is_file():found=None
            previous=(data.get(key) or {}).get('image')
            if not isinstance(previous,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+\.png',previous) or '..' in previous or not (folder/previous).is_file():previous=None
            merged['image'] = previous or found
        data[key] = merged
    result = {}
    for key, value in data.items():
        if not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9_]+',key) or not isinstance(value,dict):
            continue
        filename = value.get('image')
        if filename is not None and (not isinstance(filename,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+\.png',filename) or '..' in filename ):
            continue
        result[key] = value
    return folder, result

def load(root):
    folder, entries = _entries(root)
    return {key: {'chapter':str(value.get('chapter','')), 'title':str(value.get('title','')),
                  'timeline':str(value.get('timeline','')), 'rank':value.get('rank',20000), 'art_note':str(value.get('art_note','')),
                  'image_url':('api/chapter-image/'+key) if value.get('image') and (folder/value['image']).is_file() else ''}
            for key,value in entries.items()}

def _default_label(card, key):
    return card.get('label') or ' · '.join(filter(None, (card.get('chapter'), card.get('title')))) or key


def project(root, catalog):
    """Decorate the assembled presentation catalog after all automatic groups are added."""
    art = load(root)
    value, revision = settings(root)
    for entry in catalog.values():
        key = entry.get('chapter')
        groups = entry.get('chapter_memberships') or []
        for group in [{'chapter': key, 'label': entry.get('chapter_label')}, *groups]:
            group_key = group.get('chapter')
            if not _real_chapter(group_key):
                continue
            card = art.setdefault(group_key, {})
            card.setdefault('rank', entry.get('chapter_rank', DEFAULT_RANK))
            if group.get('label'):
                card.setdefault('label', group['label'])
    labels = {}
    for key, row in value['chapters'].items():
        card = art.setdefault(key, {'rank': row.get('rank', DEFAULT_RANK), 'label': row.get('default_label') or key})
        if row.get('label'):
            card.update(label=row['label'], title=row['label'])
            labels[key] = row['label']
        path = _user_art_path(root, row.get('image'))
        if path is not None and path.is_file():
            card.update(image_url=f'api/chapter-image/{key}?v={path.stem}', custom_image=True, art_note='')
        if row.get('custom'):
            card['custom'] = True
    for identity, entry in catalog.items():
        key = value['moves'].get(identity)
        if key in art:
            label = _default_label(art[key], key)
            entry.update(chapter=key, chapter_label=label, chapter_rank=art[key].get('rank', DEFAULT_RANK),
                         chapter_memberships=[{'chapter': key, 'label': label}], user_chapter=key)
            continue
        if entry.get('chapter') in labels:
            entry['chapter_label'] = labels[entry['chapter']]
        groups = entry.get('chapter_memberships') or []
        if any(group.get('chapter') in labels for group in groups):
            entry['chapter_memberships'] = [dict(group, label=labels[group['chapter']])
                                            if group.get('chapter') in labels else group for group in groups]
    return art, revision


def _decode_image(image):
    prefix = 'data:image/png;base64,'
    if not isinstance(image, str) or not image.startswith(prefix):
        raise ValueError('章节封面需要 PNG 图片')
    payload = image[len(prefix):]
    if len(payload) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
        raise ValueError('章节封面超过 2 MiB')
    try:
        blob = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError('章节封面编码无效') from exc
    validate_png(blob, max_bytes=MAX_IMAGE_BYTES, max_dimension=1024)
    return blob


def save(root, body, art):
    """Save one chapter while the workbench save lock is held."""
    from skin_import import write_atomic

    value, current = settings(root)
    _check_revision(body.get('revision'), current)
    label = body.get('label')
    if not isinstance(label, str) or not label.strip() or len(label) > 100 or not label.isprintable():
        raise ValueError('章节名称需填写 1 至 100 个可显示字符')
    key = body.get('id')
    if key is None:
        key = 'custom_' + uuid.uuid4().hex
        row = {'custom': True}
    elif _real_chapter(key) and key in art:
        row = value['chapters'].setdefault(key, {'rank': art[key].get('rank', DEFAULT_RANK)})
    else:
        raise ValueError('请选择有效的章节')
    row['label'] = label.strip()
    previous = None
    if 'image' in body:
        previous = _user_art_path(root, row.pop('image', None))
        if body['image'] is not None:
            blob = _decode_image(body['image'])
            filename = _revision(key.encode('ascii') + b'\x00' + blob) + '.png'
            write_atomic(_user_art_path(root, filename), blob)
            row['image'] = filename
    value['chapters'][key] = row
    revision = _save_settings(root, value)
    if previous is not None and previous.name != row.get('image'):
        try:
            previous.unlink(missing_ok=True)
        except OSError:
            pass  # The saved chapter no longer references this image.
    return {'id': key, 'revision': revision}


def move(root, body, catalog, art):
    """Apply one exclusive chapter per appearance while the save lock is held."""
    value, current = settings(root)
    _check_revision(body.get('revision'), current)
    ids = body.get('ids')
    if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or x not in catalog for x in ids):
        raise ValueError('请选择有效的外观')
    chapter = body['chapter']
    if chapter is None:
        for identity in ids:
            value['moves'].pop(identity, None)
    else:
        if not _real_chapter(chapter) or chapter not in art:
            raise ValueError('请选择有效的目标章节')
        card = art[chapter]
        value['chapters'].setdefault(chapter, {'default_label': _default_label(card, chapter),
                                              'rank': card.get('rank', DEFAULT_RANK)})
        value['moves'].update(dict.fromkeys(ids, chapter))
    return {'revision': _save_settings(root, value)}


def image(root, key):
    root = pathlib.Path(root)
    value, _ = settings(root)
    path = _user_art_path(root, value['chapters'].get(key, {}).get('image'))
    if path is not None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            pass
    folder, entries = _entries(root)
    name = entries.get(key,{}).get('image')
    if not name: return None
    try: return (folder/name).read_bytes()
    except OSError: return None
