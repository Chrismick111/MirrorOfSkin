#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"

enum { LOOKUP_LOG = 1, LOOKUP_INT, CURRENT_LOG, GET_MODEL, GET_ID, GET_TEXT, SET_TEXT, GET_UPTIE,
       GET_GAME_OBJECT, GET_ACTIVE, GET_DEFENSE_IDS, GET_COUNT, GET_ITEM, IS_DEFENSE, GET_SKILLS,
       SIN_OWNER, SIN_ID, SIN_SKILL, SIN_ACTION, ACTION_ID, ACTION_SKILL, GET_ICON };
static int requested_id = 1011503;
static int current_id = 1011503;
static int current_active, int_lookups, typed_available=1;
static int action_uses_defense=1, selection_has_skill=1, selection_has_id=1;
static int uptie = 3;
static char current_viewer, stock_viewer, appearance;
static void *view[5],*shared_view[5],*foreign_view[5],*manager[2],*skill_ui[2],*preview[4],*skill_detail[2];
static void *compared[6],*player_panel[2],*enemy_panel[2];
static struct {void *cached,*label; int owner; uint8_t open;} banner;
static struct {int id,tier;} banner_skill;
static int active=1, defense_id=98989801, base_id=1011501, defense_count=1;
static struct {void *cached; int id;} preview_icon;
static char model, enemy_model, defense_ids, model_skills, selection, enemy_selection, action;
static int enemy_skill_id=1031503;
enum { FIELD_MANAGER=5, FIELD_OWNER, FIELD_OPEN, FIELD_DATA, FIELD_ID, FIELD_TIER,
       FIELD_MODEL, FIELD_ICON_ID, FIELD_INSTANCE, FIELD_SELECTION, FIELD_DETAIL, FIELD_COMPARISON };
static char original_name, replacement_name, next_owner_name, default_name, tier_three_name, guard_name, original_unit_name;
static void *text_component[2], *displayed_name, *unit_name_component[2], *unit_name;
static struct { int instance_id; uint8_t open; } primitive_fields;

