#define main legacy_test_main
#include "test_camera_lifecycle.c"
#undef main
static int enabled=1,hasTable=1,hasText=1,hasDialog=1,shown=0;
static uintptr_t view_obj[2],manager_obj[2],dummy[8];
static struct {uintptr_t x,y;int length;uint16_t chars[8];} t={0,0,4,{65,66,67,68}};
static uint8_t yes=1;
static void *b_class(void *image,const char *space,const char *name){return (void*)1;}
static void *b_field(void *klass,const char *name){if(!strcmp(name,"_voiceTable"))return (void*)1;if(!strcmp(name,"_uiManager"))return (void*)2;if(!strcmp(name,"_dialogUI"))return (void*)3;return NULL;}
static size_t b_offset(void *f){return 0;}
static void *b_value(void *field,void *obj){assert(!obj&&field==(void*)1);return hasTable?dummy:NULL;}
static void *b_method(void *klass,const char *name,int count){if(!strcmp(name,"CheckSpeechBubbleSystemEnabled"))return (void*)201;if(!strcmp(name,"GetVoiceTextData_SpeachBubble"))return (void*)202;if(!strcmp(name,".ctor"))return (void*)203;if(!strcmp(name,"ShowDialog"))return (void*)204;return NULL;}
static void *b_invoke(void *m,void *obj,void **args,void **exc){*exc=NULL;switch((uintptr_t)m){case 201:yes=enabled;return &yes;case 202:assert(*(int*)args[0]==8378);return hasText?&t:NULL;case 203:assert(args[0]==&t);return NULL;case 204:assert(obj==dummy);shown++;return NULL;}return NULL;}
static void *b_unbox(void *v){return v;}
static void *b_new(void *k){return dummy;}
static void *b_string(const char *s){return dummy;}
int main(void){
 static void *apis[37];api=apis;api[API_CLASS]=b_class;api[API_FIELD]=b_field;api[API_FIELD_OFFSET]=b_offset;api[API_FIELD_VALUE]=b_value;api[API_OBJECT_CLASS]=fake_class;api[API_PARENT]=fake_parent;api[API_METHOD]=b_method;api[API_INVOKE]=b_invoke;api[API_UNBOX]=b_unbox;api[API_OBJECT_NEW]=b_new;api[API_STRING_NEW]=b_string;api[API_ROOT]=fake_root;api[API_UNROOT]=fake_unroot;
 view_obj[0]=(uintptr_t)manager_obj;manager_obj[0]=(uintptr_t)dummy;
 assert(!priest_death_bubble(NULL,8378,dummy,2));assert(!priest_death_bubble(view_obj,1,dummy,2));
 enabled=0;assert(!priest_death_bubble(view_obj,8378,dummy,2));enabled=1;
 hasTable=0;assert(!priest_death_bubble(view_obj,8378,dummy,2));hasTable=1;
 hasText=0;assert(!priest_death_bubble(view_obj,8378,dummy,2));hasText=1;
 t.length=0;assert(!priest_death_bubble(view_obj,8378,dummy,2));t.length=4;
 manager_obj[0]=0;assert(!priest_death_bubble(view_obj,8378,dummy,2));manager_obj[0]=(uintptr_t)dummy;
 assert(priest_death_bubble(view_obj,8378,dummy,2));assert(shown==1&&roots==0);puts("PASS localized priest bubble and missing setting/table/text/dialog fallback");
}
