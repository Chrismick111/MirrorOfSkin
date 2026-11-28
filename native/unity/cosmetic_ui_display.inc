#include "cosmetic_ui_state.h"

enum { COSMETIC_UI_TEXT, COSMETIC_UI_SPRITE };
enum { COSMETIC_UI_SCAN_COIN,COSMETIC_UI_SCAN_TARGET,COSMETIC_UI_SCAN_PAIRED };
typedef struct {
 void *component,*stock,*installed;
 uintptr_t component_root,stock_root,installed_root;
 unsigned kind,scan,seen;
} CosmeticUIOverride;

static CosmeticUIOverride cosmetic_ui_overrides[384];
static unsigned cosmetic_ui_epoch;

static void *method_by_types(void *klass,const char *name,const char **types,int count);

static int cosmetic_control_is_class(void *object,const char *name){
 void *klass=ui_class(object);
 const char *actual=klass?((const char *(*)(void *))api[API_CLASS_NAME])(klass):NULL;
 return actual&&!strcmp(actual,name);
}

static void *cosmetic_control_get(void *object,const char *method){
 return object?call_obj(find_method(ui_class(object),method,0),object,NULL,NULL):NULL;
}

static int cosmetic_control_integer(void *object,const char *method,void **args){
 return object?call_int(find_method(ui_class(object),method,args?1:0),object,args):-1;
}

static void *cosmetic_control_box(void *object,const char *name){
 void *field=find_field_obj(object,name);
 return field?((void *(*)(void *,void *))api[API_FIELD_VALUE])(field,object):NULL;
}

static int cosmetic_control_int_field(void *object,const char *name){
 int value;
 return story_int(object,name,&value)?value:-1;
}

static int cosmetic_control_bool_field(void *object,const char *name){
 void *field=find_field_obj(object,name);
 if(!field)return 0;
 size_t offset=((size_t (*)(void *))api[API_FIELD_OFFSET])(field);
 return *(const uint8_t *)((const char *)object+offset)!=0;
}

static int cosmetic_control_single_id(void *list){
 if(list_count(list)!=1)return -1;
 void *value=list_item(list,0),*klass=ui_class(value);
 const char *name=klass?((const char *(*)(void *))api[API_CLASS_NAME])(klass):NULL;
 return name&&!strcmp(name,"Int32")?*(int *)ui_unbox(value):-1;
}

static int cosmetic_control_live(void *object){
 return object&&rfield(object,"m_CachedPtr");
}

static int cosmetic_control_visible(void *object){
 if(!cosmetic_control_live(object)||!m_getActiveInHierarchy)return 0;
 void *go=cosmetic_control_get(object,"get_gameObject");
 return go&&call_bool(m_getActiveInHierarchy,go,NULL)==1;
}

static int cosmetic_control_read(void *component,unsigned kind,void **value){
 void *method=find_method(ui_class(component),kind==COSMETIC_UI_TEXT?"get_text":"get_sprite",0);
 if(!method)return 0;
 void *exception=NULL;
 *value=ui_invoke(method,component,NULL,&exception);
 return !exception;
}

static int cosmetic_control_write(void *component,unsigned kind,void *value){
 void *method=find_method(ui_class(component),kind==COSMETIC_UI_TEXT?"set_text":"set_sprite",1);
 void *args[]={value};
 return call_exc(method,component,args);
}

static CosmeticUIOverride *cosmetic_control_find(void *component,unsigned kind){
 for(unsigned i=0;i<sizeof(cosmetic_ui_overrides)/sizeof(*cosmetic_ui_overrides);i++){
  CosmeticUIOverride *slot=&cosmetic_ui_overrides[i];
  if(slot->component==component&&slot->kind==kind)return slot;
 }
 return NULL;
}

static void cosmetic_control_drop(CosmeticUIOverride *slot){
 ui_unroot(slot->installed_root);
 ui_unroot(slot->stock_root);
 ui_unroot(slot->component_root);
 memset(slot,0,sizeof(*slot));
}

static void cosmetic_control_restore(CosmeticUIOverride *slot){
 if(cosmetic_control_live(slot->component)){
  void *current=NULL;
  if(!cosmetic_control_read(slot->component,slot->kind,&current))return;
  if(cosmetic_ui_change(current,slot->installed,NULL)==COSMETIC_UI_RESTORE&&
     !cosmetic_control_write(slot->component,slot->kind,slot->stock))return;
 }
 cosmetic_control_drop(slot);
}

