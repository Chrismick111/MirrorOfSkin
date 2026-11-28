"""Exercise Carra2 with real game models and synthetic author object tables.

Use a Python environment with UnityPy available, such as the launcher Python.
Supply --cache and --index if your local game resource paths differ.
"""
import argparse
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import lzma
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import traceback
from unittest.mock import patch
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
GAME_MODELS = ('10101_YiSang_BaseAppearance', '11201_Gregor_BaseAppearance')


@dataclass
class Model:
    name: str
    relative: Path
    address: str
    root_id: int
    raw: bytes
    asset: object


def load_model(cache, index, name, unity):
    (relative, entry), = [(Path(relative), entry) for relative, entry in index['entries'].items()
                         if name in entry.get('prefabs', {})]
    bundle = (cache / relative).resolve(strict=True)
    if not bundle.is_relative_to(cache):
        raise ValueError('Model location escapes the game cache: ' + str(bundle))
    stat = bundle.stat()
    if [stat.st_size, stat.st_mtime_ns] != entry['fingerprint']:
        raise ValueError('The resource index fingerprint is stale: ' + str(relative))
    address = entry['prefabs'][name]
    raw = bundle.read_bytes()
    env = unity.load(raw)
    if not address.endswith('/' + name + '.prefab') or address not in env.container:
        raise ValueError('The indexed prefab is missing from its Unity container: ' + address)
    asset, = env.assets
    return Model(name, relative, address, env.container[address].path_id, raw, asset)


def script_key(asset, file_id, path_id):
    if path_id and 0 < file_id <= len(asset.externals):
        external = asset.externals[file_id - 1]
        return (external.path.casefold(), external.guid, external.type, path_id)


def type_key(asset, typ):
    if typ.class_id != 114 or not 0 <= typ.script_type_index < len(asset.script_types):
        return None
    ref = asset.script_types[typ.script_type_index]
    file_id = ref.local_serialized_file_index
    if ref.local_identifier_in_file and 0 < file_id <= len(asset.externals):
        return script_key(asset, file_id, ref.local_identifier_in_file)


def source_object(model, *, missing_in=None):
    forbidden = {type_key(missing_in.asset, typ) for typ in missing_in.asset.types} if missing_in else set()
    for obj in sorted(model.asset.objects.values(), key=lambda item: (item.type_id, item.path_id)):
        typ = obj.serialized_type
        if not typ or not typ.node or typ.is_stripped_type or typ.type_dependencies or not 0 < obj.byte_size < 65536:
            continue
        key = type_key(model.asset, typ)
        if not key or key in forbidden:
            continue
        if missing_in and not any((ref.path.casefold(), ref.guid, ref.type) == key[:3]
                                  for ref in missing_in.asset.externals):
            continue
        tree = obj.read_typetree()
        ref = tree.get('m_Script')
        if ref and isinstance(tree.get('m_Name'), str) and script_key(model.asset, ref['m_FileID'], ref['m_PathID']) == key:
            return obj, key
    raise ValueError('No suitable MonoBehaviour object in ' + model.name)


def edited_object(obj, marker, *, script_file=None):
    from UnityPy.helpers.TypeTreeHelper import write_typetree
    from UnityPy.streams import EndianBinaryWriter

    tree = obj.read_typetree()
    tree['m_Name'] = marker
    if script_file is not None:
        tree['m_Script']['m_FileID'] = script_file
    writer = EndianBinaryWriter(endian=obj.assets_file.reader.endian)
    write_typetree(tree, obj.serialized_type.node, writer, obj.assets_file)
    return writer.bytes


def make_patch(model, entries):
    output = BytesIO()
    with ZipFile(output, 'w') as archive:
        group = model.relative.parent.as_posix()
        for path_id, author_slot, raw in entries:
            archive.writestr(f'{group}/{path_id}.{author_slot}', lzma.compress(raw))
    return output.getvalue()


def verify_object(asset, path_id, raw, marker, key, *, slot=None):
    obj = asset.objects[path_id]
    if slot is not None:
        assert obj.type_id == slot, (path_id, obj.type_id, slot)
    tree = obj.read_typetree()
    assert tree['m_Name'] == marker, (path_id, tree['m_Name'])
    if key is None:
        assert obj.type.name == 'GameObject', ('wrong native object class', path_id, obj.type.name)
    else:
        assert type_key(asset, obj.serialized_type) == key, ('wrong serialized script', path_id, obj.type_id)
        ref = tree['m_Script']
        assert script_key(asset, ref['m_FileID'], ref['m_PathID']) == key, ('wrong object script reference', path_id)
    assert obj.get_raw_data() == raw, ('wrong serialized bytes', path_id)
    return obj.type_id