static void *fake_class(void *object){return object;}
static void *fake_parent(void *klass){return NULL;}
static void *fake_unbox(void *object){return object;}
static void *fake_field(void *klass,const char *name){
 if(klass==&primitive_fields&&!strcmp(name,"_instanceID"))return (void *)3;
 if(klass==&primitive_fields&&!strcmp(name,"_open"))return (void *)4;
 if(!strcmp(name,"m_CachedPtr"))return (void *)1;
 if((klass==view||klass==shared_view||klass==foreign_view)&&!strcmp(name,"_curAppearance"))return (void *)2;
 if((klass==view||klass==shared_view)&&!strcmp(name,"_uiManager"))return (void *)FIELD_MANAGER;
 if((klass==view||klass==shared_view||klass==foreign_view)&&!strcmp(name,"_instanceID"))
  return (void *)FIELD_INSTANCE;
 if((klass==view||klass==foreign_view)&&!strcmp(name,"_unitModel"))return (void *)FIELD_MODEL;
 if(klass==manager&&!strcmp(name,"_unitSkillInfoUI"))return (void *)2;
 if(klass==skill_ui&&!strcmp(name,"_skillParryingUI"))return (void *)2;
 if(klass==&banner&&!strcmp(name,"tmp_skillName"))return (void *)2;
 if(klass==&banner&&!strcmp(name,"_ownerUnitId"))return (void *)FIELD_OWNER;
 if(klass==&banner&&!strcmp(name,"_open"))return (void *)FIELD_OPEN;
 if(klass==&banner&&!strcmp(name,"_skillUIData"))return (void *)FIELD_DATA;
 if(klass==&banner_skill&&!strcmp(name,"_id"))return (void *)FIELD_ID;
 if(klass==&banner_skill&&!strcmp(name,"_skillTier"))return (void *)FIELD_TIER;
 if((klass==preview||klass==skill_detail)&&!strcmp(name,"tmp_name"))return (void *)2;
 if(klass==preview&&!strcmp(name,"_tmp_skillName"))return (void *)2;
 if((klass==player_panel||klass==enemy_panel)&&!strcmp(name,"_tmp_skillName"))return (void *)2;
 if(klass==compared){
  static const char *const fields[]={"_playerInfo","_enemyInfo","_leftInfo","_rightInfo","_leftSin","_rightSin"};
  for(unsigned i=0;i<sizeof(fields)/sizeof(*fields);i++)
   if(!strcmp(name,fields[i]))return (void *)(uintptr_t)(FIELD_COMPARISON+i);
 }
 if(klass==preview&&!strcmp(name,"_chosenUnitSinModel"))return (void *)FIELD_SELECTION;
 if(klass==preview&&!strcmp(name,"_skillDetail"))return (void *)FIELD_DETAIL;
 if(klass==&preview_icon&&!strcmp(name,"_currentSetSkillId"))return (void *)FIELD_ICON_ID;
 return NULL;
}
static void *fake_field_value(void *field,void *object){
 return field==(void *)FIELD_DATA&&object==&banner?&banner_skill:NULL;
}
static const char *fake_class_name(void *klass){
 if(klass==&banner_skill)return "SkillUIData";
 if(klass==&defense_id)return "Int32";
 return NULL;
}
static size_t fake_offset(void *field){
 if(field==(void *)3)return 0;
 if(field==(void *)4)return sizeof(int);
 if(field==(void *)FIELD_MANAGER)return 2*sizeof(void *);
 if(field==(void *)FIELD_OWNER)return 2*sizeof(void *);
 if(field==(void *)FIELD_OPEN)return 2*sizeof(void *)+sizeof(int);
 if(field==(void *)FIELD_ID)return 0;
 if(field==(void *)FIELD_TIER)return sizeof(int);
 if(field==(void *)FIELD_MODEL)return 3*sizeof(void *);
 if(field==(void *)FIELD_ICON_ID)return sizeof(void *);
 if(field==(void *)FIELD_INSTANCE)return 4*sizeof(void *);
 if(field==(void *)FIELD_SELECTION)return 2*sizeof(void *);
 if(field==(void *)FIELD_DETAIL)return 3*sizeof(void *);
 if((uintptr_t)field>=FIELD_COMPARISON)return ((uintptr_t)field-FIELD_COMPARISON)*sizeof(void *);
 return ((uintptr_t)field-1)*sizeof(void *);
}
static uintptr_t fake_root(void *object,int pinned){return (uintptr_t)object;}
static void fake_unroot(uintptr_t handle){}
static void *fake_method(void *klass,const char *name,int count){
 if(klass==view&&count==1&&!strcmp(name,"GetSkillViewer"))return (void *)LOOKUP_LOG;
 if(klass==view&&count==0&&!strcmp(name,"GetCurrentLogSkillViewer"))return (void *)CURRENT_LOG;
 if(count==0&&!strcmp(name,"GetSkillModel"))return (void *)GET_MODEL;
 if(count==0&&!strcmp(name,"GetID"))return (void *)GET_ID;
 if((klass==text_component||klass==unit_name_component)&&count==0&&!strcmp(name,"get_text"))return (void *)GET_TEXT;
 if((klass==text_component||klass==unit_name_component)&&count==1&&!strcmp(name,"set_text"))return (void *)SET_TEXT;
 if(count==0&&!strcmp(name,"GetGaksungLevel"))return (void *)GET_UPTIE;
 if(count==0&&!strcmp(name,"get_gameObject"))return (void *)GET_GAME_OBJECT;
 if(klass==&model&&count==0&&!strcmp(name,"GetDefenseSkillIDList"))return (void *)GET_DEFENSE_IDS;
 if(klass==&model&&count==0&&!strcmp(name,"GetSkillList"))return (void *)GET_SKILLS;
 if((klass==&defense_ids||klass==&model_skills)&&count==0&&!strcmp(name,"get_Count"))return (void *)GET_COUNT;
 if((klass==&defense_ids||klass==&model_skills)&&count==1&&!strcmp(name,"get_Item"))return (void *)GET_ITEM;
 if((klass==&defense_id||(klass==&requested_id&&requested_id==defense_id))&&
    count==0&&!strcmp(name,"IsDefense"))return (void *)IS_DEFENSE;
 if((klass==&selection||klass==&enemy_selection)&&count==0&&!strcmp(name,"get_Model"))return (void *)SIN_OWNER;
 if((klass==&selection||klass==&enemy_selection)&&count==0&&!strcmp(name,"get_SkillID"))return (void *)SIN_ID;
 if((klass==&selection||klass==&enemy_selection)&&count==0&&!strcmp(name,"GetSkill"))return (void *)SIN_SKILL;
 if(klass==&selection&&count==0&&!strcmp(name,"GetBattleActionModel"))return (void *)SIN_ACTION;
 if(klass==&action&&count==0&&!strcmp(name,"GetSkillID"))return (void *)ACTION_ID;
 if(klass==&action&&count==0&&!strcmp(name,"get_Skill"))return (void *)ACTION_SKILL;
 if(klass==preview&&count==0&&!strcmp(name,"get_SkillIconUI"))return (void *)GET_ICON;
 return NULL;
}
static void *fake_methods(void *klass,void **iterator){
 if(klass!=view||(uintptr_t)*iterator>=LOOKUP_INT)return NULL;
 *iterator=(void *)((uintptr_t)*iterator+1);
 return *iterator;
}
static const char *fake_method_name(void *method){return "GetSkillViewer";}
static uint32_t fake_param_count(void *method){return 1;}
static void *fake_param(void *method,uint32_t index){return method;}
static char *fake_type_name(void *type){return _strdup(type==(void *)LOOKUP_INT?"System.Int32":"BattleActionLog");}
static void *fake_invoke(void *method,void *object,void **args,void **exception){
 switch((uintptr_t)method){
 case LOOKUP_LOG: return NULL;
 case LOOKUP_INT:
  assert(object==view&&*(int *)args[0]==requested_id);
  int_lookups++;
  return typed_available?&stock_viewer:NULL;
 case CURRENT_LOG: return current_active?&current_viewer:NULL;
 case GET_MODEL: return object==&current_viewer?&current_id:&requested_id;
 case GET_ID: return object;
 case GET_TEXT: return object==unit_name_component?unit_name:displayed_name;
 case SET_TEXT:
  if(object==unit_name_component)unit_name=args[0];
  else displayed_name=args[0];
  return NULL;
 case GET_UPTIE: return &uptie;
 case GET_GAME_OBJECT: return object;
 case GET_ACTIVE: return &active;
 case GET_DEFENSE_IDS: return &defense_ids;
 case GET_SKILLS: return &model_skills;
 case GET_COUNT: return &defense_count;
 case GET_ITEM: return &defense_id;
 case IS_DEFENSE: return &active;
 case SIN_OWNER: return object==&enemy_selection?&enemy_model:&model;
 case SIN_ID: return object==&enemy_selection?&enemy_skill_id:selection_has_id?&base_id:NULL;
 case SIN_SKILL: return object==&enemy_selection?&enemy_skill_id:selection_has_skill?&base_id:NULL;
 case SIN_ACTION: return &action;
 case ACTION_ID: case ACTION_SKILL: return action_uses_defense?&defense_id:&base_id;
 case GET_ICON: return &preview_icon;
 default: return NULL;
 }
}

