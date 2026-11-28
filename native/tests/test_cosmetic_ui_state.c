#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "cosmetic_ui_state.h"

int main(void){
 int stock,own,other,fresh;
 assert(cosmetic_ui_change(&stock,NULL,&own)==COSMETIC_UI_APPLY);
 assert(cosmetic_ui_change(&own,&own,&own)==COSMETIC_UI_KEEP);
 assert(cosmetic_ui_change(&own,&own,&other)==COSMETIC_UI_APPLY);
 assert(cosmetic_ui_change(&own,&own,NULL)==COSMETIC_UI_RESTORE);
 assert(cosmetic_ui_change(&fresh,&own,NULL)==COSMETIC_UI_KEEP);
 assert(cosmetic_ui_change(&fresh,&own,&own)==COSMETIC_UI_APPLY);
 assert(cosmetic_ui_change(&fresh,NULL,NULL)==COSMETIC_UI_KEEP);
 assert(cosmetic_ui_tier(2,0)==2);
 assert(cosmetic_ui_tier(3,1)==3);
 assert(cosmetic_ui_tier(-1,2)==2);
 assert(cosmetic_ui_tier(4,0)==0);
 assert(cosmetic_ui_tier(0,4)==0);
 assert(cosmetic_ui_tier(0,0)==0);
 return 0;
}