static int cosmetic_control_replace(void *component,unsigned kind,void *replacement,unsigned scan){
 if(!cosmetic_control_live(component))return 0;
 CosmeticUIOverride *slot=cosmetic_control_find(component,kind);
 if(!replacement){if(slot)cosmetic_control_restore(slot);return 0;}
 void *current=NULL;
 if(!cosmetic_control_read(component,kind,&current))return 0;
 if(slot&&current!=slot->installed){
  cosmetic_control_drop(slot);
  slot=NULL;
 }
 if(cosmetic_ui_change(current,slot?slot->installed:NULL,replacement)==COSMETIC_UI_KEEP){
  if(slot){slot->seen=cosmetic_ui_epoch;slot->scan=scan;}
  return 0;
 }
 if(!slot){
  for(unsigned i=0;i<sizeof(cosmetic_ui_overrides)/sizeof(*cosmetic_ui_overrides);i++){
   if(!cosmetic_ui_overrides[i].component){slot=&cosmetic_ui_overrides[i];break;}
  }
  if(!slot)return 0;
  uintptr_t target=ui_root(component),stock=ui_root(current);
  if(!target||(current&&!stock)){ui_unroot(target);ui_unroot(stock);return 0;}
  *slot=(CosmeticUIOverride){.component=component,.stock=current,.component_root=target,
                            .stock_root=stock,.kind=kind,.scan=scan};
 }
 uintptr_t installed=ui_root(replacement);
 if(!installed||!cosmetic_control_write(component,kind,replacement)){
  ui_unroot(installed);
  if(!slot->installed)cosmetic_control_drop(slot);
  return 0;
 }
 ui_unroot(slot->installed_root);
 slot->installed=replacement;
 slot->installed_root=installed;
 slot->scan=scan;
 slot->seen=cosmetic_ui_epoch;
 return 1;
}

static Unit *cosmetic_control_unit(void *model,int instance){
 if(!model&&instance<=0)return NULL;
 Unit *found=NULL;
 for(int i=0;i<SR_UNIT_MAX;i++){
  Unit *unit=&g_units[i];
  if(!unit->used||!cosmetic_control_live(unit->view))continue;
  if(model?rfield(unit->view,"_unitModel")!=model:
           cosmetic_control_int_field(unit->view,"_instanceID")!=instance)continue;
  if(found)return NULL;
  found=unit;
 }
 return found&&!found->switching&&voice_worn_skin(found)?found:NULL;
}

static void *cosmetic_control_unit_banner(const Unit *unit){
 if(!unit->used||!cosmetic_control_live(unit->view))return NULL;
 void *manager=rfield(unit->view,"_uiManager");
 return rfield(rfield(manager,"_unitSkillInfoUI"),"_skillParryingUI");
}

static const char *const cosmetic_control_name_surface[]={"battle banner","selected skill","paired skills"};

static void cosmetic_control_log_name(Unit *unit,int id,int tier,int level,int written,unsigned scan){
 static struct { int id,written; char look[sizeof(((Skin *)0)->look)]; } seen[3][192];
 static size_t counts[3];
 size_t count=counts[scan];
 const Skin *skin=voice_worn_skin(unit);
 if(!skin||count>=sizeof(seen[scan])/sizeof(*seen[scan]))return;
 for(size_t i=0;i<count;i++)
  if(seen[scan][i].id==id&&seen[scan][i].written==written&&!strcmp(seen[scan][i].look,skin->look))return;
 seen[scan][count].id=id;
 seen[scan][count].written=written;
 memcpy(seen[scan][count].look,skin->look,sizeof(skin->look));
 counts[scan]++;
 char line[232];
 snprintf(line,sizeof(line),"cosmetic UI %s: skill=%d look=%s tier=%d gaksung=%d name=%s written=%d reason=%s",
          cosmetic_control_name_surface[scan],id,skin->look,tier,level,
          written?"applied":"unavailable",written,written?"resolved":level?"no-name-for-level":"unknown-level-or-no-default");
 bootlog(line);
}

