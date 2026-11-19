"""Enumerate author-defined FMOD event strings using the installed FMOD Studio API."""
import ctypes
from pathlib import Path


def event_strings(game_data):
    api = ctypes.CDLL(str(game_data / 'Plugins/x86_64/fmodstudio.dll'))
    system, core, bank = (ctypes.c_void_p() for _ in range(3))
    def check(status):
        if status:
            raise RuntimeError(f'FMOD returned error {status}')
    # FMOD validates major/minor API compatibility against the shipped binary.
    check(api.FMOD_Studio_System_Create(ctypes.byref(system), 0x00020200))
    try:
        check(api.FMOD_Studio_System_GetCoreSystem(system, ctypes.byref(core)))
        check(api.FMOD5_System_SetOutput(core, 2))  # NOSOUND
        check(api.FMOD_Studio_System_Initialize(system, 32, 1, 0, None))
        path = game_data / 'StreamingAssets/Assets/Sound/FMODBuilds/Desktop/Master.strings.bank'
        check(api.FMOD_Studio_System_LoadBankFile(system, bytes(str(path),'utf8'), 0, ctypes.byref(bank)))
        n, used = ctypes.c_int(), ctypes.c_int()
        check(api.FMOD_Studio_Bank_GetStringCount(bank, ctypes.byref(n)))
        guid = (ctypes.c_int32 * 4)()
        buffer = ctypes.create_string_buffer(8192)
        paths = {}
        for i in range(n.value):
            check(api.FMOD_Studio_Bank_GetStringInfo(bank, i, ctypes.byref(guid), buffer,
                  len(buffer), ctypes.byref(used)))
            path = buffer.value.decode('utf8')
            if path.startswith('event:/'):
                paths[tuple(guid)] = path
        return paths
    finally:
        check(api.FMOD_Studio_System_Release(system))
