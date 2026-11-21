#ifndef SR_STAGE_GROUPS_H
#define SR_STAGE_GROUPS_H
#include <stdint.h>
#include <string.h>
#include <stddef.h>
#define SR_SG_MAGIC 0x3147534eu
#define SR_SG_MAGIC_V2 0x3247534eu
#define SR_SG_MAX (64 + 13) /* User groups plus the ten chapter profiles and three alternate resources. */
#define SR_SG_STAGES 8
#define SR_SG_CONDS 4
typedef struct { uint32_t type,compare; int32_t threshold; uint32_t reserved; } SrSgCondition;
typedef struct { char identity[64]; uint32_t form,priority,count,logic; SrSgCondition cond[SR_SG_CONDS]; } SrSgStage;
typedef struct { uint32_t enabled,count,hold,reserved; SrSgStage stage[SR_SG_STAGES]; } SrSgGroup;
typedef struct { uint32_t revision,count; SrSgGroup group[SR_SG_MAX]; char id[SR_SG_MAX][64]; } SrSgConfig;
typedef struct { int hp,maxhp,mp,mpValid; unsigned defenses; int nativeStage,nativeValid,chapterPhase,chapterValid; } SrSgStatus;
static uint32_t sr_sg_crc(const unsigned char *p,size_t n){
 uint32_t crc=0xffffffffu;while(n--){crc^=*p++;for(int b=0;b<8;b++)crc=(crc>>1)^((0u-(crc&1u))&0xedb88320u);}return ~crc;
}
static int sr_sg_id_valid(const char *id){
 size_t n=0;for(;n<64&&id[n];n++){unsigned char c=(unsigned char)id[n];if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-'))return 0;}return n>0&&n<64;
}
static int sr_sg_parse(SrSgConfig *out,const void *bytes,size_t size){
 uint32_t h[4]; if(!out||!bytes||size<16)return 0;memcpy(h,bytes,16);
 int v2=h[0]==SR_SG_MAGIC_V2&&h[1]==2;
 if((!v2&&(h[0]!=SR_SG_MAGIC||h[1]!=1))||h[3]>SR_SG_MAX)return 0;
 size_t stride=sizeof(SrSgGroup)+(v2?64:0);if(size!=16+(size_t)h[3]*stride)return 0;
 if(v2&&sr_sg_crc((const unsigned char *)bytes+16,size-16)!=h[2])return 0;
 static SrSgConfig next;memset(&next,0,sizeof(next));next.revision=h[2];next.count=h[3];
 for(uint32_t i=0;i<h[3];i++){const char *record=(const char *)bytes+16+(size_t)i*stride;
  if(v2){memcpy(next.id[i],record,64);if(!sr_sg_id_valid(next.id[i]))return 0;for(uint32_t j=0;j<i;j++)if(!strcmp(next.id[i],next.id[j]))return 0;record+=64;}
  memcpy(&next.group[i],record,sizeof(SrSgGroup));
 }
 for(uint32_t g=0;g<next.count;g++){
  SrSgGroup *x=&next.group[g];if(x->enabled>1||!x->count||x->count>SR_SG_STAGES||x->hold>1||x->reserved)return 0;
  for(uint32_t s=0;s<x->count;s++){
   SrSgStage *p=&x->stage[s];if(!p->identity[0]||!memchr(p->identity,0,64)||p->form>3||p->priority>65535||p->count>SR_SG_CONDS||p->logic>1||(!s&&p->count))return 0;
   for(uint32_t c=0;c<p->count;c++){SrSgCondition *v=&p->cond[c];if(v->type<1||v->type>5||v->compare>1||v->reserved)return 0;if((v->type==1&&(v->threshold<0||v->threshold>100))||(v->type==2&&(v->threshold< -45||v->threshold>45))||(v->type==3&&(v->threshold<0||v->threshold>65535))||(v->type==4&&(v->threshold<0||v->threshold>1))||(v->type==5&&(v->threshold<0||v->threshold>3)))return 0;}
   if(!v2&&x->enabled)for(uint32_t k=0;k<g;k++)if(next.group[k].enabled)for(uint32_t j=0;j<next.group[k].count;j++)if(!strcmp(p->identity,next.group[k].stage[j].identity))return 0;
  }
 }
 *out=next;return 1;
}
/* Three-valued evaluation: -1 means missing game state. */
static int sr_sg_condition(const SrSgCondition *c,const SrSgStatus *v){
 int64_t lhs,rhs;if(c->type==1){if(v->maxhp<=0||v->hp<0||v->hp>v->maxhp)return -1;lhs=(int64_t)v->hp*100;rhs=(int64_t)v->maxhp*c->threshold;}
 else if(c->type==2){if(!v->mpValid)return -1;lhs=v->mp;rhs=c->threshold;}
 else if(c->type==3){lhs=v->defenses;rhs=c->threshold;} else if(c->type==4){if(!v->nativeValid)return -1;lhs=v->nativeStage;rhs=c->threshold;}
 else {if(!v->chapterValid)return -1;lhs=v->chapterPhase;rhs=c->threshold;}
 return c->compare?lhs<=rhs:lhs>=rhs;
}
static int sr_sg_matches(const SrSgStage *s,const SrSgStatus *v){
 if(!s->count)return 1;int unknown=0;
 for(uint32_t i=0;i<s->count;i++){int x=sr_sg_condition(&s->cond[i],v);if(x<0)unknown=1;else if((!s->logic&&!x)||(s->logic&&x))return x;}
 return unknown?-1:!s->logic;
}
/* Return -1 on uncertainty so callers can keep the current appearance. */
static int sr_sg_select(const SrSgGroup *g,const SrSgStatus *v,int current){
 int best=-1,uncertain=-1;uint32_t priority=0;
 for(uint32_t i=1;i<g->count;i++){int m=sr_sg_matches(&g->stage[i],v);if(m<0){if(uncertain<0||g->stage[i].priority>=g->stage[uncertain].priority)uncertain=(int)i;}else if(m>0&&(best<0||g->stage[i].priority>=priority)){best=(int)i;priority=g->stage[i].priority;}}
 if(uncertain>=0&&(best<0||g->stage[uncertain].priority>priority||(g->stage[uncertain].priority==priority&&uncertain>best)))return -1;
 if(best<0){best=0;priority=g->stage[0].priority;}
 /* Hold means no backwards stage transition; priority only resolves matches. */
 if(g->hold&&current>=0&&(uint32_t)current<g->count&&current>best)return current;
 return best;
}
static int sr_sg_has_native(const SrSgGroup *g){
 if(!g)return 0;for(uint32_t s=0;s<g->count&&s<SR_SG_STAGES;s++)for(uint32_t c=0;c<g->stage[s].count&&c<SR_SG_CONDS;c++)if(g->stage[s].cond[c].type==4)return 1;return 0;
}
/* -1 means do not reselect until this exact source's native state is known. */
static int sr_sg_reselect_stage(const SrSgGroup *g,const SrSgStatus *v,int choice,int presented,int currentNativeValid){
 if(!sr_sg_has_native(g))return choice;
 if(!currentNativeValid||!v||!v->nativeValid)return -1;
 return sr_sg_select(g,v,presented);
}
static int sr_sg_find_id(const SrSgConfig *cfg,const char *id){
 if(!cfg||!id||!id[0])return -1;for(uint32_t g=0;g<cfg->count;g++)if(cfg->group[g].enabled&&!strcmp(id,cfg->id[g]))return (int)g;return -1;
}
static int sr_sg_find(const SrSgConfig *cfg,const char *identity){
 if(!cfg||!identity)return -1;for(uint32_t g=0;g<cfg->count;g++)if(cfg->group[g].enabled)for(uint32_t s=0;s<cfg->group[g].count;s++)if(!strcmp(identity,cfg->group[g].stage[s].identity))return (int)g;return -1;
}
/* Advance hold only after the requested stage has actually appeared.  If
   multiple stages describe exactly the same appearance, keep the previously
   displayed stage while it still matches. */
static int sr_sg_presented(const SrSgGroup *g,const char *identity,int form,int previous){
 if(!g||!identity)return -1;
 if(previous>=0&&(uint32_t)previous<g->count&&g->stage[previous].form==(uint32_t)form&&!strcmp(g->stage[previous].identity,identity))return previous;
 for(uint32_t i=0;i<g->count;i++)if(g->stage[i].form==(uint32_t)form&&!strcmp(g->stage[i].identity,identity))return (int)i;
 return -1;
}
/* Only the director-owned request may be cancelled; an external draw can
   choose the same row independently and must not be silently discarded. */
static int sr_sg_cancel_wanted(int wanted,int owned,int target,int current,int needs_switch){
 return wanted>=0&&wanted==owned&&(wanted!=target||(target==current&&!needs_switch));
}
#ifdef SR_STAGE_GROUPS_WINDOWS
static SrSgConfig g_stageGroups;
static int g_stageNeedsHp;
static void sr_sg_poll(HMODULE module){
 static DWORD at;static FILETIME stamp;static DWORD previousSize;DWORD now=GetTickCount();if((DWORD)(now-at)<500)return;at=now;
 wchar_t path[32768];sr_data_path(module,path,32768,L"native_stage_groups.bin");if(!path[0])return;
 HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);if(f==INVALID_HANDLE_VALUE)return;
 DWORD size=GetFileSize(f,NULL),got=0;FILETIME modified;static unsigned char bytes[16+SR_SG_MAX*(64+sizeof(SrSgGroup))];
 if(GetFileTime(f,NULL,NULL,&modified)&&!(size==previousSize&&CompareFileTime(&modified,&stamp)==0)&&size<=sizeof(bytes)&&ReadFile(f,bytes,size,&got,NULL)&&got==size&&sr_sg_parse(&g_stageGroups,bytes,size)){
  stamp=modified;previousSize=size;g_stageNeedsHp=0;
  for(uint32_t i=0;i<g_stageGroups.count&&!g_stageNeedsHp;i++)if(g_stageGroups.group[i].enabled)for(uint32_t j=0;j<g_stageGroups.group[i].count&&!g_stageNeedsHp;j++)for(uint32_t k=0;k<g_stageGroups.group[i].stage[j].count;k++)if(g_stageGroups.group[i].stage[j].cond[k].type==1){g_stageNeedsHp=1;break;}
 }
 CloseHandle(f);
}
#endif
#endif