def test_anchored(model, author_slot, scratch, unity, *, game_object=False):
    from carra_import import expanded, materialize

    obj, key = (model.asset.objects[model.root_id], None) if game_object else source_object(model)
    other_id = 8_861_000_000_000_000_001
    inherited_id = other_id + 1
    assert other_id not in model.asset.objects and inherited_id not in model.asset.objects
    changed = edited_object(obj, 'verification-existing-object')
    inserted = edited_object(obj, 'verification-reuse-anchored')
    entries = [(obj.path_id, author_slot, changed, 'verification-existing-object'),
               (other_id, author_slot, inserted, 'verification-reuse-anchored')]
    if not game_object:
        marker = 'verification-reuse-script-only'
        entries.append((inherited_id, author_slot + 41, edited_object(obj, marker), marker))
    raw_patch = make_patch(model, [entry[:3] for entry in entries])
    with ZipFile(BytesIO(raw_patch)) as archive:
        meta = [(info, pid, slot) for info, (pid, slot, _, _) in zip(archive.infolist(), entries)]
        direct = materialize(archive, model.raw, meta, unity)

    patch_path = scratch / f'{model.name}-{author_slot}.carra2'
    patch_path.write_bytes(raw_patch)
    with expanded(patch_path, scratch, unity) as output, ZipFile(output) as archive:
        emitted = f'{patch_path.stem}/Installation/{model.relative.as_posix()}'
        expanded_data = archive.read(emitted)
    for raw in (direct, expanded_data):
        env = unity.load(raw)
        asset, = env.assets
        assert model.address in env.container
        assert len(asset.objects) == len(model.asset.objects) + len(entries) - 1
        assert len(asset.types) == len(model.asset.types) and len(asset.script_types) == len(model.asset.script_types)
        for path_id, _, payload, marker in entries:
            verify_object(asset, path_id, payload, marker, key, slot=obj.type_id)
    author_slots = '/'.join(str(slot) for slot in dict.fromkeys(entry[1] for entry in entries))
    kind = 'GameObject' if game_object else f'MonoBehaviour script {key[-1]}'
    print(f'PASS {model.name}: {kind}, materialize and expanded, author {author_slots} -> game slot {obj.type_id}, '
          f'asset types {len(model.asset.types)}')


def test_companion(model, donor, author_slot, scratch, unity, *, collision=False):
    from carra_import import expanded

    obj, key = source_object(donor, missing_in=model)
    (file_id,) = [i + 1 for i, external in enumerate(model.asset.externals)
                  if (external.path.casefold(), external.guid, external.type) == key[:3]]
    if collision:
        assert type_key(model.asset, model.asset.types[author_slot]) not in (None, key)
    else:
        assert author_slot >= len(model.asset.types)
    marker = 'verification-new-companion-script'
    payload = edited_object(obj, marker, script_file=file_id)
    new_id = 8_862_000_000_000_000_001
    assert new_id not in model.asset.objects
    patch_data = make_patch(model, [(new_id, author_slot, payload)])
    patch_name = f'cross-model-{author_slot}.carra2'
    model_member = 'bases/' + model.relative.as_posix()
    donor_member = 'bases/' + donor.relative.as_posix()
    empty_cache = scratch / 'empty-game-cache'
    empty_cache.mkdir(exist_ok=True)
    with patch.dict(os.environ, {'LIMBUS_RESOURCE_ROOT': str(empty_cache)}):
        for with_donor in (False, True) if not collision else (True,):
            package = scratch / f'cross-model-{author_slot}-{with_donor}.zip'
            with ZipFile(package, 'w') as outer:
                outer.writestr(patch_name, patch_data)
                outer.writestr(model_member, model.raw)
                if with_donor:
                    outer.writestr(donor_member, donor.raw)
            source = {}
            try:
                with expanded(package, scratch, unity, source_members=source) as output, ZipFile(output) as archive:
                    member = f'{Path(patch_name).stem}/Installation/{model.relative.as_posix()}'
                    raw = archive.read(member)
                    if with_donor:
                        assert source[member.casefold()] == patch_name and archive.read(donor_member) == donor.raw
            except ValueError as exc:
                if with_donor or '缺少匹配的脚本定义' not in str(exc):
                    raise
                continue
            assert with_donor, 'A missing script was accepted without the companion and with an empty game cache'
            env = unity.load(raw)
            asset, = env.assets
            assert model.address in env.container
            assert len(asset.objects) == len(model.asset.objects) + 1
            assert len(asset.types) == len(model.asset.types) + 1
            assert len(asset.script_types) == len(model.asset.script_types) + 1
            slot = verify_object(asset, new_id, payload, marker, key, slot=len(model.asset.types))
            if collision:
                assert type_key(asset, asset.types[author_slot]) == type_key(model.asset, model.asset.types[author_slot])
                existing = next(obj for obj in model.asset.objects.values() if obj.type_id == author_slot)
                assert asset.objects[existing.path_id].get_raw_data() == existing.get_raw_data()
            print(f'PASS {model.name} <- {donor.name}: companion provides script {key[-1]}, '
                  f'author {author_slot} -> game slot {slot}, collision={collision}')


