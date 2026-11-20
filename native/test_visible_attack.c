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
int main(void){
 static void *table[40];api=table;table[API_OBJECT_CLASS]=fake_class;table[API_PARENT]=fake_parent;
 table[API_FIELD]=fake_field;table[API_FIELD_OFFSET]=fake_offset;table[API_METHOD]=fake_method;
 table[API_INVOKE]=fake_invoke;table[API_ROOT]=root;table[API_UNROOT]=unroot;table[API_UNBOX]=unbox;
 Config cfg={0};cfg.enabled=1;cfg.heartbeat=GetTickCount();g_cfg=&cfg;g_busy=1;
 Unit *u=&g_units[0];u->used=1;u->baseApp=&source;u->view=&view;u->last=0;u->coinIndex=1;
 view.fields[0]=(uintptr_t)&donor;donor.fields[1]=source.fields[1]=view.fields[1]=1;
 Skin *skin=u->skins;skin->used=1;skin->app=&donor;skin->go=&donorGo;strcpy(skin->look,"fixture_donor");
 m_getTransform=(void *)10;orig_changeMotion=change;orig_getMotion=motion;g_rowCount=1;
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
 return 0;
}
