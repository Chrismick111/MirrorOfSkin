#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include "special_policy.h"
int main(void){
 assert(!sr_scissors_suspend("10917_Rodion_ScissorsAppearance",1));
 assert(sr_scissors_suspend("10917_Rodion_ScissorsAppearance",0));
 assert(!sr_scissors_suspend("10916_Rodion_Thumb_FatherAppearance",0));
 assert(sr_dawn_form(45,1)==1);assert(sr_dawn_form(44,1)==0);assert(sr_dawn_form(-45,1)==0);
 assert(sr_dawn_form(45,0)==-1);assert(sr_dawn_form(46,1)==-1);
 assert(sr_dawn_spine_name("11009_Sinclair_Philip_AwakenAppearance",1));
 assert(!sr_dawn_spine_name("11009_Sinclair_Philip_AwakenAppearance",0));
 assert(sr_dawn_spine_name("11009_Sinclair_PhilipAppearance",0));
 assert(!sr_dawn_spine_name("11010_Sinclair_Zwei_WestAppearance",1));
 assert(sr_is_scissors_source("10917_Rodion_ScissorsAppearance"));assert(!sr_is_scissors_source("10916_Rodion_Thumb_FatherAppearance"));
 puts("PASS sanity boundary/invalid state, named spine matching, special-source isolation");
}
