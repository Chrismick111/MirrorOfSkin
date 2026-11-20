# -*- coding: utf-8 -*-
"""Open the workbench in an independent pywebview window."""
import argparse
import pathlib
import sys


def _alive(pid):
    try:
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    except Exception:
        return False


def _focus_existing():
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "镜像幻化")
        if hwnd:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False


def _read_lock(path):
    try:
        import json
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _acquire_lock(path):
    import json
    import os

    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"pid": os.getpid()}).encode("utf-8"))
            os.close(fd)
            return True
        except FileExistsError:
            info = _read_lock(path)
            if _alive(info.get("pid", 0)):
                _focus_existing()
                return False
            try:
                path.unlink()
            except OSError:
                pass
        except OSError:
            return False
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--addon", required=True)
    args = parser.parse_args()
    import webview

    addon = pathlib.Path(args.addon).resolve()
    launcher = addon.parent.parent
    lock = addon / "Workbench/webview-window.json"
    if not _acquire_lock(lock):
        return 0
    width, height, x, y = 0, 0, 0, 0
    try:
        screens = list(getattr(webview, "screens", []) or [])
        if screens:
            screen = screens[0]
            sw, sh = int(screen.width), int(screen.height)
            width = max(1100, min(1400, int(sw * 0.82)))
            height = max(760, min(1200, sh - 40))
            x = int(getattr(screen, "x", 0)) + max(0, (sw - width) // 2)
            y = int(getattr(screen, "y", 0)) + max(0, (sh - height) // 2)
    except Exception:
        pass
    icon = launcher / "assets/images/icon/icon.ico"
    webview.create_window(
        "镜像幻化",
        args.url,
        width=width or 1280,
        height=height or 900,
        x=x or None,
        y=y or None,
        min_size=(1000, 650),
        background_color="#17191d",
        text_select=True,
    )
    import os
    try:
        webview.start(gui="edgechromium", icon=str(icon) if icon.is_file() else None)
    finally:
        try:
            if _read_lock(lock).get("pid") == os.getpid():
                lock.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
