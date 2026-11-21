"""Track each launcher and its optional game by kernel process handles."""
import ctypes
import os
import threading


class Process:
    def __init__(self, pid):
        if type(pid) is not int or not 0 < pid <= 0xffffffff or os.name != 'nt':
            raise ValueError('无法验证会话进程')
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        self.kernel.OpenProcess.restype = ctypes.c_void_p
        self.kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.kernel.WaitForSingleObject.restype = ctypes.c_ulong
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.pid = pid
        self.handle = self.kernel.OpenProcess(0x100000, False, pid)
        if not self.handle or self.exited():
            self.close()
            raise ValueError('会话进程已退出或无法验证')

    def exited(self, timeout_ms=0):
        return self.kernel.WaitForSingleObject(self.handle, timeout_ms) != 258

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class Lifetime:
    def __init__(self):
        self.lock = threading.Lock()
        self.hosts = {}
        self.standalone = False
        self.closing = False
        self.closed = threading.Event()

    def register(self, pid, game_pid=None, startup_pid=None):
        with self.lock:
            if self.closing:
                raise ValueError('工作台正在退出，请重新打开')
            if startup_pid is not None:
                # Check under the same lock as release: late wrapper requests
                # cannot resurrect a host after it cancels its startup wrapper.
                wrapper = Process(startup_pid)
                wrapper.close()
            if pid is None and game_pid is None:
                self.standalone = True
                return
            previous = self.hosts.get(pid)
            if previous and previous[0].exited():
                self._remove(pid)
                previous = None
            host, game = previous or (Process(pid), None)
            try:
                if game_pid is not None and (not game or game.pid != game_pid or game.exited()):
                    new_game = Process(game_pid)
                    if game:
                        game.close()
                    game = new_game
                self.hosts[pid] = (host, game)
            except BaseException:
                if not previous:
                    host.close()
                raise

    def _remove(self, pid):
        for process in self.hosts.pop(pid, ()):
            if process:
                process.close()

    def release(self, pid):
        with self.lock:
            self._remove(pid)

    def begin_shutdown(self):
        with self.lock:
            self.closing = True

    def unowned(self):
        with self.lock:
            for pid, processes in list(self.hosts.items()):
                if any(proc and proc.exited() for proc in processes):
                    self._remove(pid)
            if self.standalone or self.hosts:
                return False
            self.closing = True
            return True

    def watch(self, server):
        def run():
            while not self.closed.wait(.2):
                if self.unowned():
                    server.shutdown()
                    return
        threading.Thread(target=run, daemon=True).start()

    def close(self):
        with self.lock:
            self.closed.set()
            self.closing = True
            for pid in list(self.hosts):
                self._remove(pid)

def contain_descendants():
    """Close this helper's entire process tree when Windows releases its last handle.

    Call only in a dedicated worker interpreter, never in the game or launcher.
    The process itself owns the sole, noninheritable job handle.
    """
    if os.name != 'nt':
        return
    from ctypes import wintypes as w

    class BasicLimits(ctypes.Structure):
        _fields_ = [('user_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                    ('flags', w.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                    ('active', w.DWORD), ('affinity', ctypes.c_size_t),
                    ('priority', w.DWORD), ('scheduling', w.DWORD)]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [('basic', BasicLimits), ('io', ctypes.c_ulonglong * 6),
                    ('memory', ctypes.c_size_t * 4)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [w.LPVOID, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return False
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not (kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
            and kernel.AssignProcessToJobObject(job, w.HANDLE(-1))):
        kernel.CloseHandle(job)
        return False  # A restrictive outer job may disallow nested jobs.
    # Intentionally keep this kernel handle open until interpreter exit.
    return True


def exit_with_owner(pid):
    """A detached helper also exits after an unexpected owner process death."""
    owner = Process(pid)

    def wait():
        owner.exited(0xffffffff)
        os._exit(1)

    threading.Thread(target=wait, daemon=True).start()
