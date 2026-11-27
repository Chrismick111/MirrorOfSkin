"""Bake Mod Spec v2 art into the verified stock battle prefab's existing rig."""
from copy import copy
from hashlib import sha256
from io import BytesIO
import math
from pathlib import PurePosixPath
import re

from import_progress import progress_range
from private_server_art import _components, _local, _pose_texture, _quad_sprite, _save


_SINGLE_FRAME = re.compile(r'(skill[0-9]*_+)(\d+)((?:[,~]\d+)*)([_\w]*)\Z', re.ASCII)
_POSE = re.compile(r'_(default|idle|move|guard|evade|damaged|dead|special\d+|s\d+)(?:_right)?$', re.I)
_ALIASES = {'default': 'idle', 'idle': 'default', 'damaged': 'dmg', 'dmg': 'damaged',
            'guard': 'gud', 'gud': 'guard', 'evade': 'miss', 'miss': 'evade'}


def _frame_numbers(first, following):
    values = {int(first)}
    for op, value in re.findall(r'([,~])(\d+)', following):
        end = int(value)
        if op == ',':
            values.add(end)
        elif min(values) <= end <= min(values) + 256:
            values.update(range(min(values), end + 1))
    return values


class FrameArt:
    def __init__(self, archive, skin):
        self.archive = archive
        self.skin = skin
        if skin.frames_dir is None:
            raise ValueError('作者包缺少战斗逐帧目录：' + skin.skin_id)
        folder = str(skin.frames_dir).casefold()
        self.frames = {p.stem: info for name, info in skin.members.items()
                       if (p := PurePosixPath(name)).suffix == '.png' and str(p.parent) == folder}
        self.params = {}
        for name, value in skin.visual.get('frame_params', {}).items():
            name = name.casefold()
            if name in self.params or not isinstance(value, dict):
                raise ValueError('无效或重复的作者贴图参数：' + name)
            self.params[name] = value
        self.grouped = []
        for name in self.frames:
            match = _SINGLE_FRAME.fullmatch(name)
            if match and match[3]:
                self.grouped.append((match[1], _frame_numbers(match[2], match[3]), match[4], name))
        self.used = set()

    def resolve(self, sprite_name, clip_name):
        name = sprite_name.casefold()
        clip = clip_name.casefold()
        suffix = ('_p' + match[1] if (match := re.search(r'_phase(\d+)_', clip)) else '')
        if clip.endswith('_right'):
            suffix += '_r'
        alias = _ALIASES.get(name)
        for key in (name + suffix, (alias + suffix if alias else None), name, alias):
            if key in self.frames:
                return key
        match = _SINGLE_FRAME.fullmatch(name)
        if match and not match[3]:
            options = [key for prefix, frames, postfix, key in self.grouped
                       if prefix == match[1] and int(match[2]) in frames and postfix == match[4]]
            if len(options) == 1:
                return options[0]
        return None

    def pixels(self, name, target_size, origin):
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps

        image = _png(self.archive, self.frames[name])
        settings = dict(scale=1., offset_x=0., offset_y=0., alpha_choke=0,
                        brightness=1., contrast=1., saturation=1.)
        for field, value in self.params.get(name, {}).items():
            if field not in settings:
                continue
            low, high = {'scale': (0.01, 20), 'offset_x': (-8192, 8192), 'offset_y': (-8192, 8192),
                         'alpha_choke': (0, 32)}.get(field, (0, 8))
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'作者贴图坐标或效果超出范围：{name} {field}')
            settings[field] = value
        choke = settings['alpha_choke']
        if choke != int(choke):
            raise ValueError('作者贴图 alpha_choke 必须是整数：' + name)
        tw, th = target_size
        fit = min(tw / image.width, th / image.height) * settings['scale']
        w, h = max(round(image.width * fit), 1), max(round(image.height * fit), 1)
        if w > 8192 or h > 8192 or w * h > 24_000_000:
            raise ValueError('应用作者贴图缩放后超出尺寸上限：' + name)
        if (w, h) != image.size:
            image = image.resize((w, h), Image.Resampling.LANCZOS)
        alpha = image.getchannel('A')
        if choke:
            alpha = ImageOps.expand(alpha, border=1).filter(ImageFilter.MinFilter(2 * int(choke) + 1))
            alpha = alpha.crop((1, 1, w + 1, h + 1))
        rect = alpha.getbbox()
        if rect is None:
            raise ValueError('作者贴图没有可见像素：' + name)
        pixels = image.crop(rect)
        for enhancement, key in ((ImageEnhance.Brightness, 'brightness'), (ImageEnhance.Contrast, 'contrast'),
                                 (ImageEnhance.Color, 'saturation')):
            if settings[key] != 1:
                pixels = enhancement(pixels).enhance(settings[key])
        pixels.putalpha(alpha.crop(rect))
        self.used.add(name)
        # Place the complete author canvas in the stock rectangle before
        # trimming. Alpha padding belongs to that canvas's coordinate system.
        left = origin[0] + (tw - w) // 2 + round(settings['offset_x'])
        top = origin[1] + th - ((th - h) // 2 + round(settings['offset_y']))
        return pixels, (left + rect[0], top - rect[3], left + rect[2], top - rect[1])


def _png(archive, info):
    from PIL import Image

    if info.file_size > 48 * 1024**2:
        raise ValueError('作者贴图超过大小上限：' + info.filename)
    with Image.open(BytesIO(archive.read(info)), formats=['PNG']) as image:
        if not 0 < image.width <= 8192 or not 0 < image.height <= 8192 or image.width * image.height > 24_000_000:
            raise ValueError('作者贴图尺寸超出范围：' + info.filename)
        return image.convert('RGBA')


def _load_base(base_asset, unity):
    from roland_merge import Prefab
    from skin_assets import _roots

    path, address = base_asset
    env = unity.load(str(path))
    choices = [row for row in _roots(env) if row[0] == address]
    if len(env.assets) != 1 or len(choices) != 1:
        raise ValueError('无法从游戏资源确认唯一的逐帧外观原型：' + address)
    return Prefab.from_asset(env, choices[0][1])


def _main_prefix(prefab, body):
    prefixes = set()
    for obj in _controller_clips(prefab):
        clip = obj.read_typetree()
        match = re.search(r'_(?:default|idle)$', clip['m_Name'], re.I)
        if match and any(binding['path'] == body and binding['typeID'] == 212 and binding['isPPtrCurve']
                         for binding in clip['m_ClipBindingConstant']['genericBindings']):
            prefixes.add(clip['m_Name'][:match.start()].casefold())
    if not prefixes:
        raise ValueError('原型动画控制器缺少可确认角色归属的待机身体轨')
    shortest = min(prefixes, key=len)
    if any(prefix != shortest and not prefix.startswith(shortest + '_') for prefix in prefixes):
        raise ValueError('原型存在多个待机身体归属')
    return shortest


def _controller_clips(prefab):
    animator = _local(prefab.objects, prefab.app['_anim'], 'Animator').read_typetree()
    controller = _local(prefab.objects, animator['m_Controller'], 'AnimatorController').read_typetree()
    return [_local(prefab.objects, pointer, 'AnimationClip') for pointer in controller['m_AnimationClips']
            if pointer['m_PathID']]


def _authors(archive, skin, prefab, partners, unity):
    from sprite_facing import body_rig

    known = {_main_prefix(prefab, body_rig(prefab)[0]): FrameArt(archive, skin)}
    for other_archive, other, base in partners:
        declared = skin.combo.get('partners', [])
        hosts = other.combo.get('mirror_into_hosts', [])
        same_pack = other_archive is archive and other.pack_root == skin.pack_root
        if (not isinstance(declared, list) or other.skin_id not in declared
                or not isinstance(hosts, list) or (int(skin.personality) not in hosts and not same_pack)):
            continue
        donor = _load_base(base, unity)
        prefix = _main_prefix(donor, body_rig(donor)[0])
        if prefix in known:
            raise ValueError('联动作者包的身体动画归属冲突：' + other.skin_id)
        known[prefix] = FrameArt(other_archive, other)
    return known


def _copy_object(objects, template, tree, object_ids):
    obj = copy(template)
    obj.path_id = next(object_ids)
    _save(obj, tree)
    objects[obj.path_id] = obj
    return obj.path_id


def _frame_template(source):
    from UnityPy.helpers.MeshHelper import MeshHandler

    sprite = source.read()
    data = sprite.m_RD
    if sprite.m_SpriteAtlas:
        atlas = sprite.m_SpriteAtlas.deref_parse_as_object()
        data = next(value for entry, value in atlas.m_RenderDataMap if entry == sprite.m_RenderDataKey)
    rect, ppu = data.textureRect, sprite.m_PixelsToUnits
    if not all(math.isfinite(v) and v > 0 for v in (rect.width, rect.height, ppu)):
        raise ValueError('原型精灵坐标无效：' + sprite.m_Name)
    size = round(rect.width), round(rect.height)
    if min(size) < 1:
        raise ValueError('原型精灵尺寸无效：' + sprite.m_Name)
    mesh = MeshHandler(sprite.m_RD, source.version)
    mesh.process()
    if mesh.m_Vertices:
        xs, ys, _ = zip(*mesh.m_Vertices)
        origin = min(xs) * ppu, min(ys) * ppu
    else:
        origin = -sprite.m_Pivot.x * size[0], -sprite.m_Pivot.y * size[1]
    return size, origin, ppu


def _sprite(prefab, source, art, key, texture, object_ids, textures):
    size, origin, ppu = _frame_template(source)
    image, bounds = art.pixels(key, size, origin)
    if image.width > 4096 or image.height > 4096 or image.width * image.height > 8_000_000:
        raise ValueError('应用作者贴图缩放后超出尺寸上限：' + key)
    tag = 'mos_frame_' + art.skin.personality + '_' + key
    texture_key = art.skin.skin_id, key, size
    if texture_key not in textures:
        textures[texture_key] = _copy_object(prefab.objects, texture, _pose_texture(texture, tag, image), object_ids)
    tid = textures[texture_key]
    tree = _quad_sprite(source, tid, image.size, ppu, tuple(edge / ppu for edge in bounds))
    tree['m_Name'] = tag
    return _copy_object(prefab.objects, source, tree, object_ids)


def _replace_frames(prefab, authors, report):
    from sprite_facing import body_mapping_indices, body_rig

    body, _, ancestors = body_rig(prefab)
    texture = next(obj for obj in prefab.objects.values() if obj.type.name == 'Texture2D')
    ids = (pid for pid in range(10000000000, 10010000000) if pid not in prefab.objects)
    mapped, textures, missing, foreign = {}, {}, set(), set()
    verify_clips = {}
    own = next(iter(authors.values()))
    prefix = next(iter(authors))
    rest_clips = (prefix + '_default', prefix + '_idle')
    rest_sprites = {}
    controller_clips = {obj.path_id for obj in _controller_clips(prefab)}

    def replace(pointer, key, art):
        src = _local(prefab.objects, pointer, 'Sprite')
        cache = (src.path_id, art.skin.skin_id, key)
        if cache not in mapped:
            mapped[cache] = _sprite(prefab, src, art, key, texture, ids, textures)
        pointer['m_PathID'] = mapped[cache]

    clips = [obj for obj in prefab.objects.values() if obj.type.name == 'AnimationClip']
    for i, obj in enumerate(clips):
        tree = obj.read_typetree()
        clip_name = tree['m_Name']
        constant = tree['m_ClipBindingConstant']
        pp = [b for b in constant['genericBindings'] if b['isPPtrCurve']]
        if not any(b['path'] == body and b['typeID'] == 212 for b in pp):
            continue
        index = range(len(constant['pptrCurveMapping'])) if len(pp) == 1 and not tree['m_PPtrCurves'] else (
            body_mapping_indices(tree, body, ancestors))
        match = _POSE.search(clip_name)
        owner = max((key for key in authors if clip_name.casefold().startswith(key + '_')), key=len, default=None)
        art = own if obj.path_id in controller_clips else authors.get(owner)
        if art is None:
            foreign.add(clip_name[:match.start()] if match else clip_name)
            continue
        frames = []
        for n in index:
            pointer = constant['pptrCurveMapping'][n]
            if pointer['m_PathID']:
                sprite = _local(prefab.objects, pointer, 'Sprite').peek_name()
                frames.append((n, pointer, sprite, art.resolve(sprite, clip_name)))
        available = [(n, key) for n, _, _, key in frames if key is not None]
        if frames and not available and match and re.fullmatch(r's\d+', match[1], re.I):
            raise ValueError('原型攻击动作缺少任何对应的作者战斗帧：' + clip_name)
        for n, pointer, sprite, key in frames:
            if key is None:
                key = min(available, key=lambda row: abs(n - row[0]))[1] if available else None
                if key is None and sprite.casefold() == 'dead':
                    key = art.resolve('damaged', clip_name)
                key = key or art.resolve('default', clip_name)
                if key is None:
                    raise ValueError('作者战斗外观缺少可用的待机身体：' + art.skin.skin_id)
                missing.add((art.skin.skin_id, sprite, key))
            replace(pointer, key, art)
            if (art is own and clip_name.casefold() in rest_clips
                    and key == own.resolve('default', clip_name)):
                rest_sprites.setdefault(clip_name.casefold(), pointer['m_PathID'])
        if frames:
            _save(obj, tree)
            verify_clips[obj.path_id] = {n: pointer['m_PathID'] for n, pointer, _, _ in frames}
        report(i * 70 // len(clips), '正在写入作者战斗帧：' + own.skin.label)

    renderer = _local(prefab.objects, prefab.app['sprenderer_charactermotion'], 'SpriteRenderer')
    tree = renderer.read_typetree()
    idle = next((rest_sprites[clip] for clip in rest_clips if clip in rest_sprites), None)
    if idle is not None:
        tree['m_Sprite'] = {'m_FileID': 0, 'm_PathID': idle}
    else:
        rest = _local(prefab.objects, tree['m_Sprite'], 'Sprite').peek_name()
        key = own.resolve('default', rest_clips[0]) or own.resolve(rest, rest_clips[0])
        if key is None:
            raise ValueError('无法找到原型待机身体对应的作者图片：' + own.skin.skin_id)
        replace(tree['m_Sprite'], key, own)
    _save(renderer, tree)
    return missing, foreign, verify_clips, (renderer.path_id, tree['m_Sprite']['m_PathID'])


def build_frame_pack_record(archive, skin, base_asset, work, unity, look, label, *, progress=None,
                            partners=(), dependency=None):
    """Return a normal workbench import record for a declared frame skin."""
    from frame_pack_spine import apply_sd_spine
    from skin_assets import _catalog_keys, _convert, _dependency, _Streams
    from skin_motions import analyze_motion

    report = progress_range(progress)
    prefab = _load_base(base_asset, unity)
    address = base_asset[1]
    if dependency is None:
        dependency = _dependency(PurePosixPath(address).stem, address, _catalog_keys())
    authors = _authors(archive, skin, prefab, partners, unity)
    _, original_timing, original = analyze_motion(prefab.env, prefab.objects[prefab.root], look, dependency,
                                                  label, stock_only=True)
    missing, foreign, verify_clips, (renderer_id, idle_id) = _replace_frames(prefab, authors, report)
    warnings, spine_scripts = apply_sd_spine(prefab, archive, skin, _png)
    if foreign:
        warnings.append('部分合击演员未提供对应作者皮肤：' + '、'.join(sorted(foreign)))
    if missing:
        warnings.append('部分战斗帧使用同动作或待机、受击的作者图片：' +
                        '、'.join(f'{skin_id}/{slot} → {key}' for skin_id, slot, key in sorted(missing)))
    report(80, '正在写入并回读独立战斗外观')
    edited = prefab.env.file.save(packer='lz4')
    encoded, _ = _convert(unity.load(edited), sha256(edited).hexdigest(), look, address, prefab.root,
                          prefab.index_id, _Streams(unity))
    parsed = unity.load(encoded)
    objects = parsed.assets[0].objects
    for pid, frames in verify_clips.items():
        if pid not in objects:
            # Conversion prunes stock clips outside the selected appearance.
            continue
        pointers = objects[pid].read_typetree()['m_ClipBindingConstant']['pptrCurveMapping']
        if any(pointers[n] != {'m_FileID': 0, 'm_PathID': sprite} or sprite not in objects
               for n, sprite in frames.items()):
            raise ValueError('回读时出现原型身体或未绑定的战斗帧：' + objects[pid].peek_name())
    if objects[renderer_id].read_typetree()['m_Sprite'] != {'m_FileID': 0, 'm_PathID': idle_id}:
        raise ValueError('回读时未找到初始的作者战斗图片：' + skin.skin_id)
    if any(pid not in objects or objects[pid].read_typetree()['m_Script'] != script
           for pid, script in spine_scripts.items()):
        raise ValueError('回读时作者战斗 Spine 资源丢失：' + skin.skin_id)
    entry, timing, actions = analyze_motion(parsed, objects[prefab.root], look,
                                             'Imported/' + look + '.prefab', label, stock_only=True)
    if timing != original_timing or any(actions[key] != original[key] for key in ('attack', 'clash', 'defense')):
        raise ValueError('作者战斗外观未能保留原型技能或动作时序：' + skin.skin_id)
    work.mkdir(parents=True, exist_ok=True)
    bundle = work / (look + '.bundle')
    bundle.write_bytes(encoded)
    return dict(look=look, name=label, asset=address, layout=look, dependency=dependency, bundle=bundle,
                entry=entry, timing=timing, actions=actions,
                model_voice_evidence=actions.pop('model_voice_evidence'), presentation_warning='；'.join(warnings))
