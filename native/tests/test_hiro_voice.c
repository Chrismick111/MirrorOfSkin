#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include <assert.h>
#include <stdlib.h>
#undef assert
#define assert(c) do {if(!(c)){fprintf(stderr,"FAILED line %d: %s\n",__LINE__,#c);exit(1);}} while(0)

#define LOOK_A "WBImp_111111111111111111111111"
#define LOOK_B "WBImp_222222222222222222222222"
#define LOOK_C "WBImp_333333333333333333333333"
#define REV_A "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
#define REV_B "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
#define REV_C "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
#define LOOK_NOAH "WBImp_a89310c5992f29551727affa"
#define REV_NOAH "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
#define LOOK_STOCK "WBImp_666666666666666666666666"
#define REV_STOCK "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
#define LOOK_D "WBImp_444444444444444444444444"
#define LOOK_E "WBImp_555555555555555555555555"
typedef struct {void *imported;char look[64];void *app;} Skin;
typedef struct {int used;void *view;Skin *worn;} Unit;
static Skin *voice_worn_skin(Unit *u){return u->worn;}
static unsigned voice_source_id(const Unit *u){(void)u;return 10115;}
static void bootlog(const char *s){puts(s);}
static wchar_t manifest[MAX_PATH], captions[MAX_PATH], generation[MAX_PATH], imported[2048], noah[2048], stock[2048];
static int addon_file_path(wchar_t *dst,size_t cap,const wchar_t *r){
 const wchar_t *path=NULL;
 if(!wcscmp(r,L"Assets\\ImportedVoices\\bindings.tsv"))path=manifest;
 else if(!wcscmp(r,L"Assets\\ImportedVoices\\runtime-revision"))path=generation;
 else if(!wcsncmp(r,L"Assets\\ImportedVoices\\",22)){
  const wchar_t *name=wcsrchr(r,L'\\')+1;
  if(!wcscmp(name,L"bubbles.tsv")&&(r[22]=='a'||r[22]=='d'))path=captions;
  else if(r[22]=='d'&&!_wcsicmp(name,L"Voice_Default_S4_3.assets.bank"))path=noah;
  else if(r[22]=='e')return swprintf(dst,cap,L"%ls%ls",stock,name)>0;
  else if(r[22]=='a'&&!_wcsicmp(name,L"Voice_Default_S7_4.assets.bank"))path=imported;
  else if(r[22]=='b'&&!_wcsicmp(name,L"Voice_Default_S7_4.bank"))return swprintf(dst,cap,L"%ls%ls",stock,name)>0;
  else if(r[22]=='c')return swprintf(dst,cap,L"%ls%ls",stock,name)>0;
 }
 if(!path||wcslen(path)>=cap)return 0;
 wcscpy(dst,path);return 1;
}
#include "appearance_voice_catalog.h"
#include "hiro_voice.inc"
static void private_playing_caption(PrivateVoiceEvent *e){(void)e;}

/* FMOD driver indices are local to each mixer. Exercise two endpoints with
   opposite enumeration orders before binding the real FMOD functions. */
