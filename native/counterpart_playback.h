#ifndef SR_COUNTERPART_PLAYBACK_H
#define SR_COUNTERPART_PLAYBACK_H
typedef struct {int id;const char *player,*story,*pool;unsigned offset,forward,reverse,playerLengths,storyLengths;} SrCounterpart;
typedef struct {int source,target,count;} SrCounterpartMotion;
typedef struct {const char *normal,*alternate,*first,*second,*group;} SrCounterpartForm;
#include "counterpart_data.inc"
#include "segment_latch.h"

static const SrCounterpartForm *sr_counterpart_form(const char *base){
 if(!base)return NULL;
 for(const SrCounterpartForm *f=sr_counterpart_forms;f->normal;f++)
  if(sr_pair_base(base,f->normal)||!strcmp(base,f->alternate))return f;
 return NULL;
}
static int sr_counterpart_member(const SrCounterpartForm *f,const char *identity){
 return f&&identity&&(!strcmp(identity,f->first)||!strcmp(identity,f->second));
}

static int sr_player_number(const char *name){
 int id=0;
 for(int i=0;i<5;i++){
  if(name[i]<'0'||name[i]>'9')return 0;
  id=id*10+name[i]-'0';
 }
 return name[5]=='_'||!name[5]?id:0;
}
static const SrCounterpart *sr_find_counterpart(const char *source,const char *target,int *reverse){
 if(!source||!target)return NULL;
 const char *story,*player;
 if(!strncmp(target,"story_",6)){story=target+6;player=source;*reverse=0;}
 else{story=!strncmp(source,"story_",6)?source+6:source;player=target;*reverse=1;}
 int id=sr_player_number(player);
 if(!id)return NULL;
 size_t lo=0,hi=sizeof(sr_counterparts)/sizeof(sr_counterparts[0]),end=hi;
 while(lo<hi){size_t mid=lo+(hi-lo)/2;if(sr_counterparts[mid].id<id)lo=mid+1;else hi=mid;}
 for(;lo<end&&sr_counterparts[lo].id==id;lo++){
  const SrCounterpart *p=&sr_counterparts[lo];
  if(sr_pair_base(player,p->player)&&(!strcmp(story,p->story)||!strcmp(*reverse?source:target,p->pool)))return p;
 }
 return NULL;
}
static int sr_counterpart_source_parts(const char *base,const char *look,int detail){
 int slot=detail>=7&&detail<=16?detail-7:detail>=24&&detail<=34?detail-14:-1;
 if(slot<0)return 0;
 int reverse=0;
 const SrCounterpart *p=sr_find_counterpart(base,look,&reverse);
 return p?sr_counterpart_lengths[reverse?p->storyLengths:p->playerLengths][slot]:0;
}
/* Used only if the native coin order for the target could not be obtained. */
static int sr_counterpart_fallback_part(int index,int src,int dst,int last){
 if(index<0||dst<=0)return index;
 if(last)return dst-1;
 if(src>1&&index<src)return index*(dst-1)/(src-1);
 return index%dst;
}
static int sr_counterpart_motion(const int *counts,const char *base,const char *look,int requested,int fallback,int tierFallback){
 int reverse=0;
 if(!counts||requested<0||requested>=SR_MOTION_CACHE)return fallback;
 const SrCounterpart *pair=sr_find_counterpart(base,look,&reverse);
 if(!pair)return fallback;
 unsigned first=pair->offset+(reverse?pair->forward:0),count=reverse?pair->reverse:pair->forward;
 for(unsigned i=first;i<first+count;i++){
  const SrCounterpartMotion *m=&sr_counterpart_motions[i];
  if(m->source==requested)return counts[m->target]==m->count?m->target:fallback;
 }
 /* The three ordinary skill tiers have a defined order on both appearances. */
 if(tierFallback&&requested>=7&&requested<=9&&counts[requested]>0)return requested;
 return fallback;
}
static int sr_counterpart_attack(const int *counts,const char *base,const char *look,int requested,int fallback){
 return sr_counterpart_motion(counts,base,look,requested,fallback,1);
}
static int sr_counterpart_ordinary(const char *name){
 if(!name||!*name)return 0;
 char lower[128];size_t len=strlen(name);
 if(len>=sizeof(lower))return 0;
 for(size_t i=0;i<=len;i++){
  char c=name[i];lower[i]=(c>='A'&&c<='Z')?(char)(c-'A'+'a'):c;
 }
 static const char *const markers[]={"_link","_duel","_clash","_parry","_special","_summon","_finish","_cinema","_transform","_assist"};
 for(unsigned i=0;i<sizeof(markers)/sizeof(*markers);i++)if(strstr(lower,markers[i]))return 0;
 return 1;
}
/* Wedge combinations use authored multi-actor choreography in either direction. */
static int sr_counterpart_choreography(const SrCounterpart *pair){
 return pair&&(pair->id==11116||pair->id==10316||pair->id==11017);
}
enum SrPairScope {SR_PAIR_ORDINARY,SR_PAIR_WITHIN_GROUP,SR_PAIR_KEEP_PART};
/* Keep the mapped part until a proven body would repeat. Prefer a new body
   over one used earlier in the skill, then the original group and closest duration.
   The state contains the actual final choice, including unmodified native parts. */