def main():
    if not __debug__:
        raise RuntimeError('Verification requires Python assertions to be enabled')
    app_data = Path.home() / 'AppData'
    roaming = Path(os.environ.get('APPDATA') or app_data / 'Roaming')
    local = Path(os.environ.get('LOCALAPPDATA') or app_data / 'Local')
    launcher_data = Path('FaustLauncher/MOS_data')
    player = roaming / launcher_data
    if not (player / 'resource-cache/resource-index.json').is_file():
        player = app_data / 'Roaming' / launcher_data
    player = Path(os.environ.get('FAUST_MOS_DATA_ROOT') or player)
    index_dir = Path(os.environ.get('LIMBUS_RESOURCE_INDEX') or player / 'resource-cache')
    unity_cache = Path('LocalLow/Unity/ProjectMoon_LimbusCompany')
    located_cache = local.parent / unity_cache
    if not located_cache.is_dir():
        located_cache = app_data / unity_cache
    default_cache = Path(os.environ.get('LIMBUS_RESOURCE_ROOT') or located_cache)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=default_cache)
    parser.add_argument('--index', type=Path, default=index_dir / 'resource-index.json')
    parser.add_argument('--source', type=Path, default=ROOT / 'MirrorOfSkin/Workbench')
    parser.add_argument('--scratch', type=Path, help='existing directory for temporary verification files')
    args = parser.parse_args()
    cache = args.cache.resolve(strict=True)
    index_path = args.index.resolve(strict=True)
    index = json.loads(index_path.read_bytes())
    if Path(index['resource_root']).resolve() != cache:
        raise ValueError('The chosen index was generated for a different game cache')
    sys.path.insert(0, str(args.source.resolve(strict=True)))
    sys.dont_write_bytecode = True
    from UnityPy import config
    import UnityPy
    import _module_paths
    from model_workspace import import_workspace

    config.FALLBACK_UNITY_VERSION = '6000.3.0f1'
    models = [load_model(cache, index, name, UnityPy) for name in GAME_MODELS]
    assert models[0].relative != models[1].relative
    for model in models:
        print(f'Model {model.name}: {model.relative.as_posix()}, SHA-256 {sha256(model.raw).hexdigest()}')

    failures = 0
    with TemporaryDirectory(prefix='carra-generality-', dir=args.scratch) as directory:
        scratch = Path(directory)
        resources = {'FAUST_MOS_DATA_ROOT': str(scratch / 'profile'), 'LIMBUS_RESOURCE_ROOT': str(cache),
                     'LIMBUS_RESOURCE_INDEX': str(index_path.parent)}
        collision_slot = source_object(models[0])[0].type_id
        cases = [(test_anchored, (models[0], 701), {}), (test_anchored, (models[1], 1729), {}),
                 (test_anchored, (models[1], 406), {'game_object': True}),
                 (test_companion, (models[0], models[1], 947), {}),
                 (test_companion, (models[1], models[0], 1553), {}),
                 (test_companion, (models[0], models[1], collision_slot), {'collision': True})]
        with patch.dict(os.environ, resources), import_workspace(scratch):
            for test, parameters, options in cases:
                try:
                    test(*parameters, scratch, UnityPy, **options)
                except (AssertionError, ValueError, RuntimeError):
                    failures += 1
                    traceback.print_exc()

    for model in models:
        assert sha256((cache / model.relative).read_bytes()).digest() == sha256(model.raw).digest(), model.name
    print(f'{len(cases) - failures}/{len(cases)} cases passed; both original bundle hashes unchanged')
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