static void cosmetic_control_skill(Unit *unit,void *skill,int id,int display_tier,void *text,void *sprite,unsigned scan){
 if(!unit||id<=0||(!text&&!sprite))return;
 int level=0,model_tier=0,defense=-1,conditional=-1;
 if(skill){
  if(cosmetic_control_integer(skill,"GetID",NULL)!=id)return;
  level=cosmetic_control_integer(skill,"GetGaksungLevel",NULL);
  model_tier=cosmetic_control_integer(skill,"GetSkillTier",NULL);
  void *model=rfield(unit->view,"_unitModel");
  void *default_check=model?find_method(ui_class(model),"HasSkillAsDefaultSkillIncludeDefenseSkill",1):NULL;
  void *default_args[]={skill};
  int is_default=default_check?call_bool(default_check,model,default_args):-1;
  void *defense_check=find_method(ui_class(skill),"IsDefense",0);
  void *attack_check=find_method(ui_class(skill),"IsAttack",0);
  defense=defense_check?call_bool(defense_check,skill,NULL):-1;
  if(defense==1){
   /* A view's SkillModel can differ from the model object stored on the unit. */
   if(cosmetic_control_single_id(cosmetic_control_get(model,"GetDefenseSkillIDList"))==id)conditional=0;
  }else if(is_default==1&&defense==0&&attack_check&&call_bool(attack_check,skill,NULL)==1){
   int value=cosmetic_ui_tier(model_tier,display_tier);
   void *args[]={&value};
   if(value&&cosmetic_control_integer(model,"GetOriginalSkillByTier",args)==id)conditional=0;
  }
 }
 int tier=cosmetic_ui_tier(model_tier,display_tier);
 void *new_text=NULL,*new_sprite=NULL;
 cosmetic_ui_resolve(unit,id,tier,defense,conditional,
                     level>0?level:0,NULL,0,&new_text,&new_sprite);
 int written=cosmetic_control_replace(text,COSMETIC_UI_TEXT,new_text,scan);
 cosmetic_control_replace(sprite,COSMETIC_UI_SPRITE,new_sprite,scan);
 if(scan<=COSMETIC_UI_SCAN_PAIRED&&text&&(written||!new_text))
  cosmetic_control_log_name(unit,id,tier,level>0?level:0,written,scan);
}

static void *cosmetic_control_viewer_model(void *viewer,int id){
 void *skill=cosmetic_control_get(viewer,"GetSkillModel");
 return cosmetic_control_integer(skill,"GetID",NULL)==id?skill:NULL;
}

static void *cosmetic_control_skill_model(Unit *unit,int id){
 if(!unit||id<=0)return NULL;
 static void *cached_class,*cached_method;
 void *klass=ui_class(unit->view);
 if(klass!=cached_class){
  cached_class=klass;
  const char *types[]={"System.Int32"};
  /* The other one-argument overload accepts BattleActionLog. */
  cached_method=method_by_types(klass,"GetSkillViewer",types,1);
 }
 if(!cached_method)return NULL;
 void *args[]={&id};
 return cosmetic_control_viewer_model(call_obj(cached_method,unit->view,args,NULL),id);
}

static void *cosmetic_control_unit_list_skill(void *unit_model,int id){
 void *skill=NULL;
 void *list=cosmetic_control_get(unit_model,"GetSkillList");
 int count=list_count(list);
 for(int i=0;i<count&&count<=64;i++){
  void *candidate=list_item(list,i);
  if(cosmetic_control_integer(candidate,"GetID",NULL)!=id)continue;
  if(skill&&skill!=candidate)return NULL;
  skill=candidate;
 }
 return skill;
}

static void *cosmetic_control_banner_model(Unit *unit,int id){
 void *viewer=cosmetic_control_get(unit->view,"GetCurrentLogSkillViewer");
 void *skill=cosmetic_control_viewer_model(viewer,id);
 if(!skill)skill=cosmetic_control_skill_model(unit,id);
 if(skill)return skill;
 void *unit_model=rfield(unit->view,"_unitModel");
 if(cosmetic_control_single_id(cosmetic_control_get(unit_model,"GetDefenseSkillIDList"))!=id)return NULL;
 return cosmetic_control_unit_list_skill(unit_model,id);
}

