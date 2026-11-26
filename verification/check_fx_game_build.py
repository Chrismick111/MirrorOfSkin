"""Exercise the installed FX worker with a real cached appearance, in a fresh profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def run(addon, game, scheme, index):
    with tempfile.TemporaryDirectory() as scratch:
        data = Path(scratch) / 'profile'
        os.environ['APPDATA'] = str(Path(scratch) / 'AppData')
        os.environ['FAUST_MOS_DATA_ROOT'] = str(data)
        if index:
            local_index = Path(scratch) / 'index'
            local_index.mkdir()
            shutil.copyfile(index / 'resource-index.json', local_index / 'resource-index.json')
            os.environ['LIMBUS_RESOURCE_INDEX'] = str(local_index)
        catalog = Path('Assets/runtime/all_sinners_pools.json')
        (data / catalog.parent).mkdir(parents=True)
        shutil.copyfile(addon / catalog, data / catalog)
        sys.path.insert(0, str(addon / 'Workbench'))
        import _module_paths
        import effect_schemes, fx_activation, fx_handoff, fx_plan_binary

        plan = json.loads(scheme.read_text(encoding='utf-8-sig'))
        effect_schemes.save(data, scheme.stem, plan)
        fx_activation.select(data, scheme.stem, True)
        if not fx_handoff.prepare(addon, game, print, python_exe=sys.executable):
            raise RuntimeError('FX worker did not prepare the scheme')
        raw = (data / 'fx-active.bin').read_bytes()
        magic, version, count = fx_plan_binary.HEADER.unpack_from(raw)
        with (game / 'GameAssembly.dll').open('rb') as stream:
            digest = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        first = fx_plan_binary.FIXED.unpack_from(raw, fx_plan_binary.HEADER.size)
        assert (magic, version, count) == (b'FXP2', 2, len(plan['effects']))
        assert first[6] == digest.digest()
        print(f'FXP2 verified: {count} operation(s), {len(raw)} bytes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('addon', 'game', 'scheme'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--index', type=Path)
    args = parser.parse_args()
    run(args.addon.resolve(), args.game.resolve(), args.scheme, args.index)
