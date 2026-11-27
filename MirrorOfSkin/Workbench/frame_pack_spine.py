"""Replace the author-declared Spine SD rig without touching same-named illustrations."""
import json
from pathlib import PurePosixPath
import re

from private_server_art import _components, _local, _pose_texture, _save


def _text(archive, info):
    if not 0 < info.file_size <= 8 * 1024**2:
        raise ValueError('作者 Spine 文本大小无效：' + info.filename)
    return archive.read(info).decode('utf-8-sig')


def _script(obj, value):
    tree = obj.read_typetree()
    tree['m_Script'] = value
    _save(obj, tree)


def _replace_atlas(objects, atlas, text, image):
    from PIL import Image, ImageChops

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if (not lines or sum(line.casefold().endswith('.png') for line in lines) != 1
            or not lines[0].casefold().endswith('.png')):
        raise ValueError('当前支持单页作者 Spine 图集')
    size = re.fullmatch(r'size:\s*(\d+)\s*,\s*(\d+)', lines[1]) if len(lines) > 1 else None
    if size is None or tuple(map(int, size.groups())) != image.size:
        raise ValueError('作者 Spine 图集尺寸与贴图不符')
    for line in lines:
        if line.startswith('bounds:'):
            coords = line.removeprefix('bounds:').split(',')
            if len(coords) != 4:
                raise ValueError('作者 Spine 图集区域无效')
            x, y, w, h = map(int, coords)
            if min(x, y) < 0 or min(w, h) < 1 or x + w > image.width or y + h > image.height:
                raise ValueError('作者 Spine 图集区域越界')
    if re.search(r'(?mi)^\s*pma\s*:\s*true\s*$', text):
        r, g, b, a = image.split()
        image = Image.merge('RGBA', (ImageChops.multiply(r, a), ImageChops.multiply(g, a),
                                     ImageChops.multiply(b, a), a))
    materials = atlas['materials']
    if len(materials) != 1:
        raise ValueError('原型 Spine 图集没有唯一的材质')
    material = _local(objects, materials[0], 'Material').read_typetree()
    main = dict(material['m_SavedProperties']['m_TexEnvs'])['_MainTex']['m_Texture']
    texture = _local(objects, main, 'Texture2D')
    _save(texture, _pose_texture(texture, texture.peek_name(), image))
    source = _local(objects, atlas['atlasFile'], 'TextAsset')
    _script(source, text)
    return source.path_id


def apply_sd_spine(prefab, archive, skin, read_png):
    if skin.spine_dir is None:
        return [], {}
    folder = str(skin.spine_dir).casefold()
    files = {p.name: info for name, info in skin.members.items()
             if str((p := PurePosixPath(name)).parent) == folder}
    targets = skin.visual.get('spine_targets', {})
    if not isinstance(targets, dict):
        raise ValueError('作者 Spine 目标声明无效')
    explicit = {stem.casefold(): scope for stem, scope in targets.items()}
    pending = {PurePosixPath(name).stem for name in files if name.endswith('.atlas')
               and explicit.get(PurePosixPath(name).stem, 'sd') == 'sd'}
    for stem in pending:
        if any(stem + ext not in files for ext in ('.json', '.png')):
            raise ValueError('作者 Spine 图集缺少配对的骨骼或纹理：' + stem)
    objects = prefab.objects
    scripts = {}
    for ref in prefab.app.get('_spineSkins', []):
        controller = _local(objects, ref, 'MonoBehaviour').read_typetree()
        go = _local(objects, controller['m_GameObject'], 'GameObject')
        for component in _components(objects, go, 'MonoBehaviour'):
            rig = component.read_typetree()
            if not rig.get('skeletonDataAsset'):
                continue
            skeleton = _local(objects, rig['skeletonDataAsset'], 'MonoBehaviour').read_typetree()
            source_json = _local(objects, skeleton['skeletonJSON'], 'TextAsset')
            stem = source_json.peek_name().casefold()
            if stem not in pending:
                continue
            text = _text(archive, files[stem + '.json'])
            doc = json.loads(text)
            old_doc = json.loads(source_json.read_typetree()['m_Script'])
            if doc.get('skeleton', {}).get('spine', '').split('.')[:2] != old_doc.get('skeleton', {}).get('spine', '').split('.')[:2]:
                raise ValueError('作者和原型使用的 Spine 骨骼版本不同：' + stem)
            if not set(old_doc.get('animations', {})).issubset(doc.get('animations', {})):
                raise ValueError('作者 Spine 缺少原型使用的动画：' + stem)
            atlases = skeleton['atlasAssets']
            if len(atlases) != 1:
                raise ValueError('原型存在多个 Spine 图集：' + stem)
            atlas = _local(objects, atlases[0], 'MonoBehaviour').read_typetree()
            atlas_text = _text(archive, files[stem + '.atlas'])
            atlas_id = _replace_atlas(objects, atlas, atlas_text, read_png(archive, files[stem + '.png']))
            _script(source_json, text)
            scripts.update({atlas_id: atlas_text, source_json.path_id: text})
            pending.remove(stem)
    warnings = ['尚未找到战斗 Spine 的唯一对应骨骼：' + '、'.join(sorted(pending))] if pending else []
    return warnings, scripts
