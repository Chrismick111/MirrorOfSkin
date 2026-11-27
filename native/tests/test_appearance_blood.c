#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"

typedef struct { void *alive; } TestView;
typedef struct { void *alive; uint8_t disabled; int writes; } TestBlood;
typedef struct { uint64_t header[2]; int length; uint16_t text[128]; } TestString;
typedef struct { TestString *identity; } TestInfo;
typedef struct { void *alive; TestView *view; TestBlood *blood; TestInfo *info; } TestAppearance;

enum { GET_BLOOD=1, SET_BLOOD, INFO_FIELD, ID_FIELD };
static unsigned roots;

static void *test_class(void *obj){return obj;}
static void *test_parent(void *obj){return NULL;}
static void *test_field(void *klass,const char *name){
 if(!strcmp(name,"charInfo"))return (void *)INFO_FIELD;
 if(!strcmp(name,"appearanceID"))return (void *)ID_FIELD;
 return NULL;
}
static size_t test_offset(void *field){
 return field==(void *)INFO_FIELD?offsetof(TestAppearance,info):offsetof(TestInfo,identity);
}
static void test_identity(TestString *out,const char *id){
 out->length=(int)strlen(id);
 for(int k=0;k<out->length;k++)out->text[k]=(uint16_t)(uint8_t)id[k];
}
static uintptr_t test_root(void *obj,int pinned){assert(obj);roots++;return (uintptr_t)obj;}
static void test_unroot(uintptr_t root){assert(root&&roots);roots--;}
static void *test_invoke(void *method,void *obj,void **args,void **exception){
 *exception=NULL;
 if(method==(void *)GET_BLOOD)return ((TestAppearance *)obj)->blood;
 assert(method==(void *)SET_BLOOD);
 TestBlood *blood=obj;
 blood->disabled=*(uint8_t *)args[0];
 blood->writes++;
 return NULL;
}

int main(void){
 SetEnvironmentVariableW(L"APPDATA",NULL);
 void *apis[37]={0};
 api=apis;
 apis[API_OBJECT_CLASS]=test_class;apis[API_PARENT]=test_parent;apis[API_FIELD]=test_field;
 apis[API_FIELD_OFFSET]=test_offset;
 apis[API_ROOT]=test_root;apis[API_UNROOT]=test_unroot;
 apis[API_INVOKE]=test_invoke;
 TestView player={(void *)1},enemy={(void *)1};
 TestBlood baseBlood={(void *)1},donorBlood={(void *)1},enemyBlood={(void *)1,1};
 TestBlood otherBlood={(void *)1},newBlood={(void *)1};
 TestAppearance base={(void *)1,&player,&baseBlood},donor={(void *)1,&player,&donorBlood};
 TestAppearance foe={(void *)1,&enemy,&enemyBlood},other={(void *)1,NULL,&otherBlood};
 TestAppearance late={(void *)1,&player,NULL};
 TestString nativeKey={0};
 TestInfo nativeInfo={&nativeKey};
 base.info=&nativeInfo;
 test_identity(&nativeKey,"10101_YiSang_BaseAppearance");
 m_getAppearanceBlood=(void *)GET_BLOOD;m_setDisableBlood=(void *)SET_BLOOD;
 blood_flag_offset=offsetof(TestBlood,disabled);
 blood_view_offset=offsetof(TestAppearance,view);

 observe_appearance_blood(&base,&player,NULL);
 observe_appearance_blood(&donor,&player,"story_Example");
 observe_appearance_blood(&foe,&enemy,"story_Enemy");
 observe_appearance_blood(&other,NULL,"other");
 observe_appearance_blood(&late,&player,"story_Late");
 assert(baseBlood.disabled&&donorBlood.disabled&&enemyBlood.disabled&&!otherBlood.disabled);
 assert(baseBlood.writes==1&&donorBlood.writes==1&&!enemyBlood.writes&&!otherBlood.writes);

 observe_appearance_blood(&base,&player,NULL);
 sync_appearance_blood(1,1);
 assert(baseBlood.writes==1&&donorBlood.writes==1&&!enemyBlood.writes);
 baseBlood.disabled=0;
 late.blood=&newBlood;
 sync_appearance_blood(1,1);
 assert(baseBlood.disabled&&baseBlood.writes==2&&newBlood.disabled);

 const char allow[]="\xef\xbb\xbf""story_Example\r\n10102\n";
 assert(replace_appearance_blood_config(allow,sizeof(allow)-1)==1);
 assert(replace_appearance_blood_config("story_Example\n10102",19)==0);
 assert(replace_appearance_blood_config("story Invalid",13)==-1);
 sync_appearance_blood(1,1);
 assert(!donorBlood.disabled&&baseBlood.disabled&&enemyBlood.disabled&&newBlood.disabled);
 int donorWrites=donorBlood.writes;
 observe_appearance_blood(&donor,&player,"story_Example");
 sync_appearance_blood(1,1);
 assert(donorBlood.writes==donorWrites);
 donor.info=&nativeInfo;
 donor.view=&enemy;
 observe_appearance_blood(&donor,&enemy,NULL);
 assert(donorBlood.disabled&&donorBlood.writes==donorWrites+1);
 assert(replace_appearance_blood_config("10101",5)==1);
 sync_appearance_blood(1,1);
 assert(!donorBlood.disabled&&!baseBlood.disabled&&enemyBlood.disabled&&newBlood.disabled);
 donorWrites=donorBlood.writes;
 assert(replace_appearance_blood_config("",0)==1);
 sync_appearance_blood(1,1);
 assert(donorBlood.disabled&&donorBlood.writes==donorWrites+1);

 enemy.alive=NULL;
 sync_appearance_blood(1,0);
 assert(enemyBlood.disabled&&!enemyBlood.writes);
 sync_appearance_blood(0,0);
 assert(!baseBlood.disabled&&!donorBlood.disabled&&!newBlood.disabled&&!roots);
 puts("character blood visibility ok");
 return 0;
}
