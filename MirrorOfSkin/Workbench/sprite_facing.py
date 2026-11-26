"""Preserve a donor's body orientation when merging sprite animation rigs."""
import math
import struct
import zlib

from PIL import Image
from UnityPy.export.SpriteHelper import SpriteSettings, get_image


def local_id(ref):
    if ref['m_FileID']:
        raise ValueError('无法验证外部引用的外观朝向')
    return ref['m_PathID']


def body_rig(prefab):
    """Return the Animator-relative body path, X parity and all ancestor paths."""
    animator = local_id(prefab.app['_anim'])
    renderer = prefab.tree(local_id(prefab.app['sprenderer_charactermotion']))
    game_object = local_id(renderer['m_GameObject'])
    chain = []
    sign = -1 if renderer['m_FlipX'] else 1
    transforms = []
    while True:
        go = prefab.tree(game_object)
        comps = [local_id(c['component']) for c in go['m_Component']]
        if animator in comps:
            break
        transform = prefab.tree(next(c for c in comps if prefab.objects[c].type.name == 'Transform'))
        chain.append(go['m_Name'])
        transforms.append(transform)
        father = local_id(transform['m_Father'])
        if not father:
            raise ValueError('主体渲染器不在其 Animator 的层级内')
        game_object = local_id(prefab.tree(father)['m_GameObject'])
    chain.reverse()
    paths = tuple(zlib.crc32('/'.join(chain[:i+1]).encode()) for i in range(len(chain)))
    for transform in transforms:
        scale, rotation = transform['m_LocalScale'], transform['m_LocalRotation']
        if not math.isfinite(scale['x']) or not scale['x'] or any(rotation[k] for k in 'xyz'):
            raise ValueError('无法安全合并包含旋转或退化缩放的主体渲染器')
        if scale['x'] < 0:
            sign = -sign
    if not paths:
        raise ValueError('主体渲染器与 Animator 无独立层级')
    return paths[-1], sign, paths


def body_mapping_indices(clip, body, ancestors):
    """Resolve streamed discrete channels to their individual Sprite mappings."""
    bindings = clip['m_ClipBindingConstant']['genericBindings']
    discrete = [b for b in bindings if b['isPPtrCurve'] or b.get('isIntCurve')]
    lanes = [i for i, b in enumerate(discrete) if b['typeID'] == 212 and b['path'] == body and b['isPPtrCurve']]
    if not lanes:
        return ()
    if (len(lanes) != 1 or clip['m_PPtrCurves']
            or any(not b['isPPtrCurve'] and (b['path'] == body and b['typeID'] == 212
                   or b['path'] in ancestors and b['typeID'] == 4 and b['attribute'] != 1)
                   for b in bindings)):
        raise ValueError('无法安全合并带独立朝向曲线的主体轨道：' + clip['m_Name'])
    mapping = clip['m_ClipBindingConstant']['pptrCurveMapping']
    streamed = clip['m_MuscleClip']['m_Clip']['data']['m_StreamedClip']
    if streamed.get('discreteCurveCount') != len(discrete):
        raise ValueError('无法识别主体精灵曲线布局：' + clip['m_Name'])
    start = streamed['curveCount']
    words = streamed['data']
    groups = [set() for _ in discrete]
    offset = 0
    while offset < len(words):
        if offset + 2 > len(words):
            raise ValueError('精灵曲线帧不完整')
        count = words[offset + 1]
        offset += 2
        if offset + 5 * count > len(words):
            raise ValueError('精灵曲线关键帧不完整')
        for key in range(offset, offset + 5 * count, 5):
            lane = words[key] - start
            if 0 <= lane < len(discrete) and discrete[lane]['isPPtrCurve']:
                value, = struct.unpack('<f', struct.pack('<I', words[key + 4]))
                if not math.isfinite(value) or value != int(value) or not 0 <= value < len(mapping):
                    raise ValueError('精灵曲线映射越界')
                groups[lane].add(int(value))
        offset += 5 * count
    selected = groups[lanes[0]]
    if not selected or any(selected & rows for i, rows in enumerate(groups) if i != lanes[0]):
        raise ValueError('主体与其他渲染轨道共用精灵映射：' + clip['m_Name'])
    return sorted(selected)


