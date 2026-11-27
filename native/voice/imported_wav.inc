#include "imported_wav_rows.h"
#include "battle_voice_key.h"

typedef struct {
 wchar_t path[2048];
 char text[4096], key[192];
 unsigned owner;
 int rank;
} ImportedWavAsset;

static wchar_t *imported_wav_manifest(const Skin *skin,wchar_t path[2048]){
 if(!skin||!skin->imported||!imported_look(skin->look))return NULL;
 LocalArtForm *form=cached_art_form(skin->look);
 if(!form||!imported_bundle_path_mode(skin->look,form->file,NULL,path,2048,0))return NULL;
 wchar_t *slash=wcsrchr(path,L'\\');if(!slash)return NULL;
 wchar_t *name=slash+1;
 size_t cap=2048-(size_t)(name-path);
 if(cap<128||swprintf(name,cap,L"%hs.voice.tsv",skin->look)<=0||!managed_bundle_file(path))return NULL;
 return name;
}

static int imported_wav_read(const Skin *skin,unsigned source,const char *key,int caption,ImportedWavAsset *asset){
 wchar_t path[2048];
 if(strncmp(key,"battle",6))return 0;
 wchar_t *name=imported_wav_manifest(skin,path);
 if(!name)return 0;
 size_t cap=2048-(size_t)(name-path);
 FILE *f=_wfopen(path,L"rb");
 if(!f)return 0;
 char line[4608],wav[69]={0};int best=0,count=0,valid=1;
 unsigned total=0;
 while(fgets(line,sizeof(line),f)){
  char *lf=strchr(line,'\n');
  if(!lf||(total+=(unsigned)(lf-line+1))>2*1024*1024){valid=0;break;}
  *lf=0;if(lf>line&&lf[-1]=='\r')lf[-1]=0;
  ImportedWavRow row;
  if(!imported_wav_row(line,&row))continue;
  int rank=imported_wav_rank(&row,source,key,caption);
  if(!rank||rank<best)continue;
  if(rank==best){count++;continue;}
  best=rank;count=1;
  asset->owner=row.owner;asset->rank=rank;
  strcpy(asset->key,row.key);
  if(caption)strcpy(asset->text,row.caption);
  else strcpy(wav,row.wav);
 }
 valid=valid&&!ferror(f)&&best&&count==1;
 fclose(f);
 if(!valid||caption)return valid;
 if(swprintf(name,cap,L"%hs",wav)<=0||!managed_bundle_file(path))return 0;
 wcscpy(asset->path,path);
 return 1;
}

#define WAV_STUDIO_API(X) \
 X(EventInstance_GetDescription,(void*,void**)) X(EventDescription_GetPath,(void*,char*,int,int*)) \
 X(EventInstance_GetPlaybackState,(void*,int*)) X(EventInstance_GetChannelGroup,(void*,void**)) \
 X(EventInstance_GetPaused,(void*,int*)) X(EventInstance_GetPitch,(void*,float*,float*)) \
 X(EventInstance_GetTimelinePosition,(void*,int*)) X(EventDescription_GetLength,(void*,int*))
#define WAV_CORE_API(X) \
 X(ChannelGroup_GetSystemObject,(void*,void**)) X(ChannelGroup_GetParentGroup,(void*,void**)) \
 X(ChannelGroup_GetVolume,(void*,float*)) X(ChannelGroup_GetPaused,(void*,int*)) \
 X(ChannelGroup_GetMute,(void*,int*)) X(ChannelGroup_SetMute,(void*,int)) \
 X(System_CreateSound,(void*,const char*,unsigned,void*,void**)) X(Sound_Release,(void*)) \
 X(Sound_GetLength,(void*,unsigned*,unsigned)) X(System_PlaySound,(void*,void*,void*,int,void**)) \
 X(Channel_SetVolume,(void*,float)) X(Channel_SetPaused,(void*,int)) X(Channel_SetPitch,(void*,float)) \
 X(Channel_IsPlaying,(void*,int*)) X(Channel_IsVirtual,(void*,int*)) X(Channel_Stop,(void*)) \
 X(Channel_GetCurrentSound,(void*,void**)) X(Channel_SetPosition,(void*,unsigned,unsigned))
