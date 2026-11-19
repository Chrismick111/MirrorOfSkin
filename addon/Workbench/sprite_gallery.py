"""List the sprite slices an appearance's animation clips point at.

Roots come from resource_catalog, so this module never invents a path. The
thumbnails are a rebuildable cache: delete the folder and the next call recreates
it. Only slices referenced by an AnimationClip PPTR curve are listed, because a
bundle also holds atlases and UI art that a skill never draws.
"""
import hashlib
import pathlib
import time

import resource_catalog
import sequence_catalog

THUMB_DIRNAME = 'sprite-thumbs'
CLIP_INDEX_NAME = 'sprite-clip-index.json'
CLIP_INDEX_VERSION = 1
THUMB_SIZE = (256, 256)


def thumb_dir(index_dir):
    return pathlib.Path(index_dir) / THUMB_DIRNAME


def clip_index_path(index_dir):
    return pathlib.Path(index_dir) / CLIP_INDEX_NAME


def appearance_tokens(appearance):
    """Name fragments that tie an appearance to its FX clips.

    10101_YiSang_BaseAppearance -> YiSang, 10101
    1079_Sancho_BerserkAppearance -> Sancho
    8381_Dulcinea_BossAppearance -> Dulcinea, Boss
    FX clips carry the character token (FX_PC_4_YiSang_7_SKL1_2_ani), never the
    identity number, so a token must be long enough to be distinctive.
    """
    if not isinstance(appearance, str):
        return []
    body = appearance
    for suffix in ('Appearance', 'Appearacne'):
        if body.endswith(suffix):
            body = body[:-len(suffix)]
    parts = [part for part in body.split('_') if part]
    tokens = []
    for part in parts:
        if part.isdigit():
            continue
        if len(part) >= 4 and part.lower() not in ('base', 'boss', 'mob', 'hand'):
            tokens.append(part)
    return tokens


def build_clip_index(resource_root, index_dir, force=False, unity_py=None, progress=None):
    """Map every AnimationClip name to the bundle that holds it.

    Sprite slices live in FX bundles, not in the appearance prefab bundle, so the
    first listing has to walk the resource once. The result is a cache: delete the
    file and the next call rebuilds it.
    """
    import json
    index_dir = pathlib.Path(index_dir)
    target = clip_index_path(index_dir)
    if not force and target.is_file():
        try:
            cached = json.loads(target.read_text(encoding='utf-8'))
            if cached.get('__version__') == CLIP_INDEX_VERSION and cached.get('resource_root') == str(pathlib.Path(resource_root).resolve()):
                return cached, 'cached'
        except (OSError, ValueError):
            pass
    if unity_py is None:
        import UnityPy as unity_py
    resource_catalog._ensure_unity_config(unity_py)
    root = pathlib.Path(resource_root).resolve()
    clips = {}
    bundles = resource_catalog.bundle_files(root)
    for position, bundle in enumerate(bundles, 1):
        relative = bundle.relative_to(root).as_posix()
        try:
            env = unity_py.load(str(bundle))
        except Exception:
            continue
        for obj in env.objects:
            try:
                if obj.type.name != 'AnimationClip':
                    continue
                name = obj.read().m_Name
            except Exception:
                continue
            if isinstance(name, str) and name:
                clips.setdefault(name, relative)
        if progress:
            progress(position, len(bundles))
    payload = {'__version__': CLIP_INDEX_VERSION, 'resource_root': str(root),
               'bundles': len(bundles), 'clips': len(clips), 'entries': clips}
    index_dir.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + '.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temp.replace(target)
    return payload, 'built'


def thumbs_available(index_dir):
    """Cheap check for the UI: does a usable cache directory exist right now."""
    folder = thumb_dir(index_dir)
    try:
        return folder.is_dir() and any(folder.glob('*.png'))
    except OSError:
        return False


def clear_thumbs(index_dir):
    folder = thumb_dir(index_dir)
    removed = 0
    if folder.is_dir():
        for item in folder.glob('*.png'):
            try:
                item.unlink()
                removed += 1
            except OSError:
                pass
    return {'removed': removed, 'directory': str(folder)}


def sprite_key(cab, path_id):
    return '%s:%s' % (cab, path_id)


