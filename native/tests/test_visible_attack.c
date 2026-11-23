#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"
typedef struct {uintptr_t fields[5];} Stub;
static Stub source,donor,view,donorGo,transform;
static uint8_t renderBits[625];static int failIndex=-1;static uintptr_t arrayStorage[629];
static Stub director,spriteRenderer,sprite;static int directorState;
static int calls,lookups,roots,writes,lastDetail,lastPart;
static void *lastReceiver,*lastCallback;
static VisiblePosition position={2,3,4};
static void *fake_class(void *o){return (void *)1;}
static void *fake_parent(void *o){return NULL;}
static void *fake_field(void *c,const char *n){
 if(!strcmp(n,"_curAppearance"))return (void *)1;
 if(!strcmp(n,"_playableDirector"))return (void *)3;
 if(!strcmp(n,"sprenderer_charactermotion"))return (void *)4;
 if(!strcmp(n,"m_CachedPtr"))return (void *)2;
 return NULL;
}
static size_t fake_offset(void *f){return ((uintptr_t)f-1)*sizeof(uintptr_t);}
static void *fake_method(void *c,const char *n,int argc){
 if(!strcmp(n,"get_forceRenderingOff"))return (void *)13;
 if(!strcmp(n,"set_forceRenderingOff"))return (void *)14;
 if(!strcmp(n,"get_state"))return (void *)15;
 if(!strcmp(n,"get_sprite"))return (void *)16;
 if(!strcmp(n,"get_localPosition"))return (void *)11;
 if(!strcmp(n,"set_localPosition"))return (void *)12;
 return NULL;
}
static void *fake_invoke(void *m,void *o,void **args,void **exc){
 *exc=NULL;
 if(m==(void *)13)return o;
 if(m==(void *)14){
  size_t index=(uint8_t *)o-renderBits;
  if((int)index==failIndex){*exc=(void *)1;return NULL;}
  *(uint8_t *)o=*(uint8_t *)args[0];return NULL;
 }
 if(m==(void *)15)return &directorState;
 if(m==(void *)16)return &sprite;
 if(m==(void *)10){assert(o==&donorGo);return &transform;}
 if(m==(void *)11){assert(o==&transform);return &position;}
 if(m==(void *)12){assert(o==&transform);position=*(VisiblePosition *)args[0];writes++;}
 return NULL;
}
static uintptr_t root(void *o,int pinned){roots++;return 1;}
static void unroot(uintptr_t h){roots--;}
static void *unbox(void *x){return x;}
static void *motion(void *self,int detail,uint8_t flag,void *mi){
 lookups++;lastReceiver=self;lastDetail=detail;return self;
}
static void change(void *self,int detail,uint8_t a1,int part,uint8_t a3,void *cb,uint8_t a5,void *mi){
 calls++;lastReceiver=self;lastDetail=detail;lastPart=part;lastCallback=cb;
}
/* Use the real build_skin entry across successive units. Only Unity's object
   lifetime, hierarchy and local bundle API are simulated. */
