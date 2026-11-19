"""Rebuild the appearance voice index from the selected installed content snapshot."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import zlib
from appearance_voice_fmod import event_strings

HERE = Path(__file__).resolve().parent
COMMON = ('battleentry', 'battle_select', 'battle_endcommand', 'battle_enemy_break',
          'battle_break', 'battle_kill', 'battle_allydead', 'battle_clear',
          'battle_clear_ex', 'battle_defeat','battle_dead','battle_loseduel',
          'formation', 'choice_success_p', 'choice_fail_n')
OWNER_KEY = re.compile(r'(?:^|_)([1-9][0-9]{3,5})(?=_|$)')
def read(path):
    return json.loads(path.read_text('utf-8-sig'))

def cstring(s):
    return json.dumps(s, ensure_ascii=False)

def generate(args):
    base, loc, archive = args.plugin, args.game_loc, args.archive
    zh = args.translation or base.parent.parent / 'lang/LLC_zh-CN'
    pool = read(base / 'Assets/runtime/all_sinners_pools.json')
    entries = [u for p in pool.values() for u in p['entries']]
    if len({u['appearance_name'] for u in entries}) != len(entries):
        raise ValueError('Duplicate appearance names in pool')
    identities = {x['appearance']: int(x['id']) for x in read(base/'identity_catalog.json')['rows']}
    forms = {f: int(u['identity_id']) for u in entries if u['identity_id'].isdigit() for f in u.get('forms', [])}
    static = defaultdict(set)
    for path, doc in read(args.static).items():
        if path.split('/')[-2] not in ('personality', 'enemy', 'abnormality-unit'): continue
        for row in doc.get('list', []):
            if isinstance(row.get('appearance'),str):
                static[row['appearance']].add((row['id'],row.get('viewid') or 0,str(row.get('unitScriptID') or '')))
    banks = sorted((archive/'sound_lib').glob('*.json.gz'))
    library = json.loads(gzip.decompress(banks[-1].read_bytes()))
    paths = event_strings(loc.parents[2])
    voice_paths = {p[len('event:/Voice/'):] for p in paths.values() if p.startswith('event:/Voice/')}
    sfx_paths = {p.rsplit('/',1)[-1]:p for p in paths.values() if p.startswith('event:/SFX/Battle/')}
    audio = defaultdict(set)
    def visit(node, path=()):
        path = path + (node['name'],)
        if ('Voicefiles' in path and 'Battle announcers' not in path) or ('Story' in path and path[-1]=='Battle lines'):
            for bank, index, key, *_ in node.get('items',[]):
                audio[key].add((bank,index))
        for child in node.get('kids',[]): visit(child,path)
    visit(library['tree'])
    text_by_locale, personality_keys, bubbles, origins = {}, defaultdict(set), set(), defaultdict(set)
    for lang, root, prefix in [('en',loc/'en','EN_'),('zh',zh,'')]:
        personality_text, bubble_text = {}, {}
        files = [*sorted((root/'PersonalityVoiceDlg').glob('*.json')), *sorted(root.glob(prefix+'BattleSpeechBubbleDlg*.json'))]
        if not files: raise ValueError('Missing localization files at '+str(root))
        for f in files:
            is_bubble = f.parent == root
            strings=bubble_text if is_bubble else personality_text
            for r in read(f).get('dataList', []):
                k=r.get('id')
                if not isinstance(k,str) or not k:continue
                if r.get('dlg'):
                    if k in strings and strings[k]!=r['dlg']:
                        # The in-game loader determines precedence. Never choose a conflicting fallback.
                        strings[k]=None
                    else: strings[k]=r['dlg']
                origins[k].add(f.name)
                if is_bubble: bubbles.add(k)
                else:
                    m=OWNER_KEY.search(k)
                    if m: personality_keys[int(m[1])].add(k)
        # In battle the authored bubble (including its color markup) takes precedence
        # over the voice gallery's plain-text transcription of the same recording.
        text_by_locale[lang]={**personality_text,**bubble_text}
    timelines=defaultdict(set)
    raw_clips=defaultdict(set)
    prefab_summary={}
    indexed=set()
    for f in sorted((base/'Workbench/timeline_data').glob('*.json.z')):
        doc=json.loads(zlib.decompress(f.read_bytes()))
        app=doc['appearance']; indexed.add(app)
        for r in doc['records']:
            if r.get('owner_status')!='resolved' or r.get('status')!='matched':continue
            for match in r.get('matches',[]):
                for e in match.get('events',[]):
                    if e.get('kind')=='voice' and e.get('label'):
                        timelines[app].add((r['name'],r['detail'],r['index'],e['relative_time'],e['label']))
    if args.raw_timelines:
        for entry in read(args.raw_timelines)['rows']:
            app=entry['appearance']
            for motion in entry['motions']:
                hits={hit['object']:hit['tree'] for hit in motion['hits']}
                for track in hits.values():
                    if track.get('m_Muted'):continue
                    voice_track='voice' in track.get('m_Name','').lower()
                    for c in track.get('m_Clips',[]):
                        ref=c['m_Asset']
                        if ref['m_FileID']: continue
                        target=hits.get(ref['m_PathID'],{})
                        guid=target.get('EventReference',{}).get('Guid',{})
                        if not guid:continue
                        path=paths.get(tuple(guid.get('Data'+str(i)) for i in range(1,5)))
                        if path and (voice_track or path.startswith('event:/Voice/')):
                            raw_clips[app].add((motion['timeline'],motion['detail'],motion['index'],
                                                c['m_Start'],path,c.get('m_DisplayName','')))
    if args.prefabs:
        scanned=read(args.prefabs)
        if scanned['errors']:raise ValueError('Prefab scan contains errors')
        for app,records in scanned['appearances'].items():
            raw_clips[app]={tuple(c) for r in records for c in r['events']}
            prefab_summary[app]=[{k:v for k,v in r.items() if k!='events'} for r in records]
    methods=defaultdict(lambda: defaultdict(set))
    for row in read(args.methods):
        for m in row['methods']:
            parsed=re.fullmatch(r'UnitScript_(\d+)\.(\w+)',m)
            if parsed:methods[int(parsed[1])][parsed[2]].add(row['key'])
    aliases, keys, reports = {}, defaultdict(set), []
    # Voice-bank names containing explicit owner IDs also cover recordings without captions.
    numbered=defaultdict(set)
    for k in voice_paths:
        if k.startswith(('battle_', 'battleentry_','formation_', 'choice_')):
            for m in OWNER_KEY.finditer(k): numbered[int(m[1])].add(k)
    for u in entries:
        app=u['appearance_name']; i=u['identity_id']; rows=sorted(static[app])
        prefix=re.match(r'^(\d+)_',app)
        # Numbered prefabs can share a visual across encounter scripts. Keep all script references
        # in the audit. A script literal alone is never used to synthesize a trigger.
        owner=identities.get(app) or forms.get(app) or (int(prefix[1]) if prefix else 0)
        if owner==0 and len({v or n for n,v,_ in rows})==1:owner=rows[0][1] or rows[0][0]
        if owner:
            aliases[app]=aliases[i]=owner
            for f in u.get('forms',[]):
                if f in forms:aliases.setdefault(f,owner)
        clips=sorted(timelines[app])
        raw=sorted(raw_clips[app])
        exact={c[-1] for c in clips} | {c[4][len('event:/Voice/'):] for c in raw if c[4].startswith('event:/Voice/')}
        script_ids={int(script) for _,_,script in rows if script.isdigit()} | ({owner} if owner in methods else set())
        method_rows={str(s):{m:sorted(ks) for m,ks in sorted(methods[s].items())} for s in sorted(script_ids) if methods.get(s)}
        linked={k for by_method in method_rows.values() for ks in by_method.values() for k in ks}
        local_keys=personality_keys[owner] | numbered[owner] | (exact & (voice_paths | bubbles)) | linked
        # The engine may emit any original key. Only owner-linked catalog keys qualify.
        if owner:keys[owner].update(personality_keys[owner] | numbered[owner] | (exact & (voice_paths | bubbles)) | {k for ks in methods.get(owner,{}).values() for k in ks})
        recording_keys=sorted(local_keys & voice_paths)
        track_sfx=sorted({sfx_paths[k] for k in exact if k in sfx_paths} | {c[4] for c in raw if c[4].startswith('event:/SFX/')})
        localized=sorted(local_keys & (text_by_locale['en'].keys()|text_by_locale['zh'].keys()))
        reports.append(dict(identity=i,appearance=app,pool_name=u.get('name'),forms=u.get('forms',[]),owner=owner,
            static_units=[dict(id=n,view_id=v or None,script=s or None) for n,v,s in rows],
            indexed_timeline=app in indexed,timeline_voice_clips=clips,native_voice_track_events=raw,prefab_scan=prefab_summary.get(app,[]),
            voice_track_sfx_paths=track_sfx,script_method_candidates=method_rows,
            localized_keys=localized,recording_keys=recording_keys,
            text_without_indexed_recording=sorted(set(localized)-set(recording_keys)),
            status=('voice_event_indexed' if recording_keys else 'text_evidence' if localized else 'voice_track_sfx' if track_sfx else 'timeline_voice_label' if exact else 'method_candidate' if linked else 'no_indexed_evidence')))
    allkeys=sorted(set().union(*keys.values(),bubbles,*(r['recording_keys'] for r in reports)))
    by_key={k:i for i,k in enumerate(allkeys)}
    # Runtime presentation can use active-language game APIs first. Chinese fallback is optional when absent.
    lines=['/* Generated by build_appearance_voice_catalog.py. UTF-8. */','#ifndef SR_APPEARANCE_VOICE_CATALOG_H','#define SR_APPEARANCE_VOICE_CATALOG_H','#include <string.h>','#include <stdio.h>',
           'static const struct { const char *appearance; unsigned owner; } sr_voice_aliases[] = {']
    lines += [' {%s,%d},'%(cstring(k),v) for k,v in sorted(aliases.items())]
    lines+=['};','static const struct { const char *key,*text; unsigned char audio,bubble; } sr_voice_labels[] = {']
    lines+=[' {%s,%s,%d,%d},'%(cstring(k),cstring(text_by_locale['zh'][k]) if text_by_locale['zh'].get(k) else 'NULL',k in voice_paths,k in bubbles) for k in allkeys]
    lines+=['};','static const struct {unsigned owner, label;} sr_voice_members[] = {']
    lines+=[' {%d,%d},'%(o,by_key[k]) for o in sorted(keys) for k in sorted(keys[o])]
    lines+=['};','static const char *const sr_voice_common_events[] = {' + ','.join(map(cstring,COMMON)) + '};', (HERE/'appearance_voice_catalog_lookup.inc').read_text('utf8'),'#endif']
    (args.out/'appearance_voice_catalog.h').write_text('\n'.join(lines)+'\n','utf8')
    summary=dict(pool_entries=len(reports),owners=len({r['owner'] for r in reports if r['owner']}),status=dict(Counter(r['status'] for r in reports)),
                 appearances_with_timeline_clips=sum(bool(r['timeline_voice_clips']) for r in reports),
                 appearances_with_method_candidates=sum(bool(r['script_method_candidates']) for r in reports),bubble_keys=len(bubbles),
                 fmod_voice_paths=len(voice_paths),native_voice_track_appearances=sum(bool(raw_clips[r['appearance']]) for r in reports),indexed_sound_lib=banks[-1].name)
    sources=[base/'Assets/runtime/all_sinners_pools.json',args.static,args.methods,banks[-1],
             loc.parents[2]/'StreamingAssets/Assets/Sound/FMODBuilds/Desktop/Master.strings.bank']
    if args.raw_timelines:sources.append(args.raw_timelines)
    if args.prefabs:sources.append(args.prefabs)
    audit=dict(summary=summary,source_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},
        scope='Pool entries counted once. Timeline clip rows contain timeline, motionDetail, motionIndex, local seconds and label. Native track event rows include the GUID-resolved FMOD path and serialized clip label. Archived motion indices and local time are not reproduced triggers. Script literals are condition-dependent candidates. A registered voice event is not evidence of in-game playback. Lack of indexed evidence does not establish silence.',
        appearances=reports, resources={k:{'event_path':'event:/Voice/'+k if k in voice_paths else None,'sample_bank_indices':sorted(audio.get(k,[])), 'localization_files':sorted(origins.get(k,set()))} for k in allkeys})
    (args.out/'appearance_voice_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=1)+'\n','utf8')
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['plugin','archive','game-loc','static','methods']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--translation',type=Path);p.add_argument('--raw-timelines',type=Path);p.add_argument('--prefabs',type=Path);p.add_argument('--out',type=Path,default=HERE)
    generate(p.parse_args())
