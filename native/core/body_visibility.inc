/* Some stock abnormalities declare alternate Spine and sprite bodies.
   Preserve their native activation timing while hiding stale body poses. */
enum { BODY_POSE_MAX=12, BODY_POSE_UNKNOWN=-2, BODY_POSE_SPINE=-1 };
typedef struct {
 void *object,*get,*set;
 int saved;
} BodyRenderer;
struct BodyVisibility {
 void *getDetail,*getActive,*getSpineEnabled,*spineGo;
 BodyRenderer spine,sprite;
 void *groups[BODY_POSE_MAX];
 int groupCount;
 int8_t motionPose[SR_MOTION_CACHE];
};

static BodyRenderer body_renderer(void *renderer){
 void *klass=renderer?ui_class(renderer):NULL;
 return (BodyRenderer){renderer,find_method(klass,"get_forceRenderingOff",0),
                        find_method(klass,"set_forceRenderingOff",1),-1};
}

static void body_mask(BodyRenderer *r,int hide){
 if(hide&&r->saved<0){
  int old=call_bool(r->get,r->object,NULL);
  uint8_t off=1;void *args[]={&off};
  if(old>=0&&(old||call_exc(r->set,r->object,args)))r->saved=old;
 }else if(!hide&&r->saved>=0){
  uint8_t off=0;void *args[]={&off};
  if(r->saved||call_exc(r->set,r->object,args))r->saved=-1;
 }
}

static void sync_donor_body(Skin *skin){
 BodyVisibility *body=skin?skin->bodyVisibility:NULL;
 if(!body||call_bool(body->getActive,skin->go,NULL)!=1)return;
 int detail=call_int(body->getDetail,skin->app,NULL);
 int pose=detail>=0&&detail<SR_MOTION_CACHE?body->motionPose[detail]:BODY_POSE_UNKNOWN;
 if(pose==BODY_POSE_UNKNOWN){
  body_mask(&body->spine,0);
  body_mask(&body->sprite,0);
  return;
 }
 if(pose==BODY_POSE_SPINE){
  body_mask(&body->spine,0);
  if(call_bool(body->getActive,body->spineGo,NULL)!=1||
     call_bool(body->getSpineEnabled,body->spine.object,NULL)!=1)return;
 }else{
  /* The requested clip may deliberately wait several frames before
     activating this root. The outgoing body follows the game's timing. */
  if(call_bool(body->getActive,body->groups[pose],NULL)!=1)return;
  body_mask(&body->spine,1);
 }
 body_mask(&body->sprite,1);
 for(int i=0;i<body->groupCount;i++){
  if(pose!=i&&go_active_self(body->groups[i])==1)set_active(body->groups[i],0);
 }
}

static int cache_donor_body_pose(BodyVisibility *body,void *motion,void *motionRoot){
 void *getDetail=find_method(ui_class(motion),"get_MotionDetail",0);
 void *isSpine=find_field_obj(motion,"isSpineAnim");
 if(!isSpine)return 0;
 int detail=call_int(getDetail,motion,NULL);
 if(detail<0||detail>=SR_MOTION_CACHE||body->motionPose[detail]!=BODY_POSE_UNKNOWN)return 0;
 int spine=*(uint8_t *)((char *)motion+((size_t (*)(void *))api[API_FIELD_OFFSET])(isSpine));
 void *objects=rfield(motion,"motionObjects");
 int count=list_count(objects),pose=BODY_POSE_UNKNOWN;
 for(int i=0;i<count;i++){
  void *go=list_item(objects,i);
  void *tr=go?call_obj(m_getTransform,go,NULL,NULL):NULL;
  void *parent=tr?call_obj(find_method(ui_class(tr),"get_parent",0),tr,NULL,NULL):NULL;
  /* The alternate body roots are direct children of Motion. Effects can
     live elsewhere or be animated below a body root by the same clip. */
  if(parent!=motionRoot)continue;
  if(spine||pose!=BODY_POSE_UNKNOWN)return 0;
  int group=0;
  while(group<body->groupCount&&body->groups[group]!=go)group++;
  if(group==body->groupCount){
   if(group==BODY_POSE_MAX)return 0;
   body->groups[body->groupCount++]=go;
  }
  pose=group;
 }
 if(!spine&&pose==BODY_POSE_UNKNOWN)return 0;
 body->motionPose[detail]=spine?BODY_POSE_SPINE:(int8_t)pose;
 return 1;
}