static void *cosmetic_control_preview_defense(Unit *unit,void *unit_model,int id){
 if(cosmetic_control_single_id(cosmetic_control_get(unit_model,"GetDefenseSkillIDList"))!=id)return NULL;
 void *skill=cosmetic_control_skill_model(unit,id);
 if(!skill)skill=cosmetic_control_unit_list_skill(unit_model,id);
 void *check=skill?find_method(ui_class(skill),"IsDefense",0):NULL;
 return check&&call_bool(check,skill,NULL)==1?skill:NULL;
}

static int cosmetic_control_skill_icon_id(void *icon){
 return cosmetic_control_int_field(icon,"_currentSetSkillId");
}

static void cosmetic_control_coin_probe(unsigned stage,int instance,int skill){
 static unsigned seen;
 if(seen&(1u<<stage))return;
 seen|=1u<<stage;
 static const char *const stages[]={"attached","closed","owner-unresolved","data-unavailable","text-hidden","scene-discovered"};
 char line[144];
 snprintf(line,sizeof(line),"cosmetic UI coin control: stage=%s owner=%d skill=%d",stages[stage],instance,skill);
 bootlog(line);
}

static void cosmetic_control_coin_for(void *object,Unit *unit,unsigned scan){
 int instance=cosmetic_control_int_field(object,"_ownerUnitId");
 if(unit)cosmetic_control_coin_probe(0,instance,-1);
 if(!cosmetic_control_bool_field(object,"_open")){
  if(unit)cosmetic_control_coin_probe(1,instance,-1);
  return;
 }
 if(!unit)unit=cosmetic_control_unit(NULL,instance);
 if(!unit){cosmetic_control_coin_probe(2,instance,-1);return;}
 void *data=cosmetic_control_box(object,"_skillUIData");
 if(!cosmetic_control_is_class(data,"SkillUIData")){cosmetic_control_coin_probe(3,instance,-1);return;}
 uintptr_t data_root=ui_root(data);
 if(!data_root)return;
 int id=cosmetic_control_int_field(data,"_id");
 int tier=cosmetic_control_int_field(data,"_skillTier");
 ui_unroot(data_root);
 if(id<=0){cosmetic_control_coin_probe(3,instance,id);return;}
 void *icon=rfield(object,"_skillIconUI");
 void *sprite=cosmetic_control_skill_icon_id(icon)==id?rfield(icon,"img_skillIcon"):NULL;
 void *text=rfield(object,"tmp_skillName");
 if(!cosmetic_control_visible(text)){cosmetic_control_coin_probe(4,instance,id);text=NULL;}
 cosmetic_control_skill(unit,cosmetic_control_banner_model(unit,id),id,tier,text,sprite,scan);
}

static void cosmetic_control_coin(void *object,unsigned scan){
 cosmetic_control_coin_for(object,NULL,scan);
}

enum { PREVIEW_NO_SELECTION, PREVIEW_NO_WORN_OWNER, PREVIEW_ID_CONFLICT, PREVIEW_NO_ID, PREVIEW_NO_LABEL, PREVIEW_DISCOVERED };
static void cosmetic_control_preview_probe(unsigned scan,unsigned stage,int id,int shown){
 static unsigned seen[2];
 unsigned *stages=&seen[scan-COSMETIC_UI_SCAN_TARGET];
 if(*stages&(1u<<stage))return;
 *stages|=1u<<stage;
 static const char *const stage_name[]={"no-selection","no-worn-owner","skill-id-conflict","no-skill-id","no-label","scene-discovered"};
 char line[160];
 snprintf(line,sizeof(line),"cosmetic UI %s control: stage=%s skill=%d shown=%d",
          cosmetic_control_name_surface[scan],stage_name[stage],id,shown);
 bootlog(line);
}

