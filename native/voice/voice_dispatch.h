#ifndef SR_VOICE_DISPATCH_H
#define SR_VOICE_DISPATCH_H
/* The stock lookup resolves an FMOD key. PrintSpeechBubble later identifies
   the deployed unit separately. Keep that unit id in the native event. */
static unsigned voice_source_id(const Unit *u){
 if(!u)return 0;
 char *end=NULL;
 unsigned long id=strtoul(u->baseName,&end,10);
 return end==u->baseName+5&&(!*end||*end=='_')?(unsigned)id:0;
}
static Skin *voice_worn_skin(Unit *u){
 if(!u||!u->view||!rfield(u->view,"m_CachedPtr"))return 0;
 Skin *skin=skin_for_app(u,rfield(u->view,"_curAppearance"));
 if(!skin||skin->row<0||(uint32_t)skin->row>=g_rowCount)return 0;
 return skin;
}
static unsigned voice_worn_owner(Unit *u){
 return voice_skin_owner(voice_worn_skin(u));
}
#include "hiro_voice.inc"
#include "imported_wav.inc"
static Unit *voice_unit(int id,void *view){
 if(!enabled_now()||cleanup_pending||g_quitting)return NULL;
 Unit *found=NULL;
 for(int i=0;i<SR_UNIT_MAX;i++){
  Unit *u=&g_units[i];
  if(!u->used||!u->view||(view?u->view!=view:voice_source_id(u)!=(unsigned)id))continue;
  if(found)return NULL;
  found=u;
 }
 return found;
}
/* Some game voice requests are delivered after the original view callback has
   returned. Resolve the character only when the id identifies one wearer. */
static Unit *voice_unit_for_async_id(int id){
 if(id<=0||!enabled_now()||cleanup_pending||g_quitting)return NULL;
 Unit *found=NULL;
 for(int i=0;i<SR_UNIT_MAX;i++){
  Unit *u=&g_units[i];
  if(!u->used||!u->view||voice_source_id(u)!=(unsigned)id)continue;
  if(found)return NULL;
  found=u;
 }
 return found;
}
static void *voice_dialog_method(void *object,int argc){
 return object?find_method(ui_class(object),"ShowDialog",argc):NULL;
}
/* Different game builds keep the per-unit dialog in differently named
   fields. Inspect only instance fields whose declared type names a dialog or
   bubble, then require the same ShowDialog method before using the object. */
static void *voice_scan_dialog(void *manager,void *(*fields)(void*,void**),unsigned (*flags)(void*)){
 if(!fields||!flags||!api[API_FIELD_TYPE]||!api[API_TYPE_NAME]||!api[API_FIELD_VALUE]||!api[API_FREE])return NULL;
 for(void *klass=ui_class(manager);klass;klass=ui_parent(klass)){
  void *iter=NULL,*field=NULL;unsigned scanned=0;
  while((field=fields(klass,&iter))&&scanned++<256){
   if(flags(field)&0x10)continue;
   void *type=((void *(*)(void*))api[API_FIELD_TYPE])(field);
   char *name=type?((char *(*)(void*))api[API_TYPE_NAME])(type):NULL;
   int candidate=name&&(strstr(name,"Dialog")||strstr(name,"Bubble"));
   if(name)((void (*)(void*))api[API_FREE])(name);
   if(!candidate)continue;
   void *value=((void *(*)(void*,void*))api[API_FIELD_VALUE])(field,manager);
   if(value&&(voice_dialog_method(value,4)||voice_dialog_method(value,3)))return value;
  }
 }
 return NULL;
}
/* WarpHook resolves obfuscated exports, so named il2cpp exports may not exist.
   Managed reflection uses the APIs already negotiated with the host. */
