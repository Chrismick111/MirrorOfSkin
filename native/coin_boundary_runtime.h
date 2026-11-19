/* No Unity hierarchy work in ChangeMotion or timeline-end callbacks.
   All queued native calls are delivered after the old callback stack returns. */
#include "queue_scope.h"
static int g_timelineEndDepth;
static int g_motionDispatchDepth;
static void *m_endTimeline,*orig_endTimeline;
static int motion_busy_mask(void *app){
 if(!app)return 0;
 int mask=0;void *field=find_field_obj(app,"_isRunningTimeline");
 if(field&&*(uint8_t *)((char *)app+((size_t (*)(void *))api[API_FIELD_OFFSET])(field)))mask|=1;
 if(rfield(app,"_curAction"))mask|=2;
 if(rfield(app,"_activeTimelineDelayReleaseCallback"))mask|=4;
 if(director_playing(app))mask|=8;
 return mask;
}
static int motion_handoff_busy(void *app,PendingMotion *m){
 int mask=motion_busy_mask(app);
 /* Only a completed native end callback proves its delegates were delivered.
    Their retained references do not prove playback is still in progress.
    Never exempt a running timeline/director, or another appearance. */
 if(m->endReturned&&app==m->source)mask&=9;
 return mask!=0;
}
static int motion_completed_tail(Unit *u,PendingMotion *m,void *current,int mask){
 if(mask!=8||g_presentationGate||current!=m->source)return 0;
 /* The first coin (including a single-coin skill) can follow a completed
    clash/idle director. End callbacks may return BEFORE motion_capture. */
 if(u->endedApp==current&&u->endedDirector&&u->endedGeneration==u->playbackGeneration&&
    u->endedDirector==rfield(current,"_playableDirector"))return 1;
 return u->deliveredValid&&
   u->deliveredApp==current&&m->action&&u->deliveredAction==m->action&&
   m->coin>u->deliveredCoin&&u->observedAction==m->action&&u->observedViewer;
}
static void motion_release(PendingMotion *m){
 ui_unroot(m->sourceRoot);ui_unroot(m->callbackRoot);memset(m,0,sizeof(*m));
}
static void motion_clear(Unit *u){
 for(int i=0;i<u->motionCount;i++)motion_release(&u->motions[i]);u->motionCount=0;
}
static int motion_capture(void *self,int detail,uint8_t a1,int index,uint8_t a3,void *callback,uint8_t a5,void *mi){
 if(!g_cfg||g_cfg->mode!=1||g_creating||g_motionDepth||cleanup_pending||!enabled_now())return 0;
 Unit *u=unit_for_app(self);
 if(!u||u->dead||u->switching||u->preserveSpecial||introUnit==u||u->coinDefense||g_presentationGate)return 0;
 if(!sr_attack_detail(detail,u->coinKnown,u->coinMotion,0,0)||u->wanted<0)return 0;
 int k=skin_index(u,u->wanted);if(k<0)return 0; /* User can play before warmup; never freeze waiting for an asset. */
 char diagnostic[160];snprintf(diagnostic,sizeof(diagnostic),"coin metadata sinner=%lu coin=%d coinType=%s sourceDetail=%d sourceIndex=%d",(unsigned long)u->sinner,u->wantedSourceCoin,diagnostic_coin_type(u),detail,index);bootlog(diagnostic);
 PendingMotion m={0};m.source=self;m.detail=detail;m.index=index;m.a1=a1;m.a3=a3;m.a5=a5;m.callback=callback;m.method=mi;
 m.row=u->wanted;m.coin=u->wantedSourceCoin;m.tier=u->coinTier;m.last=u->coinLast;m.action=rfield(u->view,"_currentActionLog");
 m.viewer=u->observedViewer;
 if(u->skins[k].chapterActor)m.chapterSkill=chapter_skill_id(u,m.action);
 if((m.tier<1||m.tier>3)&&detail>=7&&detail<=9)m.tier=detail-6;
 /* The live viewer's coin index has already been used by decide_and_apply.
    Query final-coin semantics against that same rooted viewer, not last frame. */
 if(u->observedViewer&&u->observedAction==m.action){
  void *model=rfield(u->observedViewer,"_currentSkillModel");
  void *tier=model?find_method(ui_class(model),"GetSkillTier",0):NULL;
  int value=tier?call_int(tier,model,NULL):-1;if(value>=1&&value<=3)m.tier=value;
  void *last=find_method(ui_class(u->observedViewer),"IsLastCoin",1);int minus=-1;void *args[]={&minus};
  value=last?call_bool(last,u->observedViewer,args):-1;if(value>=0)m.last=value;
 }
 m.sourceRoot=ui_root(self);if(!m.sourceRoot)return 0;
 if(callback){m.callbackRoot=ui_root(callback);if(!m.callbackRoot){motion_release(&m);return 0;}}
 /* Coalesce only an identical outstanding request. Distinct callbacks/coins
    remain ordered; no callback is overwritten by the following coin. */
 if(u->motionCount){
  PendingMotion *old=&u->motions[u->motionCount-1];
  if(old->action==m.action&&old->coin==m.coin&&old->detail==m.detail&&old->index==m.index&&old->callback==m.callback){
   motion_release(old);*old=m;u->wanted=-1;return 1;
  }
 }
 if(u->motionCount==SR_MOTION_QUEUE){motion_release(&m);bootlog("coin dispatch queue full; forwarding original motion");return 0;}
 u->motions[u->motionCount++]=m;u->wanted=-1;return 1;
}
static void motion_dispatch(Unit *u,int original_only){
 if(g_quitting||!u||!u->motionCount||g_timelineEndDepth||g_motionDispatchDepth||u->switching)return;
 if(u->dead||!u->view||!rfield(u->view,"m_CachedPtr")){motion_clear(u);return;}
 PendingMotion m=u->motions[0];
 memmove(u->motions,u->motions+1,(u->motionCount-1)*sizeof(PendingMotion));u->motionCount--;
 void *target=m.source;int detail=m.detail,index=m.index,changed=0;
 void *current=rfield(u->view,"_curAppearance");
 int slot=m.row>=0&&(uint32_t)m.row<g_rowCount?skin_index(u,m.row):-1;
 /* A real scope or a still-playing timeline must not stop native delivery:
    forwarding to the original receiver lets its own end markers complete. */
 int currentMask=motion_busy_mask(current),baseMask=motion_busy_mask(u->baseApp);
 if(!original_only&&enabled_now()&&!g_presentationGate&&slot>=0&&(!motion_handoff_busy(current,&m)||motion_completed_tail(u,&m,current,currentMask))){
  Skin *held=held_appearance(u);
  int busy=(u->baseApp!=current&&motion_handoff_busy(u->baseApp,&m))||
    (held&&held->app!=current&&held->app!=u->baseApp&&motion_handoff_busy(held->app,&m));
  if(!busy){
   Skin *skin=&u->skins[slot];
   if(current==skin->app||unit_switch(u,skin)){
    target=skin->app;changed=current!=target;
   }
  }
 }
 if(target==m.source&&slot>=0&&current!=u->skins[slot].app){
  char why[320];snprintf(why,sizeof(why),"coin handoff rejected sinner=%lu coin=%d camera=%d currentMask=%d baseMask=%d endEvidence=%d generation=%u:%u sameAction=%d deliveredCoin=%d slot=%d originalOnly=%d",(unsigned long)u->sinner,m.coin,g_presentationGate,currentMask,baseMask,u->endedApp==current,u->endedGeneration,u->playbackGeneration,u->deliveredAction==m.action,u->deliveredCoin,slot,original_only);bootlog(why);
 }
 Skin *playing=skin_for_app(u,target);
 if(playing&&(g_rows[playing->row].excluded&SR_STATIC_APPEARANCE_FLAG)){
  ((void (*)(void *,int,uint8_t,int,uint8_t,void *,uint8_t,void *))orig_changeMotion)(target,0,0,0,0,NULL,0,m.method);
  target=u->baseApp;detail=m.detail;index=m.index;playing=NULL;
 }
 if(playing&&!playing->chapterActor){
  detail=sr_resolve_attack(playing->motionCounts,detail,1,m.tier,m.detail,0,0);
  if(strcmp(playing->look,u->baseName))detail=sr_donor_tier_detail(playing->motionCounts,detail,m.tier);
  detail=sr_native_motion_detail(playing->motionCounts,playing->nativeMotionDetail,detail,detail);
  int paired=sr_verified_paired_attack(playing->motionCounts,paired_source(u,playing),motion_identity(playing),m.detail,-1);
  if(paired>=0)detail=paired;
  if(detail>=0&&detail<SR_MOTION_CACHE){
   if(paired>=0)index=counterpart_part(u,playing,m.action,m.coin,m.detail,playing->motionCounts[paired],m.index,m.last);
   else if(!native_order_index(u,m.action,m.coin,playing->motionCounts[detail],&index)){
    index=sr_playback_index(index,playing->motionCounts[detail],m.last);
    static DWORD lastFallback;DWORD now=GetTickCount();if(now-lastFallback>5000){lastFallback=now;bootlog("native order unavailable; legacy index fallback");}
   }
  }
 }
 if(playing&&!playing->chapterActor)sr_salvador_s3(playing->motionCounts,u->baseName,motion_identity(playing),m.detail,m.coin,&detail,&index);
 if(rfield(target,"m_CachedPtr")){
  ++g_motionDispatchDepth;
  /* Apply only while the captured event still matches live skill context. */
  if(playing&&playing->chapterActor&&enabled_now()&&!cleanup_pending)
   target=chapter_forward(u,playing,m.detail,m.index,m.chapterSkill,m.action,m.coin,m.last,m.a1,m.a3,m.callback,m.a5,m.method);
  else forward_projected_motion(target,detail,m.a1,index,m.a3,m.callback,m.a5,m.method,m.detail,m.index,m.coin,sr_queue_scope(m.action,m.viewer,m.coin,m.tier,u->observedAction,u->observedViewer,current_attack_coin(u),u->coinTier));
  --g_motionDispatchDepth;
  /* The native metadata container already projects donor motion onto the
     source motion. Do not override SetAnimSpeed after native playback starts:
     that changes callback timing and can apply projection a second time.
     Cached raw timeline lengths are diagnostic, not a gameplay clock. */

  u->deliveredAction=m.action;u->deliveredApp=target;u->deliveredCoin=m.coin;u->deliveredValid=1;
  if(changed)InterlockedIncrement(&g_switches);
  void *visible=rfield(u->view,"_curAppearance");Skin *shown=skin_for_app(u,visible);
  char line[480];snprintf(line,sizeof(line),"coin play sinner=%lu coin=%d selected=%.63s receiver=%.63s shown=%.63s changed=%d original=%d detail=%d index=%d endReturned=%d camera=%d currentMask=%d baseMask=%d",(unsigned long)u->sinner,m.coin,m.row>=0&&(uint32_t)m.row<g_rowCount?g_rows[m.row].identity:"unknown",playing?g_rows[playing->row].identity:u->baseName,shown?g_rows[shown->row].identity:visible==u->baseApp?u->baseName:"native_special",changed,target==m.source,detail,index,m.endReturned,g_presentationGate,currentMask,baseMask);bootlog(line);
 }
 motion_release(&m);
}
static void timeline_end_hook(void *app,void *director,void *mi){
 Unit *before=unit_for_app(app);unsigned generation=before?before->playbackGeneration:0;
 g_timelineEndDepth++;
 ((void (*)(void *,void *,void *))orig_endTimeline)(app,director,mi);
 /* Capture happens during the callback; permit handoff only after it returns. */
 Unit *u=unit_for_app(app);
 if(u&&u->playbackGeneration==generation&&director&&director==rfield(app,"_playableDirector")&&!(motion_busy_mask(app)&7)){
  Skin *skin=skin_for_app(u,app);if(skin&&skin->wedge)wedge_end(skin);
  u->endedApp=app;u->endedDirector=director;u->endedGeneration=generation;
 }
 if(u)for(int i=0;i<u->motionCount;i++)if(u->motions[i].source==app)u->motions[i].endReturned=1;
 g_timelineEndDepth--;
}

