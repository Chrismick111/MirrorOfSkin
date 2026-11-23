/* Exercise the production dispatch functions using a fake game view and stock
   method callbacks. No running game or mod installation is required. */
#include "sinners_native.c"
#include <assert.h>
typedef struct {void *klass,*cached,*appearance;} TestView;
typedef struct {void *klass,*monitor;int n;uint16_t chars[192];} TestString;
static TestString test_string(const char *text){
 TestString s={0};s.n=(int)strlen(text);
 for(int i=0;i<s.n;i++)s.chars[i]=(unsigned char)text[i];
 return s;
}
static void *object_class(void *o){return o;}
static void *no_parent(void *k){(void)k;return NULL;}
static void *field_named(void *k,const char *name){
 (void)k;
 if(!strcmp(name,"m_CachedPtr"))return (void *)offsetof(TestView,cached);
 if(!strcmp(name,"_voiceTable"))return (void*)1;
 if(!strcmp(name,"_curAppearance"))return (void *)offsetof(TestView,appearance);
 return NULL;
}
static int field_offset(void *field){return (int)(uintptr_t)field;}
static int bubblesEnabled=1,textLookups,centerShown,languageMissing,allowCenter=1;
static const char *captionObserved;
static const char *expectedCaption="custom caption";
static int lastTextOwner;static float lastLength;static uint8_t lastCustom;
static int uiToken,lineToken;
static void *field_value(void *f,void *o){(void)f;(void)o;return &uiToken;}
static void *mock_class(void *image,const char *ns,const char *name){(void)image;(void)ns;(void)name;return &uiToken;}
static void *mock_method(void *k,const char *name,int count){
 (void)k;(void)count;
 if(!strcmp(name,"CheckSpeechBubbleSystemEnabled"))return (void*)1;
 if(!strcmp(name,"GetVoiceTextData_SpeachBubble"))return (void*)2;
 if(!strcmp(name,".ctor"))return (void*)3;
 if(!strcmp(name,"TryPrintCenterSubtitle"))return (void*)4;
 return NULL;
}
static void *new_strobj(const char *text){
 if(!strcmp(text,expectedCaption))captionObserved=expectedCaption;
 static TestString strings[8];static unsigned cursor;
 TestString *str=&strings[cursor++%8];
 *str=test_string(strlen(text)<180?text:"localized-text");return str;
}
static void *new_dialog(void *klass){(void)klass;return &lineToken;}
static void *mock_invoke(void *method,void *o,void **args,void **exc){
 (void)o;*exc=NULL;
 switch((uintptr_t)method){
 case 1:return &bubblesEnabled;
 case 2:++textLookups;lastTextOwner=*(int*)args[0];return languageMissing?NULL:new_strobj("native-localized");
 case 3:return NULL;
 case 4:++centerShown;lastLength=*(float*)args[2];lastCustom=*(uint8_t*)args[3];return &allowCenter;
 default:return NULL;
 }
}
static unsigned roots;
static uintptr_t root_stub(void *o,int pinned){(void)pinned;++roots;return (uintptr_t)o;}
static void unroot_stub(uintptr_t h){assert(h&&roots);--roots;}
static int lastId,lastIndex,lastBlock,lastType,lookups;
static void *stock_lookup_path;
static int lookup_stub(void *path,int id,int index,void **key,void **out,void *mi){
 (void)mi;*key=path;*out=stock_lookup_path;lastId=id;lastIndex=index;++lookups;return 0;
}
static int stock_event;
static void *add_stub(uintptr_t instance,int id,int type,float volume,uint8_t custom,float length,
                       void *alternate,uint8_t blocked,void *subtitle,uint8_t duck,uint8_t interrupt,void *mi){
 assert(instance==42&&volume==0.75f&&custom==1&&length==3.5f&&duck==0&&interrupt==1&&mi==NULL);
 (void)alternate;(void)subtitle;lastId=id;lastBlock=blocked;lastType=type;return &stock_event;
}
static void *multi_stub(int id,void *key,void *view,uint8_t special,uint8_t custom,float length,void *mi){
 assert(id==10102&&special==1&&custom==1&&length==3.5f&&mi==NULL&&view!=NULL);
 return voice_add_hook(42,id,7,0.75f,custom,length,key,0,NULL,0,1,NULL);
}
int main(void){
 static void *functions[37];api=functions;functions[API_OBJECT_CLASS]=object_class;
 functions[API_PARENT]=no_parent;functions[API_FIELD]=field_named;functions[API_FIELD_OFFSET]=field_offset;
 c_voiceGenerator=&uiToken;functions[API_CLASS]=mock_class;functions[API_METHOD]=mock_method;
 functions[API_FIELD_VALUE]=field_value;functions[API_INVOKE]=mock_invoke;functions[API_UNBOX]=object_class;
 functions[API_STRING_NEW]=new_strobj;functions[API_OBJECT_NEW]=new_dialog;
 functions[API_ROOT]=root_stub;functions[API_UNROOT]=unroot_stub;
 Config config={0};config.enabled=1;config.heartbeat=GetTickCount();g_cfg=&config;
 int app;TestView view={0,&app,&app};Unit *u=&g_units[0];
 u->used=1;u->view=&view;strcpy(u->baseName,"10101_YiSang_BaseAppearance");
 Skin *skin=&u->skins[0];skin->used=1;skin->app=&app;skin->row=0;strcpy(skin->look,"10102_YiSang_7Appearance");
 g_rowCount=1;strcpy(g_rows[0].identity,"10103");strcpy(g_rows[0].appearance_name,"10103_Yisang_SwordGroupAppearance");
 assert(voice_worn_owner(u)==10102);
 orig_checkVoiceIndex=lookup_stub;orig_multiVoice=multi_stub;orig_addMultiVoice=add_stub;
 TestString event=test_string("battle_select");void *key,*out;stock_lookup_path=&app;
 assert(voice_index_hook(&event,10101,2,&key,&out,NULL)==0);
 assert(lookups==1&&lastId==10102&&lastIndex==2&&key==&event&&out==&app);
 g_units[1].used=1;g_units[1].view=&app;strcpy(g_units[1].baseName,u->baseName);
 voice_index_hook(&event,10101,5,&key,&out,NULL);assert(lastId==10101);
 voiceView=u;voice_index_hook(&event,10101,5,&key,&out,NULL);assert(lastId==10102);
 voiceView=NULL;g_units[1].used=0;
 TestString donorKey=test_string("battle_select_10102_1");
 assert(voice_multi_hook(10102,&donorKey,&view,1,1,3.5f,NULL)==&stock_event);
 assert(lastId==10101&&!lastBlock&&lastType==7&&roots==0);
 assert(voice_add_hook(42,10102,7,0.75f,1,3.5f,&donorKey,1,NULL,0,1,NULL)==&stock_event);
 assert(lastId==10102&&lastBlock);
 voiceSegment=(VoiceSegment){u,skin,42};
 voice_add_hook(42,10102,7,0.75f,1,3.5f,&donorKey,1,NULL,0,1,NULL);
 assert(lastId==10101&&lastBlock&&u->voiceCueNext==0);
 voice_add_hook(42,10102,7,0.75f,1,3.5f,&donorKey,0,NULL,0,1,NULL);
 print_bubble_hook(10101,&donorKey,3.5f,1,NULL);
 assert(centerShown==1&&lastTextOwner==10102&&lastLength==3.5f&&lastCustom==1&&roots==0);
 assert(u->voiceCues[0].appearance==NULL&&u->voiceCueNext==1);
 /* The actual segment may request a subtitle again at a later clip boundary. */
 voice_add_hook(42,10102,7,0.75f,1,3.5f,&donorKey,0,NULL,0,1,NULL);
 assert(u->voiceCueNext==2&&u->voiceCues[1].appearance==skin->app&&!strcmp(u->voiceCues[1].key,"battle_select_10102_1"));
 languageMissing=1;
 int hasFallback=sr_voice_catalog_text(10102,"battle_select_10102_1")!=NULL;
 assert(voice_show_key(u,10102,"battle_select_10102_1",4.25f,0)==hasFallback);
 if(hasFallback)assert(lastLength==4.25f&&!lastCustom);
 bubblesEnabled=0;int prior=textLookups;
 assert(!voice_show_key(u,10102,"battle_select_10102_1",4.25f,0)&&textLookups==prior&&!roots);
 bubblesEnabled=1;
 strcpy(skin->look,"UnmappedTransformedResource");assert(!voice_worn_owner(u));
 voice_index_hook(&event,10101,1,&key,&out,NULL);assert(lastId==0);
 ImportedConfig imported={0};skin->imported=&imported;
 strcpy(imported.layout,"10109_Yisang_RingFingerAppearance");voiceManifestRead=1;
 voice_index_hook(&event,10101,1,&key,&out,NULL);assert(lastId==10109);
 strcpy(imported.layout,"UnknownLayout");
 voice_index_hook(&event,10101,1,&key,&out,NULL);assert(lastId==10101);
 VoiceLibrary lib={.captionsRead=1};
 VoiceCaption *cap=calloc(1,sizeof(*cap)+strlen(expectedCaption)+1);assert(cap);
 strcpy(cap->key,"battle_select_10109_1");strcpy(cap->text,expectedCaption);cap->owner=10109;lib.captions=cap;
 VoiceBinding binding={.owner=10109,.library=&lib};strcpy(binding.look,skin->look);voiceBindings=&binding;
 /* Native subtitle before or after the FMOD fallback, including equal source
    and donor ids. Each real event should print just once on its own view. */
 strcpy(u->baseName,"10109_Yisang_RingFingerAppearance");
 PrivateVoiceEvent *e=&privateVoiceEvents[0];
 *e=(PrivateVoiceEvent){.u=u,.view=&view,.app=&app,.binding=&binding};strcpy(e->key,cap->key);
 TestString selection=test_string(cap->key);
 int priorShown=centerShown;languageMissing=0;
 print_bubble_hook(10109,&selection,3.5f,1,NULL);private_playing_caption(e);
 assert(e->captionHandled&&captionObserved&&centerShown==priorShown+1);
 e->captionHandled=0;private_playing_caption(e);print_bubble_hook(10109,&selection,3.5f,1,NULL);
 assert(e->captionHandled&&centerShown==priorShown+2);
 e->captionHandled=0;e->captionBlocked=1;private_playing_caption(e);
 assert(!e->captionHandled&&centerShown==priorShown+2);
 VoiceBinding other=binding;other.owner=10102;
 assert(!private_caption(&other,cap->key)&&!private_caption(&binding,"battle_kill_10109_1"));
 memset(e,0,sizeof(*e));voiceBindings=NULL;skin->imported=NULL;free(cap);
 view.appearance=NULL;voice_index_hook(&event,10101,1,&key,&out,NULL);assert(lastId==10101);
 assert(sr_voice_request(&view,8378,"OnDie_View")&&roots==1);
 assert(!sr_voice_request(&view,8378,"OnDie_View"));
 sr_voice_cancel_view(&view);assert(!roots&&!g_voicePendingCount);
 assert(sr_voice_request(&view,8378,"OnDie_View"));sr_voice_clear();assert(!roots);
 char tiny[3];assert(!sr_voice_single(8378,"OnDie_View",tiny,sizeof(tiny)));
 puts("Voice routing tests passed");return 0;
}