def mirror_sprite(prefab, obj):
    """Return a detached mirrored Sprite and a new texture's type/tree."""
    sprite = obj.read_typetree()
    if sprite['m_Bones'] or sprite['m_RD']['m_Bindpose']:
        raise ValueError('不能安全镜像带骨骼权重的精灵：' + sprite['m_Name'])
    rd = sprite['m_RD']
    atlas = local_id(sprite['m_SpriteAtlas'])
    atlas_rd = rd
    if atlas:
        rows = prefab.tree(atlas)['m_RenderDataMap']
        atlas_rd = next((v for k, v in rows if k == sprite['m_RenderDataKey']), None)
        if not atlas_rd:
            raise ValueError('找不到精灵所在图集：' + sprite['m_Name'])
    if atlas_rd.get('secondaryTextures'):
        raise ValueError('不能安全镜像含多通道纹理的精灵：' + sprite['m_Name'])
    texture = prefab.objects[local_id(atlas_rd['texture'])]
    texture_tree = texture.read_typetree()
    parsed = obj.read()
    texture_ref = texture.read()
    # SpriteHelper caches the source RGBA atlas. Crop its actual render rect,
    # undo atlas packing and mirror artwork once around the reflected pivot.
    from UnityPy.classes import PPtr
    ptr = lambda p: PPtr(m_FileID=p['m_FileID'],m_PathID=p['m_PathID'],assetsfile=obj.assets_file)
    alpha = atlas_rd['alphaTexture']
    source = get_image(parsed, ptr(atlas_rd['texture']), ptr(alpha) if local_id(alpha) else None)
    rect = atlas_rd['textureRect']
    x, y, width, height = (rect[k] for k in ('x', 'y', 'width', 'height'))
    if not all(float(v).is_integer() for v in (x,y,width,height)) or not (
            0 < width <= 4096 and 0 < height <= 4096 and 0 <= x <= source.width-width and 0 <= y <= source.height-height):
        raise ValueError('不能安全镜像非整数或越界图集区域：' + sprite['m_Name'])
    settings = SpriteSettings(atlas_rd['settingsRaw'])
    rotation = settings.packingRotation if settings.packed else 0
    modes = {1: Image.Transpose.FLIP_LEFT_RIGHT, 2: Image.Transpose.FLIP_TOP_BOTTOM,
             3: Image.Transpose.ROTATE_180}
    if rotation and rotation not in modes:
        raise ValueError('不能安全镜像未知旋转布局的精灵：' + sprite['m_Name'])
    image = source.crop(tuple(map(int,(x,y,x+width,y+height)))).convert('RGBA')
    if rotation:
        image = image.transpose(modes[rotation])
    image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    name = sprite['m_Name'] + '__MOS_mirror_x'
    # get_image() returns texture-space order (bottom row first).
    texture_ref.set_image(image.transpose(Image.Transpose.FLIP_TOP_BOTTOM), target_format=4)
    for field in ('m_Width','m_Height','m_TextureFormat','m_MipCount','m_CompleteImageSize'):
        texture_tree[field] = getattr(texture_ref, field)
    texture_tree.update(m_Name=name, m_StreamData={'offset':0,'size':0,'path':''},
                        m_MipsStripped=0, m_IsPreProcessed=False,
                        m_StreamingMipmaps=False)
    texture_tree['image data'] = texture_ref.image_data
    vertex = rd['m_VertexData']
    n = vertex['m_VertexCount']
    channels = [(i,c['stream'],c['offset'],c['format'],c['dimension'])
                for i,c in enumerate(vertex['m_Channels']) if c['dimension']]
    data = bytearray(vertex['m_DataSize'])
    uv_start = (n*12+15)//16*16
    if channels != [(0,0,0,0,3),(4,1,0,0,2)] or not n or len(data) != uv_start+n*8 or any(data[uv_start:]):
        raise ValueError('不能安全镜像未知顶点布局的精灵：' + sprite['m_Name'])
    uv = atlas_rd['uvTransform']
    px, py = uv['y'] - x, uv['w'] - y
    for i in range(n):
        vx, vy, _ = struct.unpack_from('<3f', data, i*12)
        u, v = (vx*uv['x']+px)/width, (vy*uv['z']+py)/height
        if not (-0.01 <= u <= 1.01 and -0.01 <= v <= 1.01):
            raise ValueError('镜像精灵的纹理坐标越界：' + sprite['m_Name'])
        struct.pack_into('<f', data, i*12, -vx)
        struct.pack_into('<2f', data, uv_start+i*8, 1-u, v)
    vertex['m_DataSize'] = bytes(data)
    indices = rd['m_IndexBuffer']
    for mesh in rd['m_SubMeshes']:
        start, count = mesh['firstByte'], mesh['indexCount']
        if mesh['topology'] or count%3 or start%2 or start+count*2>len(indices):
            raise ValueError('不能安全镜像未知三角形布局：' + sprite['m_Name'])
        for i in range(start,start+count*2,6):
            indices[i+2:i+6] = indices[i+4:i+6] + indices[i+2:i+4]
        mesh['localAABB']['m_Center']['x'] *= -1
    zero = {'m_FileID':0, 'm_PathID':0}
    rd.update(texture=zero.copy(), alphaTexture=zero.copy(), settingsRaw=rd['settingsRaw'] & ~61,
              textureRect=dict(x=0.,y=0.,width=width,height=height), textureRectOffset={'x':0., 'y':0.},
              atlasRectOffset={'x':-1.,'y':-1.}, downscaleMultiplier=1.,
              uvTransform=dict(x=uv['x'],y=width-px,z=uv['z'],w=py))
    sprite.update(m_Name=name, m_AtlasTags=[], m_SpriteAtlas=zero)
    sprite['m_Pivot']['x'] = 1 - sprite['m_Pivot']['x']
    sprite['m_Offset']['x'] *= -1
    border = sprite['m_Border']
    border['x'], border['z'] = border['z'], border['x']
    for shape in sprite['m_PhysicsShape']:
        shape.reverse()
        for point in shape:
            point['x'] *= -1
    return sprite, texture, texture_tree
