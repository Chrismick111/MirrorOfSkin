/* Each imported revision owns a private Studio mixer. Multiple wearers can
   share its bank data, while each voice has an independent event instance. */
typedef struct {int samples;float peak[32],rms[32];short channels;} VoiceMeter;
#define VOICE_STUDIO_API(X) \
 X(Studio_System_GetCoreSystem,(void*,void**)) \
 X(Studio_System_Create,(void**,unsigned)) X(Studio_System_Initialize,(void*,int,unsigned,unsigned,void*)) \
 X(Studio_System_LoadBankFile,(void*,const char*,unsigned,void**)) X(Studio_System_Update,(void*)) \
 X(Studio_System_GetEventByID,(void*,const GUID*,void**)) X(Studio_System_Release,(void*)) \
 X(Studio_EventDescription_GetID,(void*,GUID*)) X(Studio_EventDescription_GetPath,(void*,char*,int,int*)) \
 X(Studio_EventDescription_CreateInstance,(void*,void**)) X(Studio_EventInstance_GetDescription,(void*,void**)) \
 X(Studio_EventInstance_GetPlaybackState,(void*,int*)) X(Studio_EventInstance_GetTimelinePosition,(void*,int*)) \
 X(Studio_EventInstance_SetTimelinePosition,(void*,int)) X(Studio_EventInstance_GetChannelGroup,(void*,void**)) \
 X(Studio_EventInstance_SetVolume,(void*,float)) X(Studio_EventInstance_SetPaused,(void*,int)) \
 X(Studio_EventInstance_SetPitch,(void*,float)) X(Studio_EventInstance_GetPitch,(void*,float*,float*)) \
 X(Studio_EventInstance_Start,(void*)) X(Studio_EventInstance_Stop,(void*,int)) X(Studio_EventInstance_Release,(void*)) \
 X(Studio_EventInstance_GetPaused,(void*,int*))
#define VOICE_CORE_API(X) X(ChannelGroup_GetParentGroup,(void*,void**)) X(ChannelGroup_GetMute,(void*,int*)) \
 X(ChannelGroup_SetMute,(void*,int)) X(ChannelGroup_GetVolume,(void*,float*)) X(ChannelGroup_GetPaused,(void*,int*)) \
 X(ChannelGroup_GetDSP,(void*,int,void**)) X(DSP_SetMeteringEnabled,(void*,int,int)) X(DSP_GetMeteringInfo,(void*,VoiceMeter*,VoiceMeter*)) \
 X(ChannelGroup_GetSystemObject,(void*,void**)) X(System_GetOutput,(void*,int*)) X(System_GetDriver,(void*,int*)) X(System_GetNumDrivers,(void*,int*)) \
 X(System_GetDriverInfo,(void*,int,char*,int,GUID*,int*,int*,int*)) X(System_SetDriver,(void*,int))
#define H_DECL(n,args) static int (*h##n)args;
VOICE_STUDIO_API(H_DECL)
VOICE_CORE_API(H_DECL)
#undef H_DECL

