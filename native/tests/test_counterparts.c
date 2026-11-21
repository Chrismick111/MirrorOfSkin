#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include "playback_policy.h"
int main(void){
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
