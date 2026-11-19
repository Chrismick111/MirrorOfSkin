"""Install missing bundled animation timings while retaining discovered and updated files."""
import os
import re
import tempfile
import zipfile
from pathlib import Path


def restore(root):
    runtime = Path(root) / 'Assets/runtime'
    folder = runtime / 'story_native'
    folder.mkdir(exist_ok=True)
    with zipfile.ZipFile(runtime / 'story_defaults.zip') as source:
        for name in source.namelist():
            if not re.fullmatch(r'story_[A-Za-z0-9_]+\.bin', name):
                raise ValueError('Invalid bundled appearance: ' + name)
            destination = folder / name
            if destination.is_file():
                continue
            data = source.read(name)
            fd, tmp = tempfile.mkstemp(dir=folder, suffix='.tmp')
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data)
                # A local scan can supply a newer file. Callers hold the
                # same workbench lock used for publishing discovered assets.
                os.replace(tmp, destination)
            finally:
                Path(tmp).unlink(missing_ok=True)