static void cosmetic_control_preview(void *object,void *sin,const char *name_field,void *detail,unsigned scan){
 if(!cosmetic_control_visible(object))return;
 if(!sin){cosmetic_control_preview_probe(scan,PREVIEW_NO_SELECTION,-1,-1);return;}
 void *unit_model=cosmetic_control_get(sin,"get_Model");
 Unit *unit=cosmetic_control_unit(unit_model,0);
 if(!unit){cosmetic_control_preview_probe(scan,PREVIEW_NO_WORN_OWNER,-1,-1);return;}
 int id=cosmetic_control_integer(sin,"get_SkillID",NULL);
 void *icon=cosmetic_control_get(object,"get_SkillIconUI");
 int shown=cosmetic_control_visible(icon)?cosmetic_control_skill_icon_id(icon):-1;
 void *skill=cosmetic_control_get(sin,"GetSkill");
 void *action=cosmetic_control_get(sin,"GetBattleActionModel");
 int action_id=cosmetic_control_integer(action,"GetSkillID",NULL);
 if(shown>0&&shown!=id){
  if(action_id!=shown&&cosmetic_control_integer(skill,"GetID",NULL)!=shown){
   skill=cosmetic_control_preview_defense(unit,unit_model,shown);
   if(!skill){cosmetic_control_preview_probe(scan,PREVIEW_ID_CONFLICT,id,shown);return;}
  }
  id=shown;
 }else if(shown<=0&&action_id>0&&(id<=0||cosmetic_control_integer(skill,"GetID",NULL)!=id)){
  /* An absent icon cannot disprove an exact skill from the selected unit's action. */
  void *action_skill=cosmetic_control_get(action,"get_Skill");
  if(cosmetic_control_integer(action_skill,"GetID",NULL)==action_id){id=action_id;skill=action_skill;}
 }
 if(id<=0){cosmetic_control_preview_probe(scan,PREVIEW_NO_ID,id,shown);return;}
 if(action_id==id){
  void *action_skill=cosmetic_control_get(action,"get_Skill");
  if(cosmetic_control_integer(action_skill,"GetID",NULL)==id)skill=action_skill;
 }
 if(cosmetic_control_integer(skill,"GetID",NULL)!=id)skill=cosmetic_control_banner_model(unit,id);
 int icon_matches=shown==id;
 void *text=name_field?rfield(object,name_field):rfield(detail,"tmp_name");
 if(!cosmetic_control_visible(text)){
  cosmetic_control_preview_probe(scan,PREVIEW_NO_LABEL,id,shown);
  text=NULL;
 }
 cosmetic_control_skill(unit,skill,id,0,text,
                        icon_matches?rfield(icon,"img_skillIcon"):NULL,scan);
}

static void cosmetic_control_target(void *object,unsigned scan){
 /* The main tmp_name is the unit's name. The skill name belongs to the detail. */
 cosmetic_control_preview(object,rfield(object,"_chosenUnitSinModel"),NULL,rfield(object,"_skillDetail"),scan);
}

static void cosmetic_control_relative_target(void *object,unsigned scan){
 /* The game binds these selections to faction panels even when screen positions swap. */
 cosmetic_control_preview(rfield(object,"_playerInfo"),rfield(object,"_leftSin"),"_tmp_skillName",NULL,scan);
 cosmetic_control_preview(rfield(object,"_enemyInfo"),rfield(object,"_rightSin"),"_tmp_skillName",NULL,scan);
}

static void cosmetic_control_operation(void *object,unsigned scan){
 void *sin=cosmetic_control_get(object,"get_UnitSin");
 if(!sin)return;
 Unit *unit=cosmetic_control_unit(cosmetic_control_get(sin,"get_Model"),0);
 if(!unit)return;
 void *slot=rfield(object,"_skillSlot");
 void *skill=cosmetic_control_get(slot,"GetSkillModel");
 int id=cosmetic_control_integer(sin,"get_SkillID",NULL);
 if(skill)cosmetic_control_skill(unit,skill,id,0,NULL,rfield(slot,"img_skillIcon"),scan);
}

static void cosmetic_control_battle_operation(void *object,unsigned scan){
 void *sin_action=rfield(object,"_sinAction");
 Unit *unit=cosmetic_control_unit(cosmetic_control_get(sin_action,"get_UnitModel"),0);
 if(!unit)return;
 void *action=cosmetic_control_get(sin_action,"get_CurrentBattleAction");
 void *slot=rfield(object,"_skillSlot");
 void *skill=cosmetic_control_get(slot,"GetSkillModel");
 int id=cosmetic_control_integer(action,"GetSkillID",NULL);
 if(skill)cosmetic_control_skill(unit,skill,id,0,NULL,rfield(slot,"img_skillIcon"),scan);
}

