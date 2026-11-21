#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "clash_motion.h"
#define SR_MOTION_CACHE 128
typedef struct {const char *base;} SrChapterActor;
typedef struct {void *app;const char *look;const SrChapterActor *chapterActor;int specialClashWarned;signed char chapterRole[128];short clashCount[128];void *clashSparse[128];} Skin;
typedef struct {void *baseApp,*view;const char *baseName;int switching,preserveSpecial,dead;} Unit;
static int cleanup_pending,g_creating,g_presentationGate,camera,busy,switches;
static void *g_duelCameraBoundary,*introUnit,*g_clashOwner,*visible;
static int g_clashRole;
static unsigned char defenseMotions[128];
static Skin skin;
static void *rfield(void *view,const char *name){assert(!strcmp(name,"_curAppearance"));return visible;}
static Skin *skin_for_app(Unit *u,void *app){return app&&app==skin.app?&skin:NULL;}
static int presentation_busy(void *app){return busy;}
static int camera_scope_active(void){return camera;}
static void *unit_switch(Unit *u,Skin *which){assert(!which);switches++;return visible=u->baseApp;}
static void bootlog(const char *s){}
static void *list_item(void *list,int part){return part==0?list:NULL;}
static int is_skill_detail(int d){return (d>=7&&d<=16)||(d>=24&&d<=34);}
#include "clash_render.inc"
static const char *chapter_source(Unit *u,const SrChapterActor *a){return a->base;}
int main(void){
 int base=0,donor=0,view=0,special=0,part=0;
 Unit u={.baseApp=&base,.baseName="10101",.view=&view};
 skin.app=visible=&donor;skin.look="1353_Pinky_DiscipleAppearance";
 skin.chapterRole[8]=1;skin.clashCount[8]=1;
 assert(clash_visible(&u,&base)==&donor);
 assert(clash_visible(&u,&special)==&special);
 g_clashOwner=&u;g_clashRole=2;
 defenseMotions[3]=1;
 assert(clash_request(&u,17)==2&&clash_request(&u,3)==7&&clash_request(&u,4)==7);
 skin.chapterRole[3]=1;assert(clash_indexed_slot(&skin,3,7,&part)==3);
 assert(clash_indexed_slot(&skin,4,7,&part)<0);
 assert(clash_request(&u,9)==0);
 part=5;assert(clash_indexed_slot(&skin,17,2,&part)==8&&part==0);
 part=-1;assert(clash_indexed_slot(&skin,17,2,&part)==8&&part==-1);
 skin.chapterRole[8]=-1;skin.chapterRole[17]=1;
 assert(clash_indexed_slot(&skin,17,2,&part)==17);
 skin.look="10205_Faust_ZweiAppearance";skin.chapterRole[23]=1;
 assert(clash_indexed_slot(&skin,38,3,&part)==23);
 skin.look="8504_kqe1j23Appearance";skin.chapterRole[37]=1;
 assert(clash_indexed_slot(&skin,17,2,&part)==17);
 assert(clash_indexed_slot(&skin,37,2,&part)==37);
 assert(clash_indexed_slot(&skin,41,6,&part)<0);
 assert(clash_indexed_slot(&skin,19,5,&part)==17);
 skin.chapterRole[19]=1;assert(clash_indexed_slot(&skin,19,5,&part)==19);
 skin.look="1525_JeanneBlueprintAppearance";skin.chapterRole[17]=-1;
 skin.clashSparse[17]=&special;skin.clashCount[17]=2;
 part=0;assert(clash_indexed_slot(&skin,17,4,&part)==17&&part==0);
 part=1;assert(clash_indexed_slot(&skin,17,4,&part)<0);
 part=-1;assert(clash_indexed_slot(&skin,17,4,&part)<0);
 void *receiver=visible;camera=1;assert(clash_fallback(&u,&skin,&receiver,32,2)==0&&receiver==&donor&&!switches);
 camera=0;busy=1;assert(clash_fallback(&u,&skin,&receiver,32,2)==0&&receiver==&donor&&!switches);
 busy=0;assert(clash_fallback(&u,&skin,&receiver,32,2)==0&&receiver==visible&&visible==&donor&&switches==0);
 SrChapterActor actor={"10115_YiSang_Index_FatherAppearance"};visible=&donor;skin.chapterActor=&actor;
 assert(clash_request(&u,32)==2&&clash_request(&u,33)==2);
 skin.look="10110_Yisang_DeadButterflyAppearance";skin.clashCount[37]=1;
 assert(skin_has_special_clash(&skin));
 skin.look="Unknown_NoClashAppearance";skin.chapterActor=NULL;assert(!skin_has_special_clash(&skin));
 skin.chapterActor=(const SrChapterActor *)1;assert(skin_has_special_clash(&skin));
 puts("Clash routing, authored and sparse poses, native camera and visible fallback passed.");
}
