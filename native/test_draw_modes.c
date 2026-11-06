#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include "draw_modes.h"
int main(void){
 SrDrawState s={0};double w[]={1,2,3,0};int ids[]={10,11,12,13};
 int a=sr_draw_mode(&s,1,ids,w,4,0.0),b=sr_draw_mode(&s,1,ids,w,4,0.0),c=sr_draw_mode(&s,1,ids,w,4,0.0);
 assert(a==10&&b==11&&c==12);assert(sr_draw_mode(&s,1,ids,w,4,0.0)==10);
 s=(SrDrawState){0};assert(sr_draw_mode(&s,2,ids,w,4,0.9)==10);assert(sr_draw_mode(&s,2,ids,w,4,0.9)==11);assert(sr_draw_mode(&s,2,ids,w,4,0.9)==12);assert(sr_draw_mode(&s,2,ids,w,4,0.9)==10);
 s=(SrDrawState){0};assert(sr_draw_mode(&s,0,ids,w,4,0.99)==12);
 assert(sr_draw_mode(&s,2,ids,w,4,0)==10);assert(sr_draw_mode(&s,2,ids,w,4,0)==11);w[1]=0;assert(sr_draw_mode(&s,2,ids,w,4,0)==12);
 w[0]=w[2]=0;assert(sr_draw_mode(&s,1,ids,w,4,0)==-1);
 puts("PASS weighted independent, weighted round without replacement, ordered wrap, zero weights and live eligibility changes");return 0;
}
