#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include "playback_policy.h"
int main(void){
 int counts[SR_MOTION_CACHE]={0};counts[7]=3;counts[8]=2;counts[32]=4;
 assert(sr_playback_detail(counts,32,2)==32);
 assert(sr_playback_detail(counts,33,2)==8);
 assert(sr_playback_detail(counts,33,0)==33);
 assert(sr_playback_detail(counts,33,3)==33);
 assert(sr_playback_detail(counts,140,2)==140);
 assert(sr_playback_index(5,3,0)==2);assert(sr_playback_index(0,3,1)==2);
 assert(sr_playback_index(-1,3,0)==-1);assert(sr_playback_index(5,0,1)==5);
 puts("PASS cached playback resolution, native tier fallback, unknown detail preservation, final coin and sentinel indices");
}