static void cosmetic_control_passive_portrait(Unit *unit,void *icon,void *banner,unsigned scan){
 if(!unit)return;
 void *sprite=NULL,*text=NULL;
 cosmetic_ui_resolve(unit,0,0,0,-1,0,NULL,1,&text,&sprite);
 cosmetic_control_replace(icon,COSMETIC_UI_SPRITE,sprite,scan);
 cosmetic_control_replace(banner,COSMETIC_UI_SPRITE,sprite,scan);
}

static void cosmetic_control_passive(void *object,unsigned scan){
 int slot_instance=cosmetic_control_int_field(object,"_instanceId");
 if(slot_instance<=0||!cosmetic_control_bool_field(object,"_isBattleUnitPassive")||
    cosmetic_control_integer(object,"GetPassiveId",NULL)<=0)return;
 void *data=rfield(object,"_passiveModel_BattleUnit");
 void *model=cosmetic_control_get(data,"get_Owner");
 if(!model||cosmetic_control_integer(model,"get_InstanceID",NULL)!=slot_instance)return;
 Unit *unit=cosmetic_control_unit(model,0);
 cosmetic_control_passive_portrait(unit,rfield(object,"_characterIconImage"),
                                   rfield(object,"_activeAnimSlotPassivePersonalityImage"),scan);
}

static void cosmetic_control_passive_display(void *object,unsigned scan){
 void *model=cosmetic_control_get(object,"GetBattleUnitModel");
 void *display=cosmetic_control_get(object,"get_Display");
 cosmetic_control_passive_portrait(cosmetic_control_unit(model,0),NULL,rfield(display,"img_portrait"),scan);
}

static void cosmetic_control_detail_skill(Unit *unit,void *content,void *summary_text,unsigned scan){
 if(!cosmetic_control_visible(content))return;
 void *icon=rfield(rfield(content,"_skillIcon"),"_skillIconUI");
 int id=cosmetic_control_skill_icon_id(icon);
 void *skill=cosmetic_control_skill_model(unit,id);
 void *name=rfield(rfield(content,"_skillNameUI"),"tmp_skillName");
 cosmetic_control_skill(unit,skill,id,0,name,rfield(icon,"img_skillIcon"),scan);
 if(summary_text&&summary_text!=name)cosmetic_control_skill(unit,skill,id,0,summary_text,NULL,scan);
}

static void cosmetic_control_detail_summary(Unit *unit,void *content,unsigned scan){
 void *list=rfield(content,"_skillSummarySlotList");
 int count=list_count(list);
 for(int i=0;i<count&&count<=64;i++){
  void *slot=list_item(list,i);
  if(!cosmetic_control_visible(slot))continue;
  void *box=cosmetic_control_box(slot,"_skillBoxData");
  void *skill=rfield(box,"skillModel"),*icon=rfield(rfield(slot,"_skillIcon"),"_skillIconUI");
  if(skill)cosmetic_control_skill(unit,skill,cosmetic_control_skill_icon_id(icon),0,NULL,
                                  rfield(icon,"img_skillIcon"),scan);
 }
 void *panel=rfield(content,"_skillSummaryPanel");
 if(cosmetic_control_visible(panel))cosmetic_control_detail_skill(unit,rfield(panel,"_skillContent"),
                                                                  rfield(panel,"tmp_skillName"),scan);
}

static void cosmetic_control_detail(void *object,unsigned scan){
 void *data=rfield(object,"_dataManager");
 Unit *unit=cosmetic_control_unit(cosmetic_control_get(data,"get_UnitModel"),0);
 if(!unit)return;
 void *contents=rfield(object,"_contents");
 int count=list_count(contents);
 for(int i=0;i<count&&count<=32;i++){
  void *content=list_item(contents,i);
  if(!cosmetic_control_visible(content))continue;
  if(cosmetic_control_is_class(content,"UnitInformationSkillTabContent")){
   void *list=rfield(content,"_skillContentUIList");
   int rows=list_count(list);
   for(int j=0;j<rows&&rows<=64;j++)cosmetic_control_detail_skill(unit,list_item(list,j),NULL,scan);
  }else if(cosmetic_control_is_class(content,"UnitInformationSummaryTabContent")){
   cosmetic_control_detail_summary(unit,content,scan);
  }
 }
}