static Stub bundles[20],prefabs[20],clones[20],appearances[20],pivot,stock,dependency[12];
static int generation,cloneCount,openFailures,unloads,rejectGeneration,detached,parentCalls;
enum { Result=31, Open, Asset, Unload, Instantiate, Pivot, Transform, Component, Init, Add, Parent };
static void *art_string(const char *s){return &stock;}
static void *art_method(void *c,const char *n,int argc){
 if(!strcmp(n,"get_Result"))return (void*)Result;
 if(!strcmp(n,"Add"))return (void*)Add;
 return NULL;
}
static void *art_field(void *c,const char *n){
 if(!strcmp(n,"m_CachedPtr"))return (void*)2;
 if(!strcmp(n,"_isInitialized"))return (void*)3;
 if(!strcmp(n,"_appearances"))return (void*)4;
 return NULL;
}
static void *art_invoke(void *method,void *o,void **a,void **exc){
 *exc=NULL;
 switch((uintptr_t)method){
 case Result:return &stock;
 case Open:
  if(openFailures){openFailures--;return NULL;}
  assert(++generation<20);
  bundles[generation].fields[1]=prefabs[generation].fields[1]=1;
  return &bundles[generation];
 case Asset:assert(o==&bundles[generation]);return &prefabs[generation];
 case Unload:assert(((Stub*)o)->fields[1]&&!*(uint8_t*)a[0]);unloads++;return NULL;
 case Instantiate:
  assert(a[0]!=&stock);
  if(a[0]!=&prefabs[generation]||!prefabs[generation].fields[1]||rejectGeneration==generation||
     (detached&&a[1])){*exc=&stock;return NULL;}
  assert(++cloneCount<20);return &clones[cloneCount];
 case Pivot:return &pivot;
 case Transform:return o;
 case Parent:assert(a[0]==&pivot);parentCalls++;return NULL;
 case Component:return &appearances[cloneCount];
 case Init:((Stub*)o)->fields[2]=1;return NULL;
 default:return NULL;
 }
}
static int build_art(int unit,const char *look){
 Unit *u=&g_units[unit];u->used=1;u->view=&view;u->sinner=101+unit;
 g_loadBox=&dependency[unit];g_loadRoot=ui_root(g_loadBox);
 lstrcpynA(g_loadLook,look,sizeof(g_loadLook));
 int built=build_skin(u,0);
 if(built==1){g_loadBox=NULL;g_loadRoot=0;}
 return built;
}
/* Missing authored outcomes and the default disabled switch must pass the
   original receiver and detail through the upstream playback entry. */
static int nativeParryCalls;
static void native_parry_playback(void *app,int detail,void *mi){
 assert(app==&source&&detail==37&&mi==&stock);nativeParryCalls++;
}
static void test_native_parry_fallback(Config *cfg,Skin *skin){
 orig_parryPlayback=native_parry_playback;
 cfg->reserved[3]=0;
 strcpy(skin->look,"BRolandBaseAppearance");
 parry_playback_hook(&source,37,&stock);
 cfg->reserved[3]=2;
 strcpy(skin->look,"fixture_donor");
 parry_playback_hook(&source,37,&stock);
 strcpy(skin->look,"10110_Yisang_DeadButterflyAppearance");
 skin->clashCount[37]=1;skin->chapterRole[37]=-1;
 parry_playback_hook(&source,37,&stock);
 assert(nativeParryCalls==3);
 skin->clashCount[37]=skin->chapterRole[37]=0;
 strcpy(skin->look,"fixture_donor");
 puts("PASS upstream default clash switch and missing ordinary donor slot retain original receiver, detail and callback");
}
/* Mirror the base prefab's authored motion list. Unity exposes its short
   defense poses through the Animator, with zero timeline entries. */
