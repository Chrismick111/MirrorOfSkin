/* Render on the current appearance without dispatching an attack or playing another timeline. */
#include "link_exact_sprite.inc"
#include "link_coin_frames.h"
#include "link_authored_timing.h"
#include "link_visual_sequence.h"
typedef struct {
 void *app,*go,*renderer,*getter,*setter,*baseline,*last;
 const void *poseWindow;
 uintptr_t appRoot,goRoot,rendererRoot,baselineRoot,lastRoot;
 int id,engaged,samples,exact,changes,errors,renderRepairs,visibilityRecorded;
 char look[120];
} LinkVisualOwner;
typedef struct {
 const LinkBeatRow *beats;int donorFirst,donorCount;LinkSwing swing;
 int owner,group;double start,duration,in,scale,span;void *animation,*sample;uintptr_t root;char clip[100];
} LinkVisualWindow;
typedef struct {
 void *app,*director,*action,*viewer,*sourceAsset;
 uintptr_t appRoot,directorRoot;
 LinkVisualClock clock;
 LinkShortBody shortBody;
 LinkVisualOwner owners[8];LinkVisualWindow windows[128];
 unsigned ownerCount,windowCount;int ensembleSize,coinNumber;double previous,end;
 char coinAsset[100];
 int cameraCues,heldCameraUpdates,earlyCoinLogged;
} LinkVisualScene;
static LinkVisualScene linkVisual;
#include "trio_stage.inc"
#include "duo_stage.inc"
static void pair_camera_end(void);
static void pair_camera_continue(void);
static void pair_camera_tick(LinkVisualScene *scene,double time,double frameDelta);
/* Sample unindexed clips on a script-free replica of the body binding path.
   Only the sprite is transferred to the visible character. */
