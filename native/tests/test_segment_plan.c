#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include "segment_latch.h"

static void setup(int counts[128],uint32_t ordinary[128],double donor[128][32]){
 memset(counts,0,sizeof(int)*128);memset(ordinary,0,sizeof(uint32_t)*128);
 for(int d=0;d<128;d++)for(int i=0;i<32;i++)donor[d][i]=0;
}

int main(void){
 /* A new viewer within the same action must not reset the segment plan. */
 SrSegmentLatch scope={0};
 assert(sr_segment_scope(&scope,(void *)1,(void *)2,(void *)3,0,0)==1);
 assert(sr_segment_scope(&scope,(void *)1,(void *)4,(void *)3,0,0)==0);
 assert(sr_segment_scope(&scope,(void *)1,(void *)4,(void *)3,0,1)==1);
 int counts[128];uint32_t ordinary[128];double donor[128][32];SrOrdinaryBodies bodies={0};

 /* A valid native request must win even when another group has fewer uses. */
 setup(counts,ordinary,donor);
 counts[7]=3;ordinary[7]=0x7;counts[8]=2;ordinary[8]=0x3;
 for(int i=0;i<3;i++)donor[7][i]=1;for(int i=0;i<2;i++)donor[8][i]=1;
 SrSegmentLatch latch={0};int detail=7,index=1;
 assert(sr_segment_pick(&latch,0,0,1,donor,counts,ordinary,&bodies,1,0,&detail,&index));
 assert(detail==7&&index==1);

 /* When the source clip index exceeds the requested group, continue in a
    different attack group instead of wrapping in the same group. */
 setup(counts,ordinary,donor);sr_segment_clear(&latch);detail=7;index=1;
 counts[7]=2;ordinary[7]=0x3;counts[8]=3;ordinary[8]=0x7;
 for(int i=0;i<2;i++)donor[7][i]=1;for(int i=0;i<3;i++)donor[8][i]=1;
 assert(sr_segment_pick(&latch,0,0,1,donor,counts,ordinary,&bodies,2,0,&detail,&index));
 assert(detail==8&&index==0);

 /* Linked timelines and non-attack details are never fallback candidates. */
 setup(counts,ordinary,donor);sr_segment_clear(&latch);detail=7;index=0;
 counts[7]=2;ordinary[7]=0x3;counts[8]=2;ordinary[8]=0x3;
 counts[9]=2;ordinary[9]=0x3;counts[17]=2;ordinary[17]=0x3;
 for(int i=0;i<2;i++){donor[7][i]=1;donor[8][i]=1;donor[9][i]=1;donor[17][i]=1;}
 assert(sr_segment_pick(&latch,0,0,1,donor,counts,ordinary,&bodies,2,0,&detail,&index));
 assert(detail==8&&index==0);

 /* Without duration data, keep the valid original request instead of guessing. */
 setup(counts,ordinary,donor);sr_segment_clear(&latch);detail=7;index=1;
 counts[7]=3;ordinary[7]=0x7;counts[8]=3;ordinary[8]=0x7;
 assert(sr_segment_pick(&latch,0,0,0,donor,counts,ordinary,&bodies,0,0,&detail,&index));
 assert(detail==7&&index==1);

 /* Repeated overflow continues in cycle order within the fallback group. */
 setup(counts,ordinary,donor);sr_segment_clear(&latch);
 counts[7]=2;ordinary[7]=0x3;counts[8]=3;ordinary[8]=0x7;
 for(int i=0;i<2;i++)donor[7][i]=1;for(int i=0;i<3;i++)donor[8][i]=1;
 detail=7;index=0;
 assert(sr_segment_pick(&latch,0,0,1,donor,counts,ordinary,&bodies,2,0,&detail,&index));
 assert(detail==8&&index==0);
 detail=7;index=1;
 assert(sr_segment_pick(&latch,1,1,1,donor,counts,ordinary,&bodies,3,0,&detail,&index));
 assert(detail==8&&index==1);

 /* A repeated native index must advance inside the same target skill group
    before borrowing other groups. */
 setup(counts,ordinary,donor);sr_segment_clear(&latch);
 counts[8]=3;ordinary[8]=0x7;
 detail=8;index=0;
 assert(sr_segment_pick(&latch,0,0,0,NULL,counts,ordinary,&bodies,0,0,&detail,&index));
 assert(detail==8&&index==0);
 detail=8;index=0;
 assert(sr_segment_pick(&latch,1,1,0,NULL,counts,ordinary,&bodies,0,0,&detail,&index));
 assert(detail==8&&index==1);
 /* A coin overflow must also continue when the game's clip index is still in range. */
 setup(counts,ordinary,donor);sr_segment_clear(&latch);
 counts[7]=2;ordinary[7]=0x3;counts[8]=3;ordinary[8]=0x7;
 for(int i=0;i<2;i++)donor[7][i]=1;for(int i=0;i<3;i++)donor[8][i]=1;
 detail=7;index=0;
 assert(sr_segment_pick(&latch,2,0,1,donor,counts,ordinary,&bodies,0,0,&detail,&index));
 assert(detail==8&&index==0);

 /* Single-clip fallback groups must be consumed before any clip repeats. */
 setup(counts,ordinary,donor);sr_segment_clear(&latch);
 counts[7]=1;ordinary[7]=0x1;counts[8]=1;ordinary[8]=0x1;counts[9]=1;ordinary[9]=0x1;
 detail=7;index=0;
 assert(sr_segment_pick(&latch,1,0,0,NULL,counts,ordinary,&bodies,0,0,&detail,&index));
 int first=detail;
 detail=7;index=0;
 assert(sr_segment_pick(&latch,2,1,0,NULL,counts,ordinary,&bodies,0,0,&detail,&index));
 assert(detail!=7&&detail!=first);
 /* Missing timing data must not turn a coin overflow back into a repeat. */
 setup(counts,ordinary,donor);sr_segment_clear(&latch);
 counts[7]=2;ordinary[7]=0x3;counts[8]=3;ordinary[8]=0x7;
 detail=7;index=0;
 assert(sr_segment_pick(&latch,2,0,0,NULL,counts,ordinary,&bodies,0,0,&detail,&index));
 assert(detail==8&&index==0);
 /* After the fallback pool is exhausted, recycle the fallback pool instead
    of locking onto one candidate group forever. */
 setup(counts,ordinary,donor);sr_segment_clear(&latch);
 counts[7]=1;ordinary[7]=0x1;counts[8]=1;ordinary[8]=0x1;counts[9]=1;ordinary[9]=0x1;
 detail=7;index=0;
 assert(sr_segment_pick(&latch,1,0,0,NULL,counts,ordinary,&bodies,0,0,&detail,&index));int p1=detail;
 detail=7;index=0;
 assert(sr_segment_pick(&latch,2,1,0,NULL,counts,ordinary,&bodies,0,0,&detail,&index));int p2=detail;
 assert(p1!=p2);
 detail=7;index=0;
 assert(sr_segment_pick(&latch,3,2,0,NULL,counts,ordinary,&bodies,0,0,&detail,&index));int p3=detail;
 assert(p3!=p2&&p3!=7);
 /* Final coin always lands on a real authored part of the selected group. */
 setup(counts,ordinary,donor);sr_segment_clear(&latch);
 counts[9]=3;ordinary[9]=0x7;
 detail=9;index=0;
 assert(sr_segment_pick(&latch,3,0,0,NULL,counts,ordinary,&bodies,0,1,&detail,&index));
 assert(detail==9&&index==2);
 puts("PASS segment allocation: original request first, overflow continuation, attack-only candidates, cycle order, final coin");
 return 0;
}