static int donor_primary_starts_empty(void *prefab){
 void *args[]={t_appearance};
 void *app=call_obj(m_getComponent,prefab,args,NULL);
 void *sprite=rfield(app,"sprenderer_charactermotion");
 void *klass=ui_class(sprite),*getSprite=find_method(klass,"get_sprite",0);
 if(!getSprite||call_bool(find_method(klass,"get_enabled",0),sprite,NULL)!=0)return 0;
 void *exception=NULL;
 return !ui_invoke(getSprite,sprite,NULL,&exception)&&!exception;
}

static int prepare_stock_donor_body(Skin *skin,void *prefab){
 BodyVisibility body={0};
 void *app=skin->app;
 void *spines=rfield(app,"_spineSkins");
 void *skeleton=list_count(spines)==1?list_item(spines,0):NULL;
 void *parts=skeleton?rfield(app,"parts"):NULL;
 if(!parts||rfield(parts,"abnormalitySpine")!=skeleton||list_count(rfield(parts,"partsViewInfo"))<=0)return 0;
 const char *partsClass=((const char *(*)(void *))api[API_CLASS_NAME])(ui_class(parts));
 if(!partsClass||strcmp(partsClass,"AbnormalityParts"))return 0;
 void *sprite=rfield(app,"sprenderer_charactermotion");
 void *spriteGo=app_go(sprite);
 void *tr=spriteGo?call_obj(m_getTransform,spriteGo,NULL,NULL):NULL;
 void *find=tr?find_method(ui_class(tr),"Find",1):NULL;
 void *name=find?make_string("Motion"):NULL;
 void *findArgs[]={name};
 void *motionRoot=name?call_obj(find,tr,findArgs,NULL):NULL;
 if(!motionRoot)return 0;
 body.spine=body_renderer(rfield(skeleton,"_spine_renderer"));
 body.sprite=body_renderer(sprite);
 body.spineGo=app_go(body.spine.object);
 body.getSpineEnabled=find_method(ui_class(body.spine.object),"get_enabled",0);
 body.getDetail=find_method(ui_class(app),"get_CurrentMotionDetail",0);
 body.getActive=find_method(ui_class(skin->go),"get_activeInHierarchy",0);
 if(!body.spine.get||!body.spine.set||!body.sprite.get||!body.sprite.set||
    !body.getDetail||!body.getActive||!body.spineGo||!body.getSpineEnabled)return 0;
 for(int i=0;i<SR_MOTION_CACHE;i++)body.motionPose[i]=BODY_POSE_UNKNOWN;
 void *motions=rfield(app,"motionList");
 int n=list_count(motions);
 if(n<1||n>SR_MOTION_CACHE)return 0;
 for(int i=0;i<n;i++){
  void *motion=list_item(motions,i);
  if(!motion||!cache_donor_body_pose(&body,motion,motionRoot))return 0;
 }
 if(body.motionPose[18]!=BODY_POSE_SPINE||body.motionPose[0]<0)return 0;
 int attack=0;
 for(int i=0;i<SR_MOTION_CACHE;i++)if(is_skill_detail(i)&&body.motionPose[i]>=0){attack=1;break;}
 if(!attack||!donor_primary_starts_empty(prefab))return 0;

 /* The donor was initialized through the base appearance method on a
    player view. Establish the native parts component's own initial state
    without attaching enemy-view callbacks from AbnormalityAppearance. */
 void *init=find_method(ui_class(parts),"Init",1);
 void *reset=find_method(ui_class(parts),"ResetParts",0);
 void *initArgs[]={app};
 if(!init||!reset||!call_exc(init,parts,initArgs)||!call_exc(reset,parts,NULL)){
  bootlog("donor body: native parts initialization failed");
  return 0;
 }
 skin->bodyVisibility=HeapAlloc(GetProcessHeap(),0,sizeof(body));
 if(!skin->bodyVisibility)return 0;
 *skin->bodyVisibility=body;
 sync_donor_body(skin);
 return 1;
}