#define W_DECL(n,args) static int (*w##n)args;
WAV_STUDIO_API(W_DECL)
WAV_CORE_API(W_DECL)
#undef W_DECL

static int imported_wav_api(void){
 static int ready;
 if(ready)return 1;
 HMODULE module=GetModuleHandleW(L"fmodstudio.dll");
 if(!module)return 0;
#define W_BIND(n,args) w##n=(void*)GetProcAddress(module,"FMOD_Studio_" #n);if(!w##n)return 0;
 WAV_STUDIO_API(W_BIND)
#undef W_BIND
#define W_BIND(n,args) w##n=(void*)GetProcAddress(module,"FMOD5_" #n);if(!w##n)return 0;
 WAV_CORE_API(W_BIND)
#undef W_BIND
 ready=1;return 1;
}
#undef WAV_STUDIO_API
#undef WAV_CORE_API

typedef struct {
 Unit *unit;
 void *view,*app,*original,*group,*sound,*channel;
 DWORD queued;
 int muted,captionBlocked,captionHandled,captionFallback,captionAttempted;
 int failed,tail,originalLength,originalPosition,suppress;
 ImportedWavAsset caption;
 char key[192];
 wchar_t path[2048];
} ImportedWavEvent;
static ImportedWavEvent importedWavEvents[32];
static _Thread_local ImportedWavEvent *registeringWav;
static void imported_wav_playing_caption(ImportedWavEvent *event);
static int imported_wav_header(wchar_t *path);

typedef struct {
 wchar_t path[2048];
 FILETIME modified;
 DWORD size;
 void *system;
} ImportedWavProof;
static ImportedWavProof importedWavProofs[32];
static unsigned importedWavProofNext;

typedef struct {
 wchar_t manifest[2048],voice[2048];
 FILETIME modified;
 DWORD size;
 unsigned source;
 int caption;
} ImportedWavChannelProof;
static ImportedWavChannelProof importedWavChannelProofs[32];
static unsigned importedWavChannelProofNext;

static int imported_wav_playable(ImportedWavAsset *asset,void *system){
 WIN32_FILE_ATTRIBUTE_DATA attr;
 if(!system||!GetFileAttributesExW(asset->path,GetFileExInfoStandard,&attr)||
    attr.nFileSizeHigh||(attr.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)))return 0;
 for(size_t i=0;i<sizeof(importedWavProofs)/sizeof(importedWavProofs[0]);i++){
  ImportedWavProof *proof=&importedWavProofs[i];
  if(proof->system==system&&proof->size==attr.nFileSizeLow&&
     !CompareFileTime(&proof->modified,&attr.ftLastWriteTime)&&!wcscmp(proof->path,asset->path))return 1;
 }
 char utf8[8192];void *sound=NULL;unsigned duration=0;
 if(!imported_wav_header(asset->path)||
    !WideCharToMultiByte(CP_UTF8,0,asset->path,-1,utf8,sizeof(utf8),NULL,NULL)||
    wSystem_CreateSound(system,utf8,0,NULL,&sound)||!sound)return 0;
 int playable=!wSound_GetLength(sound,&duration,1)&&duration;
 wSound_Release(sound);
 if(playable){
  ImportedWavProof *proof=&importedWavProofs[importedWavProofNext++%32];
  wcscpy(proof->path,asset->path);proof->system=system;proof->modified=attr.ftLastWriteTime;proof->size=attr.nFileSizeLow;
 }
 return playable;
}

typedef struct {
 char sourceKey[192],wav[69];
 int rank;
} ImportedWavCandidate;

static int imported_wav_compare_candidates(const void *a,const void *b){
 const ImportedWavCandidate *first=a,*second=b;
 int order=strcmp(first->sourceKey,second->sourceKey);
 return order?order:second->rank-first->rank;
}

/* Group exact variants by their projected speaker key. Exact source matches
   win, as in playback. A broader caption cannot outrank an exact variant. */
