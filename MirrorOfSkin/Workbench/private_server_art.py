"""Bake the author's private-server body poses onto a native sprite rig."""
from collections import defaultdict
from copy import copy
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
import re
import struct
import zlib


def _refs(value):
    if isinstance(value, dict):
        if 'm_FileID' in value and 'm_PathID' in value:
            yield value
        else:
            for child in value.values():
                yield from _refs(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _refs(child)


def _local(objects, pointer, kind):
    obj = objects.get(pointer['m_PathID']) if pointer['m_FileID'] == 0 else None
    if obj is None or obj.type.name != kind:
        raise ValueError('作者外观需要可解析的本地资源 ' + kind)
    return obj


def _save(obj, tree):
    # The bundled UnityPy reads its original reader even after save_typetree.
    # Point subsequent analysis and the dependency walk at the new bytes.
    from UnityPy.streams import EndianBinaryReader
    data = obj.save_typetree(tree)
    obj.reader = EndianBinaryReader(data, endian=obj.reader.endian)
    obj.byte_start, obj.byte_size = 0, len(data)


def _components(objects, go, kind):
    for item in go.read_typetree()['m_Component']:
        pointer = item['component']
        component = objects.get(pointer['m_PathID'])
        if not pointer['m_FileID'] and component and component.type.name == kind:
            yield component


def _body_path(objects, root, renderer):
    transform, = _components(objects, _local(objects, renderer['m_GameObject'], 'GameObject'), 'Transform')
    chain, seen = [], set()
    while transform.path_id not in seen:
        seen.add(transform.path_id)
        tree = transform.read_typetree()
        obj = _local(objects, tree['m_GameObject'], 'GameObject')
        if obj.path_id == root:
            return zlib.crc32('/'.join(reversed(chain)).encode('utf8'))
        chain.append(obj.peek_name())
        transform = _local(objects, tree['m_Father'], 'Transform')
    raise ValueError('身体渲染节点不在声明的角色层级内')


def _body_clips(objects, app, body_path, *, allow_unrelated_curves=False):
    kinds = {'MonoBehaviour', 'AnimationClip', 'AnimatorController', 'Animator'}
    todo, seen = [app], set()
    while todo:
        obj = todo.pop()
        if obj.path_id in seen:
            continue
        seen.add(obj.path_id)
        tree = obj.read_typetree()
        if obj.type.name == 'AnimationClip':
            bindings = tree['m_ClipBindingConstant']['genericBindings']
            pointers = [b for b in bindings if b['isPPtrCurve']]
            if any(b['path'] == body_path and b['typeID'] == 212 for b in pointers):
                if len(pointers) != 1:
                    if allow_unrelated_curves:
                        continue
                    raise ValueError('同一宿主动画同时绑定身体和其他对象：' + tree['m_Name'])
                yield obj, tree
        else:
            for ptr in _refs(tree):
                child = objects.get(ptr['m_PathID'])
                if not ptr['m_FileID'] and child and child.type.name in kinds:
                    todo.append(child)


def _role(name):
    match = re.search(r'(?:^|_)(default|idle|move|guard|evade|damaged|dead|s[1-9][0-9]*)(?:_helmet)?$', name, re.I)
    return match.group(1).lower() if match else None


def _sequences(source):
    """Use the actual sprite PPtrs, as alternate skins can have identical names."""
    objects = source.assets[0].objects
    sequences = {}
    for address, ref in source.container.items():
        key = PurePosixPath(address.lower())
        if key.suffix != '.playable' or not re.fullmatch(r'(?:idle|default|move|evade|guard|damaged|dead|s\d+(?:_\d+)?)', key.stem):
            continue
        obj = objects.get(ref.path_id)
        if not obj or obj.type.name != 'MonoBehaviour':
            continue
        found = []
        for track_ref in obj.read_typetree().get('m_Tracks', []):
            track = _local(objects, track_ref, 'MonoBehaviour').read_typetree()
            infinite = track.get('m_InfiniteClip')
            if not infinite or not infinite['m_PathID'] or track.get('m_Muted'):
                continue
            clip = _local(objects, infinite, 'AnimationClip').read_typetree()
            binding = clip['m_ClipBindingConstant']
            curves = [b for b in binding['genericBindings'] if b['isPPtrCurve']]
            if len(curves) == 1 and curves[0]['typeID'] == 212 and curves[0]['path'] == 0:
                frames = [_local(objects, p, 'Sprite').path_id for p in binding['pptrCurveMapping'] if p['m_PathID']]
                if frames:
                    found.append(frames)
        if len(found) != 1 or key.stem in sequences:
            raise ValueError('无法唯一确认作者时间轴的身体帧：' + str(key))
        sequences[key.stem] = found[0]
    return sequences


def _frames(role, sequences):
    if role == 'dead' and role not in sequences:
        role = 'damaged'
    if role in ('idle', 'default') and role not in sequences:
        role = 'default' if role == 'idle' else 'idle'
    if role not in sequences:
        raise ValueError('作者时间轴缺少对应的身体姿势：' + str(role))
    poses = list(sequences[role])
    if role.startswith('s'):
        suffixes = sorted((int(k[len(role)+1:]), v) for k,v in sequences.items() if k.startswith(role+'_'))
        for _, frames in suffixes:
            poses.extend(frames)
    return [v for i,v in enumerate(poses) if not i or poses[i-1] != v]


def _matching_pixels(archive, candidates, original, other_sizes, unique_scope):
    from PIL import Image, ImageChops, ImageStat
    if not candidates:
        return original
    best, pixels = None, original
    same_size = []
    sizes = set()
    for info in candidates:
        with Image.open(BytesIO(archive.read(info))) as image:
            sizes.add(image.size)
            if image.size != original.size or image.format != 'PNG':
                continue
            frame = image.convert('RGBA')
        same_size.append(frame)
        # Compare visible premultiplied colour. Exporters differ in the RGB
        # of transparent pixels and a packed texture may be GPU-compressed.
        diff = ImageChops.difference(frame.convert('RGBa'), original.convert('RGBa'))
        score = max(ImageStat.Stat(diff).mean)
        if score <= 12 and (best is None or score < best):
            best, pixels = score, frame
        elif best is not None and score == best and frame.tobytes() != pixels.tobytes():
            raise ValueError('存在多个无法区分的作者动作贴图：' + info.filename)
    if best is not None:
        return pixels
    other = other_sizes()
    if len(same_size) == 1 and original.size not in other and unique_scope():
        return same_size[0]
    if not same_size and sizes.issubset(other):
        return original
    raise ValueError('无法唯一匹配作者散图的角色或尺寸：' + candidates[0].filename)


def _pose_texture(template, name, image):
    from PIL import Image
    raw = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
    tree = template.read_typetree()
    tree.update(m_Name=name, m_Width=image.width, m_Height=image.height, m_TextureFormat=4,
                m_CompleteImageSize=len(raw), m_MipCount=1, m_MipsStripped=0,
                m_IsPreProcessed=False, m_StreamingMipmaps=False, m_ImageCount=1,
                m_TextureDimension=2, m_PlatformBlob=[], m_StreamData={'path':'', 'offset':0, 'size':0})
    tree['image data'] = raw
    return tree


def _pose_sprite(source, texture_id, image, scale):
    """Build a quad in the tight source mesh's local bounds, preserving the feet and pivot."""
    from UnityPy.helpers.MeshHelper import MeshHandler
    original = source.read()
    mesh = MeshHandler(original.m_RD, source.version)
    mesh.process()
    xs, ys, zs = zip(*mesh.m_Vertices)
    if len(set(zs)) != 1:
        raise ValueError('暂不支持有深度的角色姿势网格')
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    ppu = original.m_PixelsToUnits
    if any(abs(a-b)>1.1 for a,b in zip(((x1-x0)*ppu,(y1-y0)*ppu), image.size)):
        raise ValueError('作者图像尺寸与动作网格不符：' + original.m_Name)
    tree = source.read_typetree()
    tree.update(m_AtlasTags=[], m_SpriteAtlas={'m_FileID':0,'m_PathID':0}, m_Bones=[], m_PhysicsShape=[])
    ppu /= scale
    tree['m_PixelsToUnits'] = ppu
    w,h = image.size
    pivot_x, pivot_y = -x0*scale*ppu/w, -y0*scale*ppu/h
    tree.update(m_Rect={'x':0.,'y':0.,'width':float(w),'height':float(h)},
                m_Pivot={'x':pivot_x,'y':pivot_y},
                m_Offset={'x':(pivot_x-0.5)*w,'y':(pivot_y-0.5)*h})
    rd = tree['m_RD']
    rd.update(texture={'m_FileID':0,'m_PathID':texture_id}, textureRect=dict(tree['m_Rect']),
              textureRectOffset={'x':0.,'y':0.}, atlasRectOffset={'x':0.,'y':0.},
              uvTransform={'x':ppu,'y':pivot_x*w,'z':ppu,'w':pivot_y*h},
              settingsRaw=2, downscaleMultiplier=1.)
    vd = rd['m_VertexData']
    channels = vd['m_Channels']
    if len(channels)<5 or [(i,c['format'],c['dimension'],c['stream'],c['offset']) for i,c in enumerate(channels) if c['dimension']] != [(0,0,3,0,0),(4,0,2,1,0)]:
        raise ValueError('暂不支持此身体网格顶点格式')
    xyz = [v for x,y in [(x0,y0),(x0,y1),(x1,y1),(x1,y0)] for v in (x*scale,y*scale,0.)]
    vd.update(m_VertexCount=4, m_DataSize=struct.pack('<20f', *(xyz+[0.,0.,0.,1.,1.,1.,1.,0.])))
    submesh = rd['m_SubMeshes'][0]
    submesh.update(firstByte=0,indexCount=6,topology=0,baseVertex=0,firstVertex=0,vertexCount=4,
                   localAABB={'m_Center':{'x':(x0+x1)*scale/2,'y':(y0+y1)*scale/2,'z':0.},
                              'm_Extent':{'x':(x1-x0)*scale/2,'y':(y1-y0)*scale/2,'z':0.}})
    rd.update(m_IndexBuffer=list(struct.pack('<6H',0,1,2,0,2,3)), m_SubMeshes=[submesh])
    if any(p['m_PathID'] for p in _refs(tree) if p is not rd['texture']):
        raise ValueError('暂不支持带附属渲染资源的角色姿势')
    return tree


def adapt_private_appearance(z, package_root, appearance, env, pid, unity, *, stock_keys=()):
    root = PurePosixPath(str(package_root).casefold())
    motion_dir = root / 'custom_motions' / appearance.casefold()
    images = defaultdict(list)
    motions = []
    sibling_motions = set()
    for info in z.infolist():
        path = PurePosixPath(info.filename.replace('\\','/').casefold())
        if root/'custom_motions' in path.parents:
            sibling_motions.add(path.parts[len(root.parts)+1])
        if path == motion_dir/'motion.bundle':
            motions.append(info)
        elif root/'custom_sprites' in path.parents and path.suffix == '.png':
            images[path.stem].append(info)
    if not motions:
        if any(re.fullmatch(r'idle|move|miss|dmg|gud|skill\d+_\d+', k) for k in images):
            # Shared artwork cannot establish a connection to an independently
            # supplied prefab. Fail only for a declared stock-layout replacement.
            layout = env.assets[0].objects[pid].peek_name().casefold()
            stock_names = {PurePosixPath(k).stem.casefold() for k in stock_keys}
            if (motion_dir.name in sibling_motions or
                    (layout in stock_names and appearance.casefold() == '!custom_'+layout)):
                raise ValueError('发现独立角色动作贴图，但没有对应外观的 motion.bundle，无法确认绑定关系')
        return None
    if len(motions)!=1:
        raise ValueError('此角色有多个同名的 motion.bundle')
    raw = z.read(motions[0])
    digest = sha256(b'private-sprite-poses-v1\0'+raw)
    source = unity.load(raw)
    if len(source.assets)!=1 or len(env.assets)!=1:
        raise ValueError('暂不支持跨文件的作者角色外观')
    sequences = _sequences(source)
    idle = _frames('idle',sequences)[0]
    src = source.assets[0].objects
    objects = env.assets[0].objects
    components = [o for o in _components(objects,objects[pid],'MonoBehaviour') if 'motionList' in o.read_typetree()]
    if len(components)!=1:
        raise ValueError('宿主缺少唯一的动作组件')
    app = components[0]
    app_tree = app.read_typetree()
    renderer = _local(objects,app_tree['sprenderer_charactermotion'],'SpriteRenderer')
    render_tree = renderer.read_typetree()
    clips = list(_body_clips(objects,app,_body_path(objects,pid,render_tree)))
    defaults = [t for _,t in clips if _role(t['m_Name']) in ('idle','default') and not t['m_Name'].lower().endswith('_helmet')]
    if not defaults:
        raise ValueError('宿主没有可用于确定显示比例的默认身体动画')
    old_idle = _local(objects,defaults[0]['m_ClipBindingConstant']['pptrCurveMapping'][0],'Sprite').read_typetree()
    new_idle = src[idle].read_typetree()
    scale = (old_idle['m_Rect']['height']/old_idle['m_PixelsToUnits']) / (new_idle['m_Rect']['height']/new_idle['m_PixelsToUnits'])
    templates = {kind: next((o for o in objects.values() if o.type.name==kind),None) for kind in ('Sprite','Texture2D')}
    if not all(templates.values()):
        raise ValueError('宿主没有可写入的 Sprite 和 Texture2D 类型')
    sprite_ids = {}
    next_id = 1

    def unique_scope():
        from private_server_appearance import read_declarations
        people = {d.appearance.casefold() for d in read_declarations(z)
                  if str(d.package_root).casefold() == str(root)}
        return sibling_motions == {appearance.casefold()} and not people - {appearance.casefold()}

    def clone(kind, tree):
        nonlocal next_id
        while next_id in objects:
            next_id += 1
        new = copy(templates[kind])
        new.path_id = next_id
        _save(new,tree)
        objects[next_id] = new
        next_id += 1
        return new.path_id

    def sprite_id(source_id):
        if source_id not in sprite_ids:
            sprite = src[source_id]
            name = sprite.peek_name()
            original = sprite.read().image.convert('RGBA')
            def other_sizes():
                return {obj.read().image.size for obj in src.values()
                        if obj.path_id != source_id and obj.type.name == 'Sprite'
                        and obj.peek_name().casefold() == name.casefold()}
            pixels = _matching_pixels(z,images[name.casefold()],original,other_sizes,unique_scope)
            if pixels is not original:
                digest.update(sha256(pixels.tobytes()).digest())
            texture = clone('Texture2D',_pose_texture(templates['Texture2D'],name,pixels))
            sprite_ids[source_id] = clone('Sprite',_pose_sprite(sprite,texture,pixels,scale))
        return sprite_ids[source_id]

    for obj,tree in clips:
        poses = _frames(_role(tree['m_Name']),sequences)
        pointers = tree['m_ClipBindingConstant']['pptrCurveMapping']
        # Native hit/coin timings remain authoritative. Sample the ordered
        # authored poses onto the existing body keys, keeping first and last.
        for i,p in enumerate(pointers):
            index = round(i*(len(poses)-1)/max(len(pointers)-1,1))
            p.update(m_FileID=0, m_PathID=sprite_id(poses[index]))
        _save(obj,tree)
    render_tree['m_Sprite'] = {'m_FileID':0,'m_PathID':sprite_id(idle)}
    _save(renderer,render_tree)
    for p in app_tree.get('_spineSkins',[]):
        spine = _local(objects,p,'MonoBehaviour')
        skin = spine.read_typetree()
        if '_isDisableSpine' not in skin:
            raise ValueError('无法关闭宿主的备用骨骼身体')
        skin['_isDisableSpine'] = 1
        _save(spine,skin)
        mesh_ptr = skin.get('_spine_renderer')
        if mesh_ptr and mesh_ptr['m_PathID']:
            mesh = objects.get(mesh_ptr['m_PathID'])
            if mesh_ptr['m_FileID'] or not mesh or mesh.type.name not in ('MeshRenderer','SkinnedMeshRenderer'):
                raise ValueError('无法识别宿主骨骼渲染器')
            state = mesh.read_typetree()
            state['m_Enabled'] = False
            _save(mesh,state)
    for motion in app_tree['motionList']:
        motion['isSpineAnim'] = 0
    _save(app,app_tree)
    return digest.hexdigest()
