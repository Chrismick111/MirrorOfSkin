import hashlib, io, json, pathlib, tempfile, unittest, zipfile
import portrait_download as p
from github_update import UpdateError

PNG = b'\x89PNG\r\n\x1a\n' + b'pinned-portrait'


def archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buffer.getvalue()


def write_source(root, blob, name='portrait_source.json', size=None, digest=None):
    source = {
        'schema': 1,
        'url': 'https://example.invalid/' + name,
        'sha256': digest or hashlib.sha256(blob).hexdigest(),
    }
    if size is not None:
        source['size'] = size
    (root / 'Workbench' / name).write_text(json.dumps(source), encoding='utf8')


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent)
        self.root = pathlib.Path(self.tmp.name) / 'addon'
        (self.root / 'Workbench').mkdir(parents=True)
        (self.root / 'addon_info.json').write_text('{"version":"0.63.2"}', encoding='utf8')
        self.original = p._fetch_direct

    def tearDown(self):
        p._fetch_direct = self.original
        self.tmp.cleanup()

    def test_download_is_independent_of_core_version(self):
        name = 'Workbench/portraits/' + 'a' * 24 + '.png'
        blob = archive({name: PNG})
        write_source(self.root, blob)
        p._fetch_direct = lambda url, limit: blob
        result = p.download(self.root)
        self.assertEqual(result['count'], 1)
        self.assertEqual((self.root / name).read_bytes(), PNG)

    def test_local_override_is_preferred(self):
        name = 'Workbench/portraits/' + 'b' * 24 + '.png'
        blob = archive({name: PNG})
        write_source(self.root, blob, name='portrait_source.json', digest='0' * 64)
        write_source(self.root, blob, name='portrait_source.local.json')
        p._fetch_direct = lambda url, limit: blob
        self.assertEqual(p.download(self.root)['count'], 1)

    def test_sha256_mismatch(self):
        blob = archive({'Workbench/portraits/' + 'c' * 24 + '.png': PNG})
        write_source(self.root, blob, digest='0' * 64)
        p._fetch_direct = lambda url, limit: blob
        with self.assertRaisesRegex(UpdateError, 'SHA-256'):
            p.download(self.root)

    def test_manifest_hashes_are_enforced_when_present(self):
        name = 'Workbench/portraits/' + 'd' * 24 + '.png'
        blob = archive({name: PNG})
        write_source(self.root, blob)
        (self.root / 'Workbench/portrait_manifest.json').write_text(
            json.dumps({'10101': {'file': name.rsplit('/', 1)[-1]}}), encoding='utf8')
        (self.root / 'Workbench/portrait_hashes.json').write_text(
            json.dumps({name: '0' * 64}), encoding='utf8')
        p._fetch_direct = lambda url, limit: blob
        with self.assertRaisesRegex(UpdateError, '校验清单'):
            p.download(self.root)

    def test_package_hash_mismatch_is_rejected(self):
        name = 'Workbench/portraits/' + 'e' * 24 + '.png'
        blob = archive({name: PNG})
        write_source(self.root, blob)
        (self.root / 'compatibility.json').write_text(
            json.dumps({'package_files': {name: '0' * 64}}), encoding='utf8')
        p._fetch_direct = lambda url, limit: blob
        with self.assertRaisesRegex(UpdateError, '当前插件校验清单'):
            p.download(self.root)

    def test_missing_source(self):
        with self.assertRaisesRegex(UpdateError, '缺少头像包直链配置'):
            p.download(self.root)


if __name__ == '__main__':
    unittest.main()
