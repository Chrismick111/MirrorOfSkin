#ifndef SR_COUNTERPART_PLAYBACK_H
#define SR_COUNTERPART_PLAYBACK_H
typedef struct {int id;const char *player,*story,*pool;unsigned offset,forward,reverse,playerLengths,storyLengths;} SrCounterpart;
typedef struct {int source,target,count;} SrCounterpartMotion;
typedef struct {const char *normal,*alternate,*first,*second,*group;} SrCounterpartForm;
#include "counterpart_data.inc"

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
static int sr_counterpart_attack(const int *counts,const char *base,const char *look,int requested,int fallback){
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
 if(requested>=7&&requested<=9&&counts[requested]>0)return requested;
 return fallback;
}
#endif
