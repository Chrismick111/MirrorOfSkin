"""Join player/enemy skill names to the game's skillMotion and actual prefab slots."""
import argparse
import collections
import gzip
import json
import re
import unicodedata
from pathlib import Path

PAIRS = {10916: ('1314',), 10716: ('1306',), 10115: ('1347','1348'),
         10314: ('1325','1355'), 11115: ('1327',), 10814: ('1328',),
         10614: ('1331',), 10215: ('1319','1336','1354'), 10415: ('1322',),
         11015: ('1318','1353')}


def archived(data, folder):
    with gzip.open(max((data/folder).glob('*.json.gz'), key=lambda p:p.stat().st_mtime_ns), 'rt', encoding='utf8') as stream:
        return json.load(stream)


def name(skill):
    labels = {r['name'] for r in skill.get('up',{}).values() if r.get('name')}
    return next(iter(labels)) if len(labels)==1 else ''


def normalized(label):
    # Preserve the words, including suffixes for enhanced skills.
    return ''.join(c for c in unicodedata.normalize('NFKC',label).casefold() if c.isalnum())


def motion(skill):
    # S1..S10 occupy slots 7..16. Resolve other types through the native path.
    motions={row['skillMotion'] for row in skill.get('skillData',[]) if row.get('skillMotion')}
    types={row['defType'] for row in skill.get('skillData',[]) if row.get('defType')}
    if len(motions)!=1 or len(types)!=1:
        return None
    m=re.fullmatch(r'S([1-9]|10)', motions.pop())
    return (int(m[1])+6, types.pop()) if m else None


def main():
    p=argparse.ArgumentParser()
    for arg in ('static','archive_data','shots','header','report'):
        p.add_argument(arg,type=Path)
    args=p.parse_args()
    static=json.loads(args.static.read_bytes())
    shots=json.loads(args.shots.read_bytes())
    enemy_db=archived(args.archive_data,'enemy_db')['skills']
    players=archived(args.archive_data,'unit_db')['ids']
    skills={}; owners=collections.defaultdict(set)
    for path,doc in static.items():
        for row in doc.get('list',[]) if isinstance(doc,dict) else []:
            if not isinstance(row,dict) or 'id' not in row:
                continue
            if 'skillData' in row and isinstance(row['skillData'],list):
                skills[row['id']]=row
            elif '/abnormality-unit/' in path and row.get('appearance') in shots:
                ids=owners[row['appearance']]
                ids.update(v['skillId'] for v in row.get('attributeList',[]) if v.get('skillId'))
                ids.update(row.get('defenseSkillIDList',[]))
    by_id=[]; by_source=collections.defaultdict(list); evidence=[]
    for player in players:
        identity=player['id']
        if identity not in PAIRS:continue
        for look,bundle in shots.items():
            if look.split('_')[0] not in PAIRS[identity]:continue
            targets=owners.get(look,set())
            if not targets: # a skin selected by the same battle unit at runtime
                targets=set().union(*(ids for other,ids in owners.items() if other.split('_')[0]==look.split('_')[0]))
            available={s['detail'] for s in bundle['motion_slots'] if s['timeline']}
            for skill in player['skills']+player['defense']:
                pid=skill['id']; src=motion(skills.get(pid,{}))
                if not src:continue
                label=normalized(name(skill))
                candidates=[]
                for eid in sorted(targets):
                    dst=motion(skills.get(eid,{}))
                    if label and dst and src[1]==dst[1] and dst[0] in available and normalized(name(enemy_db.get(str(eid),{})))==label:
                        candidates.append((eid,dst[0]))
                dest={d for _,d in candidates}
                d=next(iter(dest)) if len(dest)==1 else -1
                by_source[identity,look,src[0]].append(d)
                if d>=0:
                    by_id.append((pid,look,src[0],d))
                    evidence.append(dict(identity=identity,player_skill=pid,player_name=name(skill),player_detail=src[0],
                                         enemy_appearance=look,enemy_detail=d,enemy_skills=[i for i,_ in candidates]))
    by_id=sorted(set(by_id))
    # If different player skills share a motion, missing or conflicting results
    # prohibit inferring the target from that motion alone.
    conservative=sorted((i,look,s,ds[0]) for (i,look,s),ds in by_source.items() if ds[0]>=0 and len(set(ds))==1)
    header=['/* Generated from game skill definitions, localized skill names and native enemy slots. */',
            '#ifndef CH9_SKILL_MAP_H','#define CH9_SKILL_MAP_H','#include <string.h>',
            'typedef struct {int id; const char *look; int source,target;} Ch9SkillMapping;']
    for table,rows in [('ch9BySkill',by_id),('ch9ByIdentity',conservative)]:
        header+=['static const Ch9SkillMapping '+table+'[]={']+[
            ' {%d,%s,%d,%d},'%(i,json.dumps(look),s,d) for i,look,s,d in rows]+['};']
    header+=['''static int ch9_mapped_slot(const Ch9SkillMapping *rows,size_t count,int id,const char *look,int source){
 if(!look)return -1;
 if(!strncmp(look,"story_",6))look+=6;
 for(size_t i=0;i<count;i++)
  if(rows[i].id==id&&rows[i].source==source&&!strcmp(rows[i].look,look))return rows[i].target;
 return -1;
}
static int ch9_exact_motion(int playerSkill,const char *donorLook,int sourceDetail){
 return ch9_mapped_slot(ch9BySkill,sizeof(ch9BySkill)/sizeof(*ch9BySkill),playerSkill,donorLook,sourceDetail);
}
static int ch9_unambiguous_motion(int identity,const char *donorLook,int sourceDetail){
 return ch9_mapped_slot(ch9ByIdentity,sizeof(ch9ByIdentity)/sizeof(*ch9ByIdentity),identity,donorLook,sourceDetail);
}''','#endif','']
    assert by_id
    args.header.write_text('\n'.join(header),encoding='ascii')
    args.report.write_text(json.dumps(evidence,ensure_ascii=False,indent=1),encoding='utf8')
    print(len(by_id),'skill/appearance matches;',len({x[0] for x in by_id}),'player skill IDs;',len(conservative),'unique source motions')


if __name__=='__main__':main()
