"""Build a matched core and portrait release from an existing validated package."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

def digest(data):
    return hashlib.sha256(data).hexdigest()

def encode(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()

def build(core, workbench, fallback, original_pack, output):
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(core) as old:
        manifest = json.loads(old.read('compatibility.json'))
        assert manifest['version'] == '0.79.0'
        wb = 'Workbench/'
        names = json.loads(old.read(wb+'portrait_manifest.json'))
        original = json.loads(old.read(wb+'portrait_hashes.json'))
        local = json.loads((workbench/'local_portraits/local_portraits.json').read_bytes())
        files = {}
        for identity, item in list(names.items()) + list(local.items()):
            name = item['file']
            assert re.fullmatch('[0-9a-f]{24}\\.png', name)
            path = wb+'portraits/'+name
            if identity not in names:
                assert item['source'].startswith('Assets/') and item['source'].lower().endswith('.png')
                names[identity] = {k:item[k] for k in ('source','kind','file')}
                image = workbench/'local_portraits'/name
            else:
                image = workbench/'portraits'/name
                if not image.is_file():
                    image = fallback/name
            blob = image.read_bytes()
            assert blob.startswith(b'\x89PNG\r\n\x1a\n') and (path not in files or files[path] == blob)
            files[path] = blob
        pinned = json.loads(old.read(wb+'portrait_source.json'))
        assert digest(original_pack.read_bytes()) == pinned['sha256']
        with zipfile.ZipFile(original_pack) as previous:
            for path in original:
                assert path in files
                files[path] = previous.read(path)
        hashes = {p:digest(data) for p,data in sorted(files.items())}
        assert all(hashes.get(k) == v for k,v in original.items())
        pack = output/'FaustRandomIdentity-Portraits.zip'
        with zipfile.ZipFile(pack,'w') as archive:
            for path in sorted(files):
                archive.writestr(zipfile.ZipInfo(path),files[path])
            archive.writestr(zipfile.ZipInfo('portrait-hashes.json'),encode(hashes),compress_type=zipfile.ZIP_DEFLATED)
        source = dict(schema=1,url='https://github.com/Chrismick111/faust-random-identity/releases/download/v0.79.1/'+pack.name,
                      size=pack.stat().st_size,sha256=digest(pack.read_bytes()))
        info = json.loads(old.read('addon_info.json'))
        info['version'] = manifest['version'] = '0.79.1'
        changes = {wb+'portrait_manifest.json':encode(names),wb+'portrait_source.json':encode(source),
                   wb+'portrait_hashes.json':encode(hashes),'addon_info.json':encode(info)}
        manifest['package_files'].update({k:digest(v) for k,v in changes.items()})
        changes['compatibility.json'] = encode(manifest)
        with zipfile.ZipFile(output/core.name,'w') as archive:
            for row in old.infolist():
                archive.writestr(row,changes[row.filename] if row.filename in changes else old.read(row))
    print(len(files),'images;',len(names),'mapped appearances;',source['sha256'])

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('core','workbench','fallback','original_pack','output'):
        parser.add_argument(name,type=Path)
    build(**vars(parser.parse_args()))