static void *voice_reflect_dialog(void *manager){
 if(!manager||!api[API_CLASS_TYPE]||!api[API_TYPE_OBJECT])return NULL;
 void *klass=ui_class(manager);
 void *raw=klass?((void *(*)(void*))api[API_CLASS_TYPE])(klass):NULL;
 void *type=raw?((void *(*)(void*))api[API_TYPE_OBJECT])(raw):NULL;
 uintptr_t tr=ui_root(type);if(!tr)return NULL;
 int bindingFlags=4|16|32,ok=0;void *args[]={&bindingFlags};
 void *get=find_method(ui_class(type),"GetFields",1);
 void *array=get?call_obj(get,type,args,&ok):NULL;uintptr_t ar=ui_root(array);
 void *result=NULL;
 if(ar&&ok){
  uintptr_t n=*(uintptr_t*)((char*)array+24);
  if(n<=256)for(uintptr_t i=0;i<n&&!result;i++){
   void *field=((void**)((char*)array+32))[i];if(!field)continue;
   void *getType=find_method(ui_class(field),"get_FieldType",0);
   void *fieldType=getType?call_obj(getType,field,NULL,&ok):NULL;
   uintptr_t fr=ui_root(fieldType);if(!fr)continue;
   void *getName=find_method(ui_class(fieldType),"get_FullName",0);
   void *name=getName?call_obj(getName,fieldType,NULL,&ok):NULL;
   char text[256];int candidate=ok&&name&&string_ascii(name,text,sizeof(text))&&
     (strstr(text,"Dialog")||strstr(text,"Bubble"));
   if(candidate){
    void *getValue=find_method(ui_class(field),"GetValue",1);void *va[]={manager};
    void *value=getValue?call_obj(getValue,field,va,&ok):NULL;
    if(ok&&value&&(voice_dialog_method(value,4)||voice_dialog_method(value,3)))result=value;
   }
   ui_unroot(fr);
  }
 }
 ui_unroot(ar);ui_unroot(tr);return result;
}
static void *voice_find_dialog(void *manager){
 if(!manager)return NULL;
 /* BattleUnitUIManager itself exposes the three-argument display method. */
 if(voice_dialog_method(manager,3))return manager;
 void *direct=rfield(manager,"_dialogUI");
 if(direct&&(voice_dialog_method(direct,4)||voice_dialog_method(direct,3)))return direct;
 HMODULE game=GetModuleHandleW(L"GameAssembly.dll");
 void *(*fields)(void*,void**)=(void*)GetProcAddress(game,"il2cpp_class_get_fields");
 unsigned (*flags)(void*)=(void*)GetProcAddress(game,"il2cpp_field_get_flags");
 void *dialog=voice_scan_dialog(manager,fields,flags);
 return dialog?dialog:voice_reflect_dialog(manager);
}
static void *voice_dialog_component(void *object){
 if(!object||!api[API_CLASS_TYPE]||!api[API_TYPE_OBJECT])return NULL;
 void *klass=((void *(*)(void*,const char*,const char*))api[API_CLASS])(g_game,"BattleUI.BattleUnit","BattleDialogUI");
 void *raw=klass?((void *(*)(void*))api[API_CLASS_TYPE])(klass):NULL;
 void *type=raw?((void *(*)(void*))api[API_TYPE_OBJECT])(raw):NULL;
 uintptr_t root=ui_root(type);if(!root)return NULL;
 void *get=find_method(ui_class(object),"GetComponentInChildren",2);int ok=0;
 uint8_t inactive=0;void *args[]={type,&inactive};
 void *component=get?call_obj(get,object,args,&ok):NULL;
 ui_unroot(root);
 return ok&&component&&voice_dialog_method(component,4)?component:NULL;
}
static int voice_show_text(void *view,int id,void *key,const char *literal,float length,uint8_t custom,int nativeCue,const char *override){
 if(!view||(!key&&!override)||!c_voiceGenerator)return 0;
 void *enabled=find_method(c_voiceGenerator,"CheckSpeechBubbleSystemEnabled",0);
 int enabledResult=enabled?call_bool(enabled,NULL,NULL):-2;
 if(enabledResult!=1){
  static unsigned logged;if(logged++<4){char m[128];snprintf(m,sizeof(m),"Imported bubble diagnostic: setting=%d",enabledResult);bootlog(m);}
  return 0;
 }
 Unit *wearer=voice_unit(0,view);
 VoiceBinding *binding=voice_binding(voice_worn_skin(wearer));
 const char *caption=override?override:binding&&binding->owner==(unsigned)id?private_caption(binding,literal):NULL;
 void *text=NULL;
 if(caption)text=make_string(caption);
 else{
  void *field=((void *(*)(void *,const char *))api[API_FIELD])(c_voiceGenerator,"_voiceTable");
  void *table=field?((void *(*)(void *,void *))api[API_FIELD_VALUE])(field,NULL):NULL;
  void *lookup=table?find_method(ui_class(table),"GetVoiceTextData_SpeachBubble",2):NULL;
  void *a[]={&id,key};int ok=0;
  text=lookup?call_obj(lookup,table,a,&ok):NULL;
  if(!ok||!text||*(int32_t *)((char *)text+16)<=0){
   const char *local=sr_voice_catalog_text((unsigned)id,literal);
   if(!local&&nativeCue)local=sr_voice_catalog_bubble(literal);
   if(!local||!*local)return 0;
   text=make_string(local);
  }
 }
 uintptr_t tr=ui_root(text);if(!tr)return 0;
 void *k=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"BattleUI.Dialog","BattleDialogLine");
 void *ctor=k?find_method(k,".ctor",2):NULL;
 void *line=ctor?ui_new(k):NULL;uintptr_t lr=ui_root(line);
 void *effect=make_string("");uintptr_t er=ui_root(effect);
 int result=0,ctorOk=0,centerFound=0,managerFound=0,dialogFound=0,showFound=0;
 if(lr&&er){
  void *args[]={text,effect};
  if((ctorOk=call_exc(ctor,line,args))){
   void *ca[]={view,line,&length,&custom};
   void *center=find_method(c_voiceGenerator,"TryPrintCenterSubtitle",4);
   centerFound=center!=NULL;
   result=center&&call_bool(center,NULL,ca)==1;
   if(!result){
    void *manager=rfield(view,"_uiManager"),*dialog=voice_find_dialog(manager);
    if(!dialog)dialog=voice_dialog_component(manager);
    if(!dialog)dialog=voice_dialog_component(view);
    void *show=voice_dialog_method(dialog,4);
    managerFound=manager!=NULL;dialogFound=dialog!=NULL;showFound=show!=NULL;
    if(show){void *da[]={line,&length,&custom,NULL};result=call_bool(show,dialog,da)==1;}
    else{
     show=voice_dialog_method(dialog,3);showFound=show!=NULL;
     void *da[]={line,&length,&custom};result=show&&call_exc(show,dialog,da);
    }
   }
  }
 }
 if(!result){
  static unsigned logged;if(logged++<8){char m[200];snprintf(m,sizeof(m),"Imported bubble diagnostic: class=%d ctor=%d roots=%d/%d ctorOk=%d center=%d manager=%d dialog=%d show=%d",k!=NULL,ctor!=NULL,lr!=0,er!=0,ctorOk,centerFound,managerFound,dialogFound,showFound);bootlog(m);}
 }
 ui_unroot(er);ui_unroot(lr);ui_unroot(tr);return result;
}
static int voice_show(void *view,int id,void *key,const char *literal,float length,uint8_t custom,int nativeCue){
 return voice_show_text(view,id,key,literal,length,custom,nativeCue,NULL);
}
static int voice_show_key(Unit *u,unsigned owner,const char *key,float length,uint8_t custom){
 if(!key)return 0;
 void *str=make_string(key);uintptr_t root=ui_root(str);
 int shown=root&&voice_show(u->view,(int)owner,str,key,length,custom,0);
 ui_unroot(root);return shown;
}
static void private_caption_result(Unit *u,VoiceBinding *b,const char *key,int shown){
 char message[420];
 snprintf(message,sizeof(message),"Imported bubble: %s view=%p owner=%u revision=%.12s key=%s shown=%d",b->look,u->view,b->owner,b->library->revision,key,shown);
 bootlog(message);
}
static void private_playing_caption(PrivateVoiceEvent *e){
 if(e->captionBlocked||e->captionHandled||e->captionFallback||!private_caption(e->binding,e->key))return;
 int shown=voice_show_key(e->u,e->binding->owner,e->key,2.0f,0);
 e->captionHandled=shown;
 private_caption_result(e->u,e->binding,e->key,shown);
}
static int imported_wav_show_caption(Unit *unit,const ImportedWavAsset *asset,float length,uint8_t custom){
 int shown=voice_show_text(unit->view,(int)asset->owner,NULL,asset->key,length,custom,0,asset->text);
 char message[360];
 snprintf(message,sizeof(message),"Imported WAV bubble: view=%p owner=%u key=%s shown=%d",unit->view,asset->owner,asset->key,shown);
 bootlog(message);
 return shown;
}
static void imported_wav_playing_caption(ImportedWavEvent *event){
 /* An event-level fallback belongs to the game's subtitle cue, which can
    cover more than one recorded variant or clip in the same skill. */
 if(event->caption.rank<=1||event->captionBlocked||event->captionHandled||event->captionFallback||event->captionAttempted)return;
 event->captionAttempted=1;
 event->captionHandled=imported_wav_show_caption(event->unit,&event->caption,2.0f,0);
}
static _Thread_local Unit *voiceView;
static _Thread_local Unit *multiRequestView;
static _Thread_local int multiHasView;
static _Thread_local PrivateVoiceEvent *registeringVoice;
static void print_bubble_hook(int32_t id,void *key,float length,uint8_t custom,void *mi){
 Unit *scope=registeringVoice?registeringVoice->u:(multiRequestView?multiRequestView:voiceView);
 if(registeringWav)scope=registeringWav->unit;
 Unit *wavUnit=scope?scope:(multiHasView?NULL:voice_unit(id,NULL));
 Skin *wavSkin=voice_worn_skin(wavUnit);
 char wavKey[192]={0};ImportedWavAsset wavCaption={0};
 if(wavSkin&&wavSkin->imported&&sr_voice_string_text(key,wavKey,sizeof(wavKey))&&
    imported_wav_read(wavSkin,voice_source_id(wavUnit),wavKey,1,&wavCaption)&&
    ((unsigned)id==voice_source_id(wavUnit)||(unsigned)id==wavCaption.owner)){
  ImportedWavEvent *event=NULL;
  int ambiguous=0;
  for(int i=0;i<32;i++){
   ImportedWavEvent *candidate=&importedWavEvents[i];
   if(candidate->unit!=wavUnit||candidate->view!=wavUnit->view||candidate->app!=wavSkin->app||
      strcmp(candidate->caption.key,wavCaption.key))continue;
   if(candidate==registeringWav){event=candidate;ambiguous=0;break;}
   if(event)ambiguous=1;
   event=candidate;
  }
  if(!ambiguous&&(!event||(!event->captionBlocked&&!event->captionFallback))){
   if(event&&event->captionHandled)return;
   int shown=imported_wav_show_caption(wavUnit,&wavCaption,length,custom);
   if(event){event->captionHandled=shown;event->captionFallback=!shown;}
   if(shown)return;
  }
 }
 Unit *u=scope?(voice_source_id(scope)==(unsigned)id||voice_worn_owner(scope)==(unsigned)id?scope:NULL):
               (multiHasView?NULL:voice_unit(id,NULL));
 Skin *skin=voice_worn_skin(u);unsigned owner=voice_skin_owner(skin);
 VoiceBinding *binding=voice_binding(skin);
 char incoming[192]={0},remapped[192];int bankCaption=0;
 if(binding&&sr_voice_string_text(key,incoming,sizeof(incoming))){
  const char *mapped=private_caption(binding,incoming)?incoming:sr_voice_catalog_event_key((unsigned)id,owner,incoming);
  if((!mapped||!private_caption(binding,mapped))&&
     battle_voice_remap(incoming,voice_source_id(u),owner,remapped,sizeof(remapped)))mapped=remapped;
  if(mapped&&private_caption(binding,mapped)){
   bankCaption=1;
   PrivateVoiceEvent *event=NULL;
   for(unsigned i=0;i<32;i++){
    PrivateVoiceEvent *e=&privateVoiceEvents[i];
    if(e->u!=u||e->view!=u->view||e->app!=skin->app||e->binding!=binding||strcmp(e->key,mapped))continue;
    if(e==registeringVoice){event=e;break;}
    if(!event||(LONG)(e->queued-event->queued)>0)event=e;
   }
   if(event&&event->captionHandled)return;
   if((scope||event||battle_voice_owner_field(incoming,voice_source_id(u)))&&
      !(event&&(event->captionBlocked||event->captionFallback))){
    int shown=voice_show_key(u,owner,mapped,length,custom);
    if(event)event->captionHandled=shown;
    private_caption_result(u,binding,mapped,shown);
    if(shown)return;
   }
   if(event)event->captionFallback=1;
  }
 }
 if(skin&&skin->imported){
  unsigned source=voice_source_id(u);
  if(!bankCaption&&!*wavCaption.key&&source==(unsigned)id&&*wavKey&&battle_voice_owner_field(wavKey,source)&&
     (private_battle_caption_ready(binding)||imported_wav_has_channel(skin,source,1,NULL)))return;
  ((void (*)(int,void *,float,uint8_t,void *))orig_printBubble)(id,key,length,custom,mi);return;
 }
 if(skin&&owner!=(unsigned)id){
  char literal[192];
  if(sr_voice_string_text(key,literal,sizeof(literal))){
   for(unsigned i=0;i<8;i++){
    SrVoiceCue *cue=&u->voiceCues[i];
    if(cue->appearance==skin->app&&(DWORD)(GetTickCount()-cue->at)<30000&&!strcmp(cue->key,literal)){
     cue->appearance=NULL;
     voice_show(u->view,(int)owner,key,literal,length,custom,1);return;
    }
   }
   const char *mapped=sr_voice_catalog_event_key((unsigned)id,owner,literal);
   if(mapped){voice_show_key(u,owner,mapped,length,custom);return;}
   /* An explicit source-owned line belongs to the appearance that requested it.
      Other native dialogue (including stage-specific lines) passes through. */
   if(sr_voice_member_index((unsigned)id,literal)>=0)return;
  }
 }
 ((void (*)(int,void *,float,uint8_t,void *))orig_printBubble)(id,key,length,custom,mi);
}
static int voice_common_event(const char *name){
 return !strncmp(name,"battle",6)&&(!strcmp(name,"battleentry")||!strcmp(name,"battle_select")||
   !strcmp(name,"battle_endcommand")||!strcmp(name,"battle_break")||!strcmp(name,"battle_enemy_break")||
   !strcmp(name,"battle_kill")||!strcmp(name,"battle_allydead")||!strcmp(name,"battle_dead")||
   !strcmp(name,"battle_loseduel")||!strcmp(name,"battle_start"));
}
/* Keep the exact requesting view through stock checks and index selection.
   Calls outside this scope still require an unambiguous deployed source id. */
