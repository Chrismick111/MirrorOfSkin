#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include "playback_policy.h"
int main(void){
 int counts[128]={0};counts[7]=2;counts[8]=3;counts[9]=4;counts[10]=1;
 assert(sr_donor_tier_detail(counts,10,2)==8);
 assert(sr_donor_tier_detail(counts,9,1)==7);
 assert(sr_donor_tier_detail(counts,7,3)==9);
 assert(sr_donor_tier_detail(counts,10,0)==10);
 counts[8]=0;assert(sr_donor_tier_detail(counts,10,2)==10);
 int boss[128]={0};boss[7]=1;
 if(sr_donor_tier_detail(boss,24,3)!=7){puts("FAIL Boss with only S1 needs an existing attack fallback");return 1;}
 unsigned char allowed[128]={0};allowed[7]=1;boss[8]=2;boss[17]=1;sr_story_attack_mask(boss,allowed);assert(boss[7]==1&&boss[8]==0&&boss[17]==1);
 puts("PASS donor motion-number collision, source skill tier priority, unknown and missing-tier preservation");
 return 0;
}
