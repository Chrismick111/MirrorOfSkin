/* Unity calls these on the rendering path. Some pipeline implementations
   skip camera event wrappers when there are no managed event subscribers. */
static void *linkSubmitMain, *linkOriginalBegin, *linkOriginalSetup, *linkOriginalPreCull;
static _Thread_local int linkSubmitActive;
static unsigned linkSubmitObserved;

static int link_submit_flag(void *obj,const char *name){
 void *method=obj?find_method(ui_class(obj),name,0):NULL;
 return method?call_bool(method,obj,NULL):-1;
}
static void link_submit_visibility(void){
 if(linkVisual.ensembleSize!=3)return;
 for(unsigned i=0;i<linkVisual.ownerCount;i++){
  LinkVisualOwner *owner=&linkVisual.owners[i];
  if(!owner->engaged||owner->visibilityRecorded||!owner->renderer)continue;
  owner->visibilityRecorded=1;
  void *go=body_get(owner->renderer,"get_gameObject");
  int active=link_submit_flag(go,"get_activeInHierarchy");
  int enabled=link_submit_flag(owner->renderer,"get_enabled");
  int hidden=link_submit_flag(owner->renderer,"get_forceRenderingOff");
  char line[132];snprintf(line,sizeof(line),"trio render owner=%d active=%d enabled=%d forceOff=%d",owner->id,active,enabled,hidden);bootlog(line);
 }
}
static void link_submit_pose(void *camera,unsigned source){
 if(!camera||!wedge_probe_main_thread()||linkSubmitActive||!linkVisual.windowCount||
    !enabled_now()||cleanup_pending||!linkSubmitMain||InterlockedCompareExchange(&g_busy,1,0))return;
 linkSubmitActive=1;
 int ok=0;void *main=call_obj(linkSubmitMain,NULL,NULL,&ok);
 if(ok&&camera==main&&link_visual_render_pose()){
  if(trioStage.part&&linkVisual.previous>=0)
   trio_stage_tick(&linkVisual,linkVisual.previous);
  if(duoStage.active&&linkVisual.previous>=0)
   duo_stage_tick(&linkVisual,linkVisual.previous);
  link_submit_visibility();
  if(!(linkSubmitObserved&source)){
   linkSubmitObserved|=source;
   const char *name=source==1?"beginCameraRendering":source==2?"setupCameraProperties":"preCull";
   char line[120];snprintf(line,sizeof(line),"link render submission reached %s",name);bootlog(line);
  }
 }
 linkSubmitActive=0;InterlockedExchange(&g_busy,0);
}
static void link_submit_begin(uintptr_t context,void *camera,void *method){
 ((void (*)(uintptr_t,void *,void *))linkOriginalBegin)(context,camera,method);
 link_submit_pose(camera,1);
}
static void link_submit_setup(void *context,void *camera,uint8_t stereo,int eye,void *method){
 ((void (*)(void *,void *,uint8_t,int,void *))linkOriginalSetup)(context,camera,stereo,eye,method);
 link_submit_pose(camera,2);
}
static void link_submit_setup_stereo(void *context,void *camera,uint8_t stereo,void *method){
 ((void (*)(void *,void *,uint8_t,void *))linkOriginalSetup)(context,camera,stereo,method);
 link_submit_pose(camera,2);
}
static void link_submit_precull(void *camera,void *method){
 ((void (*)(void *,void *))linkOriginalPreCull)(camera,method);
 link_submit_pose(camera,4);
}
static int link_submit_register(void *klass,const char *name,const char **types,int count,int isStatic,
                                void *handler,void **original){
 void *m=klass?method_by_types_one(klass,name,types,count):NULL;
 if(!m||!*(void **)m||!team_returns(m,"System.Void")||
    !(isStatic?linked_is_static(klass,m):team_instance_method(klass,m)))return 0;
 void *target=*(void **)m;
 if(MH_CreateHook(target,handler,original)!=MH_OK)return 0;
 if(MH_EnableHook(target)==MH_OK)return 1;
 MH_RemoveHook(target);*original=NULL;return 0;
}
static void link_submit_install(void){
 void *cam=unity_class_anywhere("UnityEngine","Camera");
 linkSubmitMain=cam?method_by_types_one(cam,"get_main",NULL,0):NULL;
 if(!linkSubmitMain||!linked_is_static(cam,linkSubmitMain)||!team_returns(linkSubmitMain,"UnityEngine.Camera")){
  linkSubmitMain=NULL;bootlog("link render submission main camera unavailable");return;
 }
 const char *ctxType="UnityEngine.Rendering.ScriptableRenderContext",*camType="UnityEngine.Camera";
 const char *beginTypes[]={ctxType,camType},*setupTypes[]={camType,"System.Boolean","System.Int32"};
 void *manager=unity_class_anywhere("UnityEngine.Rendering","RenderPipelineManager");
 void *context=unity_class_anywhere("UnityEngine.Rendering","ScriptableRenderContext");
 int begin=link_submit_register(manager,"BeginCameraRendering",beginTypes,2,1,link_submit_begin,&linkOriginalBegin);
 if(!begin){
  void *pipeline=unity_class_anywhere("UnityEngine.Rendering","RenderPipeline");
  begin=link_submit_register(pipeline,"BeginCameraRendering",beginTypes,2,1,link_submit_begin,&linkOriginalBegin);
 }
 int setup=link_submit_register(context,"SetupCameraProperties",setupTypes,3,0,link_submit_setup,&linkOriginalSetup);
 if(!setup)setup=link_submit_register(context,"SetupCameraProperties",setupTypes,2,0,link_submit_setup_stereo,&linkOriginalSetup);
 int pre=link_submit_register(cam,"FireOnPreCull",&camType,1,1,link_submit_precull,&linkOriginalPreCull);
 char line[112];snprintf(line,sizeof(line),"link render submission installed begin=%d setup=%d preCull=%d",begin,setup,pre);bootlog(line);
}