static int imported_wav_has_channel(const Skin *skin,unsigned source,int caption,void *system){
 wchar_t path[2048];
 WIN32_FILE_ATTRIBUTE_DATA attr;
 wchar_t *name=source?imported_wav_manifest(skin,path):NULL;
 if(!name||!GetFileAttributesExW(path,GetFileExInfoStandard,&attr)||attr.nFileSizeHigh||
    !attr.nFileSizeLow||attr.nFileSizeLow>2*1024*1024)return 0;
 ImportedWavAsset asset={0};
 for(size_t i=0;i<sizeof(importedWavChannelProofs)/sizeof(importedWavChannelProofs[0]);i++){
  ImportedWavChannelProof *proof=&importedWavChannelProofs[i];
  if(proof->source!=source||proof->caption!=caption||proof->size!=attr.nFileSizeLow||
     CompareFileTime(&proof->modified,&attr.ftLastWriteTime)||wcscmp(proof->manifest,path))continue;
  if(caption)return 1;
  wcscpy(asset.path,proof->voice);
  if(system?imported_wav_playable(&asset,system):imported_wav_header(asset.path))return 1;
 }
 FILE *f=_wfopen(path,L"rb");if(!f)return 0;
 char line[4608];unsigned total=0;int valid=1,ready=0;
 size_t count=0,capacity=0;
 ImportedWavCandidate *candidates=NULL;
 while(fgets(line,sizeof(line),f)){
  char *lf=strchr(line,'\n');
  if(!lf||(total+=(unsigned)(lf-line+1))>2*1024*1024){valid=0;break;}
  *lf=0;if(lf>line&&lf[-1]=='\r')lf[-1]=0;
  ImportedWavRow row;ImportedWavCandidate candidate={0};
  if(!imported_wav_row(line,&row)||!(caption?*row.caption:*row.wav)||
     !battle_voice_remap(row.key,row.owner,source,candidate.sourceKey,sizeof(candidate.sourceKey)))continue;
  candidate.rank=imported_wav_rank(&row,source,candidate.sourceKey,caption);
  if(candidate.rank<3)continue;
  strcpy(candidate.wav,row.wav);
  if(count==capacity){
   capacity=capacity?capacity*2:32;
   ImportedWavCandidate *grown=realloc(candidates,capacity*sizeof(*grown));
   if(!grown){valid=0;break;}
   candidates=grown;
  }
  candidates[count++]=candidate;
 }
 valid=valid&&!ferror(f);
 fclose(f);
 if(valid&&count){
  size_t base=(size_t)(name-path);
  qsort(candidates,count,sizeof(*candidates),imported_wav_compare_candidates);
  for(size_t i=0,j;i<count;i=j){
   for(j=i+1;j<count&&!strcmp(candidates[i].sourceKey,candidates[j].sourceKey);j++){}
   if(j>i+1&&candidates[i].rank==candidates[i+1].rank)continue;
   if(caption){ready=1;break;}
   memcpy(asset.path,path,base*sizeof(*path));
   if(swprintf(asset.path+base,2048-base,L"%hs",candidates[i].wav)>0&&
      (system?imported_wav_playable(&asset,system):imported_wav_header(asset.path))){ready=1;break;}
  }
 }
 free(candidates);
 if(ready){
  ImportedWavChannelProof *proof=&importedWavChannelProofs[importedWavChannelProofNext++%32];
  wcscpy(proof->manifest,path);wcscpy(proof->voice,asset.path);
  proof->modified=attr.ftLastWriteTime;proof->size=attr.nFileSizeLow;proof->source=source;proof->caption=caption;
 }
 return ready;
}

static void imported_wav_release(ImportedWavEvent *event){
 void *sound=NULL;
 if(event->channel&&!wChannel_GetCurrentSound(event->channel,&sound)&&sound==event->sound)wChannel_Stop(event->channel);
 if(event->sound)wSound_Release(event->sound);
 event->channel=event->sound=NULL;
}

static void imported_wav_end(ImportedWavEvent *event){
 void *group=NULL;
 if(event->muted&&!wEventInstance_GetChannelGroup(event->original,&group)&&group==event->group)
  wChannelGroup_SetMute(group,0);
 imported_wav_release(event);
 memset(event,0,sizeof(*event));
}

