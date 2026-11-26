"""Read Lethe's per-motion PNG animations from one declared appearance directory."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import io
import math
from pathlib import PurePosixPath
from zipfile import ZipInfo

from custom_asset_manifest import relative_path
from private_server_appearance import _read_json, valid_appearance_key


_MAX_IMAGE_BYTES = 32 * 1024**2
_MAX_PIXELS = 16 * 1024**2


@dataclass(frozen=True)
class AuthoredFrame:
    time: float
    sprite: ZipInfo
    offset: tuple[float, float]
    scale: float
    width: int
    height: int

    def read_image(self, archive):
        """Load an RGBA image for the native writer from the same archive."""
        with _open_image(archive, self.sprite) as image:
            return image.convert('RGBA')


@dataclass(frozen=True)
class FrameMotion:
    role: str
    duration: float
    ppu: float
    filter_mode: str | None
    frames: tuple[AuthoredFrame, ...]


def _open_image(archive, info):
    from PIL import Image

    if not 0 < info.file_size <= _MAX_IMAGE_BYTES:
        raise ValueError('作者动作 PNG 文件过大：' + info.filename)
    try:
        image = Image.open(io.BytesIO(archive.read(info)), formats=('PNG',))
        if image.width * image.height > _MAX_PIXELS or getattr(image, 'is_animated', False):
            image.close()
            raise ValueError('作者动作 PNG 尺寸或帧数无效：' + info.filename)
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError('无法读取作者动作 PNG：' + info.filename) from error
    return image


def _number(value):
    try:
        return type(value) in (float, int) and math.isfinite(value)
    except OverflowError:
        return False


def _read_motion(archive, role, definition, images):
    document = _read_json(archive, definition)
    if not isinstance(document, dict):
        raise ValueError('作者动作动画声明无效：' + definition.filename)
    duration, ppu, filter_mode = (document.get(key) for key in ('duration', 'ppu', 'filter'))
    rows = document.get('frames')
    if (not _number(duration) or not 0 < duration <= 600
            or not _number(ppu) or ppu <= 0
            or filter_mode not in (None, 'point', 'bilinear', 'trilinear')
            or not isinstance(rows, list) or not 1 <= len(rows) <= 10000):
        raise ValueError('作者动作动画声明无效：' + definition.filename)

    frames, dimensions = [], {}
    previous = -1
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('作者动作帧无效：' + definition.filename)
        time, sprite = row.get('t'), row.get('sprite')
        offset, scale = row.get('offset', [0.0, 0.0]), row.get('scale', 1.0)
        if (not _number(time) or not previous < time <= duration or time < 0
                or (not frames and time != 0)
                or not isinstance(offset, list) or len(offset) != 2 or not all(map(_number, offset))
                or not _number(scale) or scale <= 0):
            raise ValueError('作者动作帧时间或变换无效：' + definition.filename)
        path = relative_path(sprite, 257)
        options = images.get(path.name.casefold(), ()) if len(path.parts) == 1 else ()
        if path.suffix.casefold() != '.png' or len(options) != 1:
            raise ValueError('无法唯一找到作者动作帧图像：' + definition.filename + ' / ' + sprite)
        info, = options
        relative_path(info.filename, 2048)
        if info not in dimensions:
            try:
                with _open_image(archive, info) as image:
                    dimensions[info] = image.size
                    image.verify()
            except (OSError, SyntaxError) as error:
                raise ValueError('无法读取作者动作 PNG：' + info.filename) from error
        frames.append(AuthoredFrame(time, info, tuple(offset), scale, *dimensions[info]))
        previous = time
    return FrameMotion(role, duration, ppu, filter_mode, tuple(frames))


def read_frame_motions(archive, appearance_directory):
    """Return animation roles keyed by casefolded name for a single package appearance.

    Only direct motions/<role>/animation.json files can bind adjacent PNG sprites.
    The caller derives the appearance directory from its personality declaration.
    """
    directory = PurePosixPath(appearance_directory)
    scope = tuple(part.casefold() for part in directory.parts) + ('motions',)
    entries = defaultdict(lambda: defaultdict(list))
    spellings = {}
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = PurePosixPath(info.filename.replace('\\', '/'))
        if len(path.parts) != len(scope) + 2:
            continue
        parent = tuple(part.casefold() for part in path.parts[:-2])
        if parent != scope:
            continue
        role = path.parent.name.casefold()
        name = path.name.casefold()
        if name == 'animation.json':
            relative_path(info.filename, 2048)
            if not valid_appearance_key(path.parent.name) or role in spellings:
                raise ValueError('作者动作目录名称无效或重复：' + info.filename)
            spellings[role] = path.parent.name
        if name == 'animation.json' or name.endswith('.png'):
            entries[role][name].append(info)

    return {role: _read_motion(archive, spelling, entries[role]['animation.json'][0], entries[role])
            for role, spelling in spellings.items()}


def match_frame_coins(motions, role, action):
    """Match exactly named segments to an action with the same per-coin duration.

    A match preserves a package's own timing and names. It does not decide which
    native game trigger, if any, can play that action.
    """
    role = role.casefold()
    numbered = {name for name in motions
                if name.startswith(role + '_') and name[len(role) + 1:].isascii()
                and name[len(role) + 1:].isdigit()}
    coins = action.get('coins') if isinstance(action, dict) else None
    if not isinstance(coins, list) or not 1 <= len(coins) <= 128 or role not in motions:
        return None
    expected = [f'{role}_{i}' for i in range(1, len(coins))]
    if numbered != set(expected):
        return None
    matching = tuple(motions[name] for name in [role, *expected])
    for clip, coin in zip(matching, coins):
        duration = coin.get('totalDuration') if isinstance(coin, dict) else None
        if not _number(duration) or not math.isclose(clip.duration, duration, rel_tol=1e-6, abs_tol=1e-6):
            return None
    return matching
