#include <stdio.h>
#include "playback_policy.h"
int main(void){int counts[128]={0},map[128];for(int i=0;i<128;i++)map[i]=-1;counts[7]=1;counts[10]=2;map[24]=10;
if(sr_native_motion_detail(counts,map,24,24)!=10)return 1;
map[24]=11;if(sr_native_motion_detail(counts,map,24,7)!=7)return 2;
if(sr_native_motion_detail(counts,map,-1,7)!=7)return 3;
map[7]=7;map[24]=10;if(sr_native_motion_detail(counts,map,24,7)!=7)return 4;
int boss[128]={0};boss[7]=1;if(!sr_prewarm_attacks_valid(boss,1)||sr_prewarm_attacks_valid(boss,0))return 5;boss[7]=0;if(sr_prewarm_attacks_valid(boss,1))return 6;
counts[0]=1;map[24]=0;if(sr_native_motion_detail(counts,map,24,24)!=24)return 7;
puts("PASS native verified fallback priority and unavailable mapping preservation");return 0;}
