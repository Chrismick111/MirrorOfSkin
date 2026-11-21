"""Put the workbench module groups on sys.path for flat imports."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
for _name in ("core", "pool", "scan", "fx", "tools"):
    _path = ROOT / _name
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
