"""Fail-closed release checks. Standard library only; never opens a process."""
import hashlib
import json
import pathlib
import struct
import ctypes


class CompatibilityError(RuntimeError):
    pass


def claim_process(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    ctypes.set_last_error(0)
    handle = kernel.CreateMutexW(None, False, 'Local\\FaustSinnersNativeRelease_' + str(pid))
    error = ctypes.get_last_error()
    if not handle:
        raise CompatibilityError('无法建立单实例保护，已停止加载')
    if error == 183:
        kernel.CloseHandle(handle)
        raise CompatibilityError('已有随机人格Native宿主正在使用此游戏，请勿重复启用')
    return kernel, handle


def release_process(claim):
    if claim:
        claim[0].CloseHandle(claim[1])


def digest(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify_files(root, expected, label):
    root = pathlib.Path(root).resolve()
    if not expected:
        raise CompatibilityError(label + '校验清单为空，已停止加载')
    for name, wanted in expected.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise CompatibilityError(label + '文件缺失或路径无效：' + name)
        if digest(path).lower() != wanted.lower():
            raise CompatibilityError(label + '版本或文件不匹配：' + name + '；已停止加载，请使用适配版本')


def pe_machine(path):
    with pathlib.Path(path).open('rb') as f:
        if f.read(2) != b'MZ':
            raise CompatibilityError('无效的Windows程序文件')
        f.seek(0x3c)
        offset = struct.unpack('<I', f.read(4))[0]
        f.seek(offset)
        if f.read(4) != b'PE\0\0':
            raise CompatibilityError('无效的PE文件')
        return struct.unpack('<H', f.read(2))[0]


def validate(root, game_dir, modules, dll_name, pointer_size=None, allow_existing=False):
    if (struct.calcsize('P') if pointer_size is None else pointer_size) != 8:
        raise CompatibilityError('需要64位FaustLauncher，已停止加载')
    root = pathlib.Path(root)
    try:
        manifest = json.loads((root / 'compatibility.json').read_text(encoding='utf-8'))
        if manifest['schema'] != 1 or manifest['dll'] != dll_name:
            raise CompatibilityError('兼容性清单与插件版本不一致')
        if any(name.lower().startswith('sinnersnative') and name.lower().endswith('.dll') for name in modules) and not allow_existing:
            raise CompatibilityError('游戏内已有随机人格Native模块，请退出游戏后重新启动，禁止叠加加载')
        addon = json.loads((root / 'addon_info.json').read_text(encoding='utf-8-sig'))
        if addon.get('version') != manifest['version']:
            raise CompatibilityError('插件版本与兼容性清单不一致')
        stable_files = {name: digest for name, digest in manifest['package_files'].items() if name != 'addon_info.json'}
        verify_files(root, stable_files, '插件')
        verify_files(game_dir, manifest['game_files'], '游戏')
        for path in (root / dll_name, pathlib.Path(game_dir) / 'GameAssembly.dll'):
            if pe_machine(path) != 0x8664:
                raise CompatibilityError('需要AMD64/x64程序，已停止加载')
        for name in manifest['system_dlls']:
            if not (name.lower() in ('kernel32.dll', 'user32.dll') or
                    name.lower().startswith('api-ms-win-crt-') and name.lower().endswith('.dll')) or '/' in name or '\\' in name:
                raise CompatibilityError('系统依赖清单无效')
            try:
                ctypes.WinDLL(name, winmode=0x800)  # System32 only; no addon search paths.
            except OSError as exc:
                raise CompatibilityError('缺少Windows系统运行库，已停止加载：' + name) from exc
        return manifest
    except CompatibilityError:
        raise
    except (OSError, ValueError, KeyError, TypeError, struct.error) as exc:
        raise CompatibilityError('兼容性检查未通过，已停止加载：' + str(exc)) from exc


def validate_aliases(result, names):
    mapping = result.get('mapping', {})
    missing = [name for name in names if not isinstance(mapping.get('il2cpp_' + name), str) or not mapping['il2cpp_' + name]]
    if missing:
        raise CompatibilityError('启动器未提供完整接口映射，已停止加载：' + ', '.join(missing))
    for name in names:
        try:
            value = mapping['il2cpp_' + name].encode('ascii')
        except UnicodeError as exc:
            raise CompatibilityError('接口映射包含无效字符') from exc
        if not 0 < len(value) < 64 or b'\0' in value:
            raise CompatibilityError('接口映射长度或内容无效')