def _resolve(ref, env_objects):
    """Follow an internal or external pointer to the object it names."""
    try:
        if not getattr(ref, 'm_PathID', 0):
            return None, None
        assets = ref.assetsfile
        if ref.m_FileID == 0:
            cab = assets.name
        else:
            cab = assets.externals[ref.m_FileID - 1].name
        return ref.read(), cab
    except Exception:
        return None, None


def collect(appearance, roots=None, make_thumbs=True, limit=240, progress=None):
    """Sprite slices shipped in this appearance's FX bundles, plus thumbnails.

    Slice discovery uses bundle contents. Decoded sequences are listed separately;
    matching a name to an appearance is a candidate, not proof of skill ownership.
    """
    roots = roots or resource_catalog.resolve_roots()
    index, index_source = resource_catalog.load_index(roots['index_dir'], roots['resource_root'],
                                                      auto_build=False)
    table = resource_catalog.appearance_table(index)
    bundle = table.get(appearance)
    result = {'appearance': appearance, 'bundle': bundle, 'index_source': index_source,
              'slices': [], 'notes': [], 'stats': {'seen': 0, 'created': 0, 'reused': 0,
                                                   'thumb_seconds': 0.0, 'scan_seconds': 0.0,
                                                   'bundles_scanned': 0, 'truncated': False},
              'thumb_dir': str(thumb_dir(roots['index_dir'])), 'clip_bundles': [],
              'clip_index_source': 'none', 'tokens': appearance_tokens(appearance),
              'derived_by': 'bundle-scan', 'frame_groups': [],
              'frame_stats': {'matched': 0, 'unavailable': 0, 'truncated': False}}
    if not roots.get('resource_root'):
        result['notes'].append('没有找到游戏资源目录')
        return result
    import UnityPy
    resource_catalog._ensure_unity_config(UnityPy)
    clip_index, clip_source = build_clip_index(roots['resource_root'], roots['index_dir'],
                                               unity_py=UnityPy, progress=(lambda done,total: progress('index',done,total)) if progress else None)
    result['clip_index_source'] = clip_source
    tokens = result['tokens']
    entries = clip_index.get('entries') or {}
    wanted = []
    for token in tokens:
        wanted.extend(name for name in entries if token.lower() in name.lower())
    wanted = sorted(set(wanted))
    candidates = sorted({entries[name] for name in wanted})
    if bundle and bundle not in candidates:
        candidates.insert(0, bundle)
    if not candidates:
        result['notes'].append('没有与外观令牌相关的片段或资源包：切片为未知，不是没有素材')
        return result
    result['clip_bundles'] = candidates
    started = time.time()
    seen = {}
    root = pathlib.Path(roots['resource_root'])
    def frame_thumb(sprite_obj):
        key=sprite_key(sprite_obj.assets_file.name,sprite_obj.path_id)
        name=hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]+'.png'
        target=thumb_dir(roots['index_dir'])/name
        if not target.is_file():
            image=sprite_obj.read().image.copy();image.thumbnail(THUMB_SIZE)
            target.parent.mkdir(parents=True,exist_ok=True)
            temp=target.with_name(target.name+'.tmp');image.save(temp,format='PNG');temp.replace(target)
        return name
    for bundle_pos, relative in enumerate(candidates, 1):
        if progress: progress('sprites',bundle_pos-1,len(candidates))
        try:
            env = UnityPy.load(str(root / relative))
        except Exception as exc:
            result['notes'].append('资源包读取失败（%s）：%s' % (relative, exc))
            continue
        result['stats']['bundles_scanned'] += 1
        if len(result['frame_groups'])<200:
            names={name for name in wanted if entries.get(name)==relative}
            groups,frame_stats=sequence_catalog.collect_sequences(
                env.objects,names,relative,frame_thumb,
                progress=(lambda: progress('sprites',bundle_pos-1,len(candidates))) if progress else None,
                limit=200-len(result['frame_groups']))
            result['frame_groups'].extend(groups)
            for key in ('matched','unavailable'):result['frame_stats'][key]+=frame_stats[key]
            result['frame_stats']['truncated'] |= frame_stats['truncated']
        else:result['frame_stats']['truncated']=True
        if result['stats']['truncated']:
            continue
        for object_pos, obj in enumerate(env.objects):
            if progress and object_pos % 50 == 0: progress('sprites',bundle_pos-1,len(candidates))
            try:
                if obj.type.name != 'Sprite':
                    continue
                sprite = obj.read()
            except Exception:
                continue
            try:
                cab = obj.assets_file.name
            except Exception:
                continue
            key = sprite_key(cab, obj.path_id)
            if key in seen:
                continue
            entry = {'sprite_key': key, 'cab': cab, 'path_id': str(obj.path_id),
                     'name': getattr(sprite, 'm_Name', ''),
                     'source_appearance': appearance, 'unresolved': False,
                     'derived_by': 'bundle-scan', 'bundle': relative, 'thumbnail': None}
            try:
                pivot = getattr(sprite, 'm_Pivot', None)
                rect = getattr(sprite, 'm_Rect', None)
                image = sprite.image
                size = list(image.size)
                entry['pivot'] = [round(float(pivot.x), 6), round(float(pivot.y), 6)] if pivot else [0.0, 0.0]
                entry['size'] = [int(size[0]), int(size[1])]
                entry['rect'] = ([float(getattr(rect, 'x', 0.0)), float(getattr(rect, 'y', 0.0)),
                                  float(getattr(rect, 'width', size[0])), float(getattr(rect, 'height', size[1]))]
                                 if rect else None)
            except Exception as exc:
                entry.update({'pivot': [0.0, 0.0], 'size': [0, 0], 'rect': None,
                              'unresolved': True, 'error': str(exc)})
            if make_thumbs and not entry['unresolved']:
                name = hashlib.sha256(key.encode('utf-8')).hexdigest()[:20] + '.png'
                target = thumb_dir(roots['index_dir']) / name
                result['stats']['seen'] += 1
                if target.is_file():
                    result['stats']['reused'] += 1
                else:
                    mark = time.time()
                    try:
                        copy = image.copy()
                        copy.thumbnail(THUMB_SIZE)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        temp = target.with_name(target.name + '.tmp')
                        copy.save(temp, format='PNG')
                        temp.replace(target)
                        result['stats']['created'] += 1
                    except Exception as exc:
                        entry['unresolved'] = True
                        entry['error'] = '缩略图生成失败：%s' % exc
                    result['stats']['thumb_seconds'] += time.time() - mark
                if target.is_file():
                    entry['thumbnail'] = name
            seen[key] = entry
            if len(seen) >= limit:
                result['stats']['truncated'] = True
                break
    result['scan_seconds'] = round(time.time() - started, 3)
    result['stats']['thumb_seconds'] = round(result['stats']['thumb_seconds'], 3)
    result['slices'] = list(seen.values())
    total = result['stats']['seen']
    result['stats']['hit_rate'] = round(result['stats']['reused'] / total, 4) if total else 0.0
    if not result['slices']:
        result['notes'].append('相关资源包里没有 Sprite 对象：切片为未知，不能当成“有素材但没显示”')
    if result['stats']['truncated']:
        result['notes'].append('切片超过上限 %d，已截断，完整数量未统计' % limit)
    return result


