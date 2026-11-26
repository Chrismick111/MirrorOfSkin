"""Resolve author-declared bodies in nonstandard private-server asset folders."""

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
import re

from custom_asset_manifest import MAX_BUNDLE, MAX_MODELS, UNITY_BUNDLE_MAGIC, relative_path
from private_server_appearance import base_appearance


_MANAGED = {'custom_appearance', 'custom_bundles', 'custom_motions', 'motion_appearances', 'installation'}
_BACKUPS = ('uninstall', 'backup', 'original', '卸载', '备份', '还原')


@dataclass(frozen=True)
class BodyEvidence:
    baseline_path: Path
    sprites: frozenset
    clips: frozenset


def _scope(declaration):
    return tuple(part.casefold() for part in declaration.package_root.parts)


def scoped_bundles(archive, declarations, all_declarations):
    roots = {_scope(declaration) for declaration in all_declarations}
    by_root = defaultdict(list)
    for declaration in declarations:
        if declaration.appearance.casefold().startswith('!custom_'):
            by_root[_scope(declaration)].append(declaration)
    if not by_root:
        return []
    selected, seen, total = [], set(), 0
    for info in archive.infolist():
        path = PurePosixPath(info.filename.replace('\\', '/'))
        if info.is_dir() or path.suffix.casefold() != '.bundle':
            continue
        parts = tuple(part.casefold() for part in path.parts)
        scopes = [root for root in roots if len(parts) > len(root) and parts[:len(root)] == root]
        if not scopes:
            continue
        scope = max(scopes, key=len)
        folders = parts[len(scope):-1]
        if (scope not in by_root or any(folder in _MANAGED for folder in folders)
                or any(part.startswith(_BACKUPS) or '.bak' in part for part in parts)):
            continue
        relative_path(info.filename, 2048)
        with archive.open(info) as contents:
            if contents.read(len(UNITY_BUNDLE_MAGIC)) != UNITY_BUNDLE_MAGIC:
                continue
        total += info.file_size
        if not len(UNITY_BUNDLE_MAGIC) <= info.file_size <= MAX_BUNDLE or total > MAX_MODELS:
            raise ValueError('待确认的私服外观模型超过读取上限：' + info.filename)
        if parts in seen:
            raise ValueError('私服外观模型路径重复：' + info.filename)
        seen.add(parts)
        selected.append((info, path, tuple(by_root[scope])))
    return selected


def _actor_clips(file, root):
    from private_server_art import _body_clips, _body_path, _components, _local

    objects = file.objects
    apps = [obj for obj in _components(objects, objects[root], 'MonoBehaviour')
            if 'motionList' in obj.read_typetree()]
    if len(apps) != 1:
        return {}
    app, = apps
    renderer = _local(objects, app.read_typetree()['sprenderer_charactermotion'], 'SpriteRenderer')
    path = _body_path(objects, root, renderer.read_typetree())
    return {obj.path_id: [p for p in tree['m_ClipBindingConstant']['pptrCurveMapping'] if p['m_PathID']]
            for obj, tree in _body_clips(objects, app, path, allow_unrelated_curves=True)}


def _sprite_pixels(file, pointer):
    if pointer['m_FileID']:
        return None
    sprite = file.objects.get(pointer['m_PathID'])
    if sprite is None or sprite.type.name != 'Sprite':
        return None
    image = sprite.read().image.convert('RGBA')
    if min(image.size) <= 1 or image.getchannel('A').getbbox() is None:
        return None
    return image.size, sha256(image.tobytes()).digest()


def _new_sprite_pixels(source, stock, pointer):
    if pointer['m_FileID']:
        return None
    pid = pointer['m_PathID']
    sprite = source.objects.get(pid)
    if sprite is None or sprite.type.name != 'Sprite':
        return None
    texture = sprite.read_typetree()['m_RD']['texture']
    if texture['m_FileID']:
        return None
    authored = source.objects.get(texture['m_PathID'])
    prior = stock.objects.get(texture['m_PathID'])
    if authored is None or authored.type.name != 'Texture2D':
        return None
    original_sprite = stock.objects.get(pid)
    if (original_sprite and original_sprite.type.name == 'Sprite' and prior and prior.type.name == 'Texture2D'
            and prior.get_raw_data() == authored.get_raw_data()
            and original_sprite.get_raw_data() == sprite.get_raw_data()):
        return None
    return _sprite_pixels(source, pointer)