static void voice_view_hook(void *view,int event,uint8_t special,void *viewer,void *mi){
 Unit *previous=voiceView;
 voiceView=voice_unit(0,view);
 ((void (*)(void *,int,uint8_t,void *,void *))orig_setViewVoice)(view,event,special,viewer,mi);
 voiceView=previous;
}
static int voice_index_hook(void *path,int id,int index,void **voiceId,void **outputPath,void *mi){
 typedef int (*Lookup)(void *,int,int,void **,void **,void *);
 char event[128];
 int scoped=voiceView&&voice_source_id(voiceView)==(unsigned)id;
 if(!sr_voice_string_text(path,event,sizeof(event))||(!scoped&&strncmp(event,"battle_",7)&&strcmp(event,"battleentry")))
  return ((Lookup)orig_checkVoiceIndex)(path,id,index,voiceId,outputPath,mi);
 Unit *u=scoped?voiceView:voice_unit(id,NULL);Skin *skin=voice_worn_skin(u);unsigned donor=voice_skin_owner(skin);
 if(!skin||skin->imported||donor==(unsigned)id)return ((Lookup)orig_checkVoiceIndex)(path,id,index,voiceId,outputPath,mi);
 /* Keep an unknown stage-script event in its native context. For a recognized
    event, zero sends an ownerless costume through the stock missing-key path. */
 if(!scoped&&!voice_common_event(event)&&!sr_voice_catalog_has_event(donor,event)&&!sr_voice_catalog_has_event((unsigned)id,event))
  return ((Lookup)orig_checkVoiceIndex)(path,id,index,voiceId,outputPath,mi);
 int result=((Lookup)orig_checkVoiceIndex)(path,(int)donor,index,voiceId,outputPath,mi);
 if(result!=0){
  char key[192];
  const char *only=NULL;
  if(index>0){
   snprintf(key,sizeof(key),"%s_%u_%d",event,donor,index);
   if(sr_voice_catalog_text(donor,key)&&!sr_voice_catalog_audio(donor,key))only=key;
  }else only=sr_voice_catalog_only_event(donor,event);
  if(only)voice_show_key(u,donor,only,2.0f,0);
 }
 return result;
}
typedef struct {int owner,source;void *key;} VoiceRegistration;
static _Thread_local VoiceRegistration voiceRegistration;
typedef struct {Unit *unit;Skin *skin;uintptr_t instance;} VoiceSegment;
static _Thread_local VoiceSegment voiceSegment;
static PrivateVoiceEvent *voice_track_bank(Unit *unit,Skin *skin,void *original,ImportedWavEvent *wav,int blocked){
 if(wav&&*wav->path)return NULL;
 int mapped=0;
 PrivateVoiceEvent *bank=private_voice_track_impl(unit,skin,original,&mapped);
 if(wav&&mapped)wav->suppress=0;
 if(bank){
  if(wav&&*wav->caption.key)bank->captionBlocked=1;
  else if(blocked>=0)bank->captionBlocked=blocked;
 }
 return bank;
}
static uint8_t voice_timeline_hook(void *mixer,void *app,uintptr_t instance,void *segment,void *mi){
 typedef uint8_t (*Register)(void *,void *,uintptr_t,void *,void *);
 Unit *unit=enabled_now()&&!cleanup_pending&&!g_quitting?unit_for_app(app):NULL;
 Skin *skin=voice_worn_skin(unit);
 VoiceSegment previous=voiceSegment;
 voiceSegment=(VoiceSegment){unit,skin&&skin->app==app?skin:NULL,instance};
 PrivateVoiceEvent *previousEvent=registeringVoice;
 ImportedWavEvent *previousWav=registeringWav;
 registeringWav=skin&&skin->app==app?imported_wav_track(unit,skin,(void*)instance):NULL;
 registeringVoice=skin&&skin->app==app?voice_track_bank(unit,skin,(void*)instance,registeringWav,-1):NULL;
 uint8_t result=((Register)orig_registerAppearanceVoice)(mixer,app,instance,segment,mi);
 if(!result&&registeringVoice)private_voice_end(registeringVoice);
 if(!result&&registeringWav&&registeringWav!=previousWav)imported_wav_end(registeringWav);
 registeringVoice=previousEvent;
 registeringWav=previousWav;
 voiceSegment=previous;
 return result;
}
static void *voice_add_hook(uintptr_t instance,int id,int type,float volume,uint8_t custom,float length,
                            void *alternate,uint8_t blocked,void *subtitle,uint8_t duck,uint8_t interrupt,void *mi){
 typedef void *(*Add)(uintptr_t,int,int,float,uint8_t,float,void *,uint8_t,void *,uint8_t,uint8_t,void *);
 if(voiceRegistration.owner==id&&voiceRegistration.key&&alternate==voiceRegistration.key)id=voiceRegistration.source;
 Unit *u=voiceSegment.unit;Skin *skin=voiceSegment.skin;
 if(u&&skin&&!skin->imported&&instance&&voiceSegment.instance==instance){
  unsigned owner=voice_skin_owner(skin),source=voice_source_id(u);
  if(source&&((unsigned)id==source||(owner&&(unsigned)id==owner))){
   id=(int)source;
   char key[192];
   if(!blocked&&(sr_voice_string_text(subtitle,key,sizeof(key))||sr_voice_string_text(alternate,key,sizeof(key)))){
    SrVoiceCue *cue=&u->voiceCues[u->voiceCueNext++%8];
    cue->appearance=skin->app;cue->at=GetTickCount();lstrcpynA(cue->key,key,sizeof(cue->key));
   }
  }
 }
 Unit *requester=voiceSegment.instance==instance?(voiceSegment.skin?voiceSegment.unit:NULL):
                 (multiHasView?multiRequestView:voiceView);
 if(!requester&&!multiHasView&&!voiceSegment.unit)requester=voice_unit_for_async_id(id);
 PrivateVoiceEvent *previousEvent=registeringVoice;
 ImportedWavEvent *previousWav=registeringWav;
 Skin *worn=voice_worn_skin(requester);
 registeringWav=requester&&((voiceSegment.skin&&voiceSegment.instance==instance)||
              voice_source_id(requester)==(unsigned)id)?imported_wav_track(requester,worn,(void*)instance):NULL;
 registeringVoice=requester?voice_track_bank(requester,worn,(void*)instance,registeringWav,blocked):NULL;
 if(registeringWav)registeringWav->captionBlocked=blocked;
 void *result=((Add)orig_addMultiVoice)(instance,id,type,volume,custom,length,alternate,blocked,subtitle,duck,interrupt,mi);
 if(!result&&registeringVoice&&registeringVoice!=previousEvent)private_voice_end(registeringVoice);
 if(!result&&registeringWav&&registeringWav!=previousWav)imported_wav_end(registeringWav);
 registeringVoice=previousEvent;
 registeringWav=previousWav;
 return result;
}
static void *voice_multi_dispatch(int id,void *key,void *view,uint8_t special,uint8_t custom,float length,void *mi){
 typedef void *(*Multi)(int,void *,void *,uint8_t,uint8_t,float,void *);
 Unit *u=view?voice_unit(id,view):NULL;
 Skin *skin=voice_worn_skin(u);unsigned owner=voice_skin_owner(skin),source=voice_source_id(u);
 char literal[192];
 if(!skin||skin->imported||owner==source||!source||((unsigned)id!=source&&(unsigned)id!=owner)||!sr_voice_string_text(key,literal,sizeof(literal)))
  return ((Multi)orig_multiVoice)(id,key,view,special,custom,length,mi);
 const char *mapped=sr_voice_catalog_event_key(source,owner,literal);
 /* A donor's own explicit request is authoritative even for newly released lines. */
 if(!mapped&&(unsigned)id==owner)mapped=literal;
 if(!mapped){
  if(sr_voice_member_index(source,literal)>=0)return NULL;
  return ((Multi)orig_multiVoice)(id,key,view,special,custom,length,mi);
 }
 void *str=strcmp(mapped,literal)?make_string(mapped):key;
 uintptr_t root=ui_root(str);if(!root)return NULL;
 VoiceRegistration previous=voiceRegistration;
 voiceRegistration=(VoiceRegistration){(int)owner,(int)source,str};
 void *result=((Multi)orig_multiVoice)((int)owner,str,view,special,custom,length,mi);
 voiceRegistration=previous;
 if(!result)voice_show(view,(int)owner,str,mapped,length,custom,1);
 ui_unroot(root);return result;
}
static void *voice_multi_hook(int id,void *key,void *view,uint8_t special,uint8_t custom,float length,void *mi){
 Unit *previous=multiRequestView;
 int previousHasView=multiHasView;multiHasView=view!=NULL;
 multiRequestView=view?voice_unit(id,view):NULL;
 void *result=voice_multi_dispatch(id,key,view,special,custom,length,mi);
 multiRequestView=previous;
 multiHasView=previousHasView;
 return result;
}
static void voice_pump(void){
 if(!m_playMultiVoice||!g_voicePendingCount)return;
 DWORD now=GetTickCount();
 for(int i=0;i<SR_VOICE_PENDING;i++){
  if(InterlockedCompareExchange(&g_voiceLock,1,0))return;
  SrVoicePending p=g_voicePending[i];
  int ready=p.view&&((int32_t)(now-p.due)>=0);
  if(ready){memset(&g_voicePending[i],0,sizeof(p));InterlockedDecrement(&g_voicePendingCount);}
  InterlockedExchange(&g_voiceLock,0);
  if(!ready)continue;
  Unit *u=voice_unit((int)p.boss,p.view);
  if(u&&voice_worn_owner(u)==p.boss){
   int id=(int)p.boss;void *str=make_string(p.key);uintptr_t root=ui_root(str);
   uint8_t special=0,custom=0;float length=2.0f;
   if(root){
    void *args[]={&id,str,p.view,&special,&custom,&length};
    int ok=0;void *result=call_obj(m_playMultiVoice,NULL,args,&ok);
    if(!voicePairReady)voice_show(p.view,id,str,p.key,length,custom,1);
    char line[160];snprintf(line,sizeof(line),"voice: owner=%d key=%s native_event=%d",id,p.key,ok&&result);bootlog(line);
   }
   ui_unroot(root);
  }
  ui_unroot(p.viewRoot);
 }
}
#endif
