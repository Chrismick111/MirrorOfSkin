/* Included after follower_component_one. All entry points run on the playback
   watch's main thread. Track and owner identities are resolved in the same
   verified graph as GetGenericBinding. No setters are installed here. */
typedef struct {
 int owner;
 uint64_t sequence;
 void *track,*renderer,*spriteGetter,*previous;
 uintptr_t rendererRoot,previousRoot;
 unsigned reads,empty,changes,errors;
 void *ownerTransform,*positionGetter;
 uintptr_t transformRoot;
 float firstPosition[3],lastPosition[3];
 unsigned positionReads,positionChanges,positionErrors,earlyLogs;
 double firstTime,lastTime;
} FollowerFrameProbe;

static FollowerFrameProbe followerFrames[8];
static unsigned followerFrameCount;

static void follower_frames_end(void){
 for(unsigned i=0;i<followerFrameCount;i++){
  FollowerFrameProbe *p=&followerFrames[i];
  char line[320];
  snprintf(line,sizeof(line),"follower body end seq=%llu owner=%d track=%p renderer=%p reads=%u empty=%u changes=%u errors=%u first=%.3f last=%.3f",
   (unsigned long long)p->sequence,p->owner,p->track,p->renderer,p->reads,p->empty,p->changes,p->errors,p->firstTime,p->lastTime);
  bootlog(line);
  snprintf(line,sizeof(line),"follower position end seq=%llu owner=%d reads=%u changes=%u errors=%u first=(%.4f,%.4f,%.4f) last=(%.4f,%.4f,%.4f)",
   (unsigned long long)p->sequence,p->owner,p->positionReads,p->positionChanges,p->positionErrors,
   p->firstPosition[0],p->firstPosition[1],p->firstPosition[2],p->lastPosition[0],p->lastPosition[1],p->lastPosition[2]);
  bootlog(line);
  ui_unroot(p->transformRoot);
  ui_unroot(p->previousRoot);
  ui_unroot(p->rendererRoot);
 }
 followerFrameCount=0;
}

static void follower_frames_sample(double when){
 for(unsigned i=0;i<followerFrameCount;i++){
  FollowerFrameProbe *p=&followerFrames[i];
  int ok=0;
  if(p->positionGetter){
   void *box=call_obj(p->positionGetter,p->ownerTransform,NULL,&ok);
   const float *xyz=ok&&box?(const float*)ui_unbox(box):NULL;
   if(xyz&&isfinite(xyz[0])&&isfinite(xyz[1])&&isfinite(xyz[2])){
    float pos[3];memcpy(pos,xyz,sizeof(pos));
    int moved=p->positionReads&&(fabsf(pos[0]-p->lastPosition[0])>0.0001f ||
     fabsf(pos[1]-p->lastPosition[1])>0.0001f || fabsf(pos[2]-p->lastPosition[2])>0.0001f);
    if(!p->positionReads)memcpy(p->firstPosition,pos,sizeof(pos));
    p->positionChanges+=moved;p->positionReads++;memcpy(p->lastPosition,pos,sizeof(pos));
    if(when>=0&&when<=0.16&&p->earlyLogs<24){
     char msg[256];p->earlyLogs++;
     snprintf(msg,sizeof(msg),"follower position sample seq=%llu owner=%d t=%.6f xyz=(%.4f,%.4f,%.4f)",
      (unsigned long long)p->sequence,p->owner,when,pos[0],pos[1],pos[2]);bootlog(msg);
    }
   }else p->positionErrors++;
  }
  if(!p->spriteGetter)continue;
  void *sprite=call_obj(p->spriteGetter,p->renderer,NULL,&ok);
  if(!ok){p->errors++;continue;}
  int changed=p->reads&&sprite!=p->previous;
  if(!p->reads||changed){
   uintptr_t keep=ui_root(sprite);
   if(sprite&&!keep){p->errors++;continue;}
   ui_unroot(p->previousRoot);p->previousRoot=keep;p->previous=sprite;
   p->changes+=changed;
   if(p->changes<16){
    char name[80]="",line[300];
    if(sprite){
     void *nm=find_method(ui_class(sprite),"get_name",0);
     void *s=nm?call_obj(nm,sprite,NULL,&ok):NULL;
     uintptr_t sr=ok?ui_root(s):0;
     if(sr){string_ascii(s,name,sizeof(name));ui_unroot(sr);}
    }
    snprintf(line,sizeof(line),"follower body frame seq=%llu owner=%d track=%p t=%.3f sprite=%p name=%.79s transitions=%u",
     (unsigned long long)p->sequence,p->owner,p->track,when,sprite,name,p->changes);
    bootlog(line);
   }
  }
  if(!p->reads)p->firstTime=when;
  p->lastTime=when;p->reads++;p->empty+=sprite==NULL;
 }
}