static Stub clashMotion,clashList;
static int cachedDetail,cachedCount,parryCalls,parryPart,parryViaPlayback;
static void *clash_test_field(void *c,const char *name){
 if(!strcmp(name,"timelineAssets")||!strcmp(name,"_anim"))return (void *)5;
 return fake_field(c,name);
}
static void *clash_test_method(void *c,const char *name,int argc){
 if(!strcmp(name,"get_MotionDetail"))return (void *)102;
 if(!strcmp(name,"get_Count"))return (void *)103;
 if(!strcmp(name,"get_Item"))return (void *)104;
 return fake_method(c,name,argc);
}
static void *clash_test_invoke(void *m,void *o,void **args,void **exc){
 *exc=NULL;
 switch((uintptr_t)m){
 case 101:
  assert(o==&donor);cachedDetail=*(int*)args[0];
  cachedCount=cachedDetail==20?4:cachedDetail==21?5:(cachedDetail==32||cachedDetail==33)?2:0;
  return &clashMotion;
 case 102:return &cachedDetail;
 case 103:return &cachedCount;
 case 104:assert(o==&clashList&&*(int*)args[0]<cachedCount);return &sprite;
 default:return fake_invoke(m,o,args,exc);
 }
}
static void clash_test_playback(void *app,int detail,void *mi){
 assert(clash_raw(app,detail));
 assert(get_motion_hook(app,detail,0,NULL)==&donor&&lastDetail==detail);
 change_motion_hook(app,detail,0,parryPart,0,(void*)87,0,NULL);
}
static int clash_test_parry(void *app,int result,float delay,uint8_t a2,int close,int defense,int detail,uint8_t a6,void *mi){
 assert(app==&donor);parryCalls++;
 if(detail==35)detail=17; /* native winner's default clash response in the installed log */
 if(parryViaPlayback)parry_playback_hook(app,detail,mi);
 else change_motion_hook(app,detail,0,parryPart,0,(void*)87,0,mi);
 return detail;
}
static int checkedDuelItems;
static void *clash_test_item(void *ret,void *app,int sourceDetail,int detail,int part,int sourcePart,uint8_t last,void *mi){
 assert(app==&donor&&sourceDetail==detail&&sourcePart==part&&part>=0);
 checkedDuelItems++;return ret;
}
static void clash_test_change(void *app,int detail,uint8_t a1,int part,uint8_t a3,void *cb,uint8_t a5,void *mi){
 if(clash_raw(app,detail)&&(detail==20||detail==21||detail==32||detail==33)){
  assert(get_motion_hook(app,detail,0,NULL)==&donor&&lastDetail==detail);
  assert(motion_anim_item_hook(&stock,app,detail,detail,part,part,0,NULL)==&stock);
 }
 change(app,detail,a1,part,a3,cb,a5,mi);
}
static void test_roland_clash(Unit *u,Skin *skin){
 strcpy(skin->look,"BRolandBaseAppearance");strcpy(u->baseName,"10901");
 api[API_FIELD]=clash_test_field;api[API_METHOD]=clash_test_method;api[API_INVOKE]=clash_test_invoke;
 m_getMotion=(void*)101;
 donor.fields[4]=(uintptr_t)&stock;clashMotion.fields[4]=(uintptr_t)&clashList;
 defenseMotions[2]=defenseMotions[3]=1;
 cache_clash_roles(skin);
 for(int d=2;d<=4;d++)assert(skin->chapterRole[d]>0);
 assert(skin->chapterRole[17]<0&&skin->chapterRole[37]<0);
 assert(skin->clashCount[20]==4&&skin->clashCount[21]==5&&skin->clashCount[32]==2&&skin->clashCount[33]==2);
 orig_parryOnly=clash_test_parry;orig_parryPlayback=clash_test_playback;
 orig_changeMotion=clash_test_change;orig_motionAnimItem=clash_test_item;
 clashResults[1]=2;clashResults[2]=3;
 static const struct {int detail,result,part,played,donorPart;} cases[]={
  {4,2,-1,4,-1},{17,1,-1,32,0},{37,1,0,32,0},{2,1,-1,2,-1},
  {3,1,-1,3,-1},{17,2,-1,20,0},{37,1,4,32,1}};
 for(int i=0;i<sizeof(cases)/sizeof(*cases);i++){
  for(parryViaPlayback=0;parryViaPlayback<=1;parryViaPlayback++){
   int before=calls,entered=parryCalls;
   parryPart=cases[i].part;
   assert(parry_hook(&source,cases[i].result,2.97f,0,1,0,cases[i].detail,0,NULL)==cases[i].detail);
   assert(parryCalls==entered+1&&calls==before+1&&lastReceiver==&donor&&lastCallback==(void*)87);
   assert(lastPart==cases[i].donorPart&&lastDetail==cases[i].played&&view.fields[0]==(uintptr_t)&donor);
   assert(!g_clashPlayback.app&&!g_clashOwner);
  }
 }
 assert(get_motion_hook(&source,37,0,NULL)==&donor&&lastDetail==32);
 change_motion_hook(&source,37,0,4,0,(void*)89,0,NULL);
 assert(lastDetail==32&&lastPart==1&&lastCallback==(void*)89);
 assert(checkedDuelItems==9);
 orig_changeMotion=change;orig_motionAnimItem=NULL;
 strcpy(u->baseName,"10115_YiSang_Index_FatherAppearance");skin->motionCounts[7]=3;
 int before=calls;
 change_motion_hook(&source,7,0,1,0,(void*)90,0,NULL);
 assert(calls==before+1&&lastReceiver==&donor&&lastDetail==7&&lastCallback==(void*)90);
 visible_watch_clear(u);assert(view.fields[0]==(uintptr_t)&donor&&roots==0);
 m_getMotion=NULL;donor.fields[4]=0;
 api[API_FIELD]=fake_field;api[API_METHOD]=fake_method;api[API_INVOKE]=fake_invoke;
 puts("PASS Roland clash entries: native Animator reactions, Parrying and Duel_Win tracks, then first attack on same donor");
}
static void test_imported_metadata_routing(void){
 Skin fixture={0}; ImportedConfig imported={0}; fixture.row=0;
 g_rows[0].story=0; strcpy(fixture.look,"BRolandBaseAppearance");
 assert(skin_uses_private_metadata(&fixture));
 strcpy(fixture.look,"WBImp_0123456789abcdef01234567");fixture.imported=&imported;
 assert(skin_uses_private_metadata(&fixture));
 fixture.imported=NULL;strcpy(fixture.look,"ordinary");
 assert(!skin_uses_private_metadata(&fixture));
 g_rows[0].story=1;assert(skin_uses_private_metadata(&fixture));g_rows[0].story=0;
 puts("PASS imported appearances use private metadata independently of native story flag");
}
static void test_roland_build(void){
 api[API_INVOKE]=art_invoke;api[API_FIELD]=art_field;api[API_METHOD]=art_method;api[API_STRING_NEW]=art_string;
 rolandOpen=(void*)Open;rolandAsset=(void*)Asset;rolandUnload=(void*)Unload;rolandGoType=&stock;
 m_instantiate=(void*)Instantiate;m_getSkinPivot=(void*)Pivot;m_getTransform=(void*)Transform;
 m_setParent=(void*)Parent;m_getComponent=(void*)Component;m_init=(void*)Init;
 g_cfg=NULL;g_rows[0].excluded=2;view.fields[3]=(uintptr_t)&stock;
 memset(g_units,0,sizeof(g_units));
 for(size_t i=0;i<sizeof(rolandForms)/sizeof(*rolandForms);i++){
  const char *look=rolandForms[i].look;
  assert(build_art(0,look)==1);                         /* father */
  int first=generation;
  assert(build_art(1,look)==1&&generation==first);     /* two simultaneous users */
  unit_release(&g_units[1]);
  assert(rolandForms[i].prefab==&prefabs[first]);
  prefabs[first].fields[1]=0;                          /* managed shell survived */
  assert(build_art(3,look)==1);                         /* Ryoshu, same process */
  assert(generation==first+1&&g_units[3].skins[0].app==&appearances[cloneCount]);
  rejectGeneration=generation;                          /* live shell rejects cloning */
  detached=1;int priorParents=parentCalls;
  assert(build_art(5,look)==1);
  assert(generation==first+2&&parentCalls==priorParents+1);
  detached=0;
  assert(g_units[0].skins[0].handleBox==&dependency[0]);
  assert(g_units[3].skins[0].handleBox==&dependency[3]);
  int priorUnloads=unloads;
  bundles[generation].fields[1]=0;openFailures=1;
  assert(build_art(6,look)==0&&g_loadBox==&dependency[6]&&unloads==priorUnloads);
  ui_unroot(g_loadRoot);g_loadBox=NULL;g_loadRoot=0;
  for(int k=0;k<SR_UNIT_MAX;k++)if(g_units[k].used)unit_release(&g_units[k]);
  g_frame+=3;collect_retire();
  assert(!rolandForms[i].bundle&&!rolandForms[i].prefab&&roots==0);
  assert(build_art(3,look)==1);                         /* fresh battle, Ryoshu first */
  int lastUnloads=unloads;
  unit_release(&g_units[3]);g_frame+=3;collect_retire();
  assert(unloads==lastUnloads+1&&!rolandForms[i].bundle&&roots==0);
 }
 puts("PASS unified Roland prefab: father to Ryoshu and another identity, stale prefab/bundle, clone retry, parent and dependency ownership");
}
#include "test_imported_art.inc"
static void imported_test_change(void *app,int detail,uint8_t a1,int part,uint8_t a3,void *cb,uint8_t a5,void *mi){
 assert(get_motion_hook(app,detail,0,NULL)==app&&lastDetail==detail);
 change(app,detail,a1,part,a3,cb,a5,mi);
}
static void test_imported_attacks(Unit *u,Skin *skin){
 ImportedConfig config={0};
 strcpy(config.layout,"10109_Yisang_RingFingerAppearance");
 strcpy(skin->look,"WBImp_a89310c5992f29551727affa");
 strcpy(u->baseName,"10115_YiSang_Index_FatherAppearance");
 skin->imported=&config;g_rows[0].story=1;
 memset(skin->motionCounts,0,sizeof(skin->motionCounts));
 skin->motionCounts[7]=3;skin->motionCounts[8]=3;skin->motionCounts[9]=4;
 u->observedAction=&view;u->observedViewer=&stock;
 u->coinKnown=1;u->coinTier=2;u->coinLast=0;u->coinIndex=1;
 int before=calls;orig_changeMotion=imported_test_change;
 change_motion_hook(&source,7,0,1,0,(void*)61,0,NULL);
 assert(calls==before+1&&lastReceiver==&donor&&lastDetail==8&&lastPart==1&&lastCallback==(void*)61);
 change_motion_hook(&source,7,0,1,0,(void*)61,0,NULL);
 assert(lastDetail==8&&lastPart==1);
 assert(get_motion_hook(&source,7,0,NULL)==&donor&&lastDetail==8);
 u->coinTier=3;u->coinIndex=0;
 change_motion_hook(&source,13,0,0,0,(void*)62,0,NULL);
 assert(lastDetail==9&&lastPart==0);
 u->coinTier=1;u->coinIndex=1;u->coinLast=1;
 change_motion_hook(&source,14,0,1,0,(void*)62,0,NULL);
 assert(lastDetail==7&&lastPart==2);
 /* Identical layout keeps the native motion and valid part even at the end. */
 strcpy(u->baseName,config.layout);u->coinTier=2;
 change_motion_hook(&source,9,0,1,0,(void*)62,0,NULL);
 assert(lastDetail==9&&lastPart==1);
 assert(get_motion_hook(&source,9,0,NULL)==&donor&&lastDetail==9);
 u->motions[0]=(PendingMotion){.source=&donor,.detail=9,.index=1,.row=0,.coin=1,.tier=2,.last=1,.callback=(void*)63};
 u->motionCount=1;motion_dispatch(u,0);
 assert(lastReceiver==&donor&&lastDetail==9&&lastPart==1&&lastCallback==(void*)63);
 /* A timing-compatible clip from another tier must never replace the group. */
 static TimeRecord src,dst;strcpy(src.look,u->baseName);strcpy(dst.look,skin_timing_key(skin));
 src.seconds[8][0]=dst.seconds[9][0]=1;
 g_timeRecords[0]=&src;g_timeRecords[1]=&dst;g_timeCount=2;
 u->viewerActive=1;u->ordinarySourceClips[8]=1;skin->ordinaryClips[9]=1;
 forward_projected_motion(&donor,8,0,0,0,(void*)64,0,NULL,8,0,0,1,&view,0);
 assert(lastDetail==8&&lastPart==0);
 g_timeCount=0;u->observedAction=NULL;u->observedViewer=NULL;u->viewerActive=0;
 skin->imported=NULL;g_rows[0].story=0;visible_watch_clear(u);orig_changeMotion=change;
 puts("PASS imported 10109 cross-layout S2 coin, same-layout direct/queued exact clip, repeat and competing duration");
}
/* A repeated authored index on a new coin must advance on the donor, while
   duplicate callbacks for the same coin stay latched to the same clip. */