static void cosmetic_control_status(void *object,unsigned scan){
 void *active=find_method(ui_class(object),"get_IsActive",0);
 if(!active||call_bool(active,object,NULL)!=1)return;
 void *info=cosmetic_control_get(object,"GetBufInfo");
 if(!info)return;
 void *givers=cosmetic_control_get(info,"GetGiverInstanceIDs");
 Unit *unit=cosmetic_control_unit(NULL,cosmetic_control_single_id(givers));
 if(!unit)return;
 void *image=rfield(object,"img_icon"),*current=NULL;
 if(!cosmetic_control_read(image,COSMETIC_UI_SPRITE,&current))return;
 CosmeticUIOverride *owned=cosmetic_control_find(image,COSMETIC_UI_SPRITE);
 void *stock=cosmetic_control_get(info,"GetIconSprite");
 if(!stock||(current!=stock&&(!owned||owned->installed!=current||owned->stock!=stock)))return;
 char key[128];
 if(!string_ascii(cosmetic_control_get(info,"GetLocalizeID"),key,sizeof(key))||!key[0])return;
 void *sprite=NULL,*text=NULL;
 cosmetic_ui_resolve(unit,0,0,0,-1,0,key,0,&text,&sprite);
 cosmetic_control_replace(image,COSMETIC_UI_SPRITE,sprite,scan);
}

typedef struct {
 const char *namespace_name,*class_name;
 void (*apply)(void *,unsigned);
 void *type,*array;
 uintptr_t type_root,array_root;
 DWORD refreshed;
} CosmeticUIScan;

static CosmeticUIScan cosmetic_ui_scans[]={
 [COSMETIC_UI_SCAN_COIN]={"BattleUI.BattleUnit.SkillInfoUI","SkillAndCoinUI",cosmetic_control_coin},
 [COSMETIC_UI_SCAN_TARGET]={"BattleUI","TargettingDetail",cosmetic_control_target},
 [COSMETIC_UI_SCAN_PAIRED]={"BattleUI","TargetDetailSkillInfoController",cosmetic_control_relative_target},
 {"BattleUI.Operation","NewOperationSinSlot",cosmetic_control_operation},
 {"BattleUI.Operation","NewOperationReadySinSlot",cosmetic_control_operation},
 {"BattleUI.Operation","NewOperationBattleViewSinSlot",cosmetic_control_battle_operation},
 {"BattleUI","PassiveIconSlot",cosmetic_control_passive},
 {"BattleUI.Passive","PassiveUISlot",cosmetic_control_passive_display},
 {"BattleUI","BufIconSlot",cosmetic_control_status},
 {"","UnitInformationTabManager",cosmetic_control_detail},
};

static int cosmetic_ui_reset(int release_types){
 int restored=1;
 for(unsigned i=0;i<sizeof(cosmetic_ui_overrides)/sizeof(*cosmetic_ui_overrides);i++){
  CosmeticUIOverride *slot=&cosmetic_ui_overrides[i];
  if(slot->component){cosmetic_control_restore(slot);if(slot->component)restored=0;}
 }
 for(unsigned i=0;i<sizeof(cosmetic_ui_scans)/sizeof(*cosmetic_ui_scans);i++){
  CosmeticUIScan *scan=&cosmetic_ui_scans[i];
  ui_unroot(scan->array_root);
  scan->array_root=0;
  scan->array=NULL;
  scan->refreshed=0;
  if(release_types){ui_unroot(scan->type_root);scan->type_root=0;scan->type=NULL;}
 }
 return restored;
}

static void cosmetic_ui_refresh(CosmeticUIScan *scan,DWORD now){
 scan->refreshed=now;
 if(!scan->type){
  void *klass=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,scan->namespace_name,scan->class_name);
  void *type=klass?((void *(*)(void *))api[API_CLASS_TYPE])(klass):NULL;
  void *reflection=type?((void *(*)(void *))api[API_TYPE_OBJECT])(type):NULL;
  scan->type_root=ui_root(reflection);
  if(!scan->type_root)return;
  scan->type=reflection;
 }
 void *args[]={scan->type};
 void *array=call_obj(m_findAll,NULL,args,NULL);
 uintptr_t root=ui_root(array);
 if(root){ui_unroot(scan->array_root);scan->array_root=root;scan->array=array;}
 if(root&&*(uintptr_t *)((char *)array+24)>0){
  unsigned index=(unsigned)(scan-cosmetic_ui_scans);
  if(index==COSMETIC_UI_SCAN_COIN)cosmetic_control_coin_probe(5,-1,-1);
  if(index==COSMETIC_UI_SCAN_TARGET||index==COSMETIC_UI_SCAN_PAIRED)
   cosmetic_control_preview_probe(index,PREVIEW_DISCOVERED,-1,-1);
 }
}

