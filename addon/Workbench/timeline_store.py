"""Read individual compressed timeline records; no external libraries required."""
import hashlib
import json
import pathlib
import zlib

MAX_RECORD_BYTES = 4 * 1024 * 1024

def _load_compressed(path, limit=MAX_RECORD_BYTES):
    compressed = pathlib.Path(path).read_bytes()
    unpacker = zlib.decompressobj()
    raw = unpacker.decompress(compressed, limit + 1)
    if len(raw) > limit or unpacker.unconsumed_tail or not unpacker.eof or unpacker.unused_data:
        raise ValueError('外观时间线资料已损坏或过大')
    return json.loads(raw.decode('utf-8-sig'))

def load(root, appearance):
    key=hashlib.sha256(appearance.encode('utf8')).hexdigest()[:24]
    root=pathlib.Path(root)
    packed=root/(key+'.json.z')
    plain=root/(key+'.json')
    if packed.is_file(): obj=_load_compressed(packed)
    elif plain.is_file(): obj=json.loads(plain.read_text(encoding='utf-8-sig'))
    else: return None
    if obj.get('appearance') != appearance:
        raise ValueError('时间线资料与外观不匹配')
    return obj
