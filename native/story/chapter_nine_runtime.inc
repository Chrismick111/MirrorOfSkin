#include "ch9_skill_map.h"
static int observed_skill_id(Unit *u,void *action,int strictOwner){
 if(!u||!u->viewerActive||!action||u->observedAction!=action||!u->observedViewer||
    rfield(u->view,"_currentActionLog")!=action||rfield(u->observedViewer,"_actor")!=u->view)return 0;
 void *model=rfield(u->observedViewer,"_currentSkillModel");
 if(!model)return 0;
 static void *lastClass,*getter,*idField;
 static int genericGetter;
 void *klass=ui_class(model);
 if(lastClass!=klass){
  lastClass=klass;getter=NULL;idField=NULL;genericGetter=0;
  const char *names[]={"GetSkillID","GetSkillId","get_SkillID","get_SkillId","GetID","get_ID"};
  for(unsigned i=0;i<sizeof(names)/sizeof(*names);i++){
   void *method=find_method(klass,names[i],0);
   if(method&&team_returns(method,"System.Int32")){getter=method;genericGetter=i>=4;break;}
  }
  const char *fields[]={"_skillID","_skillId","skillID","skillId","<SkillID>k__BackingField"};
  for(unsigned i=0;i<sizeof(fields)/sizeof(*fields);i++){
   void *f=find_field_obj(model,fields[i]);if(!f)continue;
   void *t=((void *(*)(void*))api[API_FIELD_TYPE])(f);
   char *n=t?((char *(*)(void*))api[API_TYPE_NAME])(t):NULL;
   int isInt=n&&!strcmp(n,"System.Int32");if(n)((void (*)(void*))api[API_FREE])(n);
   if(isInt){idField=f;break;}
  }
 }
 int id=getter?call_int(getter,model,NULL):0;
 int owner=atoi(u->baseName);
 if(id>0&&((!strictOwner&&!genericGetter)||id/100==owner))return id;
 if(idField){
  void *boxed=((void *(*)(void*,void*))api[API_FIELD_VALUE])(idField,model);
  int *value=boxed?ui_unbox(boxed):NULL;
  if(value&&*value>0&&(!strictOwner||*value/100==owner))return *value;
 }
 /* A model instance ID cannot identify a personality skill record. */
 return 0;
}
static int chapter_skill_id(Unit *u,void *action){
 return observed_skill_id(u,action,1);
}
/* Both immediate and deferred playback use the same authored group. */
static const char *chapter_source(Unit *unit,const SrChapterActor *actor){
 if(actor->alternate){
  enum SrChapterSignal signal=sr_chapter_signal(unit->baseName,unit->stageSource);
  if((signal==CH_DON||signal==CH_FAUST)&&unit->chapterSignal==(int)signal&&
     unit->chapterPhase>=0&&unit->observedModel&&unit->chapterModel==unit->observedModel)
   return unit->chapterPhase?actor->alternate:actor->base;
 }
 if(actor->alternate&&(unit->nativeValid?unit->nativeStage==1:!strcmp(unit->baseName,actor->alternate)))return actor->alternate;
 return actor->base;
}
static int chapter_group(Unit *unit,Skin *skin,int requested,int skillId,int *verified){
 const SrChapterActor *actor=skin->chapterActor;
 const char *source=chapter_source(unit,actor);
 /* These source slots sit in the attack enum range but contain duel wins. */
 if(!strncmp(source,"10115_",6)&&(requested==32||requested==33)){*verified=5;return skin->chapterRole[requested]<0?-1:requested;}
 if(!strncmp(source,"11115_",6)&&requested==15){
  *verified=5;
  return !strcmp(skin->look,"1327_MiddleFinger_father_Phase4Appearance")&&skin->chapterRole[37]>=0?37:-1;
 }
 /* The awakened player's second transformation is the enemy's death slot. */
 if(!strcmp(source,"10314_Donquixote_Index_Disciple_AwakenAppearance")&&requested==21){*verified=5;return -1;}
 if(requested>=0&&requested<SR_MOTION_CACHE&&skin->chapterRole[requested]<0&&!is_skill_detail(requested)){
  *verified=5;return -1;
 }
 int mapped=ch9_exact_motion(skillId,skin->look,requested);
 if(!skillId)mapped=ch9_unambiguous_motion(atoi(actor->base),skin->look,requested);
 if(mapped>=0){
  *verified=2;
  /* A known skill with absent timing metadata stays with its source viewer. */
  return mapped<SR_MOTION_CACHE&&skin->motionCounts[mapped]>0?mapped:-1;
 }
 return sr_chapter_group(actor,source,skin->look,motion_identity(skin),skin->motionCounts,requested,verified);
}
/* A source skill can report the same motion index for several coins. Without
   per-coin de-duplication every one of those coins replays the same donor clip,
   which reads as a stuck animation. Prefer the game's native build order, then
   the next unused ordinary clip of the same group, and finally borrow an unused
   segment from the nearest attack group when the current group is exhausted. */
