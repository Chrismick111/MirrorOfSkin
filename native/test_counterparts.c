#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include "playback_policy.h"
#include "ordinary_body_index.h"
/* Installed ATX times and the coin order observed in PID 56428. Story
   slots here are present in 8044's SST. Body identities come from the
   archive-derived sprite binding index, never from detail numbers. */
static void test_camellia(void){
 const char *enemy="8044_Camellia_AwakenAppearance",*player="10104_YiSang_SpicebushFlowerAppearance";
 double time[128][32]={{0}};
 const double source[3][3]={{.933333,1.083333,1.083333},{2.266667,.816667,2.983333},{.85,.85}};
 const double story[8][3]={{1.177031,1.183333},{3.2,2.3,2.483333},{2.683333},{1.25,1,1.05},
                           {5},{1.25,1.05},{2.3,1.2},{3.983333,2.9,4.483333}};
 int counts[128]={0};uint32_t masks[128]={0};
 SrOrdinaryBodies bodies={0};
 for(int i=0;i<8;i++)for(int j=0;j<3&&story[i][j];j++){
  int d=7+i;counts[d]++;time[d][j]=story[i][j];masks[d]|=UINT32_C(1)<<j;
  bodies.classes[i][j]=sr_ordinary_body_class(enemy,d,j);assert(bodies.classes[i][j]);
 }
 int groups[]={7,8,9},native[][3]={{0,0,1},{0,1,2},{0,0}};
 int total[]={3,3,2};
 for(int t=0;t<3;t++){
  SrSegmentLatch s={0};
  printf("Camellia S%d:",t+1);
  for(int i=0;i<total[t];i++){
   int d=groups[t],k=native[t][i];
   assert(sr_counterpart_choose(&s,i,groups[t],native[t][i],0,source[t][i],time,counts,masks,masks,&bodies,&d,&k));
   unsigned chosen=sr_cached_body(&bodies,d,k);
   for(int j=0;j<i;j++)assert(s.playedBody[j]!=chosen);
   int again=groups[t],index=native[t][i];SrSegmentLatch saved=s;
   assert(sr_counterpart_choose(&s,i,groups[t],native[t][i],0,0,NULL,counts,masks,masks,&bodies,&again,&index)&&again==d&&index==k);
   assert(!memcmp(&saved,&s,sizeof(s)));
   printf(" %d:%d(body %u)",d,k,chosen);
  }
  puts("");
 }
 /* Reverse, enemy's two same-body parts target Yi Sang with three
    ordinary skills. Resolve player sprite data by the actual target name. */
 int reverse=0;
 assert(sr_find_counterpart(enemy,player,&reverse)&&reverse);
 const double playerTimes[][3]={{.933333,1.083333,1.033333},{2.266667,.816667,2.983333},{.85,.883333,1.383333}};
 memset(counts,0,sizeof(counts));memset(masks,0,sizeof(masks));
 for(int g=0;g<3;g++)for(int j=0;j<3;j++){
  int d=g+7;counts[d]++;masks[d]|=UINT32_C(1)<<j;time[d][j]=playerTimes[g][j];
  bodies.classes[g][j]=sr_ordinary_body_class(player,d,j);
 }
 SrSegmentLatch s={0};int d=7,k=0;
 assert(sr_counterpart_choose(&s,0,7,1,0,1.177031,time,counts,masks,masks,&bodies,&d,&k)&&d==7);
 k=1;assert(sr_counterpart_choose(&s,1,7,1,0,1.183333,time,counts,masks,masks,&bodies,&d,&k)&&d!=7);
 int subDetail=8,subPart=2;
 for(int callback=0;callback<2;callback++){
  assert(!sr_counterpart_choose(&s,1,7,2,0,1.183333,time,counts,masks,masks,&bodies,&subDetail,&subPart));
  assert(subDetail==8&&subPart==2&&s.playedBody[1]==sr_cached_body(&bodies,8,2));
 }
 int replayDetail=7,replayPart=1;
 assert(sr_counterpart_choose(&s,1,7,1,0,1.183333,time,counts,masks,masks,&bodies,&replayDetail,&replayPart));
 assert(replayDetail==d&&replayPart==k&&s.playedBody[1]==sr_cached_body(&bodies,d,k));
 printf("Camellia reverse: 7:0(body %u) %d:%d(body %u)\n",s.playedBody[0],d,k,s.playedBody[1]);
 /* A missing player metadata slot, a protected chapter finish, and a
    negative native index must not become an ordinary replacement. */
 uint32_t only[128]={0};only[7]=7;d=7;k=0;
 assert(sr_counterpart_choose(&s,2,7,1,0,1.183333,time,counts,masks,only,&bodies,&d,&k)&&d==7&&k==0);
 k=1;assert(sr_counterpart_choose(&s,3,7,1,2,1.183333,time,counts,masks,masks,&bodies,&d,&k)&&d==7&&k==1);
 k=-1;assert(!sr_counterpart_choose(&s,4,7,1,0,1.183333,time,counts,masks,masks,&bodies,&d,&k)&&k==-1);
}
/* Replay repeated ordinary beats drawn from all supplied asset pairs.
   A separate action per source clip isolates the repeat policy from RNG. */
