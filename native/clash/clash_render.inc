static int local_clash_skin(Skin *skin){
 return skin_local_policy(skin)!=NULL;
}
/* A donor without any authored clash timeline should keep the game's native
   clash, not be forced through the special-clash pose path. */
static int skin_has_special_clash(Skin *skin){
 if(!skin)return 0;
 if(skin->chapterActor||local_clash_skin(skin))return 1;
 for(unsigned i=0;i<sizeof(sr_named_clashes)/sizeof(*sr_named_clashes);i++){
  const int d=sr_named_clashes[i].detail;
  if(sr_named_clashes[i].look&&!strcmp(sr_named_clashes[i].look,skin->look)&&
     d>=0&&d<SR_MOTION_CACHE&&(skin->clashCount[d]>0||skin->clashSparse[d]))return 1;
 }
 return 0;
}
static int special_clash_available(Skin *skin,const char *where){
 if(skin_has_special_clash(skin))return 1;
 if(skin&&!skin->specialClashWarned){
  skin->specialClashWarned=1;
  char line[192];snprintf(line,sizeof(line),"special clash assets unavailable; native clash retained look=%.63s where=%s",skin->look,where?where:"unknown");bootlog(line);
 }
 return 0;
}
static void *clash_visible(Unit *u,void *self){
 if(!u||u->switching||u->preserveSpecial||u->dead||cleanup_pending||g_creating||introUnit==u)return self;
 void *current=rfield(u->view,"_curAppearance");
 if(current==u->baseApp&&u->staticHidden&&(self==current||skin_for_app(u,self))){
  Skin *shown=held_appearance(u);
  if(shown&&shown->imported)return shown->app;
 }
 if(current&&(self==u->baseApp||skin_for_app(u,self))&&(current==u->baseApp||skin_for_app(u,current)))return current;
 return self;
}
static const char *clash_layout(Skin *skin){
 const ImportedConfig *policy=skin_local_policy(skin);
 return policy?policy->layout:skin->look;
}
static int clash_donor_role(Skin *skin,int detail){
 const ImportedConfig *policy=skin_local_policy(skin);
 if(!policy)return sr_clash_role(skin->look,detail);
 return detail>=0&&detail<128?policy->roles[detail]:0;
}
static int bundled_clash_slot(Skin *skin,int requested,int role){
 const unsigned char *roles=skin->bundledPolicy->roles;
 const signed char *available=skin->chapterRole;
 if(role<1||role==6||role>7)return -1;
 if(requested>=0&&requested<128&&roles[requested]==role&&available[requested]>0)return requested;
 if(role==7)return -1;
 for(int d=0;d<128;d++)
  if(roles[d]==role&&available[d]>0&&sr_clash_default_role(d)!=role)return d;
 if(role==5&&roles[19]==5&&available[19]>0)return 19;
 return (role==2||role==3||role==5)?bundled_clash_slot(skin,17,4):-1;
}
static int clash_donor_slot(Skin *skin,int requested,int role){
 if(skin->bundledPolicy)return bundled_clash_slot(skin,requested,role);
 if(!skin->imported)return sr_clash_slot(skin->look,skin->chapterRole,requested,role);
 if(role<1||role>7||role==6)return -1;
 const unsigned char *roles=skin->imported->roles;
 if(requested>=0&&requested<128&&roles[requested]==role&&skin->chapterRole[requested]>0)return requested;
 if(role==7){
  /* Evade and guard are defensive; a neutral parry is not. When the exact
     defense is absent use the other verified defense, never the hit pose. */
  int other=requested==2?3:requested==3?2:-1;
  return other>=0&&roles[other]==7&&skin->chapterRole[other]>0?other:-1;
 }
 static const int generic[]={0,36,37,38,17,19};
 int standard=generic[role];
 if(roles[standard]==role&&skin->chapterRole[standard]>0)return standard;
 for(int i=0;;i++){
  int d=sr_named_clash_slot(clash_layout(skin),role,i);if(d<0)break;
  if(roles[d]==role&&skin->chapterRole[d]>0)return d;
 }
 for(int d=0;d<128;d++)if(roles[d]==role&&skin->chapterRole[d]>0)return d;
 return (role==2||role==3||role==5)?clash_donor_slot(skin,17,4):-1;
}
static int clash_fallback(Unit *u,Skin *skin,void **receiver,int requested,int role){
 *receiver=skin->app;
 int detail=requested;
 if(*receiver==skin->app){
  int neutral=role==7?-1:clash_donor_slot(skin,17,4);
  detail=neutral>=0?neutral:0;
 }
 char line[216];snprintf(line,sizeof(line),"clash fallback look=%.63s source=%d role=%d receiver=%s played=%d",
   skin->look,requested,role,*receiver==skin->app?"donor":"native",detail);bootlog(line);
 return detail;
}
static int clash_indexed_slot(Skin *skin,int detail,int role,int *index){
 int slot=clash_donor_slot(skin,detail,role);
 /* Sparse lists are safe only with an explicit, non-null leaf. */
 if(*index>=0&&detail>=0&&detail<SR_MOTION_CACHE&&skin->clashSparse[detail]&&
    ((*index<skin->clashCount[detail])&&list_item(skin->clashSparse[detail],*index))&&
    (clash_donor_role(skin,detail)==role||(!skin->imported&&detail==17&&slot<0&&(role==2||role==3))))
  return detail;
 if(slot>=0&&skin->clashCount[slot]>0&&*index>=skin->clashCount[slot])*index=skin->clashCount[slot]-1;
 return slot;
}
static int clash_indexed_slot_exact(Skin *skin,int detail,int role,int *index){
 int slot=sr_clash_slot_exact(skin->look,skin->chapterRole,detail,role);
 if(slot<0)return -1;
 if(*index>=0&&detail>=0&&detail<SR_MOTION_CACHE&&skin->clashSparse[detail]&&
    ((*index<skin->clashCount[detail])&&list_item(skin->clashSparse[detail],*index))&&
    sr_clash_role(skin->look,detail)==role)return detail;
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
 if(clash_native_response(detail)){
  if(u==g_clashOwner)return 7;
  Skin *shown=skin_for_app(u,clash_visible(u,u->baseApp));
  if(shown&&shown->imported)return 7;
 }
 int role=sr_clash_role(source,detail);
 /* A source-specific Special slot is ambiguous outside the parry callback.
    Inside it, an imported actor may use its verified outcome or neutral pose. */
 if(!role&&u==g_clashOwner&&detail>=20&&detail<=22&&!(u->coinKnown&&u->coinMotion==detail)){
  Skin *shown=skin_for_app(u,clash_visible(u,u->baseApp));
  if(shown&&shown->imported)role=4;
 }
 if(role==4&&u==g_clashOwner&&g_clashRole)return g_clashRole;
 return role;
}
