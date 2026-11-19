static void *clash_visible(Unit *u,void *self){
 if(!u||u->switching||u->preserveSpecial||u->dead||cleanup_pending||g_creating||introUnit==u)return self;
 void *current=rfield(u->view,"_curAppearance");
 if(current&&(self==u->baseApp||skin_for_app(u,self))&&(current==u->baseApp||skin_for_app(u,current)))return current;
 return self;
}
static void *clash_source_if_safe(Unit *u,Skin *skin){
 void *current=rfield(u->view,"_curAppearance");
 if(!current)return skin->app;
 if(current==u->baseApp)return current;
 if(current!=skin->app||presentation_busy(current)||presentation_busy(u->baseApp)||
    (!g_duelCameraBoundary&&camera_scope_active())||g_presentationGate)return current;
 if(unit_switch(u,NULL))return u->baseApp;
 current=rfield(u->view,"_curAppearance");return current?current:skin->app;
}
static int clash_fallback(Unit *u,Skin *skin,void **receiver,int requested,int role){
 *receiver=clash_source_if_safe(u,skin);
 int detail=requested;
 if(*receiver==skin->app){
  int neutral=sr_clash_slot(skin->look,skin->chapterRole,17,4);
  detail=neutral>=0?neutral:0;
 }
 char line[216];snprintf(line,sizeof(line),"clash fallback look=%.63s source=%d role=%d receiver=%s played=%d",
   skin->look,requested,role,*receiver==skin->app?"donor":"native",detail);bootlog(line);
 return detail;
}
static int clash_indexed_slot(Skin *skin,int detail,int role,int *index){
 int slot=sr_clash_slot(skin->look,skin->chapterRole,detail,role);
 /* Sparse lists are safe only with an explicit, non-null leaf. */
 if(*index>=0&&detail>=0&&detail<SR_MOTION_CACHE&&skin->clashSparse[detail]&&
    ((*index<skin->clashCount[detail])&&list_item(skin->clashSparse[detail],*index))&&
    (sr_clash_role(skin->look,detail)==role||(detail==17&&slot<0&&(role==2||role==3))))
  return detail;
 if(slot>=0&&skin->clashCount[slot]>0&&*index>=skin->clashCount[slot])*index=skin->clashCount[slot]-1;
 return slot;
}
static const char *chapter_source(Unit *u,const SrChapterActor *actor);
static int clash_native_response(int detail){
 return detail==4||(detail>=0&&detail<128&&defenseMotions[detail]);
}
static int clash_request(Unit *u,int detail){
 const char *source=u->baseName;
 if(is_skill_detail(detail)||detail==20||detail==21){
  Skin *skin=skin_for_app(u,rfield(u->view,"_curAppearance"));
  if(skin&&skin->chapterActor)source=chapter_source(u,skin->chapterActor);
 }
 if(u==g_clashOwner&&clash_native_response(detail))return 7;
 int role=sr_clash_role(source,detail);
 if(role==4&&u==g_clashOwner&&g_clashRole)return g_clashRole;
 return role;
}
