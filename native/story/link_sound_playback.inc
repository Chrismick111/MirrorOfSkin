/* Play the events of a shortened coin on its visible clock. A cue reaches
   this plan only when its native Timeline slot was removed from the private
   graph; all other tracks continue through the game's normal FMOD mixer. */
typedef struct {void *reference,*emitter;uintptr_t refRoot,emitterRoot;double time;int fired;} LinkTimedEvent;
typedef struct {void *actor,*action,*viewer;int coin,count;char scene[100];LinkTimedEvent events[96];} LinkSoundPlan;
static LinkSoundPlan linkPendingSounds,linkPlayingSounds;
static void *linkPlayAttached,*linkEventRef,*linkGuidClass;
static void link_sound_release_events(LinkSoundPlan *plan,int keep){
 while(plan->count>keep){
  LinkTimedEvent *e=&plan->events[--plan->count];ui_unroot(e->refRoot);ui_unroot(e->emitterRoot);
 }
}
static void link_sound_reset_plan(LinkSoundPlan *plan){
 link_sound_release_events(plan,0);memset(plan,0,sizeof(*plan));
}
static void link_sound_plan_start(WedgeProbeCtx *ctx){
 link_sound_reset_plan(&linkPendingSounds);
 if(!linkPlayAttached||ctx->visualCoin<0)return;
 if(strcmp(ctx->scene,"11017_S3_Link_02 1")&&strcmp(ctx->scene,"11116_S5_Link_01")&&strcmp(ctx->scene,"11116_S5_Link_02"))return;
 Unit *u=unit_for_app(ctx->target);if(!u||!u->observedAction||!u->observedViewer)return;
 linkPendingSounds.actor=ctx->target;linkPendingSounds.action=u->observedAction;linkPendingSounds.viewer=u->observedViewer;
 linkPendingSounds.coin=ctx->visualCoin;snprintf(linkPendingSounds.scene,sizeof(linkPendingSounds.scene),"%.99s",ctx->scene);
}
static int link_sound_queue_track(int owner,const LinkSoundCue *slots,int n,const LinkSoundBank *bank){
 LinkSoundPlan *p=&linkPendingSounds;int saved=p->count;
 if(!p->actor||n<1||n>96-saved||bank->count<1||bank->count>96)return 0;
 void *app=wedge_presentation_owner(p->actor,owner),*go=app?body_get(app,"get_gameObject"):NULL;
 if(!go)return 0;
 for(int i=0;i<n;i++){
  int index=n==1?0:(int)lround((double)i*(bank->count-1)/(n-1));
  void *asset=bank->cues[index].asset,*params=rfield(asset,"Parameters");
  /* Parameterized events need FMOD's authored parameter setup. */
  if(params&&*(uintptr_t*)((char*)params+24))break;
  void *f=find_field_obj(asset,"EventReference");
  void *box=f?((void*(*)(void*,void*))api[API_FIELD_VALUE])(f,asset):NULL;
  if(!box||ui_class(box)!=linkEventRef)break;
  void *guidField=find_field_obj(box,"Guid");
  void *guid=guidField?((void*(*)(void*,void*))api[API_FIELD_VALUE])(guidField,box):NULL;
  static const unsigned char emptyGuid[16]={0};
  if(!guid||ui_class(guid)!=linkGuidClass||!memcmp(ui_unbox(guid),emptyGuid,sizeof(emptyGuid)))break;
  uintptr_t rh=ui_root(box),gh=ui_root(go);
  if(!rh||!gh){ui_unroot(rh);ui_unroot(gh);break;}
  p->events[p->count++]=(LinkTimedEvent){box,go,rh,gh,slots[i].start,0};
 }
 if(p->count==saved+n)return 1;
 link_sound_release_events(p,saved);return 0;
}
static void link_sound_queue_cancel(int count){link_sound_release_events(&linkPendingSounds,linkPendingSounds.count-count);}
static void link_sound_activate(void *app,void *action,void *viewer,const char *scene,int coin){
 LinkSoundPlan *p=&linkPendingSounds;
 if(p->actor&&p->actor==app&&p->action==action&&p->viewer==viewer&&p->coin==coin&&!strcmp(p->scene,scene)){
  /* A later director can be the first graph to prepare its audio. When the
     same coin builds twice, preserve every matching event already emitted. */
  unsigned char used[96]={0};
  for(int i=0;i<p->count;i++)for(int j=0;j<linkPlayingSounds.count;j++){
   LinkTimedEvent *a=&p->events[i],*b=&linkPlayingSounds.events[j];
   if(!used[j]&&a->emitter==b->emitter&&a->time==b->time){
    used[j]=1;a->fired=b->fired;break;
   }
  }
  link_sound_reset_plan(&linkPlayingSounds);
  linkPlayingSounds=*p;memset(p,0,sizeof(*p));
 }else link_sound_reset_plan(p);
}
static void link_sound_tick_events(double bodyTime,double visibleTime,double end,const LinkShortBody *body,int directorAdvanced){
 LinkSoundPlan *plan=&linkPlayingSounds;
 if(!plan->count)return;
 double time=bodyTime;
 /* All attack cues use the visual body's sampled authored time. Compress
    only the tail after the last body key into the recorded handoff gap.
    S5_02 reaches its uncompressed second body key at 0.15 s. */
 double recovery=body->count?body->recoveryAt:.15,last=body->count?body->lastCue:.15;
 double finish=!strcmp(plan->scene,"11017_S3_Link_02 1")?1./3:.375;
 if(!directorAdvanced&&visibleTime>recovery&&end>last&&finish>recovery)
  time=fmax(time,last+fmin(1.,(visibleTime-recovery)/(finish-recovery))*(end-last));
 for(int i=0;i<plan->count;i++){
  LinkTimedEvent *e=&plan->events[i];
  if(e->fired||time+.000001<e->time)continue;
  e->fired=1;void *args[]={ui_unbox(e->reference),e->emitter};
  int played=call_exc(linkPlayAttached,NULL,args);
  char msg[180];snprintf(msg,sizeof(msg),"link timed donor sound scene=%.70s cue=%.4f frame=%.4f played=%d",plan->scene,e->time,visibleTime,played);bootlog(msg);
 }
}
static void link_sound_runtime_init(void){
 void *rm=unity_class_anywhere("FMODUnity","RuntimeManager");
 linkEventRef=unity_class_anywhere("FMODUnity","EventReference");
 linkGuidClass=unity_class_anywhere("FMOD","GUID");
 const char *types[]={"FMODUnity.EventReference","UnityEngine.GameObject"};
 void *m=rm?method_by_types_one(rm,"PlayOneShotAttached",types,2):NULL;
 if(m&&linkEventRef&&linkGuidClass&&linked_is_static(rm,m)&&team_returns(m,"System.Void"))linkPlayAttached=m;
 link_begin_sound_plan=link_sound_plan_start;link_queue_sound_track=link_sound_queue_track;link_cancel_sound_track=link_sound_queue_cancel;
 bootlog(linkPlayAttached?"link timed donor sound ready":"link timed donor sound using native tracks");
}
