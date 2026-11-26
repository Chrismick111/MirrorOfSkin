#include <assert.h>
#include "appearance_visibility_state.h"
int main(void){
 int a,b;void *hidden=0;
 sr_visibility_event(&hidden,&a,&a,0,1);assert(!hidden);
 sr_visibility_event(&hidden,&a,&b,0,0);assert(!hidden);
 sr_visibility_event(&hidden,&a,&a,0,0);assert(sr_visibility_suspended(hidden,&a));
 sr_visibility_event(&hidden,&a,&a,1,1);assert(sr_visibility_suspended(hidden,&a));
 sr_visibility_event(&hidden,&a,&a,1,0);assert(!hidden);
 sr_visibility_event(&hidden,&a,&a,0,0);sr_visibility_selection(&hidden,&b);assert(!hidden);
 assert(sr_retreat_next(0,-1)==0);assert(sr_retreat_next(1,-1)==1);
 assert(sr_retreat_next(0,1)==1);assert(sr_retreat_next(1,0)==0);
 assert(!sr_retreat_hide_ready(1,1,4999));assert(sr_retreat_hide_ready(1,1,5000));
 assert(sr_retreat_hide_ready(0,0,0));
 return 0;
}
