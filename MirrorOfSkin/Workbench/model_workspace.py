"""Keep large, transient model files on the same volume as the active add-on."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from tempfile import TemporaryDirectory

_addon = ContextVar("model_import_addon", default=None)
CACHE_DIR = "appearance-cache"
LEGACY_CACHE_DIR = "外观资源缓存"


@contextmanager
def import_workspace(addon):
    token = _addon.set(Path(addon).resolve(strict=True))
    try:
        yield
    finally:
        _addon.reset(token)


def model_tempdir(*, prefix=".mos-model-"):
    return TemporaryDirectory(prefix=prefix, dir=_addon.get())


def carra_base_path(profile, revision, first, second):
    legacy = Path(profile) / "Assets/CarraBases" / revision / first / second / "__data"
    addon = _addon.get()
    if addon is None:
        return legacy, legacy
    cache = addon / CACHE_DIR
    old = addon / LEGACY_CACHE_DIR
    if old.is_dir() and not cache.exists():
        try:
            old.rename(cache)
        except OSError:
            pass
    dest = cache / "Carra2" / revision / first / second / "__data"
    if dest.resolve() != dest:
        raise ValueError("Carra2 缓存目录不能指向其他位置")
    return dest, legacy
