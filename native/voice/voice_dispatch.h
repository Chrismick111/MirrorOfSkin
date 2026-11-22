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
static int voice_show(void *view,int id,void *key,const char *literal,float length,uint8_t custom,int nativeCue){
 if(!view||!key||!c_voiceGenerator)return 0;
 void *enabled=find_method(c_voiceGenerator,"CheckSpeechBubbleSystemEnabled",0);
 if(!enabled||call_bool(enabled,NULL,NULL)!=1)return 0;
 Unit *wearer=voice_unit(0,view);
 VoiceBinding *binding=voice_binding(voice_worn_skin(wearer));
 const char *caption=binding&&binding->owner==(unsigned)id?private_caption(binding,literal):NULL;
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
 int result=0;
 if(lr&&er){
  void *args[]={text,effect};
  if(call_exc(ctor,line,args)){
   void *ca[]={view,line,&length,&custom};
   void *center=find_method(c_voiceGenerator,"TryPrintCenterSubtitle",4);
   result=center&&call_bool(center,NULL,ca)==1;
   if(!result){
    void *manager=rfield(view,"_uiManager"),*dialog=manager?rfield(manager,"_dialogUI"):NULL;
    void *show=dialog?find_method(ui_class(dialog),"ShowDialog",3):NULL;
    void *da[]={line,&length,&custom};result=show&&call_exc(show,dialog,da);
   }
  }
 }
 ui_unroot(er);ui_unroot(lr);ui_unroot(tr);return result;
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
 if(e->captionBlocked||e->captionHandled||!private_caption(e->binding,e->key))return;
 int shown=voice_show_key(e->u,e->binding->owner,e->key,2.0f,0);
 e->captionHandled=shown;
 private_caption_result(e->u,e->binding,e->key,shown);
}
static _Thread_local Unit *voiceView;
static _Thread_local Unit *multiRequestView;
static _Thread_local PrivateVoiceEvent *registeringVoice;
static void print_bubble_hook(int32_t id,void *key,float length,uint8_t custom,void *mi){
 Unit *scope=registeringVoice?registeringVoice->u:(multiRequestView?multiRequestView:voiceView);
 Unit *u=scope&&(voice_source_id(scope)==(unsigned)id||voice_worn_owner(scope)==(unsigned)id)?scope:voice_unit(id,NULL);
 Skin *skin=voice_worn_skin(u);unsigned owner=voice_skin_owner(skin);
 VoiceBinding *binding=voice_binding(skin);
 char incoming[192];
 if(binding&&sr_voice_string_text(key,incoming,sizeof(incoming))){
  const char *mapped=private_caption(binding,incoming)?incoming:sr_voice_catalog_event_key((unsigned)id,owner,incoming);
  if(mapped&&private_caption(binding,mapped)){
   PrivateVoiceEvent *event=NULL;
   for(unsigned i=0;i<32;i++){
    PrivateVoiceEvent *e=&privateVoiceEvents[i];
    if(e->u==u&&e->app==skin->app&&e->binding==binding&&!strcmp(e->key,mapped)&&
       (!event||(LONG)(e->queued-event->queued)>0))event=e;
   }
   if(registeringVoice&&registeringVoice->u==u&&!strcmp(registeringVoice->key,mapped))event=registeringVoice;
   if(event&&(event->captionHandled||event->captionBlocked))return;
   int shown=voice_show_key(u,owner,mapped,length,custom);
   if(event)event->captionHandled=shown;
   private_caption_result(u,binding,mapped,shown);
   if(shown)return;
  }
 }
 if(skin&&skin->imported&&!owner){
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
 if(!skin||(!donor&&skin->imported)||donor==(unsigned)id)return ((Lookup)orig_checkVoiceIndex)(path,id,index,voiceId,outputPath,mi);
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
static _Thread_local int multiHasView;
static uint8_t voice_timeline_hook(void *mixer,void *app,uintptr_t instance,void *segment,void *mi){
 typedef uint8_t (*Register)(void *,void *,uintptr_t,void *,void *);
 Unit *unit=enabled_now()&&!cleanup_pending&&!g_quitting?unit_for_app(app):NULL;
 Skin *skin=voice_worn_skin(unit);
 VoiceSegment previous=voiceSegment;
 voiceSegment=(VoiceSegment){unit,skin&&skin->app==app?skin:NULL,instance};
 PrivateVoiceEvent *previousEvent=registeringVoice;
 registeringVoice=skin&&skin->app==app?private_voice_track(unit,skin,(void*)instance):NULL;
 uint8_t result=((Register)orig_registerAppearanceVoice)(mixer,app,instance,segment,mi);
 if(!result&&registeringVoice)private_voice_end(registeringVoice);
 registeringVoice=previousEvent;
 voiceSegment=previous;
 return result;
}
static void *voice_add_hook(uintptr_t instance,int id,int type,float volume,uint8_t custom,float length,
                            void *alternate,uint8_t blocked,void *subtitle,uint8_t duck,uint8_t interrupt,void *mi){
 typedef void *(*Add)(uintptr_t,int,int,float,uint8_t,float,void *,uint8_t,void *,uint8_t,uint8_t,void *);
 if(voiceRegistration.owner==id&&voiceRegistration.key&&alternate==voiceRegistration.key)id=voiceRegistration.source;
 Unit *u=voiceSegment.unit;Skin *skin=voiceSegment.skin;
 if(u&&skin&&instance&&voiceSegment.instance==instance){
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
 PrivateVoiceEvent *previousEvent=registeringVoice;
 registeringVoice=requester?private_voice_track(requester,voice_worn_skin(requester),(void*)instance):NULL;
 if(registeringVoice)registeringVoice->captionBlocked=blocked;
 void *result=((Add)orig_addMultiVoice)(instance,id,type,volume,custom,length,alternate,blocked,subtitle,duck,interrupt,mi);
 if(!result&&registeringVoice&&registeringVoice!=previousEvent)private_voice_end(registeringVoice);
 registeringVoice=previousEvent;
 return result;
}
static void *voice_multi_dispatch(int id,void *key,void *view,uint8_t special,uint8_t custom,float length,void *mi){
 typedef void *(*Multi)(int,void *,void *,uint8_t,uint8_t,float,void *);
 Unit *u=view?voice_unit(id,view):NULL;
 Skin *skin=voice_worn_skin(u);unsigned owner=voice_skin_owner(skin),source=voice_source_id(u);
 char literal[192];
 if(!skin||(!owner&&skin->imported)||owner==source||!source||((unsigned)id!=source&&(unsigned)id!=owner)||!sr_voice_string_text(key,literal,sizeof(literal)))
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
