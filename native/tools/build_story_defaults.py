"""Build portable copies of verified story animation timings for fresh installations."""
import argparse
import json
from pathlib import Path
import re
import struct
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_named_clash_slots import read_archive

CATALOG = 'Assets/runtime/all_sinners_pools.json'


def verified(blob, look):
    magic, version, count, size = struct.unpack_from('<4sIII', blob)
    offset = 16 + 140*count
    if magic!=b'SST1' or version!=1 or not 0<count<=512 or len(blob)!=offset+size:
        raise ValueError(look + ': invalid timing file')
    metadata = json.loads(blob[offset:])
    if metadata['AppearanceName']!=look:
        raise ValueError(look + ': appearance mismatch')
    return blob


def rebuild(entry, groups, build_entry):
    metadata = entry['story_metadata']
    motions = []
    for motion in metadata['motionList']:
        d = motion['motionDetail']
        rows = sorted(groups.get(d, []))
        parts = motion['motionTimelineDatas']
        if not parts or len(parts)!=len(rows):
            return None
        names = []
        for j,(part,(index,count,seconds,name)) in enumerate(zip(parts,rows)):
            # Some metadata records end at the hit marker, before the visual
            # tail. The runtime reads the actual duration from this named asset.
            if (index!=j or count!=len(rows) or part['motionIndex']!=j or seconds<=0
                    or max(part['duration'],part['hitMarkerTime'],part['endMarkerTime'])>seconds+.001):
                return None
            names.append(dict(name=name))
        motions.append(dict(detail=d,timelines=names))
    if not motions:
        return None
    _, blob = build_entry(dict(appearance=entry['appearance_name'],motions=motions),metadata,entry['asset_key'])
    return blob


def from_prefab(entry, bundle, build_entry):
    import UnityPy
    UnityPy.config.FALLBACK_UNITY_VERSION='6000.3.0f1'
    env=UnityPy.load(str(bundle))
    objects={(o.assets_file.name,o.path_id):o for o in env.objects}
    look=entry['appearance_name']
    for (cab,_),go in objects.items():
        if go.type.name!='GameObject' or go.peek_name()!=look:
            continue
        for component in go.read_typetree()['m_Component']:
            owner=objects.get((cab,component['component']['m_PathID']))
            motion_list=owner.read_typetree().get('motionList') if owner else None
            if motion_list is None:
                continue
            motions=[]
            for group in motion_list:
                parts=[]
                for ref in group['timelineAssets']:
                    obj=objects.get((cab,ref['m_PathID'])) if ref['m_FileID']==0 else None
                    parts.append(dict(name=obj.peek_name() if obj else None))
                if parts:
                    motions.append(dict(detail=group['_motiondetail'],timelines=parts))
            _,blob=build_entry(dict(appearance=look,motions=motions),entry['story_metadata'],entry['asset_key'])
            return blob
    raise ValueError('Could not locate the named prefab: '+look)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('addon','baseline','output'):
        parser.add_argument(arg,type=Path)
    parser.add_argument('--queen-bundle',type=Path,required=True)
    args=parser.parse_args()
    sys.path[:0]=[str(args.addon/'Workbench'),str(args.addon/'Workbench/pool'),str(args.addon/'Workbench/timeline_vendor')]
    from boss_importer import build_entry
    with zipfile.ZipFile(args.baseline) as release:
        catalog=json.loads(release.read(CATALOG))
        shipped=set(release.namelist())
    entries={e['identity_id']:e for p in catalog.values() for e in p['entries'] if e.get('story_metadata')}
    archive=read_archive(args.addon/'archive-times-candidate')
    rebuilt=[]; unresolved=[]; copied=0
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'w') as bundle:
        for identity,entry in sorted(entries.items()):
            look=entry['appearance_name']
            if not re.fullmatch(r'story_[A-Za-z0-9_]+',identity) or not re.fullmatch(r'[A-Za-z0-9_]+',look):
                raise ValueError(identity)
            path=Path('Assets/runtime/story_native')/(identity+'.bin')
            if path.as_posix() in shipped:
                continue
            current=args.addon/path
            if current.is_file():
                blob=verified(current.read_bytes(),look)
                copied+=1
            else:
                blob=from_prefab(entry,args.queen_bundle,build_entry) if look=='400003_QueenOfHatred' else rebuild(entry,archive.get(look,{}),build_entry)
                if blob is None:
                    unresolved.append(identity)
                    continue
                rebuilt.append(identity)
            item=zipfile.ZipInfo(path.name)
            item.compress_type=zipfile.ZIP_DEFLATED
            bundle.writestr(item,blob)
    print('Portable timings:',copied,'verified;',len(rebuilt),'reconstructed',rebuilt,'; unresolved',unresolved)


if __name__=='__main__':
    main()