static void test_names_at_displayed_level(Unit *owner){
 static char data[]=
  "MOSUI1\nT\t10315\n"
  "S\t1031501\tunknown\t0\tDefault name\t\n"
  "S\t1031503\tunknown\t3\tStrike Air\t\n"
  "S\t90909\tdefense\t0\tGuard name\t\n";
 static CosmeticUiManifest table;
 static CosmeticUiText names[3];
 static LocalArtEntry art;
 static Config config;
 assert(cosmetic_ui_parse(data,sizeof(data)-1,&table));
 strcpy(art.art.look,"TestBanner");
 art.art.loadedPath=L"test-banner.bundle";
 localArtEntries=&art;
 cosmetic_ui_look_count=1;
 CosmeticUiLook *look=&cosmetic_ui_looks[0];
 strcpy(look->look,art.art.look);
 wcscpy(look->model,art.art.loadedPath);
 look->table=&table;
 names[0]=(CosmeticUiText){.utf8=table.skills[0].art.text,.text=&default_name,.next=&names[1]};
 names[1]=(CosmeticUiText){.utf8=table.skills[1].art.text,.text=&tier_three_name,.next=&names[2]};
 names[2]=(CosmeticUiText){.utf8=table.skills[2].art.text,.text=&guard_name};
 look->texts=names;
 g_rowCount=1;
 Skin *skin=&owner->skins[0];
 skin->used=1;
 skin->app=&appearance;
 skin->imported=&art.art.config;
 strcpy(skin->look,art.art.look);
 view[0]=view[1]=&appearance;
 g_cfg=&config;
 config.enabled=1;
 config.heartbeat=GetTickCount();
 ur_in_canvas=1;
 displayed_name=&original_name;

 cosmetic_control_skill(owner,NULL,1011501,1,text_component,NULL,COSMETIC_UI_SCAN_COIN);
 assert(displayed_name==&default_name);
 cosmetic_control_skill(owner,NULL,1011503,3,text_component,NULL,COSMETIC_UI_SCAN_COIN);
 assert(displayed_name==&original_name);
 cosmetic_control_skill(owner,cosmetic_control_skill_model(owner,1011503),1011503,3,
                        text_component,NULL,COSMETIC_UI_SCAN_COIN);
 assert(displayed_name==&tier_three_name);
 cosmetic_control_restore(cosmetic_control_find(text_component,COSMETIC_UI_TEXT));

 /* The unit-owned component remains reachable even with no global array or usable owner ID. */
 owner->used=1;
 view[2]=manager;
 manager[1]=skill_ui;
 skill_ui[1]=&banner;
 banner.cached=&appearance;
 banner.label=text_component;
 banner.open=1;
 banner_skill.id=requested_id;
 banner_skill.tier=3;
 cosmetic_ui_apply(COSMETIC_UI_SCAN_COIN);
 assert(displayed_name==&tier_three_name);
 banner.open=0;
 cosmetic_ui_apply(COSMETIC_UI_SCAN_COIN);
 assert(displayed_name==&original_name);

 /* Selection and execution agree when the active defense supersedes the slot's base skill ID. */
 view[3]=&model;
 preview[0]=&appearance;
 preview[1]=text_component;
 preview_icon.cached=&appearance;
 preview_icon.id=defense_id;
 cosmetic_control_preview(preview,&selection,"tmp_name",NULL,COSMETIC_UI_SCAN_TARGET);
 assert(displayed_name==&guard_name);
 cosmetic_control_restore(cosmetic_control_find(text_component,COSMETIC_UI_TEXT));
 cosmetic_control_preview(preview,NULL,"tmp_name",NULL,COSMETIC_UI_SCAN_PAIRED);
 cosmetic_control_preview(preview,&selection,"tmp_name",NULL,COSMETIC_UI_SCAN_PAIRED);
 assert(displayed_name==&guard_name);
 cosmetic_control_restore(cosmetic_control_find(text_component,COSMETIC_UI_TEXT));

 /* A displayed defense from the same unit can lead its cached selection action. */
 action_uses_defense=0;
 typed_available=0;
 requested_id=defense_id;
 preview[1]=unit_name_component;
 preview[2]=&selection;
 preview[3]=skill_detail;
 skill_detail[0]=&appearance;
 skill_detail[1]=text_component;
 unit_name_component[0]=&appearance;
 unit_name=&original_unit_name;
 cosmetic_control_target(preview,COSMETIC_UI_SCAN_TARGET);
 assert(displayed_name==&guard_name&&unit_name==&original_unit_name);
 cosmetic_control_restore(cosmetic_control_find(text_component,COSMETIC_UI_TEXT));
 typed_available=1;
 cosmetic_control_target(preview,COSMETIC_UI_SCAN_TARGET);
 assert(displayed_name==&guard_name&&unit_name==&original_unit_name);
 cosmetic_control_restore(cosmetic_control_find(text_component,COSMETIC_UI_TEXT));
 int lookups_before=int_lookups;
 preview_icon.id=1011503; /* A different skill from the same unit is not current defense evidence. */
 cosmetic_control_target(preview,COSMETIC_UI_SCAN_TARGET);
 assert(displayed_name==&original_name&&int_lookups==lookups_before);
 preview_icon.id=defense_id+1;
 cosmetic_control_target(preview,COSMETIC_UI_SCAN_TARGET);
 assert(displayed_name==&original_name&&int_lookups==lookups_before);
 preview_icon.id=defense_id;
 defense_count=2;
 cosmetic_control_target(preview,COSMETIC_UI_SCAN_TARGET);
 assert(displayed_name==&original_name&&int_lookups==lookups_before);
 defense_count=1;
 preview_icon.cached=NULL;
 cosmetic_control_target(preview,COSMETIC_UI_SCAN_TARGET);
 assert(displayed_name==&default_name&&unit_name==&original_unit_name);
 cosmetic_control_restore(cosmetic_control_find(text_component,COSMETIC_UI_TEXT));
 action_uses_defense=1;
 selection_has_skill=0;
 cosmetic_control_target(preview,COSMETIC_UI_SCAN_TARGET);
 assert(displayed_name==&guard_name&&unit_name==&original_unit_name);
 cosmetic_control_restore(cosmetic_control_find(text_component,COSMETIC_UI_TEXT));
 selection_has_id=0;
 cosmetic_control_target(preview,COSMETIC_UI_SCAN_TARGET);
 assert(displayed_name==&guard_name&&unit_name==&original_unit_name);
 cosmetic_control_restore(cosmetic_control_find(text_component,COSMETIC_UI_TEXT));
 selection_has_id=1;
 typed_available=0;
 requested_id=banner_skill.id=defense_id;
 banner_skill.tier=0;
 banner.open=1;
 cosmetic_ui_apply(COSMETIC_UI_SCAN_COIN);
 assert(displayed_name==&guard_name);
 view[4]=(void *)701;
 memcpy(shared_view,view,sizeof(view));
 shared_view[4]=(void *)702;
 g_units[1].used=1;
 g_units[1].view=shared_view;
 cosmetic_ui_apply(COSMETIC_UI_SCAN_COIN);
 assert(displayed_name==&original_name);
 banner.owner=701;
 cosmetic_ui_apply(COSMETIC_UI_SCAN_COIN);
 assert(displayed_name==&guard_name);
 foreign_view[0]=foreign_view[1]=&appearance;
 foreign_view[4]=(void *)703;
 g_units[2].used=1;
 g_units[2].view=foreign_view;
 g_units[2].skins[0]=owner->skins[0];
 banner.owner=703;
 cosmetic_ui_apply(COSMETIC_UI_SCAN_COIN);
 assert(displayed_name==&original_name);
 g_units[2].used=0;
 banner.owner=0;
 g_units[1].used=0;
 cosmetic_ui_apply(COSMETIC_UI_SCAN_COIN);
 assert(displayed_name==&guard_name);
 defense_count=2;
 cosmetic_ui_apply(COSMETIC_UI_SCAN_COIN);
 assert(displayed_name==&original_name);

 /* Screen positions can swap while the game keeps each sin with its faction panel. */
 selection_has_skill=1;
 action_uses_defense=0;
 foreign_view[3]=&enemy_model;
 g_units[2].used=1;
 g_units[2].skins[0].used=0;
 player_panel[0]=enemy_panel[0]=&appearance;
 player_panel[1]=text_component;
 enemy_panel[1]=unit_name_component;
 compared[0]=player_panel;
 compared[1]=enemy_panel;
 compared[2]=enemy_panel;
 compared[3]=player_panel;
 compared[4]=&selection;
 compared[5]=&enemy_selection;
 unit_name=&next_owner_name;
 cosmetic_control_relative_target(compared,COSMETIC_UI_SCAN_PAIRED);
 assert(displayed_name==&default_name&&unit_name==&next_owner_name);
 g_units[2].skins[0].used=1;
 cosmetic_control_relative_target(compared,COSMETIC_UI_SCAN_PAIRED);
 assert(displayed_name==&default_name&&unit_name==&tier_three_name);
}