typedef struct VoiceFile {
 struct VoiceFile *next;
 char name[256];
} VoiceFile;
typedef struct VoiceCaption {
 struct VoiceCaption *next;
 unsigned owner;
 char key[192],text[];
} VoiceCaption;
typedef struct VoiceLibrary {
 struct VoiceLibrary *next;
 char revision[65];
 VoiceFile *files;
 VoiceCaption *captions;
 int captionsRead;
 void *system;
 DWORD attempt;
} VoiceLibrary;
typedef struct VoiceBinding {
 struct VoiceBinding *next;
 char look[64];
 unsigned owner;
 VoiceLibrary *library;
} VoiceBinding;
static VoiceBinding *voiceBindings;
static VoiceLibrary *voiceLibraries;
static int voiceManifestRead;
static void voice_free_manifest(void){
 while(voiceBindings){
  VoiceBinding *b=voiceBindings;voiceBindings=b->next;free(b);
 }
 while(voiceLibraries){
  VoiceLibrary *l=voiceLibraries;voiceLibraries=l->next;
  if(l->system)hStudio_System_Release(l->system);
  while(l->captions){VoiceCaption *c=l->captions;l->captions=c->next;free(c);}
  while(l->files){VoiceFile *f=l->files;l->files=f->next;free(f);}
  free(l);
 }
}
static VoiceFile *voice_file(VoiceLibrary *l,const char *name){
 for(VoiceFile *f=l->files;f;f=f->next)if(!_stricmp(f->name,name))return f;
 return NULL;
}
static int voice_register_line(char *line){
 char *field[4]={line};
 for(int i=1;i<4;i++){
  char *tab=strchr(field[i-1],'\t');if(!tab)return 0;
  *tab=0;field[i]=tab+1;
 }
 const char *hex="0123456789abcdef",*digits="0123456789";
 char *look=field[0],*owner=field[1],*rev=field[2],*name=field[3];
 if(strlen(look)!=30||strncmp(look,"WBImp_",6)||strspn(look+6,hex)!=24||
    strlen(owner)<3||strlen(owner)>8||*owner=='0'||strspn(owner,digits)!=strlen(owner)||
    strlen(rev)!=64||strspn(rev,hex)!=64||strlen(name)>=246)return 0;
 size_t base=strspn(name,"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-");
 if(!base||(base==6&&!_strnicmp(name,"Master",6))||
    (_stricmp(name+base,".assets.bank")&&_stricmp(name+base,".bank")))return 0;
 VoiceLibrary *lib=voiceLibraries;
 while(lib&&strcmp(lib->revision,rev))lib=lib->next;
 if(!lib){
  lib=calloc(1,sizeof(*lib));if(!lib)return 0;
  strcpy(lib->revision,rev);lib->next=voiceLibraries;voiceLibraries=lib;
 }
 unsigned id=(unsigned)strtoul(owner,NULL,10);
 VoiceBinding *b=voiceBindings;
 while(b&&strcmp(b->look,look))b=b->next;
 if(b&&(b->library!=lib||b->owner!=id))return 0;
 if(!b){
  b=calloc(1,sizeof(*b));if(!b)return 0;
  strcpy(b->look,look);b->owner=id;b->library=lib;b->next=voiceBindings;voiceBindings=b;
 }
 if(!voice_file(lib,name)){
  VoiceFile *f=calloc(1,sizeof(*f));if(!f)return 0;
  strcpy(f->name,name);f->next=lib->files;lib->files=f;
 }
 return 1;
}
static VoiceBinding *voice_binding(const Skin *skin){
 if(!skin||!skin->imported)return NULL;
 if(!voiceManifestRead){
  voiceManifestRead=1;
  wchar_t path[2048];
  if(!addon_file_path(path,2048,L"Assets\\ImportedVoices\\bindings.tsv"))return NULL;
  FILE *f=_wfopen(path,L"rb");if(!f)return NULL;
  char line[512];int valid=1;
  while(fgets(line,sizeof(line),f)){
   char *nl=strchr(line,'\n');if(!nl){valid=0;break;}*nl=0;
   if(nl>line&&nl[-1]=='\r')nl[-1]=0;
   if(!voice_register_line(line)){valid=0;break;}
  }
  if(!valid||ferror(f)){voice_free_manifest();bootlog("Imported voice: invalid bindings.tsv");}
  fclose(f);
 }
 for(VoiceBinding *b=voiceBindings;b;b=b->next)if(!strcmp(b->look,skin->look))return b;
 return NULL;
}
static int voice_load_bank(void *system,const wchar_t *path){
 char utf8[8192];void *bank=NULL;
 return WideCharToMultiByte(CP_UTF8,0,path,-1,utf8,sizeof(utf8),NULL,NULL)&&
        !hStudio_System_LoadBankFile(system,utf8,0,&bank);
}
static const char *private_caption(VoiceBinding *binding,const char *key){
 if(!binding||!key)return NULL;
 VoiceLibrary *lib=binding->library;
 if(!lib->captionsRead){
  lib->captionsRead=1;
  wchar_t relative[128],path[2048];
  swprintf(relative,128,L"Assets\\ImportedVoices\\%hs\\bubbles.tsv",lib->revision);
  FILE *f=addon_file_path(path,2048,relative)?_wfopen(path,L"rb"):NULL;
  if(f){
   char line[4352];
   while(fgets(line,sizeof(line),f)){
    char *lf=strchr(line,'\n');if(!lf)break;
    *lf=0;
    char *event=strchr(line,'\t');if(!event)continue;*event++=0;
    char *text=strchr(event,'\t');if(!text)continue;*text++=0;
    size_t n=strlen(text),k=strlen(event),digits=strspn(line,"0123456789");
    if(digits<3||digits>8||line[digits]||*line=='0'||!k||k>=192||!n||n>4095)continue;
    if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,(int)n,NULL,0))continue;
    VoiceCaption *c=malloc(sizeof(*c)+n+1);if(!c)break;
    c->owner=(unsigned)strtoul(line,NULL,10);strcpy(c->key,event);memcpy(c->text,text,n+1);
    c->next=lib->captions;lib->captions=c;
   }
   fclose(f);
  }
 }
 for(VoiceCaption *c=lib->captions;c;c=c->next)
  if(c->owner==binding->owner&&!strcmp(c->key,key))return c->text;
 return NULL;
}
static int voice_open(VoiceLibrary *library,const wchar_t *gameExe,int silentOutput){
 HMODULE lib=GetModuleHandleW(L"fmodstudio.dll");if(!lib)return 0;
#define H_BIND(n,args) h##n=(void*)GetProcAddress(lib,"FMOD_" #n);if(!h##n)return 0;
 VOICE_STUDIO_API(H_BIND)
#undef H_BIND
#define H_BIND(n,args) h##n=(void*)GetProcAddress(lib,"FMOD5_" #n);if(!h##n)return 0;
 VOICE_CORE_API(H_BIND)
#undef H_BIND
 wchar_t folder[2048];if(wcslen(gameExe)>=1900)return 0;
 wcscpy(folder,gameExe);wchar_t *slash=wcsrchr(folder,L'\\');if(!slash)return 0;
 *slash=0;wcscat(folder,L"\\LimbusCompany_Data\\StreamingAssets\\Assets\\Sound\\FMODBuilds\\Desktop\\");
 void *sys=NULL;if(hStudio_System_Create(&sys,0x00020200))return 0;
 if(silentOutput){
  void *core=NULL;
  int (*getCore)(void*,void**)=(void*)GetProcAddress(lib,"FMOD_Studio_System_GetCoreSystem");
  int (*setOutput)(void*,int)=(void*)GetProcAddress(lib,"FMOD5_System_SetOutput");
  if(!getCore||!setOutput||getCore(sys,&core)||setOutput(core,2))goto fail;
 }
 if(hStudio_System_Initialize(sys,64,0,0,NULL))goto fail;

 wchar_t path[2600];
 const wchar_t *masters[]={L"Master.bank",L"Master.strings.bank"};
 for(int i=0;i<2;i++){
  swprintf(path,2600,L"%ls%ls",folder,masters[i]);
  if(!voice_load_bank(sys,path))goto fail;
 }
 for(VoiceFile *f=library->files;f;f=f->next){
  char companion[256];
  const char *ext=strchr(f->name,'.');int asset=!_stricmp(ext,".assets.bank");
  snprintf(companion,sizeof(companion),"%.*s%s",(int)(ext-f->name),f->name,asset?".bank":".assets.bank");
  if(!voice_file(library,companion)){
   swprintf(path,2600,L"%ls%hs",folder,companion);
   /* Standalone event banks may contain their own samples. An assets-only
      replacement always needs the game's event definitions. */
   if((asset||GetFileAttributesW(path)!=INVALID_FILE_ATTRIBUTES)&&!voice_load_bank(sys,path))goto fail;
  }
  wchar_t relative[512];
  swprintf(relative,512,L"Assets\\ImportedVoices\\%hs\\%hs",library->revision,f->name);
  if(!addon_file_path(path,2600,relative)||!voice_load_bank(sys,path))goto fail;
 }
 library->system=sys;return 1;
fail:hStudio_System_Release(sys);return 0;
}
static int voice_ready(VoiceLibrary *lib){
 if(lib->system)return 1;
 DWORD now=GetTickCount();if(lib->attempt&&(DWORD)(now-lib->attempt)<15000)return 0;
 lib->attempt=now;wchar_t game[2048];DWORD n=GetModuleFileNameW(NULL,game,2048);
 int ok=n&&n<2048&&voice_open(lib,game,0);
 char message[160];snprintf(message,sizeof(message),"Imported voice: revision %.64s %s",lib->revision,ok?"ready":"unavailable");
 bootlog(message);return ok;
}
static unsigned private_voice_owner(const Skin *skin){
 VoiceBinding *b=voice_binding(skin);return b?b->owner:0;
}
typedef struct {
 Unit *u;void *view,*app,*original,*replacement,*group;
 VoiceBinding *binding;DWORD queued;int muted,started,captionHandled,captionBlocked;
 char key[192];void *meter;int peakLogged;
} PrivateVoiceEvent;
static PrivateVoiceEvent privateVoiceEvents[32];
static void private_playing_caption(PrivateVoiceEvent *e);
/* The game can route audio to a non-default Windows device. Mirror its endpoint
   before suppressing the game's original instance. Null-output tests have no drivers. */