def borrowed_body_evidence(source, stock, source_roots, stock_roots, baseline):
    if (source.name.casefold() != stock.name.casefold()
            or source._m_target_platform != stock._m_target_platform):
        return []
    known = {(address.casefold(), pid) for address, pid, _, _ in stock_roots}
    matched = []
    edited, original_pixels = {}, {}
    for root in source_roots:
        address, pid, _, _ = root
        if (address.casefold(), pid) not in known:
            continue
        try:
            clips = _actor_clips(source, pid)
            original = _actor_clips(stock, pid)
            authored_clips, sprites = set(), set()
            baseline_pixels = None
            for clip, pointers in clips.items():
                if not pointers:
                    continue
                changed = []
                for pointer in pointers:
                    key = pointer['m_FileID'], pointer['m_PathID']
                    if key not in edited:
                        edited[key] = _new_sprite_pixels(source, stock, pointer)
                    changed.append(edited[key])
                if not all(changed):
                    continue
                if baseline_pixels is None:
                    baseline_pixels = set()
                    for old_pointers in original.values():
                        for pointer in old_pointers:
                            key = pointer['m_FileID'], pointer['m_PathID']
                            if key not in original_pixels:
                                original_pixels[key] = _sprite_pixels(stock, pointer)
                            if original_pixels[key] is not None:
                                baseline_pixels.add(original_pixels[key])
                if baseline_pixels and all(pixels not in baseline_pixels for pixels in changed):
                    authored_clips.add(clip)
                    sprites.update(p['m_PathID'] for p in pointers)
        except (KeyError, TypeError, ValueError):
            continue
        if authored_clips:
            matched.append((root, BodyEvidence(baseline, frozenset(sprites), frozenset(authored_clips))))
    return matched


def _published(env):
    from skin_assets import _roots

    if len(env.assets) != 1:
        return []
    objects = env.assets[0].objects
    return [(*row, objects[row[1]].peek_name()) for row in _roots(env)]


def discover_private_bodies(archive, declarations, all_declarations, unity):
    from addressable_materials import _cab_files
    from scan.resource_catalog import bundle_files, resolve_roots

    options = defaultdict(list)
    missing_cabs = set()
    root_counts = defaultdict(int)
    for declaration in all_declarations:
        root_counts[_scope(declaration)] += 1
    paths = None
    for info, path, owners in scoped_bundles(archive, declarations, all_declarations):
        env = unity.load(archive.read(info))
        roots = _published(env)
        for declaration in owners:
            key = declaration.appearance.casefold().removesuffix('.prefab')
            for root in roots:
                address, _, _, layout = root
                keys = {PurePosixPath(address).stem.casefold(), layout.casefold()}
                if key in keys:
                    options[declaration].append((0, info, path, root, None))
                elif base_appearance(key) in keys:
                    options[declaration].append((1, info, path, root, None))
        if (not roots or len(owners) != 1 or root_counts[_scope(owners[0])] != 1
                or any(option[0] < 2 for option in options.get(owners[0], ()))):
            continue
        source, = env.assets
        cab = source.name.casefold()
        if not re.fullmatch(r'cab-[0-9a-f]{32}', cab):
            continue
        if paths is None:
            resource = resolve_roots()['resource_root']
            paths = (bundle_files(resource) or sorted(resource.rglob('*.bundle'))) if resource else []
        baseline = _cab_files(paths, {cab}).get(cab)
        if baseline is None:
            missing_cabs.add(source.name)
            continue
        base = unity.load(baseline.read_bytes())
        stock_roots = _published(base)
        if not stock_roots:
            continue
        for root, proof in borrowed_body_evidence(source, base.assets[0], roots, stock_roots, baseline):
            options[owners[0]].append((2, info, path, root, proof))

    matches, resources, proofs = defaultdict(list), {}, {}
    for declaration, entries in options.items():
        priority = min(entry[0] for entry in entries)
        best = [entry for entry in entries if entry[0] == priority]
        if len(best) != 1:
            raise ValueError('私服人格外观匹配到多个战斗预制体：' + declaration.appearance)
        _, info, path, root, proof = best[0]
        matches[path].append((declaration, root))
        resources[path] = info
        if proof:
            proofs[path, root[1]] = proof
    return matches, resources, proofs, sorted(missing_cabs)
