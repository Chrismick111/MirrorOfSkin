#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include "workbench_forms.h"
int main(void){
 struct {uint32_t h[4];SrWfRule r[2];} f={{SR_WF_MAGIC,1,3,1},{{11009,2,30,1,0,{0}}}};SrWfConfig c={0};
 assert(sr_wf_parse(&c,&f,48));assert(sr_wf_stage(&c,11009,0,2,0,30,1,10,100)==1);assert(sr_wf_stage(&c,11009,1,2,0,20,1,10,100)==0);assert(sr_wf_stage(&c,11009,1,2,0,20,0,10,100)==1);
 f.r[0]=(SrWfRule){11009,1,2,3,0,{0}};assert(sr_wf_parse(&c,&f,48));assert(sr_wf_stage(&c,11009,0,4,5,0,1,0,0)==2);assert(sr_wf_stage(&c,11009,0,4,99,0,1,0,0)==3);
 f.r[0]=(SrWfRule){11009,3,20,1,1,{0}};assert(sr_wf_parse(&c,&f,48));assert(sr_wf_stage(&c,11009,0,2,0,0,1,20,100)==1);assert(sr_wf_stage(&c,11009,0,2,0,0,1,21,100)==0);
 f.h[3]=2;f.r[1]=f.r[0];assert(!sr_wf_parse(&c,&f,80));assert(c.count==1);assert(!sr_wf_parse(&c,&f,47));
 puts("PASS form thresholds, exact HP boundary, defense progression cap, invalid observations, malformed/duplicate config preservation");return 0;
}
