#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include "form_state.h"
int main(void){
 SrFormState s={0};
 sr_form_round(&s,1,45,1);assert(!s.index_awake);
 sr_form_evade(&s);sr_form_round(&s,2,24,1);assert(!s.index_awake);
 sr_form_round(&s,3,25,1);assert(s.index_awake);
 sr_form_round(&s,3,-1,1);assert(s.index_awake); /* repeated callback ignored */
 sr_form_round(&s,4,1,1);assert(s.index_awake);
 sr_form_round(&s,5,0,1);assert(!s.index_awake);
 sr_form_round(&s,6,25,0);assert(!s.index_awake);
 assert(sr_form_stage(&s,"10410",3,0,1)==1);
 sr_form_evade(&s);assert(sr_form_stage(&s,"10410",3,0,1)==2);
 sr_form_evade(&s);assert(sr_form_stage(&s,"10410",3,0,1)==2);
 sr_form_survived_hit(&s,21,100);assert(!s.kcorp_helmet);
 sr_form_survived_hit(&s,0,100);assert(!s.kcorp_helmet);
 sr_form_survived_hit(&s,20,100);assert(s.kcorp_helmet);
 sr_form_survived_hit(&s,100,100);assert(s.kcorp_helmet);
 assert(sr_form_stage(&s,"10312",2,-1,1)==1);
 assert(sr_form_stage(&s,"10312",2,0,1)==0);
 assert(sr_form_stage(&s,"10913",2,-1,0)==0);
 assert(sr_form_stage(&s,"11009",2,44,1)==0);
 assert(sr_form_stage(&s,"11009",2,45,1)==1);
 s=(SrFormState){0};assert(!s.evades&&!s.kcorp_helmet&&!s.index_awake);
 puts("PASS form state: evade stages, round deduplication, 25/0 hysteresis, 20% survived-hit latch, sanity boundary and battle reset");
}