def thumb_path(index_dir, name):
    """Resolve one cached thumbnail, refusing anything outside the cache folder."""
    folder = thumb_dir(index_dir).resolve()
    candidate = (folder / pathlib.Path(name).name).resolve()
    if folder not in candidate.parents or candidate.suffix.lower() != '.png':
        raise ValueError('缩略图名称无效')
    return candidate if candidate.is_file() else None


def inventory(appearance, roots=None, progress=None):
    """Explicit classification the UI must show, so wording cannot drift.

    sprite_slice  -- original slice, replaceable by this task
    frame_sequence-- individually decoded sprite references, not composited video
    spine_binding -- skeleton binding, unresolved unless proven otherwise
    """
    listing = collect(appearance, roots, make_thumbs=True, progress=progress)
    return {'appearance': appearance, 'bundle': listing['bundle'],
            'sprite_slice': {'count': len([s for s in listing['slices'] if not s['unresolved']]),
                             'label': 'Sprite 原始切片（可选为替换素材，尚未应用到游戏）'},
            'frame_sequence': {'status': 'partial' if listing['frame_groups'] else 'unavailable',
                               'label': '候选动作帧（部分解析）', 'groups': listing['frame_groups'],
                               'stats': listing['frame_stats']},
            'spine_binding': {'status': 'unresolved',
                              'label': 'Spine 绑定（未解析）'},
            'slices': listing['slices'], 'stats': listing['stats'], 'thumb_dir': listing['thumb_dir'],
            'notes': listing['notes']}
