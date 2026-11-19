#ifndef SR_SEGMENT_LATCH_H
#define SR_SEGMENT_LATCH_H
#include <stdint.h>
#include <string.h>
#define SR_VARIETY_COINS 128
typedef struct {unsigned classes[21][32];} SrOrdinaryBodies;
static int sr_attack_group_slot(int detail){
 if(detail>=7&&detail<=16)return detail-7;
 return detail>=24&&detail<=34?detail-14:-1;
}
static unsigned sr_cached_body(const SrOrdinaryBodies *bodies,int detail,int part){
 int slot=sr_attack_group_slot(detail);
 return bodies&&slot>=0&&part>=0&&part<32?bodies->classes[slot][part]:0;
}
typedef struct {
 void *action,*viewer,*app;
 int stage;
 unsigned char seen[SR_VARIETY_COINS],groups[SR_VARIETY_COINS],indices[SR_VARIETY_COINS];
 unsigned playedBody[SR_VARIETY_COINS];
 unsigned char uses[128],nextClip[128];
} SrSegmentLatch;
static void sr_segment_clear(SrSegmentLatch *s){memset(s,0,sizeof(*s));}
static int sr_segment_scope(SrSegmentLatch *s,void *action,void *viewer,void *app,int stage){
 if(s->action==action&&s->viewer==viewer&&s->app==app&&s->stage==stage)return 0;
 sr_segment_clear(s);s->action=action;s->viewer=viewer;s->app=app;s->stage=stage;return 1;
}
static int sr_ordinary_timeline(const char *name){
 if(!name||!*name)return 0;
 return !strstr(name,"_Link")&&!strstr(name,"_link")&&!strstr(name,"_LINK");
}
/* Each coin uses its actual source clip, even when several coins repeat a
   native index. Pick a different timing-compatible group before reusing one.
   Within a group continue from the last selected clip. */
static int sr_segment_pick(SrSegmentLatch *s,int coin,unsigned ordinal,double source,
                           const double donor[128][32],const int counts[128],
                           const uint32_t ordinary[128],const SrOrdinaryBodies *bodies,int *detail,int *index){
 if(coin<0||coin>=SR_VARIETY_COINS||!s||!detail||!index)return 0;
 if(!s->seen[coin]){
  s->seen[coin]=1;
  /* The ordinary fallback can still be the previous coin's visible body. */
  s->playedBody[coin]=sr_cached_body(bodies,*detail,*index);
  unsigned previous=coin?s->playedBody[coin-1]:0;
  if(!(source>0)||!donor||!counts||!ordinary)return 0;
  int winner=-1,clip=-1,least=256,knownChange=0;
  double best=1e30;
  /* Visit only attack details. Rotate the starting group across uses of a skill. */
  for(unsigned i=0;i<21;i++){
   unsigned offset=(i+ordinal)%21;
   int d=offset<10?7+(int)offset:14+(int)offset;
   int n=counts[d];if(n<1||n>32||!ordinary[d])continue;
   for(int j=0;j<n;j++){
    int k=(s->nextClip[d]+j)%n;
    if(!(ordinary[d]&(UINT32_C(1)<<k)))continue;
    double ratio=donor[d][k]/source;
    if(!(ratio>=.67&&ratio<=1.5))continue;
    double error=ratio>=1?ratio-1:1/ratio-1;
    /* A small timing difference is perceptually interchangeable. Prefer the
       first clip in cycle order on ties, otherwise use the closer duration. */
    unsigned body=sr_cached_body(bodies,d,k);
    int changes=previous&&body&&body!=previous;
    if(changes<knownChange)continue;
    if(changes>knownChange||s->uses[d]<least||(s->uses[d]==least&&error+.07<best)){
     knownChange=changes;
     least=s->uses[d];best=error;winner=d;clip=k;
    }
   }
  }
  if(winner>=0){
   s->groups[coin]=(unsigned char)winner;s->indices[coin]=(unsigned char)clip;
   s->playedBody[coin]=sr_cached_body(bodies,winner,clip);
   s->uses[winner]++;s->nextClip[winner]=(unsigned char)(clip+1);
  }
 }
 if(!s->groups[coin])return 0;
 *detail=s->groups[coin];*index=s->indices[coin];return 1;
}
#endif
