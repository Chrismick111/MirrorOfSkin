#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"

typedef struct { int active, affects; void *parent; } TestGo;
typedef struct { void *items[12]; int count; } TestList;
typedef struct { TestList *objects; uint8_t spine; int detail; } TestMotion;
typedef struct { void *spine; TestList *viewInfo; } TestParts;
typedef struct { void *sprite; TestList *spines; TestParts *parts; TestList *motions; } TestApp;
static TestGo donorGo={1}, sourceGo={0}, idle={1}, skill1={1}, skill2={0}, skill3={0}, retire={0};
static TestGo externalFx={1}, writingFx={1}, motionRoot={1}, spriteGo={1}, spineGo={1};
static uint8_t spriteHidden,spineHidden,spineEnabled=1,spriteEnabled,spriteHasArt;
static int currentDetail=18;
static void *currentApp;
static TestApp app;
static int source,other,partsInit,partsReset;
static TestParts parts;
static void *spine=&spineHidden;

enum { GET_GO=1, GET_ACTIVE, SET_ACTIVE, GET_DETAIL, GET_FORCE, SET_FORCE,
       GET_TR, FIND, GET_PARENT, COUNT, ITEM, MOTION_DETAIL, PARTS_INIT, PARTS_RESET, GET_APP, GET_SPRITE, GET_ENABLED };
static void *test_class(void *obj){return (void *)1;}
static void *test_parent(void *klass){return NULL;}
static void *test_field(void *klass,const char *name){
 const char *names[]={"_curAppearance","sprenderer_charactermotion","_spineSkins","parts",
                      "motionList","isSpineAnim","motionObjects","_spine_renderer","abnormalitySpine","partsViewInfo"};
 for(int i=0;i<10;i++)if(!strcmp(names[i],name))return (void *)(uintptr_t)(i+1);
 return NULL;
}
static size_t test_offset(void *field){
 size_t offsets[]={0,offsetof(TestApp,sprite),offsetof(TestApp,spines),offsetof(TestApp,parts),
                   offsetof(TestApp,motions),offsetof(TestMotion,spine),offsetof(TestMotion,objects),0,
                   offsetof(TestParts,spine),offsetof(TestParts,viewInfo)};
 return offsets[(uintptr_t)field-1];
}
static void *test_method(void *klass,const char *name,int args){
 const struct {const char *name;int id;} methods[]={
  {"get_gameObject",GET_GO},{"get_activeInHierarchy",GET_ACTIVE},{"get_CurrentMotionDetail",GET_DETAIL},
  {"get_forceRenderingOff",GET_FORCE},{"set_forceRenderingOff",SET_FORCE},{"Find",FIND},{"get_parent",GET_PARENT},
  {"get_Count",COUNT},{"get_Item",ITEM},{"get_MotionDetail",MOTION_DETAIL},{"Init",PARTS_INIT},{"ResetParts",PARTS_RESET},
  {"get_enabled",GET_ENABLED},{"get_sprite",GET_SPRITE}};
 for(int i=0;i<sizeof(methods)/sizeof(methods[0]);i++){
  if(!strcmp(methods[i].name,name))return (void *)(uintptr_t)methods[i].id;
 }
 return NULL;
}
static const char *test_class_name(void *klass){return "AbnormalityParts";}
static void *test_string(const char *text){
 assert(!strcmp(text,"Motion"));return (void *)1;
}
static void *test_unbox(void *value){return value;}
static void *test_invoke(void *method,void *object,void **args,void **exception){
 *exception=NULL;
 TestGo *go=object;
 switch((uintptr_t)method){
 case GET_GO:
  if(object==&app)return &donorGo;
  if(object==&spriteHidden)return &spriteGo;
  if(object==&spineHidden)return &spineGo;
  return &sourceGo;
 case GET_ACTIVE:return &go->active;
 case SET_ACTIVE:go->active=*(uint8_t *)args[0];go->affects++;return NULL;
 case GET_DETAIL:return &currentDetail;
 case GET_FORCE:return object;
 case SET_FORCE:*(uint8_t *)object=*(uint8_t *)args[0];return NULL;
 case GET_TR:return object;
 case GET_PARENT:return go->parent;
 case FIND:assert(object==&spriteGo&&args[0]);return &motionRoot;
 case COUNT:return &((TestList *)object)->count;
 case ITEM:return ((TestList *)object)->items[*(int *)args[0]];
 case MOTION_DETAIL:return &((TestMotion *)object)->detail;
 case PARTS_INIT:assert(object==&parts&&args[0]==&app);partsInit++;return NULL;
 case PARTS_RESET:assert(object==&parts&&partsInit==partsReset+1);partsReset++;return NULL;
 case GET_APP:assert(object==&donorGo);return &app;
 case GET_ENABLED:return object==&spineHidden?&spineEnabled:&spriteEnabled;
 case GET_SPRITE:return spriteHasArt?&spriteHasArt:NULL;
 default:assert(0);return NULL;
 }
}
static void test_motion_change(void *object,int detail,uint8_t a1,int index,uint8_t a3,void *cb,uint8_t a5,void *mi){
 assert(object==&app);
 currentDetail=detail;
 if(detail==17)skill1.active=1;
}