static void *body_get(void *obj,const char *name){
 if(!obj)return NULL;
 void *m=find_method(ui_class(obj),name,0);
 int ok=0;
 void *value=m?call_obj(m,obj,NULL,&ok):NULL;
 return ok?value:NULL;
}

static const char *follower_body_attach(void *owner,void *bound,FollowerFrameProbe *p){
 /* Full animation curve path present in the checked 8380 and 1318 prefabs.
    Brackets and the comma are literal characters in the Transform names. */
 const char *path="[Transform,Fixed]ScaleAndPositionPivot/[Transform]PivotForAnim/[SpRenderer]";
 if(!bound||strcmp(director_binding_kind(bound),"animator"))return "wrong-binding-type";
 void *go=body_get(owner,"get_gameObject");
 void *tr=body_get(go,"get_transform");
 void *pos=tr?find_method(ui_class(tr),"get_position",0):NULL;
 if(pos&&team_returns(pos,"UnityEngine.Vector3")){
  p->transformRoot=ui_root(tr);
  if(p->transformRoot){p->ownerTransform=tr;p->positionGetter=pos;}
 }
 if(!go||body_get(bound,"get_gameObject")!=go)return "wrong-binding-root";
 const char *argTypes[]={"System.String"};
 void *find=tr?method_by_types_one(ui_class(tr),"Find",argTypes,1):NULL;
 if(!find||!team_returns(find,"UnityEngine.Transform"))return "find-unavailable";
 void *str=make_string(path);uintptr_t sr=ui_root(str);
 if(!sr)return "path-allocation";
 void *args[]={str};int ok=0;
 void *node=call_obj(find,tr,args,&ok);
 uintptr_t nr=ok?ui_root(node):0;ui_unroot(sr);
 if(!nr)return "curve-path-missing";
 void *k=unity_class_anywhere("UnityEngine","SpriteRenderer");
 void *type=k?((void *(*)(void *))api[API_TYPE_OBJECT])(((void *(*)(void *))api[API_CLASS_TYPE])(k)):NULL;
 uintptr_t th=ui_root(type);
 void *renderer=NULL;
 const char *status=th&&m_getComponent?follower_component_one(node,type,&renderer):"renderer-type-unavailable";
 uintptr_t rr=ui_root(renderer);
 ui_unroot(th);ui_unroot(nr);
 if(!rr)return renderer?"renderer-root":status;
 void *getter=find_method(ui_class(renderer),"get_sprite",0);
 if(!getter||!team_returns(getter,"UnityEngine.Sprite")){ui_unroot(rr);return "sprite-getter";}
 p->renderer=renderer;p->rendererRoot=rr;p->spriteGetter=getter;
 return "ready";
}

static void follower_frames_begin(void *app,void *director,uint64_t seq){
 if(!app||app!=g_playbackWatchApp||director!=g_playbackWatchDirector||!director_binding_method)return;
 for(int i=0;i<g_wedgeTrackMap.count;i++){
  const WedgeTrack *track=&g_wedgeTrackMap.rows[i];
  if(!track->root||!track->owner||!link_standard_track(track->name)||!link_instance(track->ptr,"AnimationTrack"))continue;
  void *owner=wedge_presentation_owner(app,track->owner);
  if(owner==app)continue;
  void *args[]={track->ptr},*exc=NULL;
  void *bound=ui_invoke(director_binding_method,director,args,&exc);
  FollowerFrameProbe next={0};
  next.owner=track->owner;next.track=track->ptr;next.sequence=seq;next.firstTime=next.lastTime=-1;
  const char *status=!owner?"owner-unavailable":exc?"binding-read-error":
    followerFrameCount>=sizeof(followerFrames)/sizeof(*followerFrames)?"capacity":follower_body_attach(owner,bound,&next);
  if(next.rendererRoot||next.transformRoot)followerFrames[followerFrameCount++]=next;
  char line[256];
  snprintf(line,sizeof(line),"follower body begin seq=%llu owner=%d app=%p track=%p renderer=%p status=%s",
   (unsigned long long)seq,track->owner,owner,track->ptr,next.renderer,status);
  bootlog(line);
 }
}
