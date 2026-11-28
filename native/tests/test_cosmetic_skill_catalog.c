#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "cosmetic_skill_catalog.h"

int main(void){
 assert(sr_cosmetic_stock_portrait("11116",NULL)==11116);
 assert(sr_cosmetic_stock_portrait(NULL,"story_90004_backstreet_slashmobAppearance")==0);
 assert(!strcmp(sr_cosmetic_cached_portrait("story_90004_backstreet_slashmobAppearance"),"99b9dba55775a70c5299619e.png"));
 assert(!sr_cosmetic_cached_portrait("unknown-mod"));
 assert(sr_cosmetic_source_conditional(1111605)==1);
 assert(sr_cosmetic_source_conditional(1111603)==0);
 assert(sr_cosmetic_source_conditional(199999999)==-1);
 assert(sr_cosmetic_stock_skill("11116",NULL,1010101,1,0,0)==1111601);
 assert(sr_cosmetic_stock_skill("11116",NULL,1111604,1,1,0)==1111604);
 assert(sr_cosmetic_stock_skill("11116",NULL,1111607,1,1,0)==1111607);
 assert(sr_cosmetic_stock_skill("11116",NULL,1111605,3,0,1)==1111605);
 assert(sr_cosmetic_stock_skill("10101",NULL,1111605,3,0,1)==0);
 assert(sr_cosmetic_stock_skill("11116",NULL,1010104,1,1,0)==0); /* two different defenses */
 assert(sr_cosmetic_stock_skill("11116",NULL,1010101,1,1,0)==0);
 assert(sr_cosmetic_stock_skill("story_missing",NULL,1010101,1,0,0)==0);
 const char *chief="1291_Village_ChiefAppearance";
 assert(sr_cosmetic_stock_skill(NULL,chief,1010102,2,0,0)==0);
 assert(sr_cosmetic_stock_display_skill(NULL,chief,1010102,2,0,0)==129103);
 assert(sr_cosmetic_stock_display_skill(NULL,chief,1010102,0,0,0)==129103);
 assert(sr_cosmetic_stock_skill("10101",NULL,1010203,2,0,0)==1010103);
 assert(sr_cosmetic_stock_display_skill("10101",NULL,1010203,2,0,0)==1010102);
 assert(sr_cosmetic_stock_display_skill("10101",NULL,1041504,1,1,0)==0); /* evade vs guard */
 assert(sr_cosmetic_stock_display_skill("10101",NULL,1070404,1,1,0)==1010104);
 assert(sr_cosmetic_stock_display_skill(NULL,chief,1010102,2,0,1)==0);
 assert(sr_cosmetic_stock_display_skill(NULL,chief,1111605,2,0,1)==0);
 const char *knight=sr_ui_appearance_key("1288_lastknight_appearance");
 assert(knight&&!strcmp(knight,"1288_LastKnight_Appearance"));
 assert(sr_cosmetic_stock_skill("1288",NULL,128803,3,0,1)==0);
 assert(sr_cosmetic_stock_skill("1288",knight,128803,3,0,1)==128803);
 assert(!sr_ui_appearance_key("1288_other_appearance"));
 const char *whale="8102_FluorescentWhaleAppearance";
 assert(sr_ui_owner(NULL,whale)->count==8);
 assert(sr_cosmetic_stock_display_skill(NULL,whale,810201,1,0,0)==810201);
 assert(sr_cosmetic_stock_display_skill(NULL,whale,813905,1,0,0)==810205);
 assert(sr_cosmetic_stock_display_skill(NULL,whale,813901,1,0,0)==0);
 return 0;
}
