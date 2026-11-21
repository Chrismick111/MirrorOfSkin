#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"
static int calls,seenDetail,seenIndex,seenFlag;
static void *seenSelf,*seenCallback,*seenMethod;
static uint8_t seenA1,seenA3,seenA5;
/* This fixture exercises slot routing without a Unity scene or renderers. */
static void *no_scene_class(void *object){(void)object;return NULL;}
static void *fake_get(void *self,int detail,uint8_t flag,void *mi){
 calls++;seenSelf=self;seenDetail=detail;seenFlag=flag;seenMethod=mi;return (void *)(uintptr_t)(1000+detail);
}
static void fake_change(void *self,int detail,uint8_t a1,int index,uint8_t a3,void *cb,uint8_t a5,void *mi){
 calls++;seenSelf=self;seenDetail=detail;seenIndex=index;seenA1=a1;seenA3=a3;seenA5=a5;seenCallback=cb;seenMethod=mi;
}
int main(void){
 api[API_OBJECT_CLASS]=no_scene_class;
 Config cfg={0};g_cfg=&cfg;cfg.enabled=1;cfg.heartbeat=GetTickCount();
 Unit *u=&g_units[0];u->used=1;u->baseApp=(void *)2;u->last=-1;
 Skin *s=&u->skins[0];s->used=1;s->app=(void *)1;s->motionCounts[8]=3;
 u->coinKnown=1;u->coinTier=2;u->coinMotion=24;
 orig_getMotion=fake_get;orig_changeMotion=fake_change;g_busy=1;
 void *result=get_motion_hook(s->app,24,1,(void *)55);
 assert(result==(void *)1008&&calls==1&&seenDetail==8&&seenFlag==1&&seenMethod==(void *)55);
 calls=0;change_motion_hook(s->app,24,1,7,1,(void *)44,1,(void *)55);
 assert(calls==1&&seenSelf==s->app&&seenDetail==8&&seenIndex==1);
 assert(seenA1==1&&seenA3==1&&seenA5==1&&seenCallback==(void *)44&&seenMethod==(void *)55);
 u->coinLast=1;change_motion_hook(s->app,24,0,0,0,NULL,0,NULL);assert(seenDetail==8&&seenIndex==2);
 change_motion_hook(s->app,24,0,-1,0,NULL,0,NULL);assert(seenIndex==-1);
 s->motionCounts[24]=2;change_motion_hook(s->app,24,0,8,0,NULL,0,NULL);assert(seenDetail==24&&seenIndex==1);
 assert(get_motion_hook(s->app,24,0,NULL)==(void *)1024);
 u->coinKnown=0;s->motionCounts[24]=0;assert(get_motion_hook(s->app,24,0,NULL)==(void *)1008);
 u->coinKnown=1;u->coinTier=0;assert(get_motion_hook(s->app,24,0,NULL)==(void *)1008);u->coinTier=2;
 u->coinMotion=20;assert(get_motion_hook(s->app,20,0,NULL)==(void *)1008);
 u->coinDefense=1;assert(get_motion_hook(s->app,20,0,NULL)==(void *)1020);u->coinDefense=0;
 introApp=s->app;assert(get_motion_hook(s->app,20,0,NULL)==(void *)1020);introApp=NULL;
 u->coinMotion=9;assert(get_motion_hook(s->app,20,0,NULL)==(void *)1020);
 assert(get_motion_hook(u->baseApp,24,0,NULL)==(void *)1024);
 g_creating=1;assert(get_motion_hook(s->app,24,0,NULL)==(void *)1024);g_creating=0;
 g_motionDepth=1;assert(get_motion_hook(s->app,24,0,NULL)==(void *)1024);g_motionDepth=0;
 cleanup_pending=1;assert(get_motion_hook(s->app,24,0,NULL)==(void *)1024);cleanup_pending=0;
 cfg.enabled=0;assert(get_motion_hook(s->app,24,0,NULL)==(void *)1024);
 puts("PASS native query/playback hooks: fallback, existing follow-up, coin indices, sentinel, callback ABI, intro/defense/source/creation/cleanup guards");
}
