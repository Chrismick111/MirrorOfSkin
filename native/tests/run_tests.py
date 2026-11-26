"""Build and run the self-contained native tests on Windows.

The chapter and imported-voice integration tests need real data and are run
separately; this runner never reads or changes the user's plugin data.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zig', required=True, type=Path)
    parser.add_argument('--minhook', required=True, type=Path)
    args = parser.parse_args()
    native = Path(__file__).resolve().parent.parent
    tests = native / 'tests'
    includes = ['-I', str(args.minhook / 'include'), '-I', str(native), '-I', str(tests)]
    for directory in sorted(native.iterdir()):
        if directory.is_dir():
            includes += ['-I', str(directory)]
    shared = [native / 'unity/wic_rgba.c'] + [args.minhook / 'src' / name for name in
        ('buffer.c', 'hook.c', 'trampoline.c', 'hde/hde64.c')]
    failures = []
    skipped = {'test_hiro_voice.c', 'test_chapter_auto.c'}
    with tempfile.TemporaryDirectory(prefix='mos-native-tests-') as tmp:
        output = Path(tmp)
        policies = native.parent / 'MirrorOfSkin' / 'Assets' / 'SkinPolicies'
        test_policies = output / 'Assets' / 'SkinPolicies'
        shutil.copytree(policies, test_policies)
        generic = (test_policies / 'BRolandBaseAppearance.cfg').read_text(encoding='ascii').splitlines()
        generic[2] = 'Assets/Prefab/OtherModel.prefab'
        generic[4:6] = ['OtherModelAppearance', '12345_ExampleAppearance']
        generic[6:9] = ['0' * 29 + '2' + '0' * 98, '0' * 128, '0' * 29 + '1' + '0' * 98]
        generic[9] = 'R|8,25'
        (test_policies / 'OtherModelAppearance.cfg').write_bytes(('\n'.join(generic) + '\n').encode('ascii'))
        profile = output / 'profile'
        data = profile / 'FaustLauncher' / 'MOS_data'
        data.mkdir(parents=True)
        env = dict(os.environ, APPDATA=str(profile), FAUST_MOS_DATA_ROOT=str(data))
        for test in sorted(tests.glob('test_*.c')):
            if test.name in skipped:
                continue
            text = test.read_text(encoding='utf8')
            full = any(name in text for name in
                       ('"sinners_native.c"', '"test_camera_lifecycle.c"', '"test_voice_dispatch.c"'))
            exe = output / (test.stem + '.exe')
            cmd = [str(args.zig), 'cc', '-target', 'x86_64-windows-gnu', '-mcpu=baseline', '-O1',
                   *includes, str(test), *(str(p) for p in shared if full), '-o', str(exe),
                   '-luser32', '-lole32', '-luuid', '-lbcrypt']
            try:
                build = subprocess.run(cmd, capture_output=True, text=True, errors='replace', timeout=120, env=env)
                if build.returncode:
                    failures.append((test.name, '编译', build.stderr))
                    continue
                result = subprocess.run([str(exe)], capture_output=True, text=True, errors='replace',
                                        timeout=30, env=env, cwd=output)
                if result.returncode:
                    failures.append((test.name, '执行', result.stdout + result.stderr))
                else:
                    print('PASS', test.name, flush=True)
            except (OSError, subprocess.TimeoutExpired) as exc:
                failures.append((test.name, '运行', str(exc)))
        for name, stage, detail in failures:
            print(f'FAIL {name} ({stage})\n{detail}', file=sys.stderr)
        print(f'跳过需要真实资源的集成测试: {", ".join(sorted(skipped))}')
        print(f'失败: {len(failures)}')
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
