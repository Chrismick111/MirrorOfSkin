/* Exact owner and group checks precede this observation. All model calls are
   read-only. A failed read keeps the last presented stage via the director. */
static void *chapter_typed_field(void *obj,const char *name,const char *expected){
 void *f=find_field_obj(obj,name);
 void *type=f?((void *(*)(void *))api[API_FIELD_TYPE])(f):NULL;
 char *tn=type?((char *(*)(void *))api[API_TYPE_NAME])(type):NULL;
 int ok=tn&&!strcmp(tn,expected);
 if(tn)((void (*)(void *))api[API_FREE])(tn);
 return ok?((void *(*)(void *,void *))api[API_FIELD_VALUE])(f,obj):NULL;
}
static void *chapter_component(void *go,const char *name){
 if(!go)return NULL;
 static void *getter;
 if(!getter){
  const char *types[]={"System.String"};
  getter=pick_method(ui_class(go),"GetComponent",types,1);
  if(getter&&!team_returns(getter,"UnityEngine.Component"))getter=NULL;
 }
 if(!getter)return NULL;
 void *label=make_string(name),*args[]={label};int ok=0;
 void *c=label?call_obj(getter,go,args,&ok):NULL;
 const char *cls=c&&ok?((const char *(*)(void *))api[API_CLASS_NAME])(ui_class(c)):NULL;
 return cls&&!strcmp(cls,name)?c:NULL;
}
static int chapter_observe(Unit *u,enum SrChapterSignal s){
 if(s==CH_AURA){
  if(!u->baseApp||!rfield(u->baseApp,"m_CachedPtr"))return -1;
  void *m=find_method(ui_class(u->baseApp),"get_gameObject",0);int ok=0;
  void *go=m?call_obj(m,u->baseApp,NULL,&ok):NULL;
  void *c=ok?chapter_component(go,"CharacterAppearanceUB_11015"):NULL;
  return go_active_self(chapter_typed_field(c,"obj_pattern","UnityEngine.GameObject"));
 }
 void *model=u->observedModel;
 if(!model)return -1;
 static void *get;
 if(!get){
  void *method=find_method(ui_class(model),"GetActivatedBuffModels",0);
  if(!method||!team_returns(method,"System.Collections.Generic.List<BuffModel>"))return -1;
  get=method;
 }
 int ok=0;void *list=call_obj(get,model,NULL,&ok);
 uintptr_t root=ok&&list?ui_root(list):0;if(!root)return -1;
 int n=list_count(list),rank=n>=0&&n<=256?0:-1;
 int armored=0;
 for(int i=0;rank>=0&&i<n;i++){
  void *buff=list_item(list,i);
  void *data=chapter_typed_field(buff,"_staticData","BuffStaticData");
  char key[192];
  if(!string_ascii(chapter_typed_field(data,"id","System.String"),key,sizeof(key))){rank=-1;break;}
  if(s==CH_FAUST&&!strcmp(key,"IronMaidenPersonality"))armored=1;
  int stack=0;
  if((s==CH_ECHO&&!strcmp(key,"SojiRyoshuEchoPast"))||(s==CH_WIRE&&!strcmp(key,"HeatingWireIshmael"))){
   void *info=chapter_typed_field(buff,"_buffInfo","BuffInfo");
   void *value=chapter_typed_field(info,"_stack","System.Int32");
   if(!value){rank=-1;break;}
   stack=*(int *)ui_unbox(value);
  }
  int r=sr_chapter_buff_rank(s,key,stack);if(r>rank)rank=r;
 }
 ui_unroot(root);
 /* Silver Opportunity can expire. Its absence by itself cannot prove armor. */
 if(s==CH_FAUST&&rank==0&&!armored)return -1;
 return rank;
}
static void chapter_cached_status(Unit *u,SrSgStatus *state){
 enum SrChapterSignal s=sr_chapter_signal(u->baseName,u->stageSource);
 if(s==CH_NONE||u->chapterSignal!=(int)s||u->chapterModel!=u->observedModel)return;
 state->chapterValid=u->chapterPhase>=0;state->chapterPhase=u->chapterPhase;
 if((s==CH_DON||s==CH_FAUST)&&state->chapterValid){
  state->nativeStage=u->chapterPhase;state->nativeValid=1;
 }
}
static void chapter_status(Unit *u,SrSgStatus *state){
 enum SrChapterSignal s=sr_chapter_signal(u->baseName,u->stageSource);
 if(s==CH_NONE)return;
 DWORD now=GetTickCount();
 if(u->chapterSignal!=(int)s||u->chapterModel!=u->observedModel||(DWORD)(now-u->chapterAt)>=350){
  u->chapterPhase=chapter_observe(u,s);u->chapterAt=now;
  u->chapterSignal=(int)s;u->chapterModel=u->observedModel;
 }
 chapter_cached_status(u,state);
}
static int chapter_visual_apply(Skin *skin,const SrChapterVisual *p,int form,int restore){
 void *c=chapter_component(skin->go,p->klass);
 if(!c)return 0;
 if(!strcmp(p->klass,"CharacterAppearanceUB_1314")||!strcmp(p->klass,"CharacterAppearanceUB_1318")){
  int eye=!strcmp(p->klass,"CharacterAppearanceUB_1314"),n=eye?2:1,old=0;
  void *nodes[2]={0};
  for(int i=0;i<n;i++){
   nodes[i]=chapter_typed_field(c,eye?(i?"effect2":"effect1"):"obj_pattern","UnityEngine.GameObject");
   int active=go_active_self(nodes[i]);if(active<0)return 0;old|=active<<i;
  }
  if(!skin->chapterApplied)skin->chapterDefault=old;
  int wanted=restore?skin->chapterDefault:eye?(form?0:skin->chapterDefault):!!form;
  for(int i=0;i<n;i++)if(((old^wanted)>>i)&1){
   if(!set_active(nodes[i],(wanted>>i)&1)){
    for(int j=0;j<i;j++)if(((old^wanted)>>j)&1)set_active(nodes[j],(old>>j)&1);
    return 0;
   }
  }
  return 1;
 }
 const char *types[]={"System.Int32","System.Boolean"};
 void *set=pick_method(ui_class(c),"SetRankEffect",types,2);
 if(!set||!team_returns(set,"System.Void"))return 0;
 uint8_t init=0;void *args[]={&form,&init};
 if(!call_exc(set,c,args))return 0;
 void *change=find_method(ui_class(c),"ChangeGroup",0);
 return !change||(team_returns(change,"System.Void")&&call_exc(change,c,NULL));
}
static void chapter_internal(Unit *u,Skin *skin,const SrChapterVisual *p){
 int owned=u->stageGroup>0&&(uint32_t)u->stageGroup<=g_stageGroups.count&&u->stageRevision==g_stageGroups.revision;
 if(owned){
  const SrSgGroup *g=&g_stageGroups.group[u->stageGroup-1];
  if(u->stageChoice<0||(unsigned)u->stageChoice>=g->count)return;
  owned=0;
  for(unsigned i=0;i<g->count;i++)if(g->stage[i].form&&!strcmp(g->stage[i].identity,p->look)){owned=1;break;}
  owned=owned&&!strcmp(g->stage[u->stageChoice].identity,p->look);
 }
 if(!owned&&!skin->chapterApplied)return;
 int form=owned?workbench_form_stage(u,p->look,0,p->count):0;
 if(owned&&skin->chapterApplied&&form==skin->internalStage)return;
 if(presentation_busy(skin->app))return;
 DWORD now=GetTickCount();if(skin->chapterRetry&&(LONG)(now-skin->chapterRetry)<0)return;
 if(chapter_visual_apply(skin,p,form,!owned)){
  skin->internalStage=form;skin->chapterApplied=owned;skin->chapterRetry=0;
  char line[180];snprintf(line,sizeof(line),"chapter form visible identity=%.64s form=%d controlled=%d",p->look,form,owned);bootlog(line);
 }else skin->chapterRetry=now+2000;
}
