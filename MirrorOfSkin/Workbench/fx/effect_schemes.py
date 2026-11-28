"""Persistent effect plans; data only, independent of external applications."""
import json
import math
import os
import pathlib
import re
import tempfile

DIRECTORY = 'fx-schemes'
_NAME = re.compile(r'^[^\\/:*?"<>|\x00-\x1f]{1,40}$')
_RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)
_COLOR = re.compile(r'^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$')

def _path(root, name):
    if not isinstance(name, str):
        raise ValueError('方案名无效')
    name = name.strip()
    if not _NAME.fullmatch(name) or name.startswith('.') or name.endswith('.') or _RESERVED.match(name):
        raise ValueError('方案名无效')
    return pathlib.Path(root) / DIRECTORY / (name + '.json')

_SCOPES = ('skill', 'global')


def _number(value, label, minimum=None, strict=False):
    """One numeric rule for both the effect fields and the sprite geometry."""
    if isinstance(value, bool):
        raise ValueError(label + '必须是数字')
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(label + '必须是数字')
    if not math.isfinite(value) or (minimum is not None and (value <= minimum if strict else value < minimum)):
        raise ValueError(label + '数值无效')
    return value


def _sprite(value):
    """Validate one optional sprite override; any bad field rejects the save.

    The override records which original slice a skill points at, so a caller can
    rebuild the same reference later without re-reading the bundle: cab + path_id
    identify the slice, pivot and size keep its geometry, scope says whether the
    swap is local to this skill or global.
    """
    if not isinstance(value, dict):
        raise ValueError('素材替换格式无效')
    sprite = dict(value)
    path_id = sprite.get('path_id')
    if isinstance(path_id, bool) or not isinstance(path_id, (str, int)):
        raise ValueError('素材 path_id 必须是数字文本')
    text = str(path_id).strip()
    if not re.fullmatch(r'-?\d+', text):
        raise ValueError('素材 path_id 必须是数字文本')
    sprite['path_id'] = text
    source = sprite.get('source_appearance')
    if source is not None and not isinstance(source, str):
        raise ValueError('素材来源外观必须是文本')
    key = sprite.get('sprite_key')
    if key is not None and not isinstance(key, str):
        raise ValueError('素材标识必须是文本')
    cab = sprite.get('cab')
    if cab is not None and not isinstance(cab, str):
        raise ValueError('素材 CAB 必须是文本')
    scope = sprite.get('scope')
    if scope not in _SCOPES:
        raise ValueError('素材作用域只能是 skill 或 global')
    unresolved = sprite.get('unresolved', False)
    if not isinstance(unresolved, bool):
        raise ValueError('素材未解析标记必须是布尔')
    for field in ('pivot', 'size'):
        pair = sprite.get(field)
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError('素材 %s 必须是两个数字' % field)
        sprite[field] = [_number(component, '素材 ' + field) for component in pair]
    sprite['unresolved'] = unresolved
    sprite['scope'] = scope
    return sprite


def _validate(plan):
    if not isinstance(plan, dict) or plan.get('schema') != 1 or not isinstance(plan.get('effects'), list):
        raise ValueError('特效方案格式无效')
    result = dict(plan)
    result['effects'] = []
    def number(value, label, minimum=None, strict=False):
        return _number(value, label, minimum, strict)
    for item in plan['effects']:
        if not isinstance(item, dict): raise ValueError('特效条目格式无效')
        effect = dict(item)
        for key in ('time', 'duration'):
            if effect.get(key) not in (None, ''): effect[key] = number(effect[key], key, 0)
        params = effect.get('parameters', {})
        if not isinstance(params, dict): raise ValueError('特效参数格式无效')
        params = dict(params)
        for key in ('offset_x', 'offset_y', 'offset_z', 'scale'):
            if params.get(key) not in (None, ''): params[key] = number(params[key], key, 0 if key == 'scale' else None, key == 'scale')
        color = params.get('color')
        if color not in (None, '') and (not isinstance(color, str) or not _COLOR.fullmatch(color)):
            raise ValueError('颜色须为 #RRGGBB 或 #RRGGBBAA')
        if params.get('anchor') is not None and not isinstance(params['anchor'], str): raise ValueError('锚点必须是文本')
        effect['parameters'] = params
        if effect.get('sprite') is not None: effect['sprite'] = _sprite(effect['sprite'])
        result['effects'].append(effect)
    return result

def get(root, name):
    path = _path(root, name)
    if not path.is_file():
        raise ValueError('特效方案不存在')
    return _validate(json.loads(path.read_text(encoding='utf-8-sig')))

def listing(root):
    folder = pathlib.Path(root) / DIRECTORY
    if not folder.exists():
        return []
    return sorted((p.stem for p in folder.glob('*.json') if p.is_file()), key=str.casefold)

def _writable(folder):
    """Check write access without touching files already present in the folder."""
    import uuid
    probe = folder / ('.effect-write-probe-' + uuid.uuid4().hex)
    created = False
    try:
        fd = os.open(str(probe), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        os.close(fd)
    except OSError as exc:
        raise ValueError('特效方案目录不可写，请检查目录权限后重试') from exc
    finally:
        if created:
            try: probe.unlink()
            except OSError: pass
def save(root, name, plan, overwrite=False):
    path = _path(root, name)
    text = json.dumps(_validate(plan), ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise ValueError('已存在同名特效方案')
    _writable(path.parent)
    fd, temp = tempfile.mkstemp(prefix='.effect-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as out:
            out.write(text)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return path.stem

def delete(root, name):
    path = _path(root, name)
    if not path.is_file():
        raise ValueError('特效方案不存在')
    path.unlink()