static int sourceCore,privateCore,activeDriver,selectedDriver,driverCount;
static int sourceOutput=3,privateOutput=3,missingEndpoint,selectionError;
static int source_core(void *group,void **out){(void)group;*out=&sourceCore;return 0;}
static int private_core(void *system,void **out){(void)system;*out=&privateCore;return 0;}
static int driver_count(void *core,int *out){assert(core==&privateCore);*out=driverCount;return 0;}
static int driver_index(void *core,int *out){*out=core==&sourceCore?0:activeDriver;return 0;}
static int driver_info(void *core,int index,char *name,int length,GUID *guid,int *rate,int *mode,int *channels){
 (void)name;(void)length;(void)rate;(void)mode;(void)channels;
 memset(guid,0,sizeof(*guid));
 guid->Data1=core==&sourceCore?(missingEndpoint?9:2):(unsigned)index+1;
 return 0;
}
static int select_driver(void *core,int index){assert(core==&privateCore);selectedDriver=index;return selectionError;}
static int output_type(void *core,int *out){*out=core==&sourceCore?sourceOutput:privateOutput;return 0;}
static void test_output_routing(void){
 hChannelGroup_GetSystemObject=source_core;hStudio_System_GetCoreSystem=private_core;
 hSystem_GetNumDrivers=driver_count;hSystem_GetDriver=driver_index;hSystem_GetDriverInfo=driver_info;
 hSystem_SetDriver=select_driver;hSystem_GetOutput=output_type;
 driverCount=2;activeDriver=0;selectedDriver=-1;
 assert(private_voice_device(NULL,NULL)&&selectedDriver==1);
 activeDriver=1;selectedDriver=-1;
 assert(private_voice_device(NULL,NULL)&&selectedDriver==-1);
 missingEndpoint=1;
 assert(!private_voice_device(NULL,NULL)&&selectedDriver==-1);
 missingEndpoint=0;activeDriver=0;selectionError=1;
 assert(!private_voice_device(NULL,NULL)&&selectedDriver==1);
 driverCount=0;assert(private_voice_device(NULL,NULL));
 privateOutput=4;assert(!private_voice_device(NULL,NULL));
 puts("PASS output routing by device GUID, unavailable device and silent output");
}

static int deny_start(void *instance){(void)instance;return 1;}
static int (*set_volume_real)(void*,float);
static int deny_audible_gain(void *instance,float gain){return gain>0?1:set_volume_real(instance,gain);}
static int (*set_mute_real)(void*,int);
static unsigned mute_attempts;
static int count_mute(void *group,int mute){
 if(mute)++mute_attempts;
 return set_mute_real(group,mute);
}
static void test_playback_failure(Unit *u,Skin *skin,void *desc,int gainFailure){
 void *stock=NULL,*group=NULL;int muted=-1;
 assert(!hStudio_EventDescription_CreateInstance(desc,&stock));
 PrivateVoiceEvent *e=private_voice_track(u,skin,stock);assert(e);
 assert(!hStudio_EventInstance_Start(stock));
 int (*start)(void*)=hStudio_EventInstance_Start;
 set_volume_real=hStudio_EventInstance_SetVolume;
 set_mute_real=hChannelGroup_SetMute;
 mute_attempts=0;hChannelGroup_SetMute=count_mute;
 if(gainFailure)hStudio_EventInstance_SetVolume=deny_audible_gain;
 else hStudio_EventInstance_Start=deny_start;
 for(int i=0;i<100&&e->original;i++){private_voice_tick(1);Sleep(5);}
 hStudio_EventInstance_Start=start;
 hStudio_EventInstance_SetVolume=set_volume_real;
 hChannelGroup_SetMute=set_mute_real;
 assert(!e->original&&!mute_attempts);
 assert(!hStudio_EventInstance_GetChannelGroup(stock,&group)&&group);
 assert(!hChannelGroup_GetMute(group,&muted)&&!muted);
 hStudio_EventInstance_Stop(stock,1);hStudio_EventInstance_Release(stock);
}

