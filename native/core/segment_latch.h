#ifndef SR_SEGMENT_LATCH_H
#define SR_SEGMENT_LATCH_H
#include <stdint.h>
#include <string.h>
#include <limits.h>
#define SR_VARIETY_COINS 128
#define SR_SEGMENT_POOL_MAX 672
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
 uint32_t usedClips[128];
 unsigned char poolDetail[SR_SEGMENT_POOL_MAX],poolClip[SR_SEGMENT_POOL_MAX];
 int poolCount,poolCursor,poolRequested;
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
/* Each coin uses its actual source clip. A valid request from the native
   order wins: only supplement it when the source clip index has outgrown the
   target group. Fallback clips must come from an ordinary attack timeline of
   another skill group with a compatible duration. Within a group clips advance
   in cycle order, so a longer source attack continues instead of wrapping to
   the same body. */
static int sr_segment_target_valid(const int counts[128],const uint32_t ordinary[128],int detail,int index){
 int slot=sr_attack_group_slot(detail);
 if(!counts||!ordinary||slot<0||index<0)return 0;
 int n=counts[detail];
 return n>=1&&n<=32&&index<n&&(ordinary[detail]&(UINT32_C(1)<<index))!=0;
}
static void sr_segment_build_pool(SrSegmentLatch *s,int requested,const int counts[128],const uint32_t ordinary[128]){
 s->poolCount=0;s->poolCursor=0;s->poolRequested=requested;
 for(unsigned i=0;i<21;i++){
  int d=i<10?7+(int)i:14+(int)i;
  if(d==requested)continue;
  int n=counts[d];if(n<1||n>32||!ordinary[d])continue;
  for(int k=0;k<n;k++)if(ordinary[d]&(UINT32_C(1)<<k))s->poolDetail[s->poolCount]=d,s->poolClip[s->poolCount++]=(unsigned char)k;
 }
}
static int sr_segment_pool_advance(SrSegmentLatch *s,int detail,int clip){
 for(int i=0;i<s->poolCount;i++)if(s->poolDetail[i]==detail&&s->poolClip[i]==clip){s->poolCursor=(i+1)%s->poolCount;return 1;}
 return 0;
}
static int sr_segment_pool_all_used(const SrSegmentLatch *s){
 for(int i=0;i<s->poolCount;i++){
  int d=s->poolDetail[i],k=s->poolClip[i];
  if(!(s->usedClips[d]&(UINT32_C(1)<<k)))return 0;
 }
 return s->poolCount>0;
}
static int sr_segment_pick(SrSegmentLatch *s,int coin,unsigned ordinal,double source,
                           const double donor[128][32],const int counts[128],
                           const uint32_t ordinary[128],const SrOrdinaryBodies *bodies,
                           int sourceIndex,int *detail,int *index){
 if(coin<0||coin>=SR_VARIETY_COINS||!s||!detail||!index)return 0;
 if(!s->seen[coin]){
  int requested=*detail,requestedIndex=*index;
  int targetValid=sr_segment_target_valid(counts,ordinary,requested,requestedIndex);
  int overflow=targetValid&&counts&&((sourceIndex>=0&&sourceIndex>=counts[requested])||(coin>=counts[requested]));
  s->seen[coin]=1;
  /* The ordinary fallback can still be the previous coin's visible body. */
  s->playedBody[coin]=sr_cached_body(bodies,requested,requestedIndex);
  unsigned previous=coin?s->playedBody[coin-1]:0;
  if(targetValid&&!overflow){
   s->groups[coin]=(unsigned char)requested;s->indices[coin]=(unsigned char)requestedIndex;
   s->uses[requested]++;s->nextClip[requested]=(unsigned char)((requestedIndex+1)%counts[requested]);
   s->usedClips[requested]|=UINT32_C(1)<<requestedIndex;
   *detail=requested;*index=requestedIndex;return 1;
  }
  if(!counts||!ordinary)return targetValid;
  if(overflow&&(s->poolCount==0||s->poolRequested!=requested))sr_segment_build_pool(s,requested,counts,ordinary);
  if(overflow&&sr_segment_pool_all_used(s)){
   int idx=s->poolCursor%s->poolCount;
   int d=s->poolDetail[idx],k=s->poolClip[idx];
   s->poolCursor=(idx+1)%s->poolCount;
   s->groups[coin]=(unsigned char)d;s->indices[coin]=(unsigned char)k;
   s->uses[d]++;s->nextClip[d]=(unsigned char)((k+1)%counts[d]);
   s->usedClips[d]|=UINT32_C(1)<<k;
   *detail=d;*index=k;return 1;
  }
  int winner=-1,clip=-1;
  int timed=source>0&&donor;
  if(timed){
   int least=256,bestChanges=-1,bestDistance=INT_MAX,bestReused=-1;
   double best=1e30;
   /* Visit only attack details. Rotate the starting group across uses of a skill. */
   for(unsigned i=0;i<21;i++){
    unsigned offset=(i+ordinal)%21;
    int d=offset<10?7+(int)offset:14+(int)offset;
    int n=counts[d];if(n<1||n>32||!ordinary[d])continue;
    if(overflow&&d==requested)continue;
    for(int j=0;j<n;j++){
     int k=(s->nextClip[d]+j)%n;
     if(!(ordinary[d]&(UINT32_C(1)<<k)))continue;
     double ratio=donor[d][k]/source;
     if(!(ratio>=.67&&ratio<=1.5))continue;
     double error=ratio>=1?ratio-1:1/ratio-1;
     unsigned body=sr_cached_body(bodies,d,k);
     int changes=previous&&body&&body!=previous;
     int distance=d>requested?d-requested:requested-d;
     int reused=(s->usedClips[d]&(UINT32_C(1)<<k))!=0;
     int better=0;
     if(winner<0)better=1;
     else if(reused!=bestReused)better=reused<bestReused;
     else if(error+1e-9<best)better=1;
     else if(error<=best+1e-9&&changes!=bestChanges)better=changes>bestChanges;
     else if(error<=best+1e-9&&changes==bestChanges&&s->uses[d]!=least)better=s->uses[d]<least;
     else if(error<=best+1e-9&&changes==bestChanges&&s->uses[d]==least&&distance!=bestDistance)better=distance<bestDistance;
     if(better){bestChanges=changes;best=error;least=s->uses[d];bestDistance=distance;bestReused=reused;winner=d;clip=k;}
    }
   }
  }
  /* If timings are not cached yet, or every duration-compatible fallback was
     rejected, continue with another ordinary attack group anyway. Repeating
     the short target group is worse than a safe, sequential donor clip. */
  if(winner<0&&(overflow||!targetValid)){
   int least=256,bestChanges=-1,bestDistance=INT_MAX,bestReused=-1;
   for(unsigned i=0;i<21;i++){
    unsigned offset=(i+ordinal)%21;
    int d=offset<10?7+(int)offset:14+(int)offset;
    int n=counts[d];if(n<1||n>32||!ordinary[d])continue;
    if(overflow&&d==requested)continue;
    for(int j=0;j<n;j++){
     int k=(s->nextClip[d]+j)%n;
     if(!(ordinary[d]&(UINT32_C(1)<<k)))continue;
     unsigned body=sr_cached_body(bodies,d,k);
     int changes=previous&&body&&body!=previous;
     int distance=d>requested?d-requested:requested-d;
     int reused=(s->usedClips[d]&(UINT32_C(1)<<k))!=0;
     int better=0;
     if(winner<0)better=1;
     else if(reused!=bestReused)better=reused<bestReused;
     else if(changes!=bestChanges)better=changes>bestChanges;
     else if(s->uses[d]!=least)better=s->uses[d]<least;
     else if(distance!=bestDistance)better=distance<bestDistance;
     if(better){bestChanges=changes;least=s->uses[d];bestDistance=distance;bestReused=reused;winner=d;clip=k;}
    }
   }
  }
  if(winner>=0){
   s->groups[coin]=(unsigned char)winner;s->indices[coin]=(unsigned char)clip;
   s->playedBody[coin]=sr_cached_body(bodies,winner,clip);
   s->uses[winner]++;s->nextClip[winner]=(unsigned char)((clip+1)%counts[winner]);
   s->usedClips[winner]|=UINT32_C(1)<<clip;
   if(overflow)sr_segment_pool_advance(s,winner,clip);
  }
 }
 if(!s->groups[coin])return 0;
 *detail=s->groups[coin];*index=s->indices[coin];return 1;
}
#endif
