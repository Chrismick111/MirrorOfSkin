import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
CATALOG = 'Assets/runtime/all_sinners_pools.json'


def png(pixel):
    def chunk(kind, content):
        return struct.pack('>I', len(content)) + kind + content + struct.pack('>I', zlib.crc32(kind + content))

    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>II5B', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0' + pixel)) + chunk(b'IEND', b''))

DRIVER = r'''
from io import BytesIO
from pathlib import Path
import json, runpy, sys

class Connection:
    def __init__(self, wire):
        self.input = BytesIO(wire)
        self.output = BytesIO()

    def makefile(self, mode, size):
        assert mode == 'rb', mode
        return self.input

    def sendall(self, content):
        self.output.write(content)

def request(handler, method, route, body=b''):
    wire = f'{method} /api/{route} HTTP/1.1\r\nHost: localhost\r\nContent-Length: {len(body)}\r\n\r\n'
    connection = Connection(wire.encode('ascii') + body)
    handler(connection, ('127.0.0.1', 0), None)
    headers, content = connection.output.getvalue().split(b'\r\n\r\n', 1)
    assert headers.startswith(b'HTTP/1.0 200 '), headers
    return content

models = Path(sys.argv[2]) / 'Assets/ImportedSkins'

def reject_model_access(event, args):
    if event in ('open', 'os.scandir') and isinstance(args[0], str):
        path = Path(args[0])
        if (path == models or models in path.parents) and (event == 'os.scandir' or path.suffix == '.bundle'):
            raise AssertionError('Unexpected preview access to ' + str(path))

sys.addaudithook(reject_model_access)
preview = runpy.run_path(sys.argv[1])
data, store = preview['load_snapshot'](sys.argv[2])
handler = preview['Handler']
handler.data, handler.store = data, store
snapshot = json.loads(request(handler, 'GET', 'data'))
portrait = request(handler, 'GET', 'portrait/10101').hex()
saved = json.loads(request(handler, 'POST', 'ruleset-save', b'{"entries": []}'))
print(json.dumps([snapshot, portrait, saved], ensure_ascii=True))
'''


def snapshot(root):
    values = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        base = Path(folder)
        for name in dirs[:]:
            path = base / name
            attrs = path.lstat()
            if getattr(attrs, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT or path.is_symlink():
                dirs.remove(name)
                values[path.relative_to(root)] = ('link',)
            else:
                values[path.relative_to(root)] = ('directory',)
        for name in files:
            path = base / name
            values[path.relative_to(root)] = (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).digest())
    return values


class FrontendPreviewTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.addon = self.root / 'installed-addon'
        self.profile = self.root / 'MOS_data'
        for relative in ('Workbench', 'Workbench/core', 'Workbench/pool', 'Workbench/scan',
                         'Workbench/fx', 'Workbench/tools'):
            target = self.addon / relative
            target.mkdir(parents=True, exist_ok=True)
            for source in (ROOT / 'MirrorOfSkin' / relative).glob('*.py'):
                shutil.copyfile(source, target / source.name)
        self.write(self.addon, 'addon_info.json', {'version': 'test-fixture'})
        self.write(self.addon, 'compatibility.json', {'protocol': 17})
        self.write(self.addon, CATALOG, self.catalog('Installed default'))
        self.write(self.addon, '演出编排.json', {'schema': 1, 'formations': {}})
        self.write(self.addon, 'Assets/ImportedSkins/model-fixture.bundle', b'model bytes')
        self.bundled_portrait = png(b'\x24\x31\x57')
        self.write(self.addon, 'Workbench/data/bundled_portraits/10101.png', self.bundled_portrait)

    def write(self, base, relative, value):
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        content = value if isinstance(value, bytes) else json.dumps(value).encode('utf8')
        path.write_bytes(content)

    def catalog(self, name):
        return {'101': {'entries': [{'identity_id': '10101', 'name': name, 'sinner': '101'}]}}

    def preview(self, expected_portrait):
        before = snapshot(self.root)
        env = dict(os.environ, FAUST_MOS_DATA_ROOT=str(self.profile), PYTHONUTF8='1')
        env.pop('PYTHONDONTWRITEBYTECODE', None)
        result = subprocess.run([sys.executable, '-c', DRIVER, str(ROOT / 'tools/preview_frontend.py'), str(self.addon)],
                                env=env, capture_output=True, text=True, encoding='utf8', timeout=30)
        after = snapshot(self.root)
        changed = [str(key) for key in before.keys() | after.keys() if before.get(key) != after.get(key)]
        if changed:
            self.fail('Preview changed files: ' + ', '.join(sorted(changed)[:20]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data, image, saved = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(bytes.fromhex(image), expected_portrait)
        self.assertEqual(saved['revision'], data['ruleRevision'])
        self.assertEqual(data['version'], 'test-fixture')
        self.assertFalse(data['tutorial'])
        return data

    def test_live_player_snapshot_does_not_migrate_or_write(self):
        self.write(self.profile, CATALOG, self.catalog('Player appearance name'))
        self.write(self.profile, '随机设置.json', {'enabled': False, 'characters': {}})
        self.write(self.profile, 'stage_director.json', {'legacy': True})
        user_portrait = png(b'\x86\x72\x33')
        portrait_id = hashlib.sha256(b'10101').hexdigest()
        self.write(self.profile, f'Workbench/user_portraits/{portrait_id}.png', user_portrait)
        data = self.preview(user_portrait)
        self.assertEqual(data['catalog'][0]['name'], 'Player appearance name')
        self.assertFalse(data['settings']['config']['enabled'])

    def test_bundled_snapshot_does_not_create_a_player_profile(self):
        data = self.preview(self.bundled_portrait)
        self.assertEqual(data['catalog'][0]['name'], 'Installed default')
        self.assertFalse(self.profile.exists())


if __name__ == '__main__':
    unittest.main()