int main(void){
 test_output_routing();
 wchar_t game[2048],exe[2300],libfile[2300],temp[MAX_PATH];
 assert(GetEnvironmentVariableW(L"HIRO_TEST_GAME",game,2048)>0);
 assert(GetEnvironmentVariableW(L"HIRO_TEST_BANK",imported,2048)>0);
 swprintf(exe,2300,L"%ls\\LimbusCompany.exe",game);
 swprintf(libfile,2300,L"%ls\\LimbusCompany_Data\\Plugins\\x86_64\\fmodstudio.dll",game);
 swprintf(stock,2048,L"%ls\\LimbusCompany_Data\\StreamingAssets\\Assets\\Sound\\FMODBuilds\\Desktop\\",game);
 assert(GetTempPathW(MAX_PATH,temp)&&GetTempFileNameW(temp,L"vb",0,manifest));
 assert(GetTempFileNameW(temp,L"vc",0,captions));
 assert(GetTempFileNameW(temp,L"vg",0,generation));
 FILE *cfile=_wfopen(captions,L"wb");assert(cfile);
 fputs("10109\tbattle_select_10109_1\t欸嘿嘿。\n10109\tbattle_kill_10109_1\t……你看吧？。\n10916\tbattle_s3_10916_1_1\tbound wearer\n",cfile);
 assert(!fclose(cfile));
 FILE *f=_wfopen(manifest,L"wb");assert(f);
 fputs(LOOK_A "\t10916\t" REV_A "\tVoice_Default_S7_4.assets.bank\n"
       LOOK_B "\t10916\t" REV_B "\tVoice_Default_S7_4.bank\n"
       LOOK_C "\t10916\t" REV_C "\tVoice_Default_S7_4.bank\n"
       LOOK_C "\t10916\t" REV_C "\tVoice_Default_S7_4.assets.bank\n"
       LOOK_D "\t10916\t" REV_A "\tVoice_Default_S7_4.assets.bank\n"
       LOOK_E "\t10915\t" REV_A "\tVoice_Default_S7_4.assets.bank\n",f);
 if(GetEnvironmentVariableW(L"NOAH_TEST_BANK",noah,2048)){
  fputs(LOOK_NOAH "\t10109\t" REV_NOAH "\tVoice_Default_S4_3.assets.bank\n"
        LOOK_STOCK "\t10109\t" REV_STOCK "\tVoice_Default_S4_3.bank\n",f);
 }
 assert(!fclose(f));
 HMODULE lib=LoadLibraryW(libfile);assert(lib);
 Skin a={(void*)1,LOOK_A,(void*)2},b={(void*)1,LOOK_B,(void*)3},c={(void*)1,LOOK_C,(void*)4};
 Skin alias={(void*)1,LOOK_D,(void*)5},regular={0,"stock",(void*)6};
 Skin wrongOwner={(void*)1,LOOK_E,(void*)7};
 Unit ua={1,(void*)10,&a},ub={1,(void*)11,&b},uc={1,(void*)12,&regular};
 VoiceBinding *ba=voice_binding(&a),*bb=voice_binding(&b),*bc=voice_binding(&c);
 assert(ba&&bb&&bc&&!voice_binding(&regular)&&voice_binding(&alias)->library==ba->library);
 assert(!strcmp(private_caption(ba,"battle_s3_10916_1_1"),"bound wearer"));
 assert(!private_caption(ba,"battle_select_10109_1")&&!private_caption(bb,"battle_s3_10916_1_1"));
 assert(voice_open(ba->library,exe,1)&&voice_open(bb->library,exe,1)&&voice_open(bc->library,exe,1));
 void *original=bc->library->system;
 assert(private_voice_owner(&a)==10916&&private_voice_owner(&b)==10916&&!private_voice_owner(&regular));
 int (*lookup)(void*,const char*,void**)=(void*)GetProcAddress(lib,"FMOD_Studio_System_GetEvent");
 void *desc=NULL,*ia=NULL,*ib=NULL,*ic=NULL;
 assert(!lookup(original,"event:/Voice/battle_s3_10916_1_1",&desc));
 assert(!hStudio_EventDescription_CreateInstance(desc,&ia)&&!hStudio_EventDescription_CreateInstance(desc,&ib)&&!hStudio_EventDescription_CreateInstance(desc,&ic));
 int parameterCount=0;VoiceParameterDescription parameter={0};
 assert(!hStudio_EventDescription_GetParameterDescriptionCount(desc,&parameterCount)&&parameterCount>0);
 assert(!hStudio_EventDescription_GetParameterDescriptionByIndex(desc,0,&parameter));
 assert(!strcmp(parameter.name,"volume_Multi")&&parameter.type==0);
 assert(!hStudio_EventInstance_SetParameterByID(ia,parameter.id,0.75f,1));
 uc.worn=&wrongOwner;private_voice_track(&uc,&wrongOwner,ic);
 assert(!privateVoiceEvents[0].original);
 uc.worn=&regular;
 private_voice_track(&ua,&a,ia);private_voice_track(&ua,&a,ia);private_voice_track(&ub,&b,ib);private_voice_track(&uc,&regular,ic);
 assert(privateVoiceEvents[0].original==ia&&privateVoiceEvents[1].original==ib&&!privateVoiceEvents[2].original);
 assert(privateVoiceEvents[0].binding==ba&&privateVoiceEvents[1].binding==bb&&ba->library->system!=bb->library->system);
 assert(!hStudio_EventInstance_Start(ia)&&!hStudio_EventInstance_Start(ib)&&!hStudio_EventInstance_Start(ic));
 for(int i=0;i<100&&(!privateVoiceEvents[0].muted||!privateVoiceEvents[1].muted);i++){private_voice_tick(1);Sleep(5);}
 assert(privateVoiceEvents[0].muted&&privateVoiceEvents[1].muted);
 float copied=-1;
 assert(!hStudio_EventInstance_GetParameterByID(privateVoiceEvents[0].replacement,parameter.id,&copied,NULL));
 assert(copied>0.74f&&copied<0.76f);
 assert(!hStudio_EventInstance_SetParameterByID(ia,parameter.id,0.35f,1));
 private_voice_tick(1);
 assert(!hStudio_EventInstance_GetParameterByID(privateVoiceEvents[0].replacement,parameter.id,&copied,NULL));
 assert(copied>0.34f&&copied<0.36f);
 void *ga=NULL,*gb=NULL,*gc=NULL;int m=-1;
 assert(!hStudio_EventInstance_GetChannelGroup(ia,&ga)&&!hStudio_EventInstance_GetChannelGroup(ib,&gb)&&!hStudio_EventInstance_GetChannelGroup(ic,&gc));
 assert(!hChannelGroup_GetMute(ga,&m)&&m&&!hChannelGroup_GetMute(gb,&m)&&m&&!hChannelGroup_GetMute(gc,&m)&&!m);
 for(int i=0;i<10;i++){private_voice_tick(1);Sleep(5);}
 int state=-1;assert(!hStudio_EventInstance_GetPlaybackState(privateVoiceEvents[0].replacement,&state)&&state==0);
 assert(!hStudio_EventInstance_GetPlaybackState(privateVoiceEvents[1].replacement,&state)&&state==0);
 assert(!hStudio_EventInstance_Stop(privateVoiceEvents[0].replacement,1));
 for(int i=0;i<6;i++){private_voice_tick(1);Sleep(5);}
 assert(privateVoiceEvents[0].muted&&!hChannelGroup_GetMute(ga,&m)&&m);
 ua.worn=&regular;private_voice_tick(1);
 assert(!privateVoiceEvents[0].original&&!hChannelGroup_GetMute(ga,&m)&&!m);
 assert(privateVoiceEvents[1].original&&!hChannelGroup_GetMute(gb,&m)&&m);
 private_voice_tick(0);assert(!hChannelGroup_GetMute(gb,&m)&&!m);
 hStudio_EventInstance_Release(ia);hStudio_EventInstance_Release(ib);hStudio_EventInstance_Release(ic);
 ua.worn=&a;
 test_playback_failure(&ua,&a,desc,0);
 test_playback_failure(&ua,&a,desc,1);
 puts("PASS start and gain failures keep the stock event audible throughout");
 /* A delayed stock voice can still refer to the wearer's identity. Resolve
    the matching donor event instead of letting the original voice leak. */
 wchar_t sourceBank[2300],sourceAssets[2300];
 swprintf(sourceBank,2300,L"%lsVoice_Default_S7_3.bank",stock);
 swprintf(sourceAssets,2300,L"%lsVoice_Default_S7_3.assets.bank",stock);
 assert(voice_load_bank(original,sourceBank)&&voice_load_bank(original,sourceAssets));
 void *sourceDesc=NULL,*sourceEvent=NULL;
 assert(!lookup(original,"event:/Voice/battle_endcommand_10115_1",&sourceDesc));
 assert(!hStudio_EventDescription_CreateInstance(sourceDesc,&sourceEvent));
 /* An author bank can own combat audio before any author line has played.
    A stock-only cue must not leak, and undoing the appearance restores it. */
 assert(private_battle_audio_ready(ba));
 const char *stockPrefix="event:/Voice/";
 void *unmatched=NULL;
 for(size_t i=0;i<sizeof(sr_voice_labels)/sizeof(*sr_voice_labels)&&!unmatched;i++){
  const char *key=sr_voice_labels[i].key;
  char stockPath[256],authorKey[192],authorPath[256];void *unused=NULL;
  if(!battle_voice_remap(key,10115,10916,authorKey,sizeof(authorKey)))continue;
  snprintf(stockPath,sizeof(stockPath),"%s%s",stockPrefix,key);
  snprintf(authorPath,sizeof(authorPath),"%s%s",stockPrefix,authorKey);
  if(!lookup(original,stockPath,&unused)&&lookup(ba->library->system,authorPath,&unused)){
   assert(!lookup(original,stockPath,&unmatched));
  }
 }
 assert(unmatched);
 void *silentOriginal=NULL,*silentGroup=NULL;
 assert(!hStudio_EventDescription_CreateInstance(unmatched,&silentOriginal));
 PrivateVoiceEvent *silenced=private_voice_track(&ua,&a,silentOriginal);
 assert(silenced&&silenced->suppress&&!silenced->replacement);
 assert(!hStudio_EventInstance_Start(silentOriginal));
 for(int i=0;i<100&&!silenced->muted;i++){private_voice_tick(1);Sleep(5);}
 assert(silenced->muted&&!hStudio_EventInstance_GetChannelGroup(silentOriginal,&silentGroup));
 assert(!hChannelGroup_GetMute(silentGroup,&m)&&m);
 ua.worn=&regular;private_voice_tick(1);
 assert(!hChannelGroup_GetMute(silentGroup,&m)&&!m);
 hStudio_EventInstance_Stop(silentOriginal,1);hStudio_EventInstance_Release(silentOriginal);
 puts("PASS a loaded author bank suppresses only the worn appearance's unmapped combat voice");
 ua.worn=&a;PrivateVoiceEvent *mapped=private_voice_track(&ua,&a,sourceEvent);
 assert(mapped&&!strcmp(mapped->key,"battle_endcommand_10916_1"));
 assert(!hStudio_EventInstance_Start(sourceEvent));
 for(int i=0;i<100&&!mapped->muted;i++){private_voice_tick(1);Sleep(5);}
 assert(mapped->muted);private_voice_tick(0);
 hStudio_EventInstance_Stop(sourceEvent,1);hStudio_EventInstance_Release(sourceEvent);
 if(noah[0]){
  Skin nskin={(void*)1,LOOK_NOAH,(void*)20},stockSkin={(void*)1,LOOK_STOCK,(void*)21};
  Unit wearer={1,(void*)22,&nskin};VoiceBinding *n=voice_binding(&nskin),*s=voice_binding(&stockSkin);
  assert(n&&s&&voice_open(n->library,exe,1)&&voice_open(s->library,exe,1));
  const char *keys[]={"battle_select_10109_1","battle_kill_10109_1"};
  const char *texts[]={"欸嘿嘿。","……你看吧？。"};
  for(int i=0;i<2;i++){
   char path[256];snprintf(path,sizeof(path),"event:/Voice/%s",keys[i]);
   void *desc=NULL,*event=NULL;assert(!lookup(s->library->system,path,&desc));
   assert(!hStudio_EventDescription_CreateInstance(desc,&event));
   assert(!strcmp(private_caption(n,keys[i]),texts[i]));
   PrivateVoiceEvent *e=private_voice_track(&wearer,&nskin,event);assert(e&&!strcmp(e->key,keys[i]));
   assert(!hStudio_EventInstance_Start(event));
   for(int tick=0;tick<350&&!e->peakLogged;tick++){private_voice_tick(1);Sleep(5);}
   assert(e->muted&&e->peakLogged);private_voice_tick(0);
   hStudio_EventInstance_Stop(event,1);hStudio_EventInstance_Release(event);
  }
 }
 /* A new binding is picked up without restarting the game, and unchanged
    files do not disrupt an already-loaded library. */
 VoiceFile stockFile={0};strcpy(stockFile.name,"Voice_Default_S7_4.bank");
 VoiceLibrary separate={0};strcpy(separate.revision,REV_B);separate.files=&stockFile;
 assert(voice_open(&separate,exe,1));
 void *activeDesc=NULL,*activeOriginal=NULL,*activeGroup=NULL;
 assert(!lookup(separate.system,"event:/Voice/battle_select_10916_1",&activeDesc));
 assert(!hStudio_EventDescription_CreateInstance(activeDesc,&activeOriginal));
 ua.worn=&a;PrivateVoiceEvent *active=private_voice_track(&ua,&a,activeOriginal);assert(active);
 assert(!hStudio_EventInstance_Start(activeOriginal));
 for(int i=0;i<100&&!active->muted;i++){hStudio_System_Update(separate.system);private_voice_tick(1);Sleep(5);}
 assert(active->muted&&!hStudio_EventInstance_GetChannelGroup(activeOriginal,&activeGroup));
 int activeMute=0;assert(!hChannelGroup_GetMute(activeGroup,&activeMute)&&activeMute);
 FILE *update=_wfopen(generation,L"wb");assert(update);fputs("revision1",update);assert(!fclose(update));
 WIN32_FILE_ATTRIBUTE_DATA generationAttr;assert(GetFileAttributesExW(generation,GetFileExInfoStandard,&generationAttr));
 voice_refresh_poll_at(1000);
 assert(voiceManifestRead&&voiceLibraries);
 voice_refresh_poll_at(1600);assert(voiceManifestRead&&voiceLibraries);
 update=_wfopen(generation,L"wb");assert(update);fputs("revision2",update);assert(!fclose(update));
 HANDLE g=CreateFileW(generation,FILE_WRITE_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);
 assert(g!=INVALID_HANDLE_VALUE&&SetFileTime(g,NULL,NULL,&generationAttr.ftLastWriteTime));CloseHandle(g);
 voice_refresh_poll_at(2200);assert(!voiceManifestRead&&!voiceLibraries);
 assert(!hChannelGroup_GetMute(activeGroup,&activeMute)&&!activeMute);
 hStudio_EventInstance_Stop(activeOriginal,1);hStudio_EventInstance_Release(activeOriginal);
 hStudio_System_Release(separate.system);
 assert(voice_binding(&a)&&voiceManifestRead&&voiceLibraries);
 update=_wfopen(manifest,L"ab");assert(update);fputs("\n",update);assert(!fclose(update));
 voice_refresh_poll_at(2800);assert(!voiceManifestRead&&!voiceLibraries);
 private_voice_close();DeleteFileW(manifest);DeleteFileW(captions);DeleteFileW(generation);
 puts("PASS real FMOD three simultaneous units, two private revisions, shared bank, event-only, assets-only, paired banks and stock voice restoration");
}