static struct {void *go,*renderer,*getter,*setter;uintptr_t root,rendererRoot;int attempted;} linkSampler;
static void link_sampler_destroy(void *go){
 if(go){void *args[]={go};call_exc(m_destroyObject,NULL,args);}
}
static void link_sampler_end(void){
 link_sampler_destroy(linkSampler.go);ui_unroot(linkSampler.rendererRoot);ui_unroot(linkSampler.root);
 memset(&linkSampler,0,sizeof(linkSampler));
}
static int link_sampler_prepare(void){
 if(linkSampler.attempted)return linkSampler.renderer!=NULL;
 linkSampler.attempted=1;
 const char *names[]={"Workbench Link Body","[Transform,Fixed]ScaleAndPositionPivot","[Transform]PivotForAnim","[SpRenderer]"};
 void *goClass=unity_class_anywhere("UnityEngine","GameObject"),*srClass=unity_class_anywhere("UnityEngine","SpriteRenderer");
 const char *strType[]={"System.String"},*sysType[]={"System.Type"};
 void *ctor=goClass?method_by_types_one(goClass,".ctor",strType,1):NULL;
 void *add=goClass?method_by_types_one(goClass,"AddComponent",sysType,1):NULL;
 void *hide=srClass?find_method(srClass,"set_forceRenderingOff",1):NULL;
 if(!ctor||!add||!hide||!srClass||!m_setParent||!m_destroyObject)return 0;
 void *parent=NULL,*leaf=NULL;
 for(int i=0;i<4;i++){
  void *name=make_string(names[i]);uintptr_t nh=ui_root(name);
  void *go=ui_new(goClass);uintptr_t gh=ui_root(go);void *args[]={name};
  int created=nh&&gh&&call_exc(ctor,go,args);ui_unroot(nh);
  if(!created){ui_unroot(gh);return 0;}
  void *tr=body_get(go,"get_transform");
  if(i==0){linkSampler.go=go;linkSampler.root=gh;}
  else{
   uint8_t preserve=0;void *pa[]={parent,&preserve};
   if(!tr||!call_exc(m_setParent,tr,pa)){link_sampler_destroy(go);ui_unroot(gh);return 0;}
   ui_unroot(gh);
  }
  if(!tr)return 0;
  parent=tr;leaf=go;
 }
 void *type=((void *(*)(void *))api[API_TYPE_OBJECT])(((void *(*)(void *))api[API_CLASS_TYPE])(srClass));
 uintptr_t th=ui_root(type);void *aa[]={type};int ok=0;
 void *sr=th?call_obj(add,leaf,aa,&ok):NULL;ui_unroot(th);
 if(!ok||!sr)return 0;
 uint8_t off=1;void *ha[]={&off};if(!call_exc(hide,sr,ha))return 0;
 const char *spriteType[]={"UnityEngine.Sprite"};
 linkSampler.getter=find_method(srClass,"get_sprite",0);linkSampler.setter=method_by_types_one(srClass,"set_sprite",spriteType,1);
 if(!linkSampler.getter||!linkSampler.setter)return 0;
 linkSampler.rendererRoot=ui_root(sr);if(!linkSampler.rendererRoot)return 0;
 linkSampler.renderer=sr;return 1;
}
static void *link_sampler_sprite(LinkVisualWindow *w,float time){
 if(!w->sample||!link_sampler_prepare())return NULL;
 void *clear[]={NULL};if(!call_exc(linkSampler.setter,linkSampler.renderer,clear))return NULL;
 void *args[]={linkSampler.go,&time};if(!call_exc(w->sample,w->animation,args))return NULL;
 int ok=0;return call_obj(linkSampler.getter,linkSampler.renderer,NULL,&ok);
}
static int link_visual_same_asset(LinkVisualScene *s){
 if(!s->director)return 0;
 void *get=wedge_probe_asset_method(ui_class(s->director));int ok=0;
 void *asset=get?call_obj(get,s->director,NULL,&ok):NULL;
 return ok&&asset&&asset==s->sourceAsset;
}
static void *link_visual_read(LinkVisualOwner *o){
 void *exc=NULL;return o->getter?ui_invoke(o->getter,o->renderer,NULL,&exc):NULL;
}
static void link_visual_release_pose(LinkVisualOwner *o){
 if(o->engaged&&o->last&&link_visual_read(o)==o->last){
  void *args[]={o->baseline};call_exc(o->setter,o->renderer,args);
 }
 ui_unroot(o->baselineRoot);ui_unroot(o->lastRoot);o->last=o->baseline=NULL;
 o->lastRoot=o->baselineRoot=0;o->engaged=0;o->poseWindow=NULL;
}
/* The animator may have evaluated between the canvas update and camera
   submission. Only re-submit the last accepted pose for this live action.
   Track the pose supplied by the engine so ending our window restores it. */