static void imported_wav_suppress(ImportedWavEvent *event,Skin *skin){
 void *group=NULL,*system=NULL;int muted=0;
 if(wEventInstance_GetChannelGroup(event->original,&group)||!group||
    wChannelGroup_GetMute(group,&muted)||muted||
    wChannelGroup_GetSystemObject(group,&system)||!system)return;
 if(!imported_wav_has_channel(skin,voice_source_id(event->unit),0,system)){
  event->suppress=0;return;
 }
 if(!wChannelGroup_SetMute(group,1)){event->group=group;event->muted=1;}
}

static ImportedWavEvent *imported_wav_track(Unit *unit,Skin *skin,void *original){
 if(!unit||!skin||!skin->imported||!original||!imported_wav_api())return NULL;
 ImportedWavEvent *slot=NULL;
 for(int i=0;i<32;i++){
  ImportedWavEvent *event=&importedWavEvents[i];
  if(event->original==original&&event->tail)imported_wav_end(event);
  if(event->original==original)
   return event->unit==unit&&event->view==unit->view&&event->app==skin->app?event:NULL;
  if(!slot&&!event->original)slot=event;
 }
 void *desc=NULL;char path[256];int length=0;
 if(!slot||wEventInstance_GetDescription(original,&desc)||
    wEventDescription_GetPath(desc,path,sizeof(path),&length)||
    strncmp(path,"event:/Voice/battle",19)||strlen(path+13)>=sizeof(slot->key))return NULL;
 const char *key=path+13;
 ImportedWavAsset wav={0},caption={0};
 int hasWav=imported_wav_read(skin,voice_source_id(unit),key,0,&wav);
 int hasCaption=imported_wav_read(skin,voice_source_id(unit),key,1,&caption);
 int suppress=!hasWav&&!*wav.key&&battle_voice_owner_field(key,voice_source_id(unit))&&
              imported_wav_has_channel(skin,voice_source_id(unit),0,NULL);
 if(!hasWav&&!hasCaption&&!suppress)return NULL;
 *slot=(ImportedWavEvent){.unit=unit,.view=unit->view,.app=skin->app,.original=original,.queued=GetTickCount()};
 strcpy(slot->key,key);
 if(hasCaption)slot->caption=caption;
 if(wEventDescription_GetLength(desc,&slot->originalLength))slot->originalLength=0;
 if(hasWav)wcscpy(slot->path,wav.path);
 slot->suppress=suppress;
 return slot;
}

static int imported_wav_header(wchar_t *path){
 if(!managed_bundle_file(path))return 0;
 HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,NULL,
                         OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(file==INVALID_HANDLE_VALUE)return 0;
 BY_HANDLE_FILE_INFORMATION info;
 char bytes[12];DWORD n=0;
 int valid=GetFileInformationByHandle(file,&info)&&
   !(info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))&&
   !info.nFileSizeHigh&&info.nFileSizeLow>=44&&info.nFileSizeLow<=16*1024*1024&&
   ReadFile(file,bytes,sizeof(bytes),&n,NULL)&&n==sizeof(bytes)&&
   !memcmp(bytes,"RIFF",4)&&!memcmp(bytes+8,"WAVE",4);
 CloseHandle(file);
 return valid;
}

/* A sibling channel gets the same voice bus, device, and parent controls.
   Only the registered original event's own group is muted. */
static int imported_wav_start(ImportedWavEvent *event,void *group,float volume,float pitch){
 void *system=NULL,*parent=NULL;
 char utf8[8192];unsigned duration=0;int playing=0,virtual=0,position=0;
 if(wChannelGroup_GetSystemObject(group,&system)||!system||
    wChannelGroup_GetParentGroup(group,&parent)||!parent||parent==group||
    !imported_wav_header(event->path)||
    !WideCharToMultiByte(CP_UTF8,0,event->path,-1,utf8,sizeof(utf8),NULL,NULL)||
    wSystem_CreateSound(system,utf8,0,NULL,&event->sound)||!event->sound||
    wSound_GetLength(event->sound,&duration,1)||!duration||
    wSystem_PlaySound(system,event->sound,parent,1,&event->channel)||!event->channel||
    wChannel_SetVolume(event->channel,volume)||wChannel_SetPitch(event->channel,pitch))return 0;
 if(!wEventInstance_GetTimelinePosition(event->original,&position)&&position>0&&
    ((unsigned)position>=duration||wChannel_SetPosition(event->channel,(unsigned)position,1)))return 0;
 if(wChannel_SetPaused(event->channel,0)||wChannel_IsPlaying(event->channel,&playing)||!playing||
    wChannel_IsVirtual(event->channel,&virtual)||virtual||wChannelGroup_SetMute(group,1))return 0;
 event->group=group;event->muted=1;
 char message[336];
 snprintf(message,sizeof(message),"Imported WAV: view=%p key=%s playing",event->view,event->key);
 bootlog(message);
 return 1;
}