static void cosmetic_ui_apply(unsigned index){
 CosmeticUIScan *scan=&cosmetic_ui_scans[index];
 if(!scan->array&&index!=COSMETIC_UI_SCAN_COIN)return;
 if(++cosmetic_ui_epoch==0)++cosmetic_ui_epoch;
 struct {void *object; Unit *unit;} attached[SR_UNIT_MAX];
 unsigned attached_count=0;
 if(index==COSMETIC_UI_SCAN_COIN){
  for(int i=0;i<SR_UNIT_MAX;i++){
   Unit *unit=&g_units[i];
   void *object=cosmetic_control_unit_banner(unit);
   if(!object)continue;
   unsigned j=0;
   while(j<attached_count&&attached[j].object!=object)j++;
   if(j<attached_count){attached[j].unit=NULL;continue;}
   attached[attached_count].object=object;
   attached[attached_count++].unit=unit;
  }
  for(unsigned i=0;i<attached_count;i++){
   Unit *unit=attached[i].unit;
   void *object=attached[i].object;
   if(!cosmetic_control_visible(object))continue;
   if(!unit){
    /* Shared controls require a matching instance among the attached views. */
    unit=cosmetic_control_unit(NULL,cosmetic_control_int_field(object,"_ownerUnitId"));
    if(!unit||cosmetic_control_unit_banner(unit)!=object)continue;
   }
   if(!unit->switching&&voice_worn_skin(unit))
    cosmetic_control_coin_for(object,unit,index);
  }
 }
 uintptr_t count=scan->array?*(uintptr_t *)((char *)scan->array+24):0;
 for(uintptr_t i=0;i<count&&count<=2048;i++){
  void *object=((void **)((char *)scan->array+32))[i];
  unsigned j=0;
  while(j<attached_count&&attached[j].object!=object)j++;
  if(j<attached_count)continue;
  if(cosmetic_control_visible(object))scan->apply(object,index);
 }
 for(unsigned i=0;i<sizeof(cosmetic_ui_overrides)/sizeof(*cosmetic_ui_overrides);i++){
  CosmeticUIOverride *slot=&cosmetic_ui_overrides[i];
  if(slot->component&&slot->scan==index&&slot->seen!=cosmetic_ui_epoch)cosmetic_control_restore(slot);
 }
}

static void cosmetic_ui_frame(int enabled){
 static int had_wearers;
 static DWORD last_scene_query;
 static unsigned next_refresh,next_apply=1;
 int wearers=0;
 if(enabled)for(int i=0;i<SR_UNIT_MAX;i++){
  Unit *unit=&g_units[i];
  if(unit->used&&voice_worn_skin(unit)){wearers=1;break;}
 }
 if(!wearers){
  if(had_wearers&&cosmetic_ui_reset(0)){cosmetic_ui_data_clear();had_wearers=0;}
  return;
 }
 had_wearers=1;
 cosmetic_ui_data_pump();
 const unsigned scans=sizeof(cosmetic_ui_scans)/sizeof(*cosmetic_ui_scans);
 /* Recheck cached controls while throttling scene-wide discovery in wall-clock time. */
 DWORD now=GetTickCount();
 if(m_findAll&&(DWORD)(now-last_scene_query)>=50){
  for(unsigned attempt=0;attempt<scans;attempt++){
   CosmeticUIScan *candidate=&cosmetic_ui_scans[next_refresh];
   next_refresh=(next_refresh+1)%scans;
   if(candidate->refreshed&&(DWORD)(now-candidate->refreshed)<600)continue;
   last_scene_query=now;
   cosmetic_ui_refresh(candidate,now);
   break;
  }
 }
 /* The game can rewrite the coin banner when a new coin rolls. */
 cosmetic_ui_apply(COSMETIC_UI_SCAN_COIN);
 cosmetic_ui_apply(next_apply);
 if(++next_apply>=scans)next_apply=1;
}
