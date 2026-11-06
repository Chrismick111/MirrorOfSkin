#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"
typedef struct {uintptr_t field[20];} Obj;
static const char *fields[]={"m_CachedPtr","_camController","_zoomActorAloneV2AppearanceCamController","_zoomActorAloneV2TriggerSource","_zoomActorAloneV2Owner","_battleUnitView","_cameraZoomV2Owner","_curCam","camera_Actor","isActiveCam","camPivot_Actor","camPivot_Enemy","camera_Enemy","_curAppearance","_currentActionLog","_isRunningTimeline","_curAction","_activeTimelineDelayReleaseCallback","_playableDirector","_skinMetadataContainer"};
static Obj manager,app,controller,view,owner,foreign,ownCamera,foreignCamera,actorPivot,enemyPivot;
static int completes,viewCompletes,cameraEnds,localClears,activeCalls;
static int appearanceCalls;static Obj *desiredAppearance;
static void *fake_class(void *o){return (void *)1;}
static void *fake_parent(void *o){return NULL;}
static void *fake_lookup(void *image,const char *space,const char *name){return (void *)1;}
static void *fake_field(void *klass,const char *name){
 for(int i=0;i<20;i++)if(!strcmp(name,fields[i]))return (void *)(uintptr_t)(i+1);return NULL;
}
static size_t fake_offset(void *field){return ((uintptr_t)field-1)*sizeof(uintptr_t);}
static void *fake_method(void *klass,const char *name,int count){
 if(!strcmp(name,"get_Instance"))return (void *)100;
 if(!strcmp(name,"CompleteZoomActorAloneV2"))return (void *)101;
 if(!strcmp(name,"CompleteCameraZoomV2"))return (void *)102;
 if(!strcmp(name,"OnCameraEnd"))return (void *)103;
 if(!strcmp(name,"ClearZoomV2FovSync"))return (void *)104;
 return NULL;
}
static void *fake_invoke(void *m,void *o,void **args,void **exception){
 *exception=NULL;
 switch((uintptr_t)m){
 case 100:return &manager;
 case 101:assert(o==&manager&&args[0]==&owner);completes++;break;
 case 102:assert(o==&view&&args[0]==&owner);viewCompletes++;break;
 case 103:assert(o==&controller);cameraEnds++;break;
 case 104:assert(o==&controller);localClears++;break;
 case 105:assert(o==&actorPivot||o==&enemyPivot);assert(*(uint8_t *)args[0]==0);activeCalls++;break;
 case 106:assert(o==&view);view.field[13]=(uintptr_t)desiredAppearance;appearanceCalls++;break;
 }
 return NULL;
}
static void reset(void){
 memset(&manager,0,sizeof(manager));memset(&app,0,sizeof(app));memset(&controller,0,sizeof(controller));memset(&view,0,sizeof(view));
 app.field[0]=controller.field[0]=view.field[0]=1;app.field[1]=(uintptr_t)&controller;app.field[5]=(uintptr_t)&view;
 controller.field[8]=(uintptr_t)&ownCamera;controller.field[9]=1;
 controller.field[10]=(uintptr_t)&actorPivot;controller.field[11]=(uintptr_t)&enemyPivot;
 completes=viewCompletes=cameraEnds=localClears=activeCalls=0;
}
static int idleCalls;static void *idleReceiver;
static void *fake_string(const char *s){return (void *)77;}
static int roots;
static uintptr_t fake_root(void *o,int pinned){roots++;return 1;}
static void fake_unroot(uintptr_t h){roots--;}
static void fake_wb(void *o,void **field,void *value){*field=value;}
static void fake_idle(void *self,int detail,uint8_t a1,int index,uint8_t a3,void *cb,uint8_t a5,void *mi){
 assert(detail==0&&index==0);idleCalls++;idleReceiver=self;
}
static int plays,playedIndex,nativeIndex;static void *playedSelf,*playedCallback;
static void fake_play(void *self,int detail,uint8_t a1,int index,uint8_t a3,void *cb,uint8_t a5,void *mi){
 assert(detail==7&&a1==1&&a3==1&&a5==1&&mi==(void *)199);
 if(cb)assert(roots>=2);
 if(g_motionDispatchDepth){int before=plays;motion_dispatch(&g_units[0],0);assert(plays==before);}
 plays++;playedSelf=self;playedIndex=index;playedCallback=cb;
}
static void fake_end(void *self,void *director,void *mi){
 assert(g_timelineEndDepth>0);
 change_motion_hook(self,7,1,nativeIndex,1,&actorPivot,1,(void *)199);
 motion_dispatch(&g_units[0],0); /* Reentrant canvas/end callback must not deliver. */
}
static int afterCalls;
static void fake_after(void *self,void *mi){assert(g_clashBoundary==1);assert(self==&manager&&mi==(void *)123);afterCalls++;}
int main(void){
 int assertion_executed=0;assert(++assertion_executed==1);if(assertion_executed!=1)return 90;
 int quiet=0;
 assert(!sr_idle_restore_ready(1,1,0,0,0,&quiet)&&quiet==0);
 assert(!sr_idle_restore_ready(0,1,0,1,0,&quiet)&&quiet==0);
 assert(!sr_idle_restore_ready(0,1,0,0,0,&quiet));
 assert(!sr_idle_restore_ready(0,1,0,0,0,&quiet));
 assert(sr_idle_restore_ready(0,1,0,0,0,&quiet));
 assert(!sr_idle_restore_ready(0,1,0,0,1,&quiet));
 assert(!sr_idle_restore_ready(0,0,0,0,0,&quiet)&&quiet==0);
 static void *table[37];api=table;table[API_OBJECT_CLASS]=fake_class;table[API_PARENT]=fake_parent;
 table[API_CLASS]=fake_lookup;table[API_FIELD]=fake_field;table[API_FIELD_OFFSET]=fake_offset;
 table[API_METHOD]=fake_method;table[API_INVOKE]=fake_invoke;m_setActive=(void *)105;
 reset();manager.field[2]=(uintptr_t)&controller;manager.field[4]=(uintptr_t)&owner;
 manager.field[7]=(uintptr_t)&ownCamera;view.field[6]=(uintptr_t)&owner;
 assert(release_owned_appearance_camera(&app));assert(completes==1&&viewCompletes==1&&cameraEnds==1);
 reset();manager.field[2]=(uintptr_t)&foreign;manager.field[4]=(uintptr_t)&foreign;
 manager.field[7]=(uintptr_t)&foreignCamera;
 assert(release_owned_appearance_camera(&app));assert(!completes&&!viewCompletes&&!cameraEnds&&localClears==1&&activeCalls==2);
 assert(controller.field[9]==0&&manager.field[4]==(uintptr_t)&foreign);
 /* A stale V1 camera pointer must not terminate someone else's V2 scope. */
 reset();manager.field[2]=(uintptr_t)&foreign;manager.field[4]=(uintptr_t)&foreign;manager.field[7]=(uintptr_t)&ownCamera;
 assert(release_owned_appearance_camera(&app));assert(!completes&&!cameraEnds&&localClears==1);
 reset();manager.field[7]=(uintptr_t)&ownCamera;
 assert(release_owned_appearance_camera(&app));assert(cameraEnds==1&&!completes);
 Config cfg={0};cfg.enabled=1;cfg.heartbeat=GetTickCount();g_cfg=&cfg;g_busy=1;g_presentationGate=1;
 Unit *u=&g_units[0];u->used=1;u->view=&view;u->baseApp=&app;u->last=0;
 u->skins[0].used=1;u->skins[0].app=&foreign;foreign.field[0]=1;view.field[13]=(uintptr_t)&foreign;
 orig_changeMotion=fake_idle;change_motion_hook(&app,0,0,0,0,NULL,0,NULL);
 assert(idleCalls==1&&idleReceiver==&app); /* Never redirect a source viewer's idle. */
 activeCalls=0;sync_visibility(u);assert(activeCalls==0);
 view.field[13]=(uintptr_t)&app;retain_last_appearance(u);assert(idleCalls==1&&u->idleRestoreFrames==0);
 /* Same viewer and same action: two ordinary coins must be able to commit
    different cached donors, while a real camera or timeline still blocks. */
 for(int viewer=0;viewer<2;viewer++)for(int camera=0;camera<2;camera++)for(int timeline=0;timeline<2;timeline++)
  assert(sr_coin_switch_ready(viewer,camera,timeline)==(!camera&&!timeline));
 table[API_STRING_NEW]=fake_string;table[API_ROOT]=fake_root;table[API_UNROOT]=fake_unroot;
 reset();memset(&foreign,0,sizeof(foreign));memset(&owner,0,sizeof(owner));
 memset(g_units,0,sizeof(g_units));memset(g_rows,0,sizeof(g_rows));memset(g_switchGate,0,sizeof(g_switchGate));
 u=&g_units[0];u->used=1;u->sinner=101;u->view=&view;u->baseApp=&app;u->last=-1;
 u->ncand=2;u->cand[0]=0;u->cand[1]=1;u->coinKnown=1;u->coinTier=1;
 g_rowCount=2;g_rows[0]=(PoolRow){.sinner=101,.enabled=1,.weight=1};strcpy(g_rows[0].identity,"10101");
 g_rows[1]=(PoolRow){.sinner=101,.enabled=1,.weight=0};strcpy(g_rows[1].identity,"10102");
 /* Rooted viewer's live index overrides a repeated donor-local index=0. */
 u->observedViewer=&enemyPivot;u->observedAction=&manager;u->observedCoinField=1;u->observedCoinOffset=15*sizeof(uintptr_t);
 enemyPivot.field[15]=0;view.field[14]=(uintptr_t)&manager;
 void *target=&app;int detail=7,index=0;
 decide_and_apply(&target,&detail,&index);assert(u->wanted==0&&u->attackDrawIndex==0);
 g_rows[0].weight=0;g_rows[1].weight=1;
 decide_and_apply(&target,&detail,&index);assert(u->wanted==0); /* Same coin reuses its draw. */
 enemyPivot.field[15]=1;
 decide_and_apply(&target,&detail,&index);assert(u->wanted==1&&u->attackDrawIndex==1);
 u->skins[0].used=1;u->skins[0].row=0;u->skins[0].app=&foreign;foreign.field[0]=1;
 u->skins[1].used=1;u->skins[1].row=1;u->skins[1].app=&owner;owner.field[0]=1;
 cfg.max_skins=2;cfg.heartbeat=GetTickCount();g_anyViewerActive=1;g_presentationGate=0;g_ready=1;g_frame=100;
 view.field[13]=(uintptr_t)&app;u->wanted=0;desiredAppearance=&foreign;m_changeAppearance=(void *)106;
 app.field[1]=0;app.field[15]=1;
 apply_pending(u,0);assert(appearanceCalls==0&&u->wanted==0); /* Incomplete timeline. */
 app.field[15]=0;g_presentationGate=1;
 apply_pending(u,0);assert(appearanceCalls==0&&u->wanted==0); /* Actual close-up. */
 g_presentationGate=0;apply_pending(u,0);assert(appearanceCalls==1&&view.field[13]==(uintptr_t)&foreign);
 g_frame++;u->wanted=1;desiredAppearance=&owner;
 apply_pending(u,0);assert(appearanceCalls==2&&view.field[13]==(uintptr_t)&owner);
 /* Idle retention stays locked for the viewer, even though coin swaps do not. */
 u->viewerActive=1;view.field[13]=(uintptr_t)&app;retain_last_appearance(u);assert(appearanceCalls==2&&u->idleRestoreFrames==0);u->viewerActive=0;
 manager.field[4]=(uintptr_t)&manager;assert(camera_scope_active());
 manager.field[4]=0;manager.field[7]=0;assert(!camera_scope_active());
 /* Full-pool variant preparation is deterministic and includes alternate prefabs. */
 u->ncand=2;u->sinner=110;g_rows[0].sinner=g_rows[1].sinner=110;
 strcpy(g_rows[0].identity,"11009");strcpy(g_rows[1].identity,"11016");
 memset(u->skins,0,sizeof(u->skins));
 for(int i=0;i<4;i++){u->skins[i].used=1;u->skins[i].row=i/2;u->skins[i].form=i%2;}
 int ready,total,units,failed;cfg.mode=1;assert(skin_limit()==SR_SKIN_MAX);
 warm_totals(&ready,&total,&units,&failed);assert(ready==4&&total==4&&units==1);
 u->skins[3].used=0;q_head=q_tail=0;u->warmCursor=0;
 warm_enqueue(u);warm_enqueue(u);Unit *job=NULL;int row=-1;
 assert(queue_pop(&job,&row)&&job==u&&row==1&&q_poppedForm==1);q_poppedForm=-1;
 u->unavailableForms=1u<<sr_form_index("11016");warm_totals(&ready,&total,&units,&failed);assert(ready==3&&total==3&&failed==1);
 /* Real deferred hook path, rooted callbacks, two coins under one viewer. */
 memset(u,0,sizeof(*u));memset(g_rows,0,sizeof(g_rows));reset();memset(&foreign,0,sizeof(foreign));memset(&owner,0,sizeof(owner));
 u->used=1;u->view=&view;u->baseApp=&app;u->sinner=101;u->last=-1;u->ncand=2;u->cand[0]=0;u->cand[1]=1;
 u->coinKnown=1;u->coinTier=1;u->observedViewer=&enemyPivot;u->observedAction=&foreignCamera;
 u->observedCoinField=1;u->observedCoinOffset=15*sizeof(uintptr_t);
 view.field[14]=(uintptr_t)&foreignCamera;view.field[13]=(uintptr_t)&app;app.field[1]=0;
 foreign.field[0]=owner.field[0]=1;
 for(int i=0;i<2;i++){u->skins[i].used=1;u->skins[i].row=i;u->skins[i].app=i?(void *)&owner:(void *)&foreign;u->skins[i].meta=&manager;u->skins[i].motionCounts[7]=i?2:3;
  g_rows[i].sinner=101;g_rows[i].enabled=1;snprintf(g_rows[i].identity,64,"1010%d",i+1);}
 g_rows[0].weight=1;g_rows[1].weight=0;g_rowCount=2;
 table[API_WBARRIER]=fake_wb;cfg.mode=1;cfg.heartbeat=GetTickCount();g_busy=1;g_ready=1;g_presentationGate=0;g_anyViewerActive=1;
 orig_changeMotion=fake_play;orig_endTimeline=fake_end;m_changeAppearance=(void *)106;
 roots=plays=appearanceCalls=0;enemyPivot.field[15]=0;nativeIndex=0;desiredAppearance=&foreign;
 timeline_end_hook(&app,NULL,NULL);assert(plays==0&&u->motionCount==1&&roots==2&&g_timelineEndDepth==0);
 /* Native end callbacks may retain delegates after playback has stopped. */
 app.field[16]=(uintptr_t)&actorPivot;app.field[17]=(uintptr_t)&enemyPivot;
 PendingMotion probe=u->motions[0];assert(probe.endReturned);
 assert(motion_busy_mask(&app)==6&&!motion_handoff_busy(&app,&probe));
 probe.endReturned=0;assert(motion_handoff_busy(&app,&probe));
 probe.endReturned=1;app.field[15]=1;assert(motion_handoff_busy(&app,&probe));
 app.field[15]=0;assert(motion_handoff_busy(&foreign,&probe)==0);
 motion_dispatch(u,0);assert(plays==1&&playedSelf==&foreign&&playedCallback==&actorPivot&&appearanceCalls==1&&roots==0);
 app.field[16]=app.field[17]=0;
 enemyPivot.field[15]=1;nativeIndex=1;g_rows[0].weight=0;g_rows[1].weight=1;u->coinLast=1;desiredAppearance=&owner;
 timeline_end_hook(&foreign,NULL,NULL);assert(plays==1&&u->motionCount==1&&roots==2);
 motion_dispatch(u,0);assert(plays==2&&playedSelf==&owner&&playedIndex==1&&appearanceCalls==2&&roots==0);
 /* If a close-up acquired the scope while queued, forward the native receiver
    instead of waiting for an end marker which requires this very motion. */
 enemyPivot.field[15]=2;g_rows[0].weight=1;g_rows[1].weight=0;nativeIndex=2;
 timeline_end_hook(&owner,NULL,NULL);assert(u->motionCount==1&&roots==2);
 g_presentationGate=1;motion_dispatch(u,0);assert(plays==3&&playedSelf==&owner&&playedIndex==1&&appearanceCalls==2&&roots==0&&u->motionCount==0);
 g_presentationGate=0;enemyPivot.field[15]=3;nativeIndex=0;
 timeline_end_hook(&owner,NULL,NULL);assert(u->motionCount==1&&roots==2);
 motion_clear(u);assert(u->motionCount==0&&roots==0);
 PendingMotion tail={0};tail.source=&owner;tail.action=&foreignCamera;tail.coin=4;
 u->deliveredValid=1;u->deliveredApp=&owner;u->deliveredAction=&foreignCamera;u->deliveredCoin=3;
 assert(motion_completed_tail(u,&tail,&owner,8));
 assert(!motion_completed_tail(u,&tail,&owner,9));
 assert(!motion_completed_tail(u,&tail,&owner,10));
 assert(!motion_completed_tail(u,&tail,&owner,12));
 assert(!motion_completed_tail(u,&tail,&foreign,8));
 tail.coin=3;assert(!motion_completed_tail(u,&tail,&owner,8));tail.coin=4;
 g_presentationGate=1;assert(!motion_completed_tail(u,&tail,&owner,8));g_presentationGate=0;
 cfg.enabled=0;orig_afterCointoss=fake_after;after_cointoss_hook(&manager,(void *)123);assert(afterCalls==1&&g_clashBoundary==0);cfg.enabled=1;
 puts("PASS enabled assertions, complete form prewarm, callback-stack barrier, real deferred two-coin playback, callback roots, camera forward progress and cancellation");
 puts("PASS same-viewer two-coin commits, one draw per live source coin, no 15-frame lock, real camera/timeline barriers, idle and foreign V1/V2 ownership protection");
 return 0;
}