static int imported_wav_channel_active(ImportedWavEvent *event){
 void *sound=NULL;int playing=0;
 return event->channel&&!wChannel_GetCurrentSound(event->channel,&sound)&&sound==event->sound&&
        !wChannel_IsPlaying(event->channel,&playing)&&playing;
}

static void imported_wav_step(ImportedWavEvent *event){
 Unit *unit=event->unit;
 Skin *skin=unit->used&&unit->view==event->view?voice_worn_skin(unit):NULL;
 int state=0;
 if(!skin||skin->app!=event->app||!skin->imported){
  imported_wav_end(event);return;
 }
 if(event->tail){
  if(!imported_wav_channel_active(event))imported_wav_end(event);
  return;
 }
 int stateError=wEventInstance_GetPlaybackState(event->original,&state);
 if(!stateError){
  int pos;
  if(!wEventInstance_GetTimelinePosition(event->original,&pos)&&pos>event->originalPosition)
   event->originalPosition=pos;
 }
 int nearEnd=event->originalLength>0&&event->originalPosition>0&&
             event->originalLength-event->originalPosition<=120;
 if(state==4&&event->muted&&nearEnd&&!event->suppress)return;
 if(stateError||state==4||(state==2&&(event->muted||(DWORD)(GetTickCount()-event->queued)>2000))){
  /* Match a naturally finishing original using its last reported timeline
     position. A cancelled event or an event with no length cannot detach. */
  if(event->muted&&nearEnd&&imported_wav_channel_active(event)){
   void *group=NULL;
   if(!wEventInstance_GetChannelGroup(event->original,&group)&&group==event->group)wChannelGroup_SetMute(group,0);
   event->muted=0;event->tail=1;
  }else imported_wav_end(event);
  return;
 }
 if(state!=0&&state!=3)return; /* The original is not yet playing or sustaining. */
 imported_wav_playing_caption(event);
 if(event->suppress&&!event->muted)imported_wav_suppress(event,skin);
 if(!*event->path||event->failed)return;
 void *group=NULL;int paused=0,groupPaused=0,muted=0;float volume=1,pitch=1;
 if(wEventInstance_GetChannelGroup(event->original,&group)||!group)return;
 if(event->muted&&event->group!=group){imported_wav_end(event);return;}
 if(wChannelGroup_GetMute(group,&muted)||wChannelGroup_GetVolume(group,&volume)||
    wChannelGroup_GetPaused(group,&groupPaused)||wEventInstance_GetPaused(event->original,&paused))return;
 if(wEventInstance_GetPitch(event->original,NULL,&pitch)||pitch<=0)pitch=1;
 paused|=groupPaused;
 if(event->muted){
  if(event->channel&&!imported_wav_channel_active(event))imported_wav_release(event);
  if(event->channel&&(wChannel_SetVolume(event->channel,volume)||wChannel_SetPaused(event->channel,paused)||
     wChannel_SetPitch(event->channel,pitch)))imported_wav_end(event);
 }else if(!muted&&!paused&&!imported_wav_start(event,group,volume,pitch)){
  imported_wav_release(event);
  event->failed=1;
 }
}

static void imported_wav_tick(int active){
 for(int i=0;i<32;i++)if(importedWavEvents[i].original){
  if(active)imported_wav_step(&importedWavEvents[i]);
  else imported_wav_end(&importedWavEvents[i]);
 }
}