static void test_local_repeated_coin(Unit *u,Skin *skin){
 ImportedConfig config={0};strcpy(config.layout,"fixture_unpaired");
 strcpy(u->baseName,"10101_YiSang_BaseAppearance");strcpy(skin->look,"WBImp_0123456789abcdef01234567");
 skin->imported=&config;skin->chapterActor=NULL;u->preserveSpecial=0;u->coinDefense=0;u->coinKnown=1;
 u->observedAction=&view;u->observedViewer=&stock;u->viewerActive=1;u->ordinarySourceClips[9]=(1u<<1);
 memset(skin->motionCounts,0,sizeof(skin->motionCounts));memset(skin->ordinaryClips,0,sizeof(skin->ordinaryClips));
 skin->motionCounts[9]=3;skin->ordinaryClips[9]=7;g_rows[skin->row].excluded=0;
 sr_segment_clear(&u->segmentLatch);orig_changeMotion=change;
 forward_projected_motion(&donor,9,0,1,0,NULL,0,NULL,9,1,0,1,&view,0);
 assert(lastDetail==9&&lastPart==1);
 forward_projected_motion(&donor,9,0,1,0,NULL,0,NULL,9,1,1,1,&view,1);
 assert(lastDetail==9&&lastPart==2);
 forward_projected_motion(&donor,9,0,1,0,NULL,0,NULL,9,1,1,1,&view,1);
 assert(lastDetail==9&&lastPart==2);
 skin->imported=NULL;strcpy(skin->look,"BRolandBaseAppearance");
 strcpy(u->baseName,"10115_YiSang_Index_FatherAppearance");sr_segment_clear(&u->segmentLatch);
 forward_projected_motion(&donor,9,0,1,0,NULL,0,NULL,9,1,0,1,&view,0);
 assert(lastDetail==9&&lastPart==1);
 forward_projected_motion(&donor,9,0,1,0,NULL,0,NULL,9,1,1,1,&view,1);
 assert(lastDetail==9&&lastPart==2);
 forward_projected_motion(&donor,9,0,1,0,NULL,0,NULL,9,1,1,1,&view,1);
 assert(lastDetail==9&&lastPart==2);
 u->observedAction=NULL;u->observedViewer=NULL;u->viewerActive=0;
 puts("PASS imported and Roland repeated coin clips advance and remain latched");
}
int main(void){
 open_test_profile();
 static void *table[40];api=table;table[API_OBJECT_CLASS]=fake_class;table[API_PARENT]=fake_parent;
 table[API_FIELD]=fake_field;table[API_FIELD_OFFSET]=fake_offset;table[API_METHOD]=fake_method;
 table[API_INVOKE]=fake_invoke;table[API_ROOT]=root;table[API_UNROOT]=unroot;table[API_UNBOX]=unbox;
 Config cfg={0};cfg.reserved[3]=2;cfg.enabled=1;cfg.heartbeat=GetTickCount();g_cfg=&cfg;g_busy=1;
 Unit *u=&g_units[0];u->used=1;u->baseApp=&source;u->view=&view;u->last=0;u->coinIndex=1;
 view.fields[0]=(uintptr_t)&donor;donor.fields[1]=source.fields[1]=view.fields[1]=1;
 Skin *skin=u->skins;skin->used=1;skin->app=&donor;skin->go=&donorGo;strcpy(skin->look,"fixture_donor");
 m_getTransform=(void *)10;orig_changeMotion=change;orig_getMotion=motion;g_rowCount=1;
 test_native_parry_fallback(&cfg,skin);
 skin->motionCounts[7]=2;
 change_motion_hook(&source,33,1,4,0,(void *)99,0,NULL);
 assert(calls==1&&lastReceiver==&donor&&lastDetail==7&&lastPart==0&&lastCallback==(void *)99);
 assert(get_motion_hook(&donor,33,0,NULL)==&donor&&lastDetail==7&&lookups==1);
 assert(get_motion_hook(&source,33,0,NULL)==&donor&&lastDetail==7);
 /* No director or sprite change after the donor native call. */
 visible_watch_tick(u,visibleWatches[0].start+185);
 assert(writes==1&&position.y>3&&roots==1);
 visible_attack_end(u);writes=0;assert(roots==0);
 /* A live director can hold the same sprite, including on multi-part actors. */
 donor.fields[2]=(uintptr_t)&director;donor.fields[3]=(uintptr_t)&spriteRenderer;directorState=1;
 visible_watch_begin(u,skin,33,1);visible_watch_tick(u,visibleWatches[0].start+200);
 assert(!visibleWatches[0].app&&!writes&&position.x==2&&position.y==3&&roots==0);
 donor.fields[2]=donor.fields[3]=0;
 /* More than 128 renderers, preserving preexisting hidden bits, including
    rollback when one component declines the change. */
 arrayStorage[3]=625;
 for(int i=0;i<625;i++){arrayStorage[4+i]=(uintptr_t)&renderBits[i];renderBits[i]=(i%3)==0;}
 assert(mask_renderer_array(u,arrayStorage));
 for(int i=0;i<625;i++)assert(renderBits[i]==1);
 static_restore_renderers(u);
 for(int i=0;i<625;i++)assert(renderBits[i]==(i%3==0));
 failIndex=411;assert(!mask_renderer_array(u,arrayStorage));
 for(int i=0;i<625;i++)assert(renderBits[i]==(i%3==0));assert(!u->staticHidden&&roots==0);
 g_rows[0].excluded=SR_STATIC_APPEARANCE_FLAG;skin->motionCounts[7]=0;
 change_motion_hook(&source,33,1,4,0,(void *)99,0,NULL);
 assert(calls==2&&lastReceiver==&source&&lastDetail==33&&lastCallback==(void *)99);
 assert(view.fields[0]==(uintptr_t)&donor&&writes==1&&position.y>3&&roots==1);
 DWORD start=visibleAttacks[0].start;
 visible_attack_tick(u,start+225);assert(writes==2&&position.x>2.4f&&position.z==4);
 visible_attack_tick(u,start+430);assert(position.x==2&&position.y==3&&roots==0);
 /* A queued attack during a busy handoff must show the same donor motion. */
 cfg.mode=1;u->motions[0]=(PendingMotion){.source=&source,.detail=9,.index=0,.row=0,.coin=2,.callback=(void *)88};
 u->motionCount=1;g_presentationGate=1;
 motion_dispatch(u,0);
 assert(calls==3&&lastReceiver==&source&&lastCallback==(void *)88&&roots==1);
 assert(position.y>3&&view.fields[0]==(uintptr_t)&donor);
 cfg.enabled=0;visible_attack_tick(u,GetTickCount());assert(position.x==2&&position.y==3&&roots==0);
 /* Sword signal and the chapter playback entry across successive callbacks. */
 cfg.enabled=1;cfg.mode=0;cfg.heartbeat=GetTickCount();g_presentationGate=0;g_rows[0].excluded=0;
 strcpy(u->baseName,"11115_Outis_Middle_FatherAppearance");strcpy(skin->look,"1327_MiddleFinger_father_Phase4Appearance");
 skin->chapterActor=sr_chapter_actor(u->baseName,skin->look);assert(skin->chapterActor);
 assert(sr_chapter_buff_rank(CH_SWORD,"MiddleFatherSwordFourOutis",1)==3);
 skin->motionCounts[8]=2;
 chapter_forward(u,skin,12,0,1111506,NULL,0,0,0,0,(void *)71,0,NULL);
 assert(lastReceiver==&donor&&lastDetail==8&&lastCallback==(void *)71);
 chapter_forward(u,skin,12,1,1111506,NULL,1,1,0,0,(void *)72,0,NULL);
 assert(lastReceiver==&donor&&lastDetail==8&&lastCallback==(void *)72&&lastPart==1);
 /* A clash tail still holding its callback cannot reveal the source or drop
    the following attack; the real queue receives the next callback once. */
 skin->chapterActor=NULL;skin->motionCounts[8]=0;skin->motionCounts[7]=1;u->coinTier=1;u->coinKnown=1;
 g_timelineEndDepth=1;g_presentationGate=1;
 u->motions[0]=(PendingMotion){.source=&source,.detail=24,.index=0,.row=0,.coin=0,.callback=(void *)73};
 u->motionCount=1;int before=calls;
 motion_dispatch(u,0);assert(calls==before&&u->motionCount==1);
 g_timelineEndDepth=0;motion_dispatch(u,0);
 assert(calls==before+1&&u->motionCount==0&&lastReceiver==&donor&&lastDetail==7&&lastCallback==(void *)73);
 visible_watch_clear(u);assert(roots==0&&view.fields[0]==(uintptr_t)&donor);
 puts("PASS chapter 9 sword/paired coin delivery and clash-end overlap");
 puts("PASS direct/queued attack: donor-only movement, visible cross-type clip, original callback once, shutdown restores position");
 strcpy(skin->look,"BRolandBaseAppearance");
 strcpy(u->baseName,"10115_YiSang_Index_FatherAppearance");
 for(int d=7;d<=16;d++)skin->motionCounts[d]=(d==16?1:3);
 for(int d=7;d<=16;d++)for(int part=0;part<skin->motionCounts[d];part++){
  int previous=calls;
  forward_projected_motion(&donor,7,0,0,0,(void *)74,0,NULL,d,part,0,1,(void*)1,0);
  assert(lastDetail==d&&lastPart==part&&lastReceiver==&donor&&lastCallback==(void*)74&&calls==previous+1);
 }
  strcpy(u->baseName,"10101");unsigned groups=0;
 skin->motionCounts[24]=skin->motionCounts[25]=16;
 /* Sweep every segment deterministically through the actual forwarding entry. */
 skin->weaponAction=(void *)3;skin->weaponViewer=u->observedViewer;
 for(int slot=0;slot<11;slot++){
  int detail=slot<9?7+slot:24+slot-9;
  for(int part=0;part<skin->motionCounts[detail];part++){
   assert(roland_draw(skin,0,(slot+(part+0.5)/skin->motionCounts[detail])/11.0)==detail);
   for(int repeat=0;repeat<2;repeat++){
    forward_projected_motion(&donor,7,0,repeat,0,(void*)75,0,NULL,7,repeat,0,1,(void*)3,0);
    assert(lastDetail==detail&&lastPart==part&&lastReceiver==&donor);
   }
  }
 }
 for(int coin=0;coin<128;coin++){
  int d=roland_weapon(u,skin,(void *)3,coin,7,7);assert((d>=7&&d<=15)||d==24||d==25);
  groups|=1u<<d;
  forward_projected_motion(&donor,7,0,0,0,(void *)75,0,NULL,7,0,coin,1,(void*)3,coin);
  assert(lastDetail==d&&lastReceiver==&donor);
  assert(roland_weapon(u,skin,(void *)3,coin,9,9)==d);
 }
 assert((groups&(groups-1))!=0);
 puts("PASS Index Father S1-S10 and all 28 authored parts; other identities reach every gun and greatsword segment and keep their draw per coin");
 test_roland_clash(u,skin);
 test_imported_clash(u,skin);
 test_imported_attacks(u,skin);
 test_local_repeated_coin(u,skin);
 test_imported_metadata_routing();
 test_roland_build();
 test_imported_art();
 close_test_profile();
 return 0;
}
