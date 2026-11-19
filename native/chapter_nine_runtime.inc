#include "ch9_skill_map.h"
static int chapter_skill_id(Unit *u,void *action){
 if(!u||!u->viewerActive||!action||u->observedAction!=action||!u->observedViewer||
    rfield(u->view,"_currentActionLog")!=action||rfield(u->observedViewer,"_actor")!=u->view)return 0;
 void *model=rfield(u->observedViewer,"_currentSkillModel");
 if(!model)return 0;
 static void *lastClass,*getter,*idField;
 void *klass=ui_class(model);
 if(lastClass!=klass){
  lastClass=klass;getter=NULL;idField=NULL;
  const char *names[]={"GetSkillID","GetSkillId","get_SkillID","get_SkillId","GetID","get_ID"};
  for(unsigned i=0;i<sizeof(names)/sizeof(*names);i++){
   void *method=find_method(klass,names[i],0);
   if(method&&team_returns(method,"System.Int32")){getter=method;break;}
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
 if((id<=0||id/100!=atoi(u->baseName))&&idField){
  void *boxed=((void *(*)(void*,void*))api[API_FIELD_VALUE])(idField,model);
  int *value=boxed?ui_unbox(boxed):NULL;if(value)id=*value;
 }
 /* A model instance ID cannot identify a personality skill record. */
 return id>0&&id/100==atoi(u->baseName)?id:0;
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
static void *chapter_forward(Unit *unit,Skin *skin,int requested,int index,int skillId,void *action,int coin,int last,
 uint8_t a1,uint8_t a3,void *callback,uint8_t a5,void *method){
 int verified=0,detail=chapter_group(unit,skin,requested,skillId,&verified);
 void *app=skin->app;
 if(detail<0){
  app=unit->baseApp;
  detail=requested;
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
 int nativeDetail=detail,nativePart=part;
 if(count>0&&part>=0&&is_skill_detail(requested)&&verified!=5){
  /* Stay inside the authored group. Exact clip matches and finishers also
     seed the body history for later callbacks without changing their pose. */
  counterpart_visual_part(unit,skin,requested,index,coin,last||verified==4?SR_PAIR_KEEP_PART:SR_PAIR_WITHIN_GROUP,&detail,&part);
 }
 void *savedApp=g_chapterPlaybackApp;int savedDetail=g_chapterPlaybackDetail;
 ProjectionContext savedProjection=g_projection;
 FxPlaybackPlan *savedCapture=g_fxCapture;uint64_t savedOwner=g_fxCaptureOwner;
 g_chapterPlaybackApp=app==skin->app?app:NULL;g_chapterPlaybackDetail=detail;
 g_projection=(ProjectionContext){0};
 if(detail!=nativeDetail||part!=nativePart)g_projection=(ProjectionContext){app,nativeDetail,nativePart,detail};
 g_fxCapture=NULL;g_fxCaptureOwner=0;
 fx_plan_close_app(app,0);playback_begin(app);
 ((void (*)(void *,int,uint8_t,int,uint8_t,void *,uint8_t,void *))orig_changeMotion)(app,detail,a1,part,a3,callback,a5,method);
 g_chapterPlaybackApp=savedApp;g_chapterPlaybackDetail=savedDetail;
 g_projection=savedProjection;g_fxCapture=savedCapture;g_fxCaptureOwner=savedOwner;
 if(is_skill_detail(requested)){
  char line[244];snprintf(line,sizeof(line),"chapter native look=%.63s source=%d:%d played=%d:%d receiver=%s evidence=%d skill=%d coin=%d last=%d",skin->look,requested,index,detail,part,app==skin->app?"enemy":"source",verified,skillId,coin,last);
  bootlog(line);
 }
 return app;
}
