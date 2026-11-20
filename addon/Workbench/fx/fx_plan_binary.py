"""Candidate v1 effect-plan wire format; not connected to the game."""
import hashlib
import math
import struct

HEADER=struct.Struct('<4sII')
FIXED=struct.Struct('<iiiB3xdd32s32s32s32s32s')
MAX_ROWS=256
MAX_BYTES=1024*1024
MAX_STRING=255
MAX_DEPTH=16
STRING_KEYS=('identity_id','appearance_id','appearance_name','timeline_name','clip_name','track_name')

class PlanError(ValueError): pass

def fingerprint(value):
    try: raw=bytes.fromhex(value)
    except (TypeError,ValueError): raise PlanError('invalid fingerprint')
    if len(raw)!=32: raise PlanError('invalid fingerprint')
    return raw

def integer(value):
    if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=0x7fffffff:
        raise PlanError('invalid index')
    return value

def text_bytes(value, allow_empty=False):
    if not isinstance(value,str): raise PlanError('invalid text')
    b=value.encode('utf8')
    if (not b and not allow_empty) or len(b)>MAX_STRING or b'\x00' in b: raise PlanError('invalid text')
    return b

def encode(ops,game_fingerprint):
    if not isinstance(ops,list) or len(ops)>MAX_ROWS: raise PlanError('invalid record count')
    game=fingerprint(game_fingerprint); result=bytearray(HEADER.pack(b'FXP2',2,len(ops)))
    keys=set()
    for op in ops:
        path=op.get('track_path')
        if not isinstance(path,list) or not 1<=len(path)<=MAX_DEPTH: raise PlanError('invalid track path')
        path=[integer(x) for x in path]
        detail,part,clip=(integer(op.get(k)) for k in ('detail','part_index','clip_index'))
        nums=[]
        for k in ('original_start','new_start'):
            v=op.get(k)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0: raise PlanError('invalid time')
            nums.append(v)
        track=op.get('track_type')
        if not isinstance(track,dict) or not isinstance(track.get('source'),dict): raise PlanError('missing track type')
        strings=[text_bytes(op.get(k)) for k in STRING_KEYS]
        if any(c >= 128 for c in strings[4]): raise PlanError('runtime clip names must be ASCII')
        strings += [text_bytes(track.get('assembly')),text_bytes(track.get('namespace'),True),text_bytes(track.get('class')),text_bytes(track.get('cab')),text_bytes(track.get('path_id'))]
        script_sha=fingerprint(track['source'].get('bundle_sha256')); script_key=fingerprint(track['source'].get('bundle_key'))
        bundle=fingerprint(op.get('bundle_sha256')); bundle_key=fingerprint(op.get('bundle_key'))
        key=(strings[0],strings[1],strings[3],detail,part,tuple(path),clip)
        if key in keys: raise PlanError('duplicate clip')
        keys.add(key)
        result.extend(FIXED.pack(detail,part,clip,len(path),*nums,game,bundle,bundle_key,script_sha,script_key))
        result.extend(struct.pack('<'+'I'*len(path),*path))
        for b in strings: result.extend(struct.pack('<H',len(b)));result.extend(b)
    if len(result)>MAX_BYTES: raise PlanError('plan too large')
    return bytes(result)

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