static int private_voice_device(void *system,void *group){
 void *game=NULL,*local=NULL;int source=0,current=0,count=0;
 if(hChannelGroup_GetSystemObject(group,&game)||hStudio_System_GetCoreSystem(system,&local)||
    hSystem_GetNumDrivers(local,&count))return 0;
 if(!count){
  int a=-1,b=-1;return !hSystem_GetOutput(game,&a)&&!hSystem_GetOutput(local,&b)&&a==b;
 }
 GUID wanted,active;
 if(hSystem_GetDriver(game,&source)||hSystem_GetDriver(local,&current)||
    hSystem_GetDriverInfo(game,source,NULL,0,&wanted,NULL,NULL,NULL)||
    hSystem_GetDriverInfo(local,current,NULL,0,&active,NULL,NULL,NULL))return 0;
 if(!memcmp(&wanted,&active,sizeof(GUID)))return 1;
 for(int i=0;i<count;i++)
  if(!hSystem_GetDriverInfo(local,i,NULL,0,&active,NULL,NULL,NULL)&&!memcmp(&wanted,&active,sizeof(GUID)))
   return hSystem_SetDriver(local,i)==0;
 return 0;
}
static void private_voice_end(PrivateVoiceEvent *e){
 if(e->muted){
  if(!e->peakLogged){
   char msg[420];snprintf(msg,sizeof(msg),"Imported voice: view=%p owner=%u key=%s ended, no nonzero event output measured",e->view,e->binding->owner,e->key);
   bootlog(msg);
  }
  void *group=NULL;
  if(!hStudio_EventInstance_GetChannelGroup(e->original,&group)&&group==e->group)hChannelGroup_SetMute(group,0);
 }
 if(e->replacement){hStudio_EventInstance_Stop(e->replacement,1);hStudio_EventInstance_Release(e->replacement);}
 memset(e,0,sizeof(*e));
}
static PrivateVoiceEvent *private_voice_track(Unit *u,Skin *skin,void *original){
 VoiceBinding *b=voice_binding(skin);
 if(!u||!b||!original||!voice_ready(b->library))return NULL;
 void *desc=NULL,*local=NULL;GUID guid;char path[256],token[24];int used=0;
 snprintf(token,sizeof(token),"_%u",b->owner);
 if(hStudio_EventInstance_GetDescription(original,&desc)||hStudio_EventDescription_GetPath(desc,path,sizeof(path),&used)||
    strncmp(path,"event:/Voice/",13))return NULL;
 const char *match=strstr(path+13,token);
 if(!(match&&(match[strlen(token)]=='_'||!match[strlen(token)]))&&sr_voice_member_index(b->owner,path+13)<0)return NULL;
 if(hStudio_EventDescription_GetID(desc,&guid)||hStudio_System_GetEventByID(b->library->system,&guid,&local))return NULL;
 PrivateVoiceEvent *slot=NULL;
 for(unsigned i=0;i<32;i++){
  PrivateVoiceEvent *e=&privateVoiceEvents[i];
  if(e->original==original)return e->u==u&&e->app==skin->app&&e->binding==b?e:NULL;
  if(!slot&&!e->original)slot=e;
 }
 void *instance=NULL;if(!slot||hStudio_EventDescription_CreateInstance(local,&instance))return NULL;
 *slot=(PrivateVoiceEvent){.u=u,.view=u->view,.app=skin->app,.original=original,.replacement=instance,.binding=b,.queued=GetTickCount()};
 const char *key=strrchr(path,'/')+1;
 if(strlen(key)<sizeof(slot->key))strcpy(slot->key,key);
 return slot;
}
static void private_voice_step(PrivateVoiceEvent *e){
 Unit *u=e->u;Skin *skin=u->used&&u->view==e->view?voice_worn_skin(u):NULL;
 int state=0;void *group=NULL;
 if(voice_binding(skin)!=e->binding||skin->app!=e->app||hStudio_EventInstance_GetPlaybackState(e->original,&state)){
  private_voice_end(e);return;
 }
 if(state==2||state==4){ /* STOPPED before first start, or already stopping */
  if(e->muted||state==4||(DWORD)(GetTickCount()-e->queued)>2000)private_voice_end(e);
  return;
 }
 if(hStudio_EventInstance_GetChannelGroup(e->original,&group)||!group)return;
 int pause=0,ownMute=0;float gain=1,pitch=1;
 hStudio_EventInstance_GetPaused(e->original,&pause);
 if(hChannelGroup_GetMute(group,&ownMute))return;
 if(!e->muted&&ownMute){if(e->started)private_voice_end(e);return;}
 if(e->muted&&group!=e->group){private_voice_end(e);return;}
 for(void *g=group;g;){
  float volume=1;int mute=0,paused=0;void *parent=NULL;
  if(!hChannelGroup_GetVolume(g,&volume))gain*=volume;
  if(g!=group&&!hChannelGroup_GetMute(g,&mute)&&mute)gain=0;
  if(!hChannelGroup_GetPaused(g,&paused)&&paused)pause=1;
  if(hChannelGroup_GetParentGroup(g,&parent)||parent==g)break;
  g=parent;
 }
 if(hStudio_EventInstance_SetVolume(e->replacement,e->muted?gain:0)){private_voice_end(e);return;}
 if(!hStudio_EventInstance_GetPitch(e->original,NULL,&pitch)&&pitch>0)hStudio_EventInstance_SetPitch(e->replacement,pitch);
 hStudio_EventInstance_SetPaused(e->replacement,pause);
 if(!e->started){
  if(!private_voice_device(e->binding->library->system,group)){
   bootlog("Imported voice: output device unavailable, retaining original");private_voice_end(e);return;
  }
  int pos=0;if(!hStudio_EventInstance_GetTimelinePosition(e->original,&pos)&&pos>0)hStudio_EventInstance_SetTimelinePosition(e->replacement,pos);
  if(hStudio_EventInstance_Start(e->replacement)){private_voice_end(e);return;}
  e->started=1;return;
 }
 /* A shorter replacement can finish before the stock line. Keep that line
    muted until its own stop or a costume change. */
 if(e->muted){
  if(!e->peakLogged&&e->meter){
   VoiceMeter meter={0};float peak=0;
   if(!hDSP_GetMeteringInfo(e->meter,NULL,&meter)){
    for(int i=0;i<meter.channels&&i<32;i++)if(meter.peak[i]>peak)peak=meter.peak[i];
    if(peak>0.00001f){
     char msg[420];snprintf(msg,sizeof(msg),"Imported voice: view=%p owner=%u key=%s private event output peak=%.5f",e->view,e->binding->owner,e->key,peak);
     bootlog(msg);e->peakLogged=1;
    }
   }
  }
  return;
 }
 int replacementState;
 if(hStudio_EventInstance_GetPlaybackState(e->replacement,&replacementState)||replacementState==2||replacementState==4){
  private_voice_end(e);return;
 }
 if(replacementState==0){
  if(hChannelGroup_SetMute(group,1)){private_voice_end(e);return;}
  e->group=group;e->muted=1;
  if(hStudio_EventInstance_SetVolume(e->replacement,gain)){private_voice_end(e);return;}
  void *privateGroup=NULL,*meter=NULL;
  if(!hStudio_EventInstance_GetChannelGroup(e->replacement,&privateGroup)&&privateGroup&&
     !hChannelGroup_GetDSP(privateGroup,-2,&meter)&&!hDSP_SetMeteringEnabled(meter,0,1))e->meter=meter;
  char message[480];snprintf(message,sizeof(message),"Imported voice: %s view=%p owner=%u revision=%.12s key=%s playing gain=%.4f paused=%d",e->binding->look,e->view,e->binding->owner,e->binding->library->revision,e->key,gain,pause);
  bootlog(message);
  private_playing_caption(e);
 }
}
static void private_voice_tick(int active){
 if(!voiceLibraries)return;
 for(unsigned i=0;i<32;i++)if(privateVoiceEvents[i].original){
  if(active)private_voice_step(&privateVoiceEvents[i]);else private_voice_end(&privateVoiceEvents[i]);
 }
 for(VoiceLibrary *l=voiceLibraries;l;l=l->next)if(l->system)hStudio_System_Update(l->system);
}
static void private_voice_close(void){
 private_voice_tick(0);voice_free_manifest();voiceManifestRead=0;
}