static int sr_counterpart_choose(SrSegmentLatch *s,int coin,int sourceGroup,int sourcePart,enum SrPairScope scope,double source,
 const double times[128][32],const int counts[128],const uint32_t ordinary[128],
 const uint32_t metadata[128],const SrOrdinaryBodies *bodies,int *detail,int *part){
 int d=*detail,k=*part;
 if(coin<0||coin>=SR_VARIETY_COINS||sr_attack_group_slot(d)<0||k<0||k>=32||
    k>=counts[d]||!(ordinary[d]&metadata[d]&(UINT32_C(1)<<k)))return 0;
 if(s->seen[coin]&&(s->pairSourceGroup[coin]!=sourceGroup||s->pairSourcePart[coin]!=sourcePart||
    scope==SR_PAIR_KEEP_PART||(scope==SR_PAIR_WITHIN_GROUP&&s->groups[coin]!=d))){
  s->playedBody[coin]=sr_cached_body(bodies,d,k);
  return 0;
 }
 if(!s->seen[coin]){
  unsigned body=sr_cached_body(bodies,d,k),previous=coin?s->playedBody[coin-1]:0;
  unsigned char used[256]={0};
  for(int i=0;i<coin;i++)if(s->playedBody[i]&&s->playedBody[i]<256)used[s->playedBody[i]]=1;
  int best=d,bestPart=k;
  if(scope!=SR_PAIR_KEEP_PART&&previous&&body&&body<256&&used[body]&&source>0&&times){
   int rank=(body==previous?0:1),sameGroup=1;
   double bestError=0;
   for(int g=7;g<=34;g++){
    if(sr_attack_group_slot(g)<0||(scope==SR_PAIR_WITHIN_GROUP&&g!=d))continue;
    uint32_t eligible=ordinary[g]&metadata[g];
    for(int j=0;j<counts[g]&&j<32;j++){
     if(!(eligible&(UINT32_C(1)<<j)))continue;
     unsigned candidate=sr_cached_body(bodies,g,j);
     if(!candidate||candidate>=256||candidate==previous)continue;
     double ratio=times[g][j]/source;
     if(!(ratio>=.67&&ratio<=1.5))continue;
     int score=used[candidate]?1:2,local=g==d;
     double error=ratio>=1?ratio-1:1/ratio-1;
     if(score>rank||(score==rank&&(local>sameGroup||(local==sameGroup&&error<bestError)))){
      best=g;bestPart=j;rank=score;sameGroup=local;bestError=error;
     }
    }
   }
  }
  s->pairSourceGroup[coin]=(unsigned char)sourceGroup;s->pairSourcePart[coin]=(unsigned char)sourcePart;
  s->seen[coin]=1;s->groups[coin]=(unsigned char)best;s->indices[coin]=(unsigned char)bestPart;
 }
 *detail=s->groups[coin];*part=s->indices[coin];
 s->playedBody[coin]=sr_cached_body(bodies,*detail,*part);return 1;
}
#endif
