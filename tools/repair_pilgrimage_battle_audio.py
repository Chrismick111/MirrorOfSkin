"""Migrate archived FMOD event data using the author's manifest and a current game schema."""
from collections import defaultdict
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import argparse
from pathlib import Path
from uuid import UUID
from zipfile import ZipFile

import UnityPy



def convert(value, example):
    if isinstance(value, dict):
        names = {n.casefold(): n for n in example}
        assert {n.casefold() for n in value} == set(names)
        return {names[k.casefold()]: convert(v, example[names[k.casefold()]]) for k, v in value.items()}
    if isinstance(value, list):
        # All events in this archive are non-parameterized.
        assert not value
    return value


def guid(ref):
    data = ref['Guid']
    return str(UUID(bytes_le=b''.join((data['Data%d' % n] & 0xffffffff).to_bytes(4,'little') for n in range(1,5))))


def rebuild(chapter, original_pack, stock_path, repaired_pack):
    UnityPy.config.FALLBACK_UNITY_VERSION='6000.3.12f1'
    with ZipFile(chapter) as z:
        rows = json.loads(z.read(next(n for n in z.namelist() if n.endswith('/battle_audio_manifest.json'))))['clips']
    with ZipFile(original_pack) as z:
        member, = [n for n in z.namelist() if n.endswith('.bundle')]
        env=UnityPy.load(z.read(member))
    f,=env.assets
    stock,=UnityPy.load(stock_path.read_bytes()).assets
    script_name='FMODEventPlayable'
    script_pid, = [o.path_id for o in f.objects.values() if o.type.name=='MonoScript'
                   and o.read_typetree()['m_ClassName']==script_name]
    def fields(obj):
        return [n.m_Name for n in obj.serialized_type.node.m_Children]
    witness=next(o for o in stock.objects.values() if o.type.name=='MonoBehaviour'
                 and 'EventReference' in fields(o) and 'EventLength' in fields(o)
                 and o.read_typetree()['m_Script']['m_PathID']==script_pid)
    example=witness.read_typetree()
    @lru_cache(None)
    def tree(pid):
        return f.objects[pid].read_typetree()
    scripts={o.path_id:tree(o.path_id)['m_ClassName'] for o in f.objects.values() if o.type.name=='MonoScript'}
    timelines=defaultdict(list)
    event_objects={}
    for o in f.objects.values():
        if o.type.name!='MonoBehaviour':continue
        t=tree(o.path_id)
        cls=scripts.get(t['m_Script']['m_PathID'])
        if cls=='TimelineAsset':
            timelines[t['m_Name']].append(t)
        if cls==script_name:
            event_objects[o.path_id]=o
    expected={}
    for r in rows:
        t,=timelines[r['timeline']]
        for j,i in enumerate(r['track']):
            t=tree(t['m_Children' if j else 'm_Tracks'][i]['m_PathID'])
        c=t['m_Clips'][r['clip']]
        assert t['m_Name']==r['trackName'] and abs(c['m_Start']-r['start'])<0.0001
        pid=c['m_Asset']['m_PathID']
        assert pid in event_objects
        pair=r['guid'],r['length']
        assert expected.setdefault(pid,pair)==pair
    before={o.path_id:hashlib.sha256(o.get_raw_data()).digest() for o in f.objects.values() if o.path_id not in event_objects}
    new={}
    for pid,o in event_objects.items():
        t=convert(tree(pid),example)
        if pid in expected:
            identifier,length=expected[pid]
            assert guid(t['EventReference'])==identifier
            assert abs(t['EventLength']-length)<1e-5
            t['Template']['EventReference']=deepcopy(t['EventReference'])
            t['EventLength']=length
        new[pid]=t
        o.save_typetree(t,nodes=witness.serialized_type.node)
    for tid in {o.type_id for o in event_objects.values()}:
        assert all(o.path_id in event_objects for o in f.objects.values() if o.type_id==tid)
        typ=f.types[tid]
        typ.node=witness.serialized_type.node
        typ.old_type_hash=witness.serialized_type.old_type_hash
    payload=env.file.save(packer='lz4')
    reread=UnityPy.load(payload)
    check,=reread.assets
    assert set(check.objects)==set(f.objects)
    assert all(check.objects[pid].read_typetree()==value for pid,value in new.items())
    assert all(hashlib.sha256(check.objects[pid].get_raw_data()).digest()==digest for pid,digest in before.items())
    for name,stream in env.file.files.items():
        if name.endswith('.resS'):
            assert stream.bytes==reread.file.files[name].bytes
    repaired_pack.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(original_pack) as source, ZipFile(repaired_pack,'x') as target:
        for info in source.infolist():
            target.writestr(info,payload if info.filename==member else source.read(info))
    print('slots',len(rows),'unique event objects',len(expected),'all event objects',len(new),'other objects verified',len(before))
    print('zip',repaired_pack,hashlib.sha256(repaired_pack.read_bytes()).hexdigest())


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('chapter', type=Path, help='Original chapter ZIP containing battle_audio_manifest.json')
    parser.add_argument('original_pack', type=Path, help='Previously exported appearance ZIP')
    parser.add_argument('stock_bundle', type=Path, help='Current stock Unity bundle with an FMODEventPlayable')
    parser.add_argument('output', type=Path, help='New ZIP in a different directory, keeping the original filename')
    args = parser.parse_args()
    if args.output.name != args.original_pack.name:
        parser.error('Keep the original filename to preserve imported identities.')
    rebuild(args.chapter, args.original_pack, args.stock_bundle, args.output)
