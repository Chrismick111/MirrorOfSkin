#define main legacy_test_main
#include "test_camera_lifecycle.c"
#undef main
static const char *extra[]={"_isEnd","_isCancel","_actor","_hasSkillUnitView","_skillViewer","view","_duelView1","_duelView2"};
typedef struct {uintptr_t field[28];} Extended;
static Extended viewerObject,behaviourObject,infoObject;
static int eventCalls,expectedDepth;
static void *event_field(void *klass,const char *name){
 void *f=fake_field(klass,name);if(f)return f;
 for(int i=0;i<8;i++)if(!strcmp(name,extra[i]))return (void *)(uintptr_t)(21+i);
 return NULL;
}
static void *event_invoke(void *m,void *o,void **args,void **exception){
 if(m==(void *)107){*exception=NULL;return &viewerObject;}
 return fake_invoke(m,o,args,exception);
}
static void event_original(void *self,int coin,void *mi){
 assert(g_visualEventDepth==expectedDepth);eventCalls++;
}
static int updates,results,duels,projectionCalls,skillStarts;
static uint8_t fake_update(void *self,int coin,int power,uint8_t a2,uint8_t a3,void *mi){
 assert(self==&view&&coin==updates&&power==13&&a2==0&&a3==1&&mi==(void *)99);updates++;return 1;
}
static void fake_evade_result(void *viewer,void *log,void *mi){
 assert(g_evadeResultDepth==1);assert(update_cointoss_hook(&view,results,13,0,1,(void *)99)==1);results++;
}
static void fake_duel_result(void *self,void *mi){assert(g_clashBoundary==1&&!g_duelCameraBoundary);duels++;}
static void *fake_anim_item(void *retbuf,void *self,int source,int donor,int index,int sourceIndex,uint8_t last,void *mi){
 assert(self==&foreign&&source==15&&donor==7&&index==1&&sourceIndex==4&&last==1&&mi==(void *)123);projectionCalls++;return retbuf;
}
static void fake_projected(void *self,int detail,uint8_t a1,int index,uint8_t a3,void *cb,uint8_t a5,void *mi){
 assert(detail==7&&index==1&&cb==&manager);
 assert(motion_anim_item_hook(&owner,self,detail,detail,index,index,1,(void *)123)==&owner);
}
static void fake_skill_start(void *self,void *mi){skillStarts++;}
int main(void){
 legacy_test_main();
 static Config cfg;cfg.enabled=1;cfg.heartbeat=GetTickCount();g_cfg=&cfg;
 api[API_FIELD]=event_field;api[API_INVOKE]=event_invoke;
 memset(g_units,0,sizeof(g_units));reset();
 Unit *u=&g_units[0];u->used=1;u->sinner=101;u->view=&view;u->baseApp=&app;u->last=-1;
 viewerObject.field[22]=(uintptr_t)&view;m_getViewer=(void *)107;
 Coin coin;coin_info(u,&coin);assert(u->viewerActive&&u->observedViewer);
 viewerObject.field[20]=1;coin_info(u,&coin);assert(!u->viewerActive&&!u->observedViewer&&!u->observedViewerRoot);
 viewerObject.field[20]=0;viewerObject.field[21]=1;coin_info(u,&coin);assert(!u->viewerActive);
 viewerObject.field[21]=0;coin_info(u,&coin);assert(u->viewerActive);
 /* Rejected early events must leave fallback motion decisions enabled. */
 orig_sourceCoin=event_original;orig_evadeEvent=event_original;expectedDepth=0;
 manager.field[4]=(uintptr_t)&owner;
 source_coin_hook(&viewerObject,0,NULL);assert(eventCalls==1&&g_visualEventDepth==0);
 behaviourObject.field[24]=(uintptr_t)&viewerObject;viewerObject.field[23]=(uintptr_t)&view;
 evade_event_hook(&behaviourObject,0,NULL);assert(eventCalls==2&&g_visualEventDepth==0);
 /* Successful selection forwards exactly once, suppressing only duplicate selection. */
 manager.field[4]=manager.field[7]=0;view.field[13]=(uintptr_t)&app;app.field[1]=0;
 u->ncand=1;u->cand[0]=0;u->skins[0].used=1;u->skins[0].row=0;u->skins[0].app=&foreign;foreign.field[0]=1;
 memset(g_rows,0,sizeof(g_rows));g_rowCount=1;g_rows[0].sinner=101;g_rows[0].enabled=1;g_rows[0].weight=1;strcpy(g_rows[0].identity,"10312");
 cfg.mode=0;desiredAppearance=&foreign;m_changeAppearance=(void *)106;expectedDepth=1;
 source_coin_hook(&viewerObject,1,NULL);assert(eventCalls==3&&g_visualEventDepth==0&&u->last==0);
 /* A viewer existing elsewhere must not block a safe clash boundary. */
 g_anyViewerActive=1;u->viewerActive=1;u->wanted=0;infoObject.field[25]=(uintptr_t)&view;
 clash_prepare_info(&infoObject);assert(u->wanted==-1&&u->last==0);
 /* Real evade-result nesting: two results get fresh weighted selections,
    UI result/arguments are forwarded once; unrelated cointosses do not draw. */
 orig_evadeResult=fake_evade_result;orig_updateCointoss=fake_update;
 u->ncand=2;u->cand[1]=1;g_rowCount=2;g_rows[1]=g_rows[0];strcpy(g_rows[1].identity,"10706");g_rows[1].weight=0;
 u->skins[1].used=1;u->skins[1].row=1;u->skins[1].app=&owner;owner.field[0]=1;
 evade_result_hook(&viewerObject,NULL,NULL);assert(u->defensePickedRow==0&&updates==1&&results==1&&!g_evadeResultDepth);
 g_rows[0].weight=0;g_rows[1].weight=1;desiredAppearance=&owner;
 evade_result_hook(&viewerObject,NULL,NULL);assert(u->defensePickedRow==1&&updates==2&&results==2&&!g_evadeResultDepth);
 assert(update_cointoss_hook(&view,2,13,0,1,(void *)99)==1&&u->defensePickedRow==1&&updates==3);
 /* A duel owns its zoom until its result callback: switching must not release
    that camera; foreign skill zooms must still reject the switch. */
 Extended duel={0};duel.field[26]=(uintptr_t)&infoObject;
 orig_afterCointoss=fake_duel_result;manager.field[4]=(uintptr_t)&duel;desiredAppearance=&foreign;
 g_rows[0].weight=1;g_rows[1].weight=0;u->motionCount=0;u->preserveSpecial=0;
 int previousCompletions=completes;
 after_cointoss_hook(&duel,NULL);assert(u->last==0&&duels==1&&completes==previousCompletions&&manager.field[4]==(uintptr_t)&duel);
 manager.field[4]=(uintptr_t)&foreignCamera;g_rows[0].weight=0;g_rows[1].weight=1;desiredAppearance=&owner;
 after_cointoss_hook(&duel,NULL);assert(u->last==0&&duels==2&&manager.field[4]==(uintptr_t)&foreignCamera);
 /* Source timing survives donor detail/index mapping, and context is restored. */
 orig_changeMotion=fake_projected;orig_motionAnimItem=fake_anim_item;
 forward_projected_motion(&foreign,7,1,1,0,&manager,0,NULL,15,4);
 assert(projectionCalls==1&&!g_projection.app);
 cfg.mode=1;u->wanted=-1;u->pending=-1;orig_skillStart=fake_skill_start;g_busy=0;
 skill_start_hook(&foreign,NULL);assert(skillStarts==1&&u->wanted==-1&&u->pending==-1);
 puts("PASS repeated evade weighted draws, exact-once UI result, duel-owned camera preservation, foreign camera protection, original source timing and no competing skill-start draw");
 puts("PASS stale viewer end/cancel, rejected event fallback, successful event exact-once forwarding, clash with extant viewer");
 return 0;
}