static int chapter_segment_used(const Unit *unit,int coin,int detail,int part){
  for(int c=0;c<coin;c++)
    if(unit->chapterReplayDetail[c]==(unsigned char)detail&&
       unit->chapterReplayPart[c]==(unsigned char)part)return 1;
  return 0;
}
static int chapter_clip_allowed(const Skin *skin,int detail,int part){
  if(!skin||detail<0||detail>=SR_MOTION_CACHE||part<0)return 0;
  int n=skin->motionCounts[detail];
  if(n<1||n>32||part>=n)return 0;
  /* Without a cached ordinary mask every authored clip is fair game. */
  uint32_t mask=skin->ordinaryClips[detail];
  return !mask||(mask&(UINT32_C(1)<<part))!=0;
}
static int chapter_reroute(Unit *unit,Skin *skin,int coin,int fromDetail,int *detail,int *part){
  int bestDetail=-1,bestPart=-1,bestScore=INT_MAX;
  for(int d=0;d<SR_MOTION_CACHE;d++){
    if(sr_attack_group_slot(d)<0)continue;
    int n=skin->motionCounts[d];
    if(n<1||n>32)continue;
    int distance=d>fromDetail?d-fromDetail:fromDetail-d;
    for(int k=0;k<n;k++){
      if(!chapter_clip_allowed(skin,d,k))continue;
      if(chapter_segment_used(unit,coin,d,k))continue;
      /* Stay close to the requested group and keep the clip order stable. */
      int score=distance*40+k;
      if(score<bestScore){bestScore=score;bestDetail=d;bestPart=k;}
    }
  }
  if(bestDetail<0)return 0;
  *detail=bestDetail;*part=bestPart;return 1;
}
static int chapter_replay_avoid(Unit *unit,Skin *skin,void *action,int coin,int *detail,int *part,int count,int last){
  if(!unit||!skin||!action||!detail||!part)return 0;
  if(unit->chapterReplayAction!=action){
    unit->chapterReplayAction=action;
    /* Group zero is a valid group. An unseen coin has no group yet. */
    memset(unit->chapterReplayDetail,0xff,sizeof(unit->chapterReplayDetail));
  }
  if(coin<0||coin>=SR_VARIETY_COINS)return 0;
  int chosen=*detail;
  if(chosen<0||chosen>=SR_MOTION_CACHE)return 0;
  int limit=skin->motionCounts[chosen];
  if(limit<1||count<1)return 0;
  if(count>limit)count=limit;
  int slot=*part;
  if(slot<0||slot>=limit)return 0;
  if(!last&&!chapter_segment_used(unit,coin,chosen,slot)){
    unit->chapterReplayDetail[coin]=(unsigned char)chosen;
    unit->chapterReplayPart[coin]=(unsigned char)slot;
    return 0;
  }
  /* The final coin keeps the authored tail of its own group while it is free.
     A shorter group that already exposed that clip may still need a reroute. */
  if(last&&!chapter_segment_used(unit,coin,chosen,slot)&&chapter_clip_allowed(skin,chosen,slot)){
    unit->chapterReplayDetail[coin]=(unsigned char)chosen;
    unit->chapterReplayPart[coin]=(unsigned char)slot;
    return 0;
  }
  int start=slot;
  if(!native_order_index(unit,action,coin,count,&start)||start<0||start>=count)start=slot;
  for(int j=0;j<count;j++){
    int k=(start+j)%count;
    if(!chapter_clip_allowed(skin,chosen,k))continue;
    if(chapter_segment_used(unit,coin,chosen,k))continue;
    char line[208];snprintf(line,sizeof(line),"chapter replay avoided coin=%d detail=%d from=%d to=%d",coin,chosen,slot,k);
    bootlog(line);
    unit->chapterReplayDetail[coin]=(unsigned char)chosen;
    unit->chapterReplayPart[coin]=(unsigned char)k;
    *part=k;return 1;
  }
  /* Every authored clip of this group already appeared on an earlier coin.
     Borrow the nearest unused attack segment instead of freezing on one clip. */
  int nextDetail=chosen,nextPart=slot;
  if(chapter_reroute(unit,skin,coin,chosen,&nextDetail,&nextPart)){
    char line[232];snprintf(line,sizeof(line),"chapter replay rerouted coin=%d from=%d:%d to=%d:%d last=%d",
                            coin,chosen,slot,nextDetail,nextPart,last);
    bootlog(line);
    unit->chapterReplayDetail[coin]=(unsigned char)nextDetail;
    unit->chapterReplayPart[coin]=(unsigned char)nextPart;
    *detail=nextDetail;*part=nextPart;return 1;
  }
  /* Nothing is free: keep the native choice rather than blanking the motion. */
  unit->chapterReplayDetail[coin]=(unsigned char)chosen;
  unit->chapterReplayPart[coin]=(unsigned char)slot;
  return 0;
}
static void *chapter_forward(Unit *unit,Skin *skin,int requested,int index,int skillId,void *action,int coin,int last,
 uint8_t a1,uint8_t a3,void *callback,uint8_t a5,void *method){
 int verified=0,detail=chapter_group(unit,skin,requested,skillId,&verified);
 void *app=skin->app;
 if(detail<0||(is_skill_detail(requested)&&detail<SR_MOTION_CACHE&&!skin->motionCounts[detail])){
  int fallback=verified==5?-1:sr_playback_detail(skin->motionCounts,requested,unit->coinTier);
  if(fallback>=0&&fallback<SR_MOTION_CACHE&&skin->motionCounts[fallback]>0)detail=fallback;
  else if(unit->staticHidden){
   /* Preserve source callbacks on missing attack or special-role contracts. */
   if(is_skill_detail(requested)&&verified!=5)visible_attack_begin(unit,skin,requested,coin);
   keep_hidden_timing_active(unit);app=unit->baseApp;detail=requested;
  }else detail=0;
 }
 int count=app==skin->app&&detail>=0&&detail<SR_MOTION_CACHE?skin->motionCounts[detail]:0,part=index;
 if(count>0&&index>=0&&verified!=5){
  const char *source=chapter_source(unit,skin->chapterActor);
  int exact=sr_chapter_exact_part(source,skin->look,requested,index,detail,count);
  int sameSize=sr_chapter_source_count(source,requested)==count;
  if(exact>=0){part=exact;verified=4;}
  else if(is_skill_detail(requested)&&!sameSize&&coin>=0&&native_order_index(unit,action,coin,count,&part)){
   /* BuildMotionOrder may emit a negative native sentinel. Preserve it. */
   if(part>=count)part=count-1;
  }else if(index>=count||(is_skill_detail(requested)&&!sameSize&&last))part=count-1;
 }
 chapter_replay_avoid(unit,skin,action,coin,&detail,&part,count,last);
 void *savedApp=g_chapterPlaybackApp;int savedDetail=g_chapterPlaybackDetail;
 ProjectionContext savedProjection=g_projection;
 FxPlaybackPlan *savedCapture=g_fxCapture;uint64_t savedOwner=g_fxCaptureOwner;
 g_chapterPlaybackApp=app==skin->app?app:NULL;g_chapterPlaybackDetail=detail;
 g_projection=(ProjectionContext){0};g_fxCapture=NULL;g_fxCaptureOwner=0;
 fx_plan_close_app(app,0);playback_begin(app);
 void *savedTiming=hiddenTimingApp;
 if(app==unit->baseApp&&unit->staticHidden)hiddenTimingApp=app;
 else if(is_skill_detail(requested)&&verified!=5&&!(g_rows[skin->row].excluded&2))visible_watch_begin(unit,skin,requested,coin);
 ((void (*)(void *,int,uint8_t,int,uint8_t,void *,uint8_t,void *))orig_changeMotion)(app,detail,a1,part,a3,callback,a5,method);
 hiddenTimingApp=savedTiming;g_chapterPlaybackApp=savedApp;g_chapterPlaybackDetail=savedDetail;
 g_projection=savedProjection;g_fxCapture=savedCapture;g_fxCaptureOwner=savedOwner;
 if(is_skill_detail(requested)){
  char line[244];snprintf(line,sizeof(line),"chapter native look=%.63s source=%d:%d played=%d:%d receiver=%s evidence=%d skill=%d coin=%d last=%d",skin->look,requested,index,detail,part,app==skin->app?"enemy":"source",verified,skillId,coin,last);
  bootlog(line);
 }
 return app;
}
