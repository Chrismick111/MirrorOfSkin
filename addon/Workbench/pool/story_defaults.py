"""Install missing bundled animation timings while retaining discovered and updated files."""
import os
import re
import tempfile
import tarfile
from pathlib import Path


def restore(root):
    root = Path(root)
    runtime = root / 'Assets/runtime'
    with tarfile.open(runtime/'motion-defaults.tar.xz', mode='r|xz') as source:
        for member in source:
            if not member.isfile() or not re.fullmatch(
                    r'(story_native/story_[A-Za-z0-9_]+|archive-times-candidate/[0-9a-f]{16})\.bin',member.name):
                raise ValueError('Invalid bundled animation: '+member.name)
            destination = (runtime if member.name.startswith('story_native/') else root)/member.name
            if destination.is_file():
                continue
            destination.parent.mkdir(exist_ok=True)
            data = source.extractfile(member).read()
            fd, tmp = tempfile.mkstemp(dir=destination.parent, suffix='.tmp')
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data)
                # A local scan can supply a newer file. Callers hold the
                # same workbench lock used for publishing discovered assets.
                os.replace(tmp, destination)
            finally:
                Path(tmp).unlink(missing_ok=True)
