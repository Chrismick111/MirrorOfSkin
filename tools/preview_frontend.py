"""Frontend-only preview server for the Mirror of Skin workbench UI.

Serves the real Workbench UI against a read-only snapshot of an installed
add-on, with all API calls answered locally. Nothing is imported or saved, so
it is safe to use for style/interaction checks while the launcher is closed.

Usage:
    python tools/preview_frontend.py --addon D:\\FaustLauncher\\addons\\faust_inst_uplabl34
    python tools/preview_frontend.py --no-browser
"""

import argparse
import json
import mimetypes
import pathlib
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
UI = ROOT / "MirrorOfSkin/Workbench/ui/index.html"
TRANSPARENT_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def load_snapshot(addon):
    """Build the same payload the real workbench sends to the UI."""
    addon = pathlib.Path(addon).resolve()
    for folder in ("Workbench", "Workbench/core", "Workbench/pool",
                   "Workbench/scan", "Workbench/fx", "Workbench/tools"):
        path = addon / folder
        if path.is_dir():
            sys.path.insert(0, str(path))
    import _module_paths  # noqa: F401
    import workbench

    store = workbench.Store(addon)
    data = store.data()
    data["tutorial"] = False
    data["launcherBackground"] = {}
    data["warmup"] = {}
    return data, store


class Handler(BaseHTTPRequestHandler):
    data = {}
    store = None

    def log_message(self, fmt, *args):
        return

    def _bytes(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf8")
        self._bytes(body, "application/json; charset=utf-8", status)

    def _route(self):
        return urlparse(self.path).path.removeprefix("/api/")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._bytes(UI.read_bytes(), "text/html; charset=utf-8")
            return
        if not path.startswith("/api/"):
            self._bytes(b"not found", "text/plain; charset=utf-8", 404)
            return

        route = self._route()
        if route == "data":
            self._json(self.data)
        elif route == "discovered":
            self._json({
                "available": True,
                "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "bundles_total": 0,
                "bundles_rescanned": 0,
                "pool_entries": len(self.data.get("catalog", [])),
                "new_prefabs": 0,
                "units": [],
                "scan": {"running": False},
            })
        elif route == "local-skin-import-status":
            self._json({"stage": "idle", "rows": [], "errors": [], "files": []})
        elif route == "package-folders":
            self._json({"removed": [], "blocked": []})
        elif route == "portrait-progress":
            self._json({"stage": "idle", "done": 0, "total": 0})
        elif route == "events":
            self._json([{"time": time.strftime("%H:%M:%S"),
                         "message": "前端预览模式"}])
        elif route == "schemes":
            self._json([])
        elif route.startswith("portrait/"):
            identity = unquote(route[len("portrait/"):])
            source = None
            try:
                source = self.store.portrait(identity)
            except Exception:
                source = None
            if source and pathlib.Path(source).is_file():
                raw = pathlib.Path(source).read_bytes()
                mime = mimetypes.guess_type(str(source))[0] or "image/png"
                self._bytes(raw, mime)
            else:
                self._bytes(TRANSPARENT_PNG, "image/png")
        else:
            self._json({})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length:
            self.rfile.read(length)
        route = self._route()
        if route == "ruleset-save":
            self._json({"revision": self.data.get("ruleRevision", "")})
        elif route in ("portrait-save", "portrait-reset"):
            self._json({"saved": True, "portrait_url": None})
        elif route == "appearance-blood":
            self._json({"blood_visible_ids": self.data.get("blood_visible_ids", [])})
        else:
            self._json({})


def main():
    parser = argparse.ArgumentParser(description="Mirror of Skin 前端预览服务器")
    parser.add_argument("--addon", default=str(ROOT / "MirrorOfSkin"),
                        help="已安装插件目录（默认用仓库源码）")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true",
                        help="不自动打开浏览器")
    args = parser.parse_args()

    data, store = load_snapshot(args.addon)
    Handler.data = data
    Handler.store = store
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print("预览地址:", url)
    print("目录:", args.addon)
    print("按 Ctrl+C 停止")
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