static void replay_archive(void){
 int pairs=0,changed[2]={0},actions[2]={0},protected=0;
 char src[128],dst[128],identity[128];int ns,nt,chapter;
 while(scanf("%127s %127s %127s %d%d%d",src,dst,identity,&ns,&nt,&chapter)==6){
  int counts[128]={0},reverse=0;uint32_t mask[128]={0};double time[128][32]={{0}};
  SrOrdinaryBodies bodies={0};
  const SrCounterpart *pair=sr_find_counterpart(src,identity,&reverse);assert(pair);
  for(int i=0;i<nt;i++){
   int d,k,n;double t;
   assert(scanf("%d%d%d%lf",&d,&k,&n,&t)==4&&k>=0&&k<32&&sr_attack_group_slot(d)>=0);
   counts[d]=n;time[d][k]=t;mask[d]|=UINT32_C(1)<<k;
   bodies.classes[sr_attack_group_slot(d)][k]=sr_ordinary_body_class(dst,d,k);
  }
  for(int i=0;i<ns;i++){
   int d,k;double t;
   assert(scanf("%d%d%lf",&d,&k,&t)==3);
   if(sr_counterpart_choreography(pair)){protected++;continue;}
   int mapped=sr_verified_paired_attack(counts,src,identity,d,-1);
   if(mapped<0||!counts[mapped])continue;
   int part=k%counts[mapped];
   if(!(mask[mapped]&(UINT32_C(1)<<part)))continue;
   SrSegmentLatch state={0};int g=mapped,j=part;
   assert(sr_counterpart_choose(&state,0,d,k,chapter,t,time,counts,mask,mask,&bodies,&g,&j));
   unsigned first=state.playedBody[0];int eligible=0;
   for(int ed=7;first&&ed<=34;ed++){
    if(chapter&&ed!=mapped)continue;
    for(int ej=0;ej<counts[ed];ej++){
     if(!(mask[ed]&(UINT32_C(1)<<ej)))continue;
     unsigned body=sr_cached_body(&bodies,ed,ej);
     double ratio=time[ed][ej]/t;
     if(body&&body!=first&&ratio>=.67&&ratio<=1.5)eligible=1;
    }
   }
   assert(sr_counterpart_choose(&state,1,d,k,chapter,t,time,counts,mask,mask,&bodies,&g,&j));
   assert((first!=state.playedBody[1])==eligible);
   actions[reverse]++;changed[reverse]+=eligible;
  }
  pairs++;
 }
 printf("Archive replay: %d directional appearances, forward %d/%d and reverse %d/%d repeated beats had verified alternatives, %d Wedge source clips reserved.\n",
        pairs,changed[0],actions[0],changed[1],actions[1],protected);
 assert(pairs>200&&changed[0]>0&&changed[1]>0&&protected>0);
}
int main(int argc,char **argv){
 if(argc==2&&!strcmp(argv[1],"--archive"))replay_archive();
 test_camellia();
 assert(sr_counterpart_ordinary("Camellia_Awaken_S4_Timeline_2"));
 assert(!sr_counterpart_ordinary("Attack_S1_LINK")&&!sr_counterpart_ordinary("Attack_S2_Summon"));
 assert(!sr_counterpart_ordinary("Attack_DuelWin")&&!sr_counterpart_ordinary("Attack_Cinematic"));
 int counts[SR_MOTION_CACHE]={0},tested=0,rev=0;
 const char *player="10315_Donquixote_LeNoir_CaptainAppearance",*look="story_1506_5F_LeNoir_CaptainAppearance";
 assert(sr_counterpart_source_parts(player,look,8)==2);
 assert(sr_counterpart_source_parts(look,player,8)==3);
 assert(sr_counterpart_fallback_part(1,2,3,1)==2);
 assert(sr_counterpart_fallback_part(0,1,4,1)==3);
 assert(sr_counterpart_fallback_part(0,1,4,0)==0);
 assert(sr_counterpart_fallback_part(-1,2,3,1)==-1);
 assert(sr_counterpart_fallback_part(2,3,2,1)==1);
 for(unsigned i=0;i<sizeof(sr_counterparts)/sizeof(sr_counterparts[0]);i++){
  const SrCounterpart *p=sr_counterparts+i;
  assert(sr_counterpart_choreography(p)==(strstr(p->player,"_Wedge")!=NULL));
  assert(sr_find_counterpart(p->player,p->pool,&rev)==p&&!rev);
  assert(sr_find_counterpart(p->story,p->player,&rev)==p&&rev);
  char id[6],full[128];snprintf(id,sizeof(id),"%.5s",p->player);
  snprintf(full,sizeof(full),"story_%s",p->story);
  assert(sr_find_counterpart(id,full,&rev)&&!rev);
  assert(!sr_find_counterpart("10501_UnrelatedAppearance",full,&rev));
  assert(!sr_find_counterpart(p->player,"story_unknown",&rev));
  for(unsigned d=0;d<p->forward+p->reverse;d++){
   const SrCounterpartMotion *m=sr_counterpart_motions+p->offset+d;
   const char *src=d<p->forward?p->player:p->story,*dst=d<p->forward?p->pool:p->player;
   counts[m->target]=m->count;
   assert(sr_counterpart_attack(counts,src,dst,m->source,-1)==m->target);
   int sourceCount=sr_counterpart_source_parts(src,dst,m->source);
   assert(sourceCount>0);
   assert(sr_counterpart_fallback_part(sourceCount-1,sourceCount,m->count,1)==m->count-1);
   counts[m->target]=0;
   assert(sr_counterpart_attack(counts,src,dst,m->source,-1)==-1);
   tested++;
  }
 }
 printf("All exact appearance pairs and %d directional group mappings passed\n",tested);
}