int main(void){
 static void *functions[128];
 api=functions;
 sr_ui_flags=SR_UI_ALL;sr_ui_loaded=1;
 functions[API_OBJECT_CLASS]=fake_class;
 functions[API_PARENT]=fake_parent;
 functions[API_UNBOX]=fake_unbox;
 functions[API_FIELD]=fake_field;
 functions[API_FIELD_OFFSET]=fake_offset;
 functions[API_FIELD_VALUE]=fake_field_value;
 functions[API_CLASS_NAME]=fake_class_name;
 functions[API_ROOT]=fake_root;
 functions[API_UNROOT]=fake_unroot;
 functions[API_METHOD]=fake_method;
 functions[API_METHODS]=fake_methods;
 functions[API_METHOD_NAME]=fake_method_name;
 functions[API_PARAM_COUNT]=fake_param_count;
 functions[API_PARAM]=fake_param;
 functions[API_TYPE_NAME]=fake_type_name;
 functions[API_FREE]=free;
 functions[API_INVOKE]=fake_invoke;
 m_getActiveInHierarchy=(void *)GET_ACTIVE;
 assert(cosmetic_control_int_field(&primitive_fields,"_missing")==-1);
 assert(cosmetic_control_int_field(&primitive_fields,"_instanceID")==0);
 assert(!cosmetic_control_bool_field(&primitive_fields,"_open"));
 primitive_fields.instance_id=705;
 primitive_fields.open=1;
 assert(cosmetic_control_int_field(&primitive_fields,"_instanceID")==705);
 assert(cosmetic_control_bool_field(&primitive_fields,"_open"));
 assert(!cosmetic_control_bool_field(&primitive_fields,"_missing"));
 Unit *owner=&g_units[0];
 owner->view=view;

 assert(cosmetic_control_skill_model(owner,requested_id)==&requested_id&&int_lookups==1);
 current_active=1;
 assert(cosmetic_control_banner_model(owner,requested_id)==&current_id&&int_lookups==1);
 current_id=1011501;
 assert(cosmetic_control_banner_model(owner,requested_id)==&requested_id&&int_lookups==2);

 text_component[0]=&original_name;
 displayed_name=&original_name;
 assert(cosmetic_control_replace(text_component,COSMETIC_UI_TEXT,&replacement_name,COSMETIC_UI_SCAN_COIN));
 assert(displayed_name==&replacement_name);
 assert(!cosmetic_control_replace(text_component,COSMETIC_UI_TEXT,&replacement_name,COSMETIC_UI_SCAN_COIN));
 displayed_name=&original_name; /* The game rewrites the label during a coin roll. */
 assert(cosmetic_control_replace(text_component,COSMETIC_UI_TEXT,&replacement_name,COSMETIC_UI_SCAN_COIN));
 cosmetic_control_restore(cosmetic_control_find(text_component,COSMETIC_UI_TEXT));
 assert(displayed_name==&original_name);
 assert(cosmetic_control_replace(text_component,COSMETIC_UI_TEXT,&replacement_name,COSMETIC_UI_SCAN_COIN));
 displayed_name=&next_owner_name; /* A recycled banner already contains the new owner's label. */
 cosmetic_control_restore(cosmetic_control_find(text_component,COSMETIC_UI_TEXT));
 assert(displayed_name==&next_owner_name);
 test_names_at_displayed_level(owner);
 return 0;
}