int main(void){
 void *apis[37]={0};api=apis;
 apis[API_OBJECT_CLASS]=test_class;apis[API_PARENT]=test_parent;apis[API_FIELD]=test_field;
 apis[API_FIELD_OFFSET]=test_offset;apis[API_METHOD]=test_method;
 apis[API_INVOKE]=test_invoke;apis[API_UNBOX]=test_unbox;
 apis[API_CLASS_NAME]=test_class_name;
 apis[API_STRING_NEW]=test_string;
 m_getTransform=(void *)GET_TR;
 m_getComponent=(void *)GET_APP;
 m_getActiveSelf=(void *)GET_ACTIVE;m_setActive=(void *)SET_ACTIVE;
 orig_changeMotion=test_motion_change;
 currentApp=&app;
 Unit *unit=&g_units[0];unit->used=1;unit->view=&currentApp;unit->baseApp=&source;unit->staticHidden=1;
 Skin *skin=&unit->skins[0];skin->used=1;skin->app=&app;skin->go=&donorGo;
 lstrcpyA(skin->look,"8100_ProphetofSkinAppearance");
 idle.parent=skill1.parent=skill2.parent=skill3.parent=retire.parent=&motionRoot;
 externalFx.parent=&donorGo;writingFx.parent=&skill2;
 TestList spines={{&spine},1},idleObjects={{&idle},1},retireObjects={{&retire},1},partInfo={{&parts},1};
 TestList attack1Objects={{&skill1},1},attack2Objects={{&skill2,&externalFx,&writingFx},3},attack3Objects={{&skill3},1};
 TestMotion motions[]={{NULL,1,18},{&idleObjects,0,0},{&attack1Objects,0,7},{&attack1Objects,0,17},
                       {&attack2Objects,0,8},{&attack3Objects,0,9},{&attack3Objects,0,10},{&retireObjects,0,20}};
 TestList motionList={{&motions[0],&motions[1],&motions[2],&motions[3],&motions[4],&motions[5],&motions[6],&motions[7]},8};
 parts=(TestParts){&spine,&partInfo};
 app=(TestApp){&spriteHidden,&spines,&parts,&motionList};
 assert(prepare_stock_donor_body(skin,&donorGo));
 assert(partsInit==1&&partsReset==1);
 sync_visibility(unit);
 assert(!idle.active&&!skill1.active&&!spineHidden&&spriteHidden&&externalFx.active&&writingFx.active);
 idle.active=1;
 change_motion_hook(&app,17,0,0,0,NULL,0,NULL);
 assert(!idle.active&&skill1.active&&spineHidden&&spriteHidden);
 currentDetail=7;
 sync_visibility(unit);
 assert(skill1.active);
 change_motion_hook(&app,8,0,0,0,NULL,0,NULL);
 assert(skill1.active&&!skill2.active&&spineHidden&&spriteHidden);
 skill2.active=1;
 sync_visibility(unit);
 assert(!skill1.active&&skill2.active&&spineHidden&&spriteHidden);
 currentDetail=9;
 sync_visibility(unit);
 assert(skill2.active&&!skill3.active);
 skill3.active=1;
 sync_visibility(unit);
 assert(!skill2.active&&skill3.active&&spineHidden);
 currentDetail=10;
 sync_visibility(unit);
 assert(skill3.active);
 currentDetail=20;retire.active=1;
 sync_visibility(unit);
 assert(!skill3.active&&retire.active);
 currentDetail=18;spineGo.active=0;
 sync_visibility(unit);
 assert(retire.active&&!spineHidden);
 spineGo.active=1;spineEnabled=0;
 sync_visibility(unit);
 assert(retire.active);
 spineEnabled=1;
 sync_visibility(unit);
 assert(!retire.active&&!spineHidden&&spriteHidden);
 currentDetail=0;idle.active=1;
 sync_visibility(unit);
 assert(idle.active&&spineHidden&&spriteHidden);
 currentDetail=22;
 sync_visibility(unit);
 assert(idle.active&&!spineHidden&&!spriteHidden);
 currentDetail=0;
 sync_visibility(unit);
 currentDetail=18;donorGo.active=0;unit->hiddenAppearance=&app;
 sync_visibility(unit);
 assert(idle.active&&spineHidden&&donorGo.active==0);
 currentApp=&other;
 sync_visibility(unit);
 assert(idle.active&&spineHidden&&donorGo.active==0);
 assert(externalFx.active&&externalFx.affects==0&&writingFx.active&&writingFx.affects==0);
 currentApp=&app;donorGo.active=1;unit->staticHidden=1;
 sync_visibility(unit);
 assert(!idle.active&&!spineHidden);
 spineHidden=1;skill1.active=1;
 currentDetail=7;
 sync_visibility(unit);
 currentDetail=18;
 sync_visibility(unit);
 assert(spineHidden&&spriteHidden);
 assert(partsInit==1&&partsReset==1);
 HeapFree(GetProcessHeap(),0,skin->bodyVisibility);skin->bodyVisibility=NULL;
 lstrcpyA(skin->look,"8101_WalkingPearlAppearance");
 spriteHasArt=1;
 assert(!prepare_stock_donor_body(skin,&donorGo)&&!skin->bodyVisibility);
 spriteHasArt=0;spriteEnabled=1;
 assert(!prepare_stock_donor_body(skin,&donorGo)&&!skin->bodyVisibility);
 spriteEnabled=0;parts.spine=NULL;
 assert(!prepare_stock_donor_body(skin,&donorGo)&&!skin->bodyVisibility);
 parts.spine=&spine;
 attack2Objects.items[1]=&idle;
 assert(!prepare_stock_donor_body(skin,&donorGo)&&!skin->bodyVisibility);
 attack2Objects.items[1]=&externalFx;
 assert(prepare_stock_donor_body(skin,&donorGo)&&partsInit==2&&partsReset==2);
 HeapFree(GetProcessHeap(),0,skin->bodyVisibility);
 puts("PASS structurally matched body poses, native activation delays, retreat, parts, unrelated effects and incompatible models");
 return 0;
}