static int link_visual_current_coin(Unit *u){
 if(!u||!u->observedViewer||!u->observedCoinField)return -1;
 return *(int *)((char *)u->observedViewer+u->observedCoinOffset);
}
static int link_visual_live(void){
 LinkVisualScene *s=&linkVisual;
 if(!s->windowCount||!wedge_probe_main_thread())return 0;
 Unit *lead=unit_for_app(s->app);
 if(!enabled_now()||cleanup_pending||!lead||!lead->view||lead->observedAction!=s->action||
    lead->observedViewer!=s->viewer||rfield(lead->view,"_curAppearance")!=s->app){
  link_visual_end();return 0;
 }
 if(s->ensembleSize>=2&&s->coinNumber>=0&&lead->observedCoinField){
  int live=link_visual_current_coin(lead);
  if(live!=s->coinNumber){
   /* In these three shortened coins the viewer advances at 27-59 ms.
      The director still owns this asset until the actual change at 350-444 ms. */
   int shortened=s->shortBody.count||!strcmp(s->coinAsset,"11116_S5_Link_02");
   if(!shortened||s->clock.directorAdvanced||s->clock.scaled>=.45||
      (live>=0&&live!=s->coinNumber+1)||!link_visual_same_asset(s)){
    link_visual_end();return 0;
   }
   if(!s->earlyCoinLogged){
    char msg[168];snprintf(msg,sizeof(msg),"link pending handoff scene=%.80s stored=%d live=%d elapsed=%.4f",s->coinAsset,s->coinNumber,live,s->clock.scaled);
    bootlog(msg);s->earlyCoinLogged=1;
   }
  }
 }
 return 1;
}
static int link_visual_render_pose(void){
 LinkVisualScene *s=&linkVisual;
 if(!link_visual_live())return 0;
 for(unsigned i=0;i<s->ownerCount;i++){
  LinkVisualOwner *o=&s->owners[i];
  if(!o->engaged||!o->lastRoot||!o->setter)continue;
  Unit *u=unit_for_app(o->app);
  if(!u||!u->view||rfield(u->view,"_curAppearance")!=o->app)continue;
  void *native=link_visual_read(o);
  if(native==o->last)continue;
  uintptr_t keep=ui_root(native);
  if(native&&!keep)continue;
  void *args[]={o->last};
  if(call_exc(o->setter,o->renderer,args)&&link_visual_read(o)==o->last){
   ui_unroot(o->baselineRoot);o->baseline=native;o->baselineRoot=keep;o->renderRepairs++;
  }else ui_unroot(keep);
 }
 return 1;
}
static void link_visual_end_segment(int cameraHandoff){
 link_sound_reset_plan(&linkPlayingSounds);
 if(linkVisual.windowCount){
  char line[250];snprintf(line,sizeof(line),"wedge authored clock scene=%.96s director=%d timelineTime=%.4f gameElapsed=%.4f heldCameraUpdates=%d",
   linkVisual.coinAsset,linkVisual.clock.directorAdvanced,linkVisual.clock.elapsed,linkVisual.clock.scaled,linkVisual.heldCameraUpdates);bootlog(line);
  if(linkVisual.shortBody.recoveryAt>0){
   snprintf(line,sizeof(line),"wedge short body scene=%.96s director=%d sample=%.4f lastCue=%.4f recoveryAt=%.4f",
    linkVisual.coinAsset,linkVisual.clock.directorAdvanced,linkVisual.shortBody.cursor,linkVisual.shortBody.lastCue,linkVisual.shortBody.recoveryAt);bootlog(line);
  }
 }
 link_overlay_end();
 trio_stage_end();
 duo_stage_end();
 if(cameraHandoff)pair_camera_continue();else pair_camera_end();
 LinkVisualScene *s=&linkVisual;
 for(unsigned i=0;i<s->ownerCount;i++){
  LinkVisualOwner *o=&s->owners[i];link_visual_release_pose(o);
  char line[180];snprintf(line,sizeof(line),"link visible end owner=%d samples=%d exact=%d changes=%d errors=%d renderRepairs=%d",o->id,o->samples,o->exact,o->changes,o->errors,o->renderRepairs);bootlog(line);
  ui_unroot(o->rendererRoot);ui_unroot(o->goRoot);ui_unroot(o->appRoot);
 }
 for(unsigned i=0;i<s->windowCount;i++)ui_unroot(s->windows[i].root);
 ui_unroot(s->directorRoot);ui_unroot(s->appRoot);link_sampler_end();link_exact_clear();memset(s,0,sizeof(*s));
}
static void link_visual_end(void){link_visual_end_segment(0);}
static int link_visual_owner(LinkVisualScene *s,void *app,int id,Skin *skin){
 for(unsigned i=0;i<s->ownerCount;i++)if(s->owners[i].app==app)return (int)i;
 if(s->ownerCount>=8)return -1;
 LinkVisualOwner *o=&s->owners[s->ownerCount];o->id=id;o->app=app;
 o->go=body_get(app,"get_gameObject");o->goRoot=ui_root(o->go);o->appRoot=ui_root(app);
 if(!o->goRoot||!o->appRoot){ui_unroot(o->goRoot);ui_unroot(o->appRoot);memset(o,0,sizeof(*o));return -1;}
 if(skin)snprintf(o->look,sizeof(o->look),"%s",link_loaded_look(skin));
 void *tr=body_get(o->go,"get_transform");const char *stringTypes[]={"System.String"};
 void *find=tr?method_by_types_one(ui_class(tr),"Find",stringTypes,1):NULL;
 void *path=make_string("[Transform,Fixed]ScaleAndPositionPivot/[Transform]PivotForAnim/[SpRenderer]");
 uintptr_t ph=ui_root(path);void *args[]={path};int ok=0;
 void *node=ph&&find?call_obj(find,tr,args,&ok):NULL;uintptr_t nh=ok?ui_root(node):0;ui_unroot(ph);
 void *k=unity_class_anywhere("UnityEngine","SpriteRenderer");
 void *type=k?((void *(*)(void *))api[API_TYPE_OBJECT])(((void *(*)(void *))api[API_CLASS_TYPE])(k)):NULL;
 uintptr_t th=ui_root(type);if(th&&nh)follower_component_one(node,type,&o->renderer);
 o->rendererRoot=ui_root(o->renderer);ui_unroot(th);ui_unroot(nh);
 if(o->rendererRoot){
  o->getter=find_method(ui_class(o->renderer),"get_sprite",0);
  const char *types[]={"UnityEngine.Sprite"};o->setter=method_by_types_one(ui_class(o->renderer),"set_sprite",types,1);
 }
 return (int)s->ownerCount++;
}
static void link_visual_load_track(LinkVisualScene *s,LinkAttackEdit *choices,const WedgeTrack *r){
 if(!r->owner||!r->ptr||!link_standard_track(r->name)||!link_instance(r->ptr,"AnimationTrack"))return;
 void *app=wedge_presentation_owner(s->app,r->owner);Unit *u=app?unit_for_app(app):NULL;
 Skin *skin=u?skin_for_app(u,app):NULL;
 if(!u||!app||(skin&&(skin->row<0||(unsigned)skin->row>=g_rowCount)))return;
 /* Keep the partner in the shot even during a section authored for only the
    lead, or when the partner is wearing their original appearance. */
 int owner=link_visual_owner(s,app,r->owner,skin);
 if(owner<0||!skin||(g_rows[skin->row].excluded&SR_STATIC_APPEARANCE_FLAG)||link_track_muted(r->ptr))return;
 void *list=rfield(r->ptr,"m_Clips");int n=list_count(list);
 for(int i=0;i<n&&n<=256&&s->windowCount<128;i++){
  void *clip=list_item(list,i),*source=rfield(rfield(clip,"m_Asset"),"m_Clip");
  if(!source||!link_instance(source,"AnimationClip"))continue;
  int group=link_skill_group(wedge_name(source));if(!group)continue;
  LinkBody *b=link_get_coin_body(choices,skin,group,s->ensembleSize>=2?s->coinAsset:NULL,s->coinNumber);if(!b||!b->asset)continue;
  double start=link_number(clip,"get_start",0),duration=link_number(clip,"get_duration",0);
  if(!isfinite(start)||start<0||!isfinite(duration)||duration<=0)continue;
  LinkVisualWindow w={0};w.start=start;w.duration=duration;w.group=group;
  w.in=b->in;w.span=fmin(b->span*b->scale,b->length-b->in);
  const char *look=link_loaded_look(skin);if(!strncmp(look,"story_",6))look+=6;
  for(unsigned ci=0;ci<sizeof(link_sprite_curves)/sizeof(*link_sprite_curves);ci++){
   if(strcmp(look,link_sprite_curves[ci].look)||strcmp(b->name,link_sprite_curves[ci].animation))continue;
   int first=link_sprite_curves[ci].first,nkeys=link_sprite_curves[ci].count;
   if(s->ensembleSize>=2){
    LinkSwing base=link_coin_base_range(first,nkeys,b->name,&w.in,&w.span);
    w.donorFirst=base.first;w.donorCount=base.count;
   }
   else if(nkeys>1){
    w.in=link_sprite_samples[first].t;
    w.span=fmin(b->length,link_sprite_samples[first+nkeys-1].t+1./60)-w.in;
   }
   break;
  }
  if(!(w.span>0))continue;
  w.animation=rfield(b->asset,"m_Clip");w.root=ui_root(w.animation);if(!w.root)continue;
  w.owner=owner;
  const char *types[]={"UnityEngine.GameObject","System.Single"};
  w.sample=method_by_types_one(ui_class(w.animation),"SampleAnimation",types,2);
  snprintf(w.clip,sizeof(w.clip),"%s",b->name);
  s->windows[s->windowCount++]=w;s->end=fmax(s->end,start+duration);
 }
}
static void link_visual_begin(void *app,void *director,void *asset){
 if(!wedge_probe_main_thread())return;
 Unit *actor=unit_for_app(app);
 int continuing=actor&&asset&&linkVisual.windowCount&&linkVisual.app==app&&
  actor->observedAction&&linkVisual.action==actor->observedAction&&
  actor->observedViewer&&linkVisual.viewer==actor->observedViewer;
 int coin=link_visual_current_coin(actor);
 if(continuing&&linkVisual.ensembleSize>=2&&coin>=0&&coin==linkVisual.coinNumber&&
    !strcmp(linkVisual.coinAsset,wedge_name(asset))){
  if(director&&director!=linkVisual.director){
   uintptr_t root=ui_root(director);
   if(root){
    ui_unroot(linkVisual.directorRoot);linkVisual.directorRoot=root;linkVisual.director=director;
    linkVisual.clock.director=-1;linkVisual.clock.directorAdvanced=0;
    bootlog("link coin director adopted");
   }
  }
  if(director&&director==linkVisual.director)linkVisual.sourceAsset=asset;
  link_sound_activate(app,actor->observedAction,actor->observedViewer,linkVisual.coinAsset,coin);
  return;
 }
 link_visual_end_segment(continuing);if(!actor||!asset)return;
 LinkVisualScene *s=&linkVisual;s->app=app;s->director=director;s->sourceAsset=asset;s->action=actor->observedAction;s->viewer=actor->observedViewer;
 char sceneName[128];snprintf(sceneName,sizeof(sceneName),"%s",wedge_name(asset));
 s->cameraCues=wedge_camera_cues(sceneName);
 if(!strncmp(sceneName,"11116_S5_Link_",14))s->ensembleSize=3;
 else if(!strncmp(sceneName,"11116_S10_Link_",15))s->ensembleSize=5;
 else if(!strncmp(sceneName,"11116_S6_Link_",14)){
  int roles[8]={0};
  for(int i=0;i<g_wedgeTrackMap.count;i++){
   int role=g_wedgeTrackMap.rows[i].owner,j=0;
   if(!role)continue;
   while(j<s->ensembleSize&&roles[j]!=role)j++;
   if(j==s->ensembleSize&&j<8)roles[s->ensembleSize++]=role;
  }
 }
 else if(!strcmp(sceneName,"11116_S9_Link")||pair_timeline_identity(actor->baseName,sceneName))s->ensembleSize=2;
 if(s->ensembleSize>=2){s->coinNumber=coin;snprintf(s->coinAsset,sizeof(s->coinAsset),"%s",sceneName);}
 s->shortBody=link_short_body(s->coinAsset);
 s->appRoot=ui_root(app);s->directorRoot=ui_root(director);s->previous=-1;
 if(!s->appRoot||(director&&!s->directorRoot)){link_visual_end();return;}
 LinkAttackEdit choices={0};
 for(int i=0;i<g_wedgeTrackMap.count;i++)link_visual_load_track(s,&choices,&g_wedgeTrackMap.rows[i]);
 link_restore_attacks(&choices);
 LinkSequencePart plan[128];
 for(unsigned i=0;i<s->windowCount;i++){
  LinkVisualWindow *w=&s->windows[i];
  plan[i]=(LinkSequencePart){w->owner,w->group,(int)i,w->start,w->duration};
  w->duration=0;
 }
 double assetEnd=link_number(asset,"get_duration",0);
 double limit=isfinite(assetEnd)&&assetEnd>0?assetEnd:s->end;
 int segments=s->ensembleSize>=2?link_sequence_coin(plan,s->windowCount,limit):link_sequence_plan(plan,s->windowCount,limit);
 s->end=0;
 for(int i=0;i<segments;i++){
  LinkVisualWindow *w=&s->windows[plan[i].index];
  w->duration=plan[i].duration;if(w->duration<=0)continue;
  w->beats=link_authored_row(s->coinAsset,s->owners[w->owner].id);
  if(w->beats&&w->donorCount>0){
   LinkSwing base={w->donorFirst,w->donorCount,w->clip};
   w->swing=link_coin_swing(s->owners[w->owner].look,w->beats->count,s->coinNumber,base);
  }
  w->scale=w->span/w->duration;s->end=fmax(s->end,w->start+w->duration);
 }
 if(s->ensembleSize>=2&&s->end>0&&isfinite(assetEnd)&&assetEnd>s->end)s->end=assetEnd;
 if(s->ensembleSize>=2){
  char coinLine[220];snprintf(coinLine,sizeof(coinLine),"link coin choreography coin=%d owners=%u cuts=%u attacks=%d timeline=%.80s",coin,s->ownerCount,s->windowCount,segments,s->coinAsset);bootlog(coinLine);
 }
 char line[256];snprintf(line,sizeof(line),"link visible start owners=%u windows=%u end=%.4f ensemble=%d cameraCues=%d timeline=%.96s",s->ownerCount,s->windowCount,s->end,s->ensembleSize,s->cameraCues,sceneName);bootlog(line);
 link_sound_activate(s->app,s->action,s->viewer,s->coinAsset,s->coinNumber);
 if(!s->windowCount){link_visual_end();return;}
 trio_stage_begin(s,asset);
 link_visual_tick();
 link_overlay_tick();
}
static void link_visual_apply(LinkVisualOwner *o,LinkVisualWindow *w,double phase){
 void *before=link_visual_read(o);
 uintptr_t beforeRoot=ui_root(before);
 if(before&&!beforeRoot){o->errors++;return;}
 float time=(float)(w->in+phase*w->scale);
 int spriteKey=-1;const char *shownClip=w->clip;double shownTime=time;
 if(w->beats){
  double unit=link_authored_progress(w->beats,w->start+phase);
  if(w->donorCount>0){
   int key=w->donorFirst+(int)floor(unit*(w->donorCount-1)+.5);
   time=(float)fmax(w->in,link_sprite_samples[key].t);
  }else time=(float)(w->in+unit*fmax(0.,w->span-.00001));
  shownTime=time;
  if(w->swing.count>0){
   int selected=w->swing.first+(int)floor(unit*(w->swing.count-1)+.5);
   spriteKey=link_sprite_samples[selected].key;shownTime=link_sprite_samples[selected].t;shownClip=w->swing.clip;
  }
 }
 void *current=before?before:o->baseline;
 void *exact=o->setter?(spriteKey>=0?link_exact_key(spriteKey,current):link_exact_sprite(o->look,w->clip,time,current)):NULL;
 void *accepted=NULL;
 if(exact){
  void *args[]={exact};
  if((exact==before||call_exc(o->setter,o->renderer,args))&&link_visual_read(o)==exact){accepted=exact;o->exact++;}
 }
 if(!accepted&&o->setter){
  void *sampled=link_sampler_sprite(w,time);
  if(sampled){void *args[]={sampled};
   if((link_visual_read(o)==sampled||call_exc(o->setter,o->renderer,args))&&link_visual_read(o)==sampled)accepted=sampled;
  }
 }
 o->samples++;
 if(!accepted){
  ui_unroot(beforeRoot);
  /* Some atlas keys are unavailable for a single sample. Keep the last
     delivered pose only while its originating attack window is still live. */
  if(o->poseWindow!=w)link_visual_release_pose(o);
  o->errors++;return;
 }
 if(!o->engaged||before!=o->last){
  ui_unroot(o->baselineRoot);o->baseline=before;o->baselineRoot=beforeRoot;beforeRoot=0;
 }
 ui_unroot(beforeRoot);o->engaged=1;o->poseWindow=w;
 if(accepted!=o->last){
  uintptr_t root=ui_root(accepted);
  if(root&&before!=accepted){
   if(o->changes<6){char line[230];snprintf(line,sizeof(line),"link visible pose owner=%d clip=%.65s t=%.4f sprite=%.75s exact=%d",o->id,exact==accepted?shownClip:w->clip,exact==accepted?shownTime:(double)time,wedge_name(accepted),accepted==exact);bootlog(line);}
   o->changes++;
  }
  ui_unroot(o->lastRoot);o->lastRoot=root;o->last=root?accepted:NULL;
 }
}
static void link_visual_tick(void){
 LinkVisualScene *s=&linkVisual;if(!link_visual_live())return;
 s->clock.shortCoin=s->shortBody.count!=0;
 double t=link_clock_now(&s->clock,s->director);if(!isfinite(t)||t<0)return;
 double frameDelta=s->clock.frameDelta;
 double bodyTime=link_body_sample_time(&s->shortBody,t,s->clock.directorAdvanced);
 link_sound_tick_events(bodyTime,t,s->end,&s->shortBody,s->clock.directorAdvanced);
 /* Keep a finished duo shot through the inter-coin handoff. In the captured
    Sinclair chain that gap reached 0.36 s. A changed action or viewer above
    still releases immediately, including while the game clock is paused. */
 if(s->ensembleSize>=2&&s->previous>=s->end-1e-6&&t>=s->end-1e-6){
  if(link_clock_tail_done(&s->clock,t,s->end))link_visual_end();
  else s->previous=t;
  return;
 }
 /* A hit hold freezes the animation sample. The subject and native camera
    can still move on each scaled game frame during that same sample. */
 if(t==s->previous){
  if(frameDelta>0&&s->cameraCues>0){s->heldCameraUpdates++;pair_camera_tick(s,t,frameDelta);}
  return;
 }
 for(unsigned i=0;i<s->ownerCount;i++){
  LinkVisualOwner *o=&s->owners[i];Unit *v=unit_for_app(o->app);
  if(!v||!v->view||rfield(v->view,"_curAppearance")!=o->app){link_visual_release_pose(o);continue;}
  LinkVisualWindow *chosen=NULL;
  for(unsigned j=0;j<s->windowCount;j++){
   LinkVisualWindow *w=&s->windows[j];double end=w->start+w->duration;
   /* The underlying body graph still evaluates its original cutaways.
      Own the donor pose for this whole coin, holding the wind-up before
      this participant's entry and their follow-through after the strike. */
   if(s->ensembleSize>=2&&w->owner==(int)i&&w->duration>0){chosen=w;break;}
   if(w->duration<=0||w->owner!=(int)i||w->start>t||(t>=end&&w->start<=s->previous))continue;
   if(!chosen||w->start>chosen->start)chosen=w;
  }
  if(chosen){
   double phase=(chosen->beats?bodyTime:t)-chosen->start;
   if(!chosen->beats){
    if(s->ensembleSize>=2)phase=fmin(fmax(0.,phase),fmax(0.,chosen->duration-1e-5));
    else if(phase>=chosen->duration)phase=chosen->duration*.5;
   }
   link_visual_apply(o,chosen,phase);
  }else link_visual_release_pose(o);
 }
 trio_stage_tick(s,t);
 duo_stage_tick(s,t);
 if(frameDelta>0)pair_camera_tick(s,t,frameDelta);
 double previous=s->previous;s->previous=t;
 if(s->ensembleSize<2&&previous>=s->end&&t>=s->end)link_visual_end();
}
