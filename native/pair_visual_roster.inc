/* Native camera and move notifications can read Followers again after the graph
   is built. Give that presentation its one missing visual partner for the coin. */
static const char *const pairFollowersField="<Followers>k__BackingField";
static _Thread_local struct {
 void *presentation,*list,*setter,*view,*actorView,*app,*viewer,*action;
 uintptr_t presentationRoot,listRoot;
 int *version;
 int writtenVersion;
} pairRoster;

static void pair_roster_finish(void *nextPresentation){
 if(!pairRoster.list||(nextPresentation&&pairRoster.presentation!=nextPresentation))return;
 if(*pairRoster.version==pairRoster.writtenVersion&&
    list_count(pairRoster.list)==1&&list_item(pairRoster.list,0)==pairRoster.view){
  int zero=0;void *args[]={&zero,NULL};
  call_exc(pairRoster.setter,pairRoster.list,args);
 }
 ui_unroot(pairRoster.listRoot);ui_unroot(pairRoster.presentationRoot);
 memset(&pairRoster,0,sizeof(pairRoster));
}
static void pair_roster_tick(void){
 if(!pairRoster.list)return;
 Unit *actor=event_unit_for_view(pairRoster.actorView);
 if(!enabled_now()||cleanup_pending||!actor||actor->dead||!actor->viewerActive||
    actor->observedAction!=pairRoster.action||actor->observedViewer!=pairRoster.viewer||
    rfield(actor->view,"_curAppearance")!=pairRoster.app||
    rfield(pairRoster.presentation,pairFollowersField)!=pairRoster.list||
    *pairRoster.version!=pairRoster.writtenVersion)pair_roster_finish(NULL);
}
static void pair_roster_begin(Unit *actor,void *app){
 pair_roster_finish(NULL);
 void *p=g_wedgePresentation;
 if(!p||!actor||!actor->observedAction||!follower_getter)return;
 int id=pair_partner_identity(actor->baseName);
 void *visible=id?wedge_presentation_owner(app,id):NULL;
 Unit *partner=visible?unit_for_app(visible):NULL;
 void *candidates=rfield(p,"_candidates");
 if(!partner||list_count(candidates)!=1||list_item(candidates,0)!=partner->view)return;
 void *list=rfield(p,pairFollowersField),*exc=NULL;
 if(!list||ui_invoke(follower_getter,p,NULL,&exc)!=list||exc||
    list_count(list)!=1)return;
 void *field=find_field_obj(list,"_version");
 const char *types[]={"System.Int32","BattleUnitView"};
 void *setter=method_by_types_one(ui_class(list),"set_Item",types,2);
 void *getItem=method_by_types_one(ui_class(list),"get_Item",types,1);
 int zero=0;void *index[]={&zero};
 if(!field||!setter||!team_returns(setter,"System.Void")||!getItem||
    !team_returns(getItem,"BattleUnitView")||ui_invoke(getItem,list,index,&exc)||exc)return;
 int *version=(int*)((char*)list+((size_t(*)(void*))api[API_FIELD_OFFSET])(field));
 uintptr_t pr=ui_root(p),lr=ui_root(list);
 void *args[]={&zero,partner->view};
 if(!pr||!lr||!call_exc(setter,list,args)||list_item(list,0)!=partner->view){
  ui_unroot(pr);ui_unroot(lr);return;
 }
 pairRoster.presentation=p;pairRoster.list=list;pairRoster.setter=setter;
 pairRoster.presentationRoot=pr;pairRoster.listRoot=lr;pairRoster.version=version;
 pairRoster.writtenVersion=*version;pairRoster.view=partner->view;pairRoster.app=app;
 pairRoster.actorView=actor->view;pairRoster.action=actor->observedAction;pairRoster.viewer=actor->observedViewer;
 if(ui_invoke(follower_getter,p,NULL,&exc)!=list||exc){pair_roster_finish(NULL);return;}
 char line[150];snprintf(line,sizeof(line),"pair presentation follower restored actor=%.40s partner=%d index=0",actor->baseName,id);bootlog(line);
}
