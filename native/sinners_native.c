/* Sinners native random personality - production plugin v1
 * Host: FaustLauncher python (scr.py). Shared section protocol 16.
 * All Unity/IL2CPP work happens on the main thread inside the Canvas render callback.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <stdarg.h>
#include "MinHook.h"
#include "special_policy.h"
#include "form_catalog.h"
#include "form_state.h"
#include "internal_form_policy.h"
#include "playback_policy.h"
#include "chapter_nine_playback.h"
#include "draw_modes.h"
#include "auto_policy.h"
#include "camera_policy.h"
static uintptr_t ui_root(void *o);
static void ui_unroot(uintptr_t h);
#include "voice_runtime.h"
#include "appearance_voice_catalog.h"
#define SR_WORKBENCH_FORMS_WINDOWS
static void bootlog(const char *line);
#define SR_WF_LOG bootlog
#include "workbench_forms.h"
#define SR_STAGE_GROUPS_WINDOWS
#include "stage_groups.h"
#include "chapter_forms.h"

#define SR_PROTOCOL_VERSION 75u
#define SR_SESSION_TEMPLATE L"Local\\FaustNativeSinners_v75_%lu"

#define SR_POOL_MAGIC 0x34505253u /* 'SRP4' */
#define SR_POOL_VERSION 4u
#define SR_ROW_MAX 4096
#define SR_UNIT_MAX 16
#define SR_SKIN_MAX 256
#define SR_CAND_MAX 256
#define SR_QUEUE_MAX 4096
#define SR_RETIRE_MAX 4096

static void *playback_methods[4],*playback_originals[4];
typedef struct {
  uint32_t magic,version,bytes,enabled,heartbeat,state,error,hits;
  char aliases[37][64];
  char message[256];
  uint32_t mode,max_skins,reserved[6];
} Config;

#include "pool_v5.h"
typedef SrPoolV5Row PoolRow;
#define SR_POOL_HAS_GROUP_KEY
#include "pool_key.h"
#include "stage_source.h"
#include "source_diagnostics.h"

#define API_DOMAIN 0
#define API_ASSEMBLIES 1
#define API_IMAGE 2
#define API_IMAGE_NAME 3
#define API_CLASS 4
#define API_METHOD 5
#define API_FIELD 6
#define API_FIELD_OFFSET 7
#define API_OBJECT_CLASS 8
#define API_PARENT 9
#define API_INVOKE 10
#define API_UNBOX 11
#define API_ATTACH 12
#define API_DETACH 13
#define API_CLASS_TYPE 14
#define API_TYPE_OBJECT 15
#define API_ROOT 16
#define API_UNROOT 17
#define API_METHODS 18
#define API_METHOD_NAME 19
#define API_PARAM_COUNT 20
#define API_PARAM 21
#define API_TYPE_NAME 22
#define API_FREE 23
#define API_CLASS_NAME 24
#define API_CLASS_COUNT 25
#define API_IMAGE_CLASS 26
#define API_STRING_NEW 27
#define API_METHOD_OBJECT 28
#define API_FROM_REFLECTION 29
#define API_ARRAY_NEW 30
#define API_WBARRIER 31
#define API_OBJECT_NEW 32
#define API_RETURN_TYPE 33
#define API_FIELD_TYPE 34
#define API_FIELD_VALUE 35
#define API_IS_VALUETYPE 36

static int list_count(void *list);
static void *list_item(void *list,int index);
static int list_add(void *list,void *item);
static int list_remove(void *list,void *item);
static void *make_string(const char *text);

static HINSTANCE g_self;
static void **api;
static Config *g_cfg;
static void *g_game,*g_core,*g_corlib,*g_addr,*g_ui,*g_json;
static volatile LONG g_quitting;

static PoolRow g_rows[SR_ROW_MAX];
static uint32_t g_rowCount;

/* classes */
static void *c_appearance,*c_view,*c_camMan,*c_metadataClass,*c_containerClass,*c_objectClass,*c_typeClass;
static void *t_appearance; /* System.Type of SD.CharacterAppearance */

/* methods */
static void *m_init,*m_changeMotion,*m_parryOnly,*m_skillStart,*m_startDuel,*m_getMotion,*m_setAnimSpeed;
static void *m_getViewer,*m_changeAppearance,*m_viewDestroy,*m_cancelDelay,*m_resetTimeline;
static void *m_die,*m_revive,*orig_revive;
static void *m_playMultiVoice,*m_printBubble,*orig_printBubble,*c_voiceGenerator;
static void *m_checkVoiceIndex,*orig_checkVoiceIndex,*orig_multiVoice,*m_addMultiVoice,*orig_addMultiVoice;
static int voicePairReady;
static void *m_registerAppearanceVoice,*orig_registerAppearanceVoice,*m_setViewVoice,*orig_setViewVoice;
static void *m_instantiate,*m_getComponent,*m_setActive,*m_getTransform,*m_setParent,*m_destroy;
static void *m_getCount,*m_getItem,*m_add,*m_remove,*m_getName,*m_getActiveSelf,*m_getActiveInHierarchy;
static void *m_loadGO,*m_releaseGO,*m_loadMeta,*m_releaseMeta,*m_destroyObject;
static void *m_getSkinPivot,*m_findAll;
static void *g_staging,*g_stagingTr; static uintptr_t g_stagingRoot;

static void *orig_init,*orig_changeMotion,*orig_parryOnly,*orig_skillStart,*orig_startDuel,*orig_getMotion;
static void *orig_viewDestroy,*orig_changeAppearance,*orig_die;
static void *m_formRound,*orig_formRound;
static void *m_formHit,*orig_formHit,*m_formHp,*m_formMaxHp;
static void (*orig_canvas)(void *);

static uintptr_t ui_root(void *o){return o?((uintptr_t (*)(void *,int))api[API_ROOT])(o,0):0;}
static void ui_unroot(uintptr_t h){if(h)((void (*)(uintptr_t))api[API_UNROOT])(h);}
static void *ui_class(void *o){return o?((void *(*)(void *))api[API_OBJECT_CLASS])(o):NULL;}
static void *ui_parent(void *k){return k?((void *(*)(void *))api[API_PARENT])(k):NULL;}
static void *ui_unbox(void *o){return o?((void *(*)(void *))api[API_UNBOX])(o):NULL;}
static void *ui_invoke(void *m,void *o,void **a,void **e){(void)e;return m?((void *(*)(void *,void *,void **,void **))api[API_INVOKE])(m,o,a,e):NULL;}
static void *ui_new(void *k){return k?((void *(*)(void *))api[API_OBJECT_NEW])(k):NULL;}

static INIT_ONCE logOnce=INIT_ONCE_STATIC_INIT;
static HANDLE logHandle=INVALID_HANDLE_VALUE;
static BOOL CALLBACK open_runtime_log(PINIT_ONCE once,PVOID param,PVOID *context){
  wchar_t path[32768];DWORD used=GetModuleFileNameW(g_self,path,32768);
  if(!used||used>=32768)return FALSE;
  wchar_t *p=wcsrchr(path,L'\\');const wchar_t name[]=L"native_runtime.log";
  if(!p||(size_t)(p+1-path)+sizeof(name)/sizeof(*name)>32768)return FALSE;
  memcpy(p+1,name,sizeof(name));
  logHandle=CreateFileW(path,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_ALWAYS,0,NULL);
  return logHandle!=INVALID_HANDLE_VALUE;
}
static void bootlog(const char *line){
  if(!InitOnceExecuteOnce(&logOnce,open_runtime_log,NULL,NULL))return;
  SYSTEMTIME t;GetLocalTime(&t);char prefix[96];
  int len=snprintf(prefix,sizeof(prefix),"[%04u-%02u-%02u %02u:%02u:%02u.%03u pid=%lu v=%u] ",t.wYear,t.wMonth,t.wDay,t.wHour,t.wMinute,t.wSecond,t.wMilliseconds,(unsigned long)GetCurrentProcessId(),SR_PROTOCOL_VERSION);
  size_t body=strlen(line);if(len<0||len>=sizeof(prefix)||body>MAXDWORD-sizeof(prefix)-2)return;
  size_t size=(size_t)len+body+2;char local[1024];
  char *record=size<=sizeof(local)?local:HeapAlloc(GetProcessHeap(),0,size);
  if(!record)return;
  memcpy(record,prefix,len);memcpy(record+len,line,body);memcpy(record+len+body,"\r\n",2);
  DWORD written;WriteFile(logHandle,record,(DWORD)size,&written,NULL);
  if(record!=local)HeapFree(GetProcessHeap(),0,record);
}
static void say(const char *format,...){
  if(!g_cfg)return;
  char buffer[256];va_list a;va_start(a,format);vsnprintf(buffer,sizeof(buffer)-1,format,a);va_end(a);
  lstrcpynA(g_cfg->message,buffer,256);
}
static void fatal(const char *msg,int code){
  if(!g_cfg)return;g_cfg->error=code;lstrcpynA(g_cfg->message,msg,256);MemoryBarrier();g_cfg->state=2;bootlog(msg);
}
static int enabled_now(void){
 const volatile Config *cfg=g_cfg;
 if(g_quitting||!cfg||!cfg->enabled)return 0;
 DWORD published=cfg->heartbeat;
 return (DWORD)(GetTickCount()-published)<3000;
}

static void *find_method(void *klass,const char *name,int count){
  for(void *c=klass;c;c=ui_parent(c)){void *m=((void *(*)(void *,const char *,int))api[API_METHOD])(c,name,count);if(m)return m;}
  return NULL;
}
/* Read metadata and entry addresses only; do not invoke or hook these methods. */
static void sprite_log_methods(void *game,void *core){
 static const struct {int core;const char *ns,*klass,*method;int argc;} rows[]={
  {0,"SD","CharacterAppearance","OnSpriteChangeCallback",1},
  {0,"SD","CharacterAppearance","get_Sprenderer_charactermotion_Parts",0},
  {1,"UnityEngine","SpriteRenderer","get_sprite",0},
  {1,"UnityEngine","SpriteRenderer","set_sprite",1},
  {1,"UnityEngine","Object","get_name",0},
  {1,"UnityEngine","Texture2D",".ctor",2},
  {1,"UnityEngine","Sprite","Create",4}};
 uintptr_t base=(uintptr_t)GetModuleHandleW(L"GameAssembly.dll");
 for(unsigned i=0;i<sizeof(rows)/sizeof(rows[0]);i++){
  void *img=rows[i].core?core:game;
  void *klass=img?((void *(*)(void *,const char *,const char *))api[API_CLASS])(img,rows[i].ns,rows[i].klass):NULL;
  void *method=klass?find_method(klass,rows[i].method,rows[i].argc):NULL;
  uintptr_t ptr=method?(uintptr_t)*(void **)method:0;HMODULE module=NULL;
  int in_game=ptr&&GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,(LPCWSTR)ptr,&module)&&module==(HMODULE)base;
  char line[256];snprintf(line,sizeof(line),"sprite method class=%s method=%s argc=%d found=%d game_rva=%llx",rows[i].klass,rows[i].method,rows[i].argc,method!=NULL,(unsigned long long)(in_game?ptr-base:0));bootlog(line);
 }
}
/* Read method entry addresses only; never invoke any Timeline method. */
static void fx_log_method_rvas(void *image){
 static const struct {const char *klass,*method;int argc;} wanted[]={
  {"TimelineClip","get_start",0},{"TimelineClip","get_extrapolatedStart",0},
  {"RuntimeClip","get_start",0},{"RuntimeClip","EvaluateAt",2},
  {"RuntimeClipBase","get_intervalStart",0},{"TimelinePlayable","Evaluate",0},
  {"TrackAsset","CompileClips",4},{"TimelineAsset","CreatePlayable",2}};
 uintptr_t base=(uintptr_t)GetModuleHandleW(L"GameAssembly.dll");
 for(unsigned i=0;i<sizeof(wanted)/sizeof(wanted[0]);i++){
  void *k=((void *(*)(void *,const char *,const char *))api[API_CLASS])(image,"UnityEngine.Timeline",wanted[i].klass);
  void *m=k?find_method(k,wanted[i].method,wanted[i].argc):NULL;uintptr_t p=m?(uintptr_t)*(void **)m:0;
  char line[240];snprintf(line,sizeof(line),"fx method rva class=%s method=%s argc=%d found=%d rva=%llx",wanted[i].klass,wanted[i].method,wanted[i].argc,p&&base&&p>=base,(unsigned long long)(p&&base&&p>=base?p-base:0));bootlog(line);
 }
}
static void *find_field_obj(void *obj,const char *name){
  if(!obj)return NULL;
  for(void *c=ui_class(obj);c;c=ui_parent(c)){void *f=((void *(*)(void *,const char *))api[API_FIELD])(c,name);if(f)return f;}
  return NULL;
}
static void *rfield(void *obj,const char *name){
  void *f=find_field_obj(obj,name);
  if(!f)return NULL;
  return *(void **)((char *)obj+((size_t (*)(void *))api[API_FIELD_OFFSET])(f));
}
static int set_ref(void *obj,const char *name,void *value){
  void *f=find_field_obj(obj,name);
  if(!f)return 0;
  ((void (*)(void *,void **,void *))api[API_WBARRIER])(obj,(void **)((char *)obj+((size_t (*)(void *))api[API_FIELD_OFFSET])(f)),value);
  return 1;
}
static void *make_string(const char *text){return ((void *(*)(const char *))api[API_STRING_NEW])(text);}
static int string_ascii(void *str,char *out,int cap){
  if(!str)return 0;
  int length=*(int *)((char *)str+16);
  if(length<0||length>=cap)return 0;
  const uint16_t *chars=(const uint16_t *)((char *)str+20);
  for(int i=0;i<length;i++){if(chars[i]>126||chars[i]<32)return 0;out[i]=(char)chars[i];}
  out[length]=0;return 1;
}
static int call_bool(void *method,void *obj,void **args){
  void *exc=NULL,*v=ui_invoke(method,obj,args,&exc);
  return (!exc&&v)?(*(uint8_t *)ui_unbox(v)?1:0):-1;
}
static int call_int(void *method,void *obj,void **args){
  void *exc=NULL,*v=ui_invoke(method,obj,args,&exc);
  return (!exc&&v)?*(int *)ui_unbox(v):-1;
}
static int call_exc(void *method,void *obj,void **args){
  if(!method)return 0;
  void *exc=NULL;
  ((void *(*)(void *,void *,void **,void **))api[API_INVOKE])(method,obj,args,&exc);
  return exc?0:1;
}
static void *call_obj(void *method,void *obj,void **args,int *ok){
  void *exc=NULL,*v=ui_invoke(method,obj,args,&exc);
  if(exc||!v){if(ok)*ok=0;return NULL;}
  if(ok)*ok=1;return v;
}

/* ---------------- pools ---------------- */
static int pool_read(HANDLE f,PoolRow *rows,uint32_t *count){
 static unsigned char bytes[16+SR_ROW_MAX*412];DWORD size=GetFileSize(f,NULL),got=0;
 if(size<16||size>sizeof(bytes)||!ReadFile(f,bytes,size,&got,NULL)||got!=size)return 0;
 uint32_t h[4];memcpy(h,bytes,16);
 if(h[0]==SR_POOL_V5_MAGIC)return sr_pool_v5_parse(rows,SR_ROW_MAX,count,bytes,size);
 if(h[0]!=SR_POOL_MAGIC||h[1]!=SR_POOL_VERSION||h[2]>SR_ROW_MAX||h[3]!=344||size!=16+(size_t)h[2]*344)return 0;
 for(uint32_t i=0;i<h[2];i++){memset(&rows[i],0,sizeof(rows[i]));memcpy(&rows[i],bytes+16+(size_t)i*344,344);}
 *count=h[2];return 1;
}
static int pool_load(void){
 wchar_t path[32768];GetModuleFileNameW(g_self,path,32768);wchar_t *p=wcsrchr(path,L'\\');if(!p)return 0;lstrcpyW(p+1,L"native_pools.bin");
 HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
 if(f==INVALID_HANDLE_VALUE){bootlog("pool snapshot missing");return 0;}
 int ok=pool_read(f,g_rows,&g_rowCount);CloseHandle(f);
 if(!ok){bootlog("pool snapshot invalid");return 0;}
 char line[128];wsprintfA(line,"pool rows=%lu",(unsigned long)g_rowCount);bootlog(line);return 1;
}

static int random_double(double *out){
  typedef LONG (WINAPI *Gen)(void *,unsigned char *,unsigned long,unsigned long);
  static Gen gen;
  if(!gen){HMODULE b=LoadLibraryW(L"bcrypt.dll");if(b)gen=(Gen)(void *)GetProcAddress(b,"BCryptGenRandom");}
  uint64_t bits=0;
  if(!gen||gen(NULL,(unsigned char *)&bits,sizeof(bits),2)<0)return 0;
  *out=(double)(bits>>11)*(1.0/9007199254740992.0);
  return 1;
}

/* ---------------- units ---------------- */
#include "segment_latch.h"
#include "ordinary_body_index.h"
typedef struct {
  int used,row;
  int formWarned,form;
  int internalStage,internalFailed,chapterApplied,chapterDefault;
  DWORD chapterRetry;
  int motionCounts[SR_MOTION_CACHE];
  uint32_t ordinaryClips[SR_MOTION_CACHE];
  SrOrdinaryBodies *ordinaryBodies;
  int nativeMotionDetail[SR_MOTION_CACHE];
  unsigned motionMapped[4],motionMissing[4];
  void *app,*go;
  uintptr_t appRoot,goRoot,handleRoot,metaRoot,storyRoot;
  void *storyTarget;
  const SrChapterActor *chapterActor;
  signed char chapterRole[SR_MOTION_CACHE];
  short clashCount[SR_MOTION_CACHE];
  /* The clone owns these lists for the lifetime of the cached skin. */
  void *clashSparse[SR_MOTION_CACHE];
  void *handleBox,*meta;
  char rid[96];
  char look[64];
} Skin;

#define SR_MOTION_QUEUE 16
typedef struct {
 void *source,*callback,*method,*action,*viewer;
 uintptr_t sourceRoot,callbackRoot;
 int row,coin,detail,index,tier,last,endReturned,chapterSkill;
 uint8_t a1,a3,a5;
} PendingMotion;
typedef struct {
  int used;
  void *view,*baseApp;
  void **staticRenderers; uint8_t *staticRendererEnabled; size_t staticRendererCount; int staticHidden; uintptr_t staticArrayRoot;
  uintptr_t viewRoot,baseRoot;
  char baseName[96];
  uint32_t sinner;
  int clashDepth,switching,last,pending,wanted;
  int startupPending,startupRow;
  SrDrawState drawState[3];
  int coinKnown,coinLast,coinTier,coinMotion,coinIndex,dead;
  SrSegmentLatch segmentLatch;
  uint32_t ordinarySourceClips[SR_MOTION_CACHE];
  unsigned segmentSequence;
  int segmentPrewarmAttempted;
  DWORD segmentPrewarmAfter;
  void *cycleAction,*cycleViewer;
  int cycleValid,cycleCoin,cycleOrdinal;char cycleLook[128];
  int preserveSpecial;
  unsigned deathVoiceAccepted;
  SrVoiceCue voiceCues[8];unsigned voiceCueNext;
  unsigned voiceBoss; /* owner of the committed appearance */
  int viewerActive,idleRestoreFrames,retainConsumed;
  unsigned warmCursor;
  PendingMotion motions[SR_MOTION_QUEUE];int motionCount;
  void *endedApp,*endedDirector;unsigned playbackGeneration,endedGeneration;
  void *observedViewer,*observedAction;uintptr_t observedViewerRoot;
  size_t observedCoinOffset;int observedCoinField;
  void *attackDrawAction,*attackDrawViewer;int attackDrawValid,attackDrawIndex,attackDrawRow;
  int wantedSourceCoin;
  void *deliveredAction,*deliveredApp;int deliveredCoin,deliveredValid;
  void *retainedAction,*retainedApp;
  unsigned char failedFormMask[SR_ROW_MAX];
  int sanity,sanityValid;
  int formHp,formMaxHp;
  char stageSource[64];
  int stageGroup,stageChoice; /* group index + 1; zero means inactive */
  int stageShown,stageWanted; /* actually presented stage, director-owned row */
  uint32_t stageRevision;
  DWORD formHpAt,chapterAt;
  int chapterSignal,chapterPhase;void *chapterModel;
  unsigned alternateForms, alternateSeen;
  int evaded;
  void *lastDefenseAction,*lastDefenseDrawAction;
  int defenseDrawLatched,defensePickedRow;
  int introPending,introRow,stageIntroPending,stageIntroRow;
  int nativeStage,nativeValid; void *nativeAppearance;
  unsigned introPlayed;
  int defenseLatch,coinDefense;
  SrFormState formState;
  uint64_t observedRound;
  int roundPending;
  int roundSanity,roundSanityValid;
  void *observedModel;
  int cand[SR_CAND_MAX],ncand;
  int bad[SR_CAND_MAX],nbad;
  Skin skins[SR_SKIN_MAX];
} Unit;

static Unit g_units[SR_UNIT_MAX];
static int candidateOrder[SR_ROW_MAX];static uint32_t candidateOrderCount;
static int base_rule_match(Unit *u,const PoolRow *r){
 if(!r->base_identity[0])return 0;
 if(!u||!u->baseName[0])return 0;
 size_t n=strlen(r->base_identity);
 return !strncmp(u->baseName,r->base_identity,n)&&(u->baseName[n]=='\0'||u->baseName[n]=='_');
}
static void rebuild_candidates(Unit *u){
 u->ncand=0;u->segmentPrewarmAttempted=0;memset(u->ordinarySourceClips,0,sizeof(u->ordinarySourceClips));sr_segment_clear(&u->segmentLatch);memset(u->drawState,0,sizeof(u->drawState));
 uint32_t count=candidateOrderCount?candidateOrderCount:g_rowCount;
 int wildHunt=sr_player_number(u->baseName)==10710;
 int specific=0;
 for(uint32_t i=0;i<count;i++){
  int k=candidateOrderCount?candidateOrder[i]:(int)i;
  PoolRow *r=&g_rows[k];
  if(r->sinner==u->sinner&&r->enabled&&r->weight>0&&base_rule_match(u,r)){specific=1;break;}
 }
 for(uint32_t i=0;i<count&&u->ncand<SR_CAND_MAX;i++){
  int k=candidateOrderCount?candidateOrder[i]:(int)i;
  PoolRow *r=&g_rows[k];
  if(r->sinner!=u->sinner||!r->enabled||r->weight<=0)continue;
  if(specific){if(!base_rule_match(u,r))continue;}
  else if(r->base_identity[0])continue;
  if(wildHunt){
   int reverse=0;
   const SrCounterpart *pair=sr_find_counterpart(u->baseName,r->identity,&reverse);
   if(!pair||reverse||!r->story||strcmp(pair->story,r->appearance_name))continue;
  }
  u->cand[u->ncand++]=k;
 }
}
static Unit *introUnit;
static void *introApp;
static uintptr_t introRoot;
static DWORD introStarted;
static int introInterrupted,introFrame,introPart,introHasSecond;
static int g_frame;
static void *m_frameCount;
static int g_lastUnityFrame=-1;
static LONG g_switches,g_loads,g_fallbacks;

static int identity_text(void *app,char *out,int cap){
  if(!app)return 0;
  void *info=rfield(app,"charInfo");
  if(!info)return 0;
  void *id=rfield(info,"appearanceID");
  return string_ascii(id,out,cap);
}
static uint32_t sinner_of(void *app){
  char text[128];if(!identity_text(app,text,sizeof(text)))return 0;
  if(strlen(text)<5)return 0;
  for(int i=0;i<5;i++)if(text[i]<'0'||text[i]>'9')return 0;
  uint32_t key=(text[0]-'0')*100+(text[1]-'0')*10+(text[2]-'0');
  return (key>=101&&key<=112)?key:0;
}
static Unit *unit_for_app(void *app){
  if(!app)return NULL;
  for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used){
    Unit *u=&g_units[i];
    if(u->baseApp==app)return u;
    for(int k=0;k<SR_SKIN_MAX;k++)if(u->skins[k].used&&u->skins[k].app==app)return u;
  }
  return NULL;
}
static Skin *skin_for_app(Unit *u,void *app){
  for(int k=0;k<SR_SKIN_MAX;k++)if(u->skins[k].used&&u->skins[k].app==app)return &u->skins[k];
  return NULL;
}
/* A transformed resource may have a voice owner distinct from its pool row. */
static unsigned voice_skin_owner(const Skin *skin){
  if(!skin||skin->row<0||(uint32_t)skin->row>=g_rowCount)return 0;
  const PoolRow *row=&g_rows[skin->row];
  unsigned owner=sr_voice_catalog_owner(skin->look);
  if(owner)return owner;
  if(skin->look[0]&&strcmp(skin->look,row->appearance_name))return 0;
  return sr_voice_catalog_owner(row->identity);
}
static Unit *unit_alloc(void){
  for(int i=0;i<SR_UNIT_MAX;i++)if(!g_units[i].used)return &g_units[i];
  return NULL;
}

/* skin index by pool row, -1 when not cached */
static int auto_desired(Unit *u,int row);
static const SrInternalForm *auto_internal(int row);
static void auto_forms_load(void);
static void auto_detect_skin(Skin *skin);
static int warm_cache_required(Unit *u,int row,int form);
static int workbench_form_count(int row);
static int resource_form_failed(Unit *u,int row,int form){
 return u&&row>=0&&(uint32_t)row<g_rowCount&&form>0&&form<4&&
        (u->failedFormMask[row]&(1u<<form));
}
static int native_desired_row_form(Unit *u,int row){
 if(!u||row<0||(uint32_t)row>=g_rowCount)return 0;
 const char *id=g_rows[row].identity;int catalog=sr_form_index(id);
 if(catalog<0)return auto_desired(u,row);
 if(!strcmp(id,"10314"))return sr_form_stage(&u->formState,id,2,u->sanity,u->sanityValid);
 if(!strcmp(id,"11009"))return sr_dawn_form(u->sanity,u->sanityValid)==1;
 if(!strcmp(id,"10401")||!strcmp(id,"10701"))return !!(u->alternateForms&(1u<<catalog));
 return u->evaded;
}
static int workbench_form_stage(Unit *u,const char *id,int native,int count){
 if(!u||!id)return native;
 if(u->stageGroup>0&&u->stageRevision==g_stageGroups.revision&&(uint32_t)u->stageGroup<=g_stageGroups.count){
  const SrSgGroup *g=&g_stageGroups.group[u->stageGroup-1];
  if(g->enabled&&u->stageChoice>=0&&(uint32_t)u->stageChoice<g->count){const SrSgStage *s=&g->stage[u->stageChoice];if(!strcmp(id,s->identity)){int f=(int)s->form;return f<count?f:native;}}
 }
 return sr_wf_stage(&g_workbenchForms,(uint32_t)strtoul(id,NULL,10),native,count,u->formState.evades,u->sanity,u->sanityValid,u->formHp,u->formMaxHp);
}
/* While the next stage's distinct appearance is loading, keep the current
   appearance unchanged and do not let legacy form updates replace wanted. */
static int stage_waiting_for_other_appearance(Unit *u,const char *id){
 if(!u||!id||u->stageGroup<=0||u->stageRevision!=g_stageGroups.revision||
    (uint32_t)u->stageGroup>g_stageGroups.count||u->stageChoice<0)return 0;
 const SrSgGroup *g=&g_stageGroups.group[u->stageGroup-1];
 return g->enabled&&(uint32_t)u->stageChoice<g->count&&strcmp(id,g->stage[u->stageChoice].identity)!=0;
}
static int desired_row_form(Unit *u,int row){
 int native=native_desired_row_form(u,row);
 if(!u||row<0||(uint32_t)row>=g_rowCount)return native;
 int desired=workbench_form_stage(u,g_rows[row].identity,native,workbench_form_count(row));
 return resource_form_failed(u,row,desired)?0:desired;
}
static int selected_row(Unit *u,int row,uint32_t action){
 if(row<0||(uint32_t)row>=g_rowCount||!action)return row;
 const char *id=g_rows[row].identity;
 if(!strcmp(id,"10401")||!strcmp(id,"10701")){
   unsigned bit=1u<<sr_form_index(id);
   if(u->alternateSeen&bit)u->alternateForms^=bit;
   else u->alternateSeen|=bit;
 }
 return row;
}
static int skin_index_form(Unit *u,int row,int form){
 for(int k=0;k<SR_SKIN_MAX;k++)if(u->skins[k].used&&u->skins[k].row==row&&u->skins[k].form==form)return k;
 return -1;
}
static int skin_index(Unit *u,int row){return skin_index_form(u,row,desired_row_form(u,row));}
static Skin *held_appearance(Unit *u){
 if(!u||!u->used||u->dead||u->preserveSpecial||u->last<0||u->last>=SR_SKIN_MAX)return NULL;
 Skin *skin=&u->skins[u->last];return skin->used&&skin->app?skin:NULL;
}
static Skin *skin_alloc(Unit *u){
  for(int k=0;k<SR_SKIN_MAX;k++)if(!u->skins[k].used)return &u->skins[k];
  return NULL;
}

static int loading_row(Unit *u,int row);
static int loading_form(Unit *u,int row,int form);
static int unit_bad(Unit *u,int row){for(int i=0;i<u->nbad;i++)if(u->bad[i]==row)return 1;return 0;}
static int skin_limit(void){if(g_cfg&&g_cfg->mode==1)return SR_SKIN_MAX;int n=g_cfg?(int)g_cfg->max_skins:3;return n<2?2:n>SR_SKIN_MAX?SR_SKIN_MAX:n;}
static int skin_count(Unit *u){int n=0;for(int i=0;i<SR_SKIN_MAX;i++)n+=!!u->skins[i].used;return n;}
/* ---------------- load queue ---------------- */
static Unit *q_unit[SR_QUEUE_MAX];
static int q_row[SR_QUEUE_MAX],q_form[SR_QUEUE_MAX];
static int q_poppedForm=-1;
static int q_head,q_tail;
static void queue_push_form(Unit *u,int row,int form){
  if(!u||!u->used||u->dead||row<0||(uint32_t)row>=g_rowCount||u->ncand==0||g_rows[row].sinner!=u->sinner||form<0||form>3)return;
  if(loading_form(u,row,form)||resource_form_failed(u,row,form))return;
  if((q_tail+1)%SR_QUEUE_MAX==q_head)return;
  for(int i=q_head;i!=q_tail;i=(i+1)%SR_QUEUE_MAX)if(q_unit[i]==u&&q_row[i]==row&&q_form[i]==form)return;
  if(skin_index_form(u,row,form)>=0)return;
  for(int i=0;i<u->nbad;i++)if(u->bad[i]==row)return;
  q_unit[q_tail]=u;q_row[q_tail]=row;q_form[q_tail]=form;q_tail=(q_tail+1)%SR_QUEUE_MAX;
}
static void queue_push(Unit *u,int row){if(u)queue_push_form(u,row,desired_row_form(u,row));}
static int queue_pop(Unit **u,int *row){
  if(q_head==q_tail)return 0;
  /* Earliest queued startup selection takes priority; FIFO among units. */
  for(int i=q_head;i!=q_tail;i=(i+1)%SR_QUEUE_MAX){
   Unit *v=q_unit[i];if(!v||!v->used||!v->startupPending||v->startupRow<0||(uint32_t)v->startupRow>=g_rowCount||v->startupRow!=q_row[i])continue;
   Unit *t=q_unit[q_head];int r=q_row[q_head],f=q_form[q_head];
   q_unit[q_head]=q_unit[i];q_row[q_head]=q_row[i];q_form[q_head]=q_form[i];
   q_unit[i]=t;q_row[i]=r;q_form[i]=f;break;
  }
  *u=q_unit[q_head];*row=q_row[q_head];q_poppedForm=q_form[q_head];q_head=(q_head+1)%SR_QUEUE_MAX;return 1;
}

/* ---------------- weighted draw ---------------- */
/* Rules file: 4 little-endian uint32 header (magic 0x31525753,
 version 1, row count, row size 16), followed by rows:
 sinner, attack mode, clash mode, defense mode. Modes 0/1/2.
 Order uses the current pool's entry order. Hot reload resets draw cycles. */
static uint32_t drawModes[12][3];
static void draw_rules_tick(void){
 static DWORD checked;static FILETIME stamp;DWORD now=GetTickCount();
 if((DWORD)(now-checked)<1000)return;checked=now;
 wchar_t path[32768];GetModuleFileNameW(g_self,path,32768);wchar_t *slash=wcsrchr(path,L'\\');if(!slash)return;lstrcpyW(slash+1,L"workbench_rules.bin");
 WIN32_FILE_ATTRIBUTE_DATA attr;
 if(!GetFileAttributesExW(path,GetFileExInfoStandard,&attr))return;
 if(!CompareFileTime(&stamp,&attr.ftLastWriteTime))return;
 HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);if(f==INVALID_HANDLE_VALUE)return;
 uint32_t header[4],rows[12][4],next[12][3]={{0}};DWORD got;int ok=ReadFile(f,header,16,&got,NULL)&&got==16&&header[0]==0x31525753&&header[1]==1&&header[2]<=12&&header[3]==16;
 if(ok)ok=GetFileSize(f,NULL)==16+header[2]*16&&ReadFile(f,rows,header[2]*16,&got,NULL)&&got==header[2]*16;
 CloseHandle(f);unsigned seen=0;
 if(ok)for(unsigned i=0;i<header[2];i++){
  unsigned n=rows[i][0]-101;if(n>=12||(seen&(1u<<n))||rows[i][1]>2||rows[i][2]>2||rows[i][3]>2){ok=0;break;}
  seen|=1u<<n;memcpy(next[n],rows[i]+1,12);
 }
 if(!ok){bootlog("workbench draw rules rejected; previous rules retained");stamp=attr.ftLastWriteTime;return;}
 memcpy(drawModes,next,sizeof(next));stamp=attr.ftLastWriteTime;
 for(int i=0;i<SR_UNIT_MAX;i++)memset(g_units[i].drawState,0,sizeof(g_units[i].drawState));
 char line[160];snprintf(line,sizeof(line),"workbench draw rules applied revision=%lu:%lu; attack/clash/defense cycles reset",(unsigned long)stamp.dwHighDateTime,(unsigned long)stamp.dwLowDateTime);bootlog(line);
}
static int unit_draw(Unit *u,uint32_t action,double random){
 int category=action==2?0:action==8?1:action==1?2:-1;
 int mode=category>=0&&u->sinner>=101&&u->sinner<=112?(int)drawModes[u->sinner-101][category]:0;
 int ids[SR_CAND_MAX],count=0;double weights[SR_CAND_MAX];
 for(int i=0;i<u->ncand&&count<SR_CAND_MAX;i++){
  int id=u->cand[i];PoolRow *r=&g_rows[id];
  if(!r->enabled||(r->excluded&action)||unit_bad(u,id)||!isfinite(r->weight)||r->weight<=0||r->weight>1000000)continue;
  ids[count]=id;weights[count++]=r->weight;
 }
 SrDrawState temporary={0};int result=sr_draw_mode(category>=0?&u->drawState[category]:&temporary,mode,ids,weights,count,random);
 return result<0?-1:selected_row(u,result,action);
}

/* ---------------- motion helpers ---------------- */
static int g_motionDepth;
static int g_clashBoundary;
static int g_presentationGate; /* Actual close-up scope, not viewer lifetime. */
static int g_anyViewerActive;
static void *g_metadataDB,*g_metaBox;
static uintptr_t g_metaBoxRoot,g_metaDBRoot;

static int timeline_count(void *motion,int *detail){
  if(!motion)return -1;
  void *getter=find_method(ui_class(motion),"get_MotionDetail",0);
  int got=getter?call_int(getter,motion,NULL):-1;
  if(detail)*detail=got;
  void *list=rfield(motion,"timelineAssets");
  if(!list)return -1;
  int count=list_count(list);
  return count;
}
static int motion_count(void *app,int detailOnDonor,int *actualDetail){
  if(!app||!m_getMotion)return -1;
  int detail=detailOnDonor;uint8_t flag=0;void *args[]={&detail,&flag};
  int ok=1;
  g_motionDepth++;
  void *motion=call_obj(m_getMotion,app,args,&ok);
  g_motionDepth--;
  if(!ok||!motion)return -1;
  int got=-1,count=timeline_count(motion,&got);
  if(actualDetail)*actualDetail=got;
  if(got!=detailOnDonor)return -1;
  return count;
}

static int cleanup_pending;
static unsigned char defenseMotions[128],defenseTypes[32];
static int defense_name(const char *name){
 char text[128];lstrcpynA(text,name,128);CharUpperBuffA(text,(DWORD)strlen(text));
 if(strstr(text,"PREP")||strstr(text,"READY"))return 0;
 return strstr(text,"GUARD")||strstr(text,"EVADE")||strstr(text,"EVASION")||strstr(text,"COUNTER")||strstr(text,"DEFENSE");
}
static int bind_defense_enum(void *klass,unsigned char *map,int cap){
 if(!klass)return 0;
 void *type=((void *(*)(void *))api[API_TYPE_OBJECT])(((void *(*)(void *))api[API_CLASS_TYPE])(klass));
 uintptr_t root=ui_root(type);if(!root)return 0;
 int ok=0;void *nm=find_method(ui_class(type),"GetEnumNames",0),*vm=find_method(ui_class(type),"GetEnumValues",0);
 void *names=nm?call_obj(nm,type,NULL,&ok):NULL;uintptr_t nr=ui_root(names);
 void *values=vm?call_obj(vm,type,NULL,&ok):NULL;uintptr_t vr=ui_root(values);int found=0;
 if(nr&&vr&&ok){
  uintptr_t n=*(uintptr_t *)((char *)names+24),v=*(uintptr_t *)((char *)values+24);
  if(n==v&&n<512)for(uintptr_t i=0;i<n;i++){
   char name[128];void *str=((void **)((char *)names+32))[i];int value=((int *)((char *)values+32))[i];
   if(value>=0&&value<cap&&string_ascii(str,name,128)&&defense_name(name)){map[value]=1;found++;}
  }
 }
 ui_unroot(vr);ui_unroot(nr);ui_unroot(root);return found;
}
static int skill_is_defense(void *model){
 void *def=model?find_method(ui_class(model),"GetDefenseType",0):NULL;
 if(!def&&model)def=find_method(ui_class(model),"get_DefenseType",0);
 int kind=def?call_int(def,model,NULL):-1;
 return kind>=0&&kind<32&&defenseTypes[kind];
}
static void count_form_defense(Unit *u,const char *source){
 if(!u||u->switching||u->dead||cleanup_pending)return;
 void *action=rfield(u->view,"_currentActionLog");
 if(action&&action==u->lastDefenseAction)return;
 if(u->defenseLatch&&(!action||!u->lastDefenseAction)){
  if(action)u->lastDefenseAction=action;
  return;
 }
 u->lastDefenseAction=action;
 u->defenseLatch=1;u->evaded=1;sr_form_evade(&u->formState);
 if(u->defenseDrawLatched){u->introPending=1;u->introRow=u->defensePickedRow;}
 if(u->stageSource[0]){char line[180];snprintf(line,sizeof(line),"form defense sinner=%lu group=%.63s count=%u via=%s",(unsigned long)u->sinner,u->stageSource,u->formState.evades,source);bootlog(line);}
}
static void observe_defense(Unit *u,int detail){
 if(!u||u->switching||u->dead||cleanup_pending)return;
 if((detail>=0&&detail<128&&defenseMotions[detail])||
    (u->coinDefense&&u->coinKnown&&detail==u->coinMotion))count_form_defense(u,"motion");
 else if(detail==0||detail==18){u->defenseLatch=0;u->defenseDrawLatched=0;}
}
static int is_skill_detail(int d){return (d>=7&&d<=16)||(d>=24&&d<=34);}
#include "clash_motion.h"
static int is_parry_detail(int d){return d==17||d==19||d==23||d==36||d==37||d==38||d==41||d==42||d==43;}
static int is_prep_detail(int d){return d==36||d==41||d==42;}

typedef struct {int known,last,tier,skillMotion,coinIndex;} Coin;

/* Read Boolean fields as bytes, never as object references. A viewer stays
   attached after completion and must not keep the entire battle locked. */
static int viewer_finished(void *viewer){
 const char *names[]={"_isEnd","_isCancel"};
 for(int i=0;i<2;i++){
  void *f=find_field_obj(viewer,names[i]);
  if(f&&*(uint8_t *)((char *)viewer+((size_t (*)(void *))api[API_FIELD_OFFSET])(f)))return 1;
 }
 return 0;
}
static void coin_info(Unit *u,Coin *coin){
  memset(coin,0,sizeof(*coin));coin->coinIndex=-1;
  if(u){u->coinDefense=0;u->viewerActive=0;u->observedAction=NULL;}
  if(!u||!u->view||!m_getViewer)return;
  int ok=1;void *viewer=call_obj(m_getViewer,u->view,NULL,&ok);
  if(!ok||!viewer||viewer_finished(viewer)){
    sr_segment_clear(&u->segmentLatch);
    if(u->observedViewerRoot)ui_unroot(u->observedViewerRoot);
    u->observedViewer=NULL;u->observedViewerRoot=0;u->observedCoinField=0;u->attackDrawValid=0;return;
  }
  void *actor=rfield(viewer,"_actor");
  if(!actor||actor!=u->view){u->attackDrawValid=0;sr_segment_clear(&u->segmentLatch);return;}
  u->viewerActive=1;
  if(viewer!=u->observedViewer){
    if(u->attackDrawViewer!=viewer)u->attackDrawValid=0;
    uintptr_t root=ui_root(viewer);
    if(u->observedViewerRoot)ui_unroot(u->observedViewerRoot);
    u->observedViewer=root?viewer:NULL;u->observedViewerRoot=root;u->observedCoinField=0;
    void *field=root?find_field_obj(viewer,"_curCoinLogIndex"):NULL;
    if(field){u->observedCoinOffset=((size_t (*)(void *))api[API_FIELD_OFFSET])(field);u->observedCoinField=1;}
  }
  u->observedAction=rfield(u->view,"_currentActionLog");
  void *model=rfield(viewer,"_currentSkillModel");
  if(model){
    void *tier=find_method(ui_class(model),"GetSkillTier",0);
    if(tier){int t=call_int(tier,model,NULL);if(t>0)coin->tier=t;}
    void *motion=find_method(ui_class(model),"GetSkillMotion",0);
    if(motion){int s=call_int(motion,model,NULL);if(s>=0)coin->skillMotion=s;}
    u->coinDefense=skill_is_defense(model);
    coin->known=1;
  }
  void *isLast=find_method(ui_class(viewer),"IsLastCoin",1);
  if(isLast){int minus=-1;void *args[]={&minus};int v=call_bool(isLast,viewer,args);if(v>=0)coin->last=v;}
  void *logIndex=find_field_obj(viewer,"_curCoinLogIndex");
  if(logIndex)coin->coinIndex=*(int *)((char *)viewer+((size_t (*)(void *))api[API_FIELD_OFFSET])(logIndex));
}

static int read_number(void *obj,const char *name,double *out){
  void *f=find_field_obj(obj,name);
  if(!f){char line[96];wsprintfA(line,"timing: field %s missing",name);bootlog(line);return 0;}
  void *type=((void *(*)(void *))api[API_FIELD_TYPE])(f);
  char *tn=type?((char *(*)(void *))api[API_TYPE_NAME])(type):NULL;
  int ok=0;
  void *value=((void *(*)(void *,void *))api[API_FIELD_VALUE])(f,obj);
  if(value){
    uintptr_t h=ui_root(value);
    if(h){
      if(tn&&!strcmp(tn,"System.Single")){*out=*(float *)ui_unbox(value);ok=1;}
      else if(tn&&!strcmp(tn,"System.Double")){*out=*(double *)ui_unbox(value);ok=1;}
      ui_unroot(h);
    }
  }
  if(tn)((void (*)(void *))api[API_FREE])(tn);
  if(ok){char line[160];snprintf(line,sizeof(line),"timing %s=%.6g",name,*out);bootlog(line);}
  return ok&&isfinite(*out)&&*out>0;
}

static int list_count(void *list);
static void *list_item(void *list,int index);
static void *pick_method(void *klass,const char *name,const char **types,int count);
typedef struct {int detail,index,count;char name[128];} StoryContract;
_Static_assert(sizeof(StoryContract)==140,"Story contract ABI");
static int story_scalar(void *obj,const char *name,double value){
 void *field=find_field_obj(obj,name);if(!field||!isfinite(value))return 0;
 void *type=((void *(*)(void *))api[API_FIELD_TYPE])(field);
 char *tn=((char *(*)(void *))api[API_TYPE_NAME])(type);int ok=0;
 size_t off=((size_t (*)(void *))api[API_FIELD_OFFSET])(field);
 if(tn&&!strcmp(tn,"System.Double")){*(double *)((char *)obj+off)=value;ok=1;}
 else if(tn&&!strcmp(tn,"System.Single")){*(float *)((char *)obj+off)=(float)value;ok=1;}
 if(tn)((void (*)(void *))api[API_FREE])(tn);return ok;
}
static int story_int(void *obj,const char *name,int *value){
 void *f=find_field_obj(obj,name);if(!f)return 0;
 *value=*(int *)((char *)obj+((size_t (*)(void *))api[API_FIELD_OFFSET])(f));return 1;
}
static void *private_story_metadata(Skin *skin){
 if(skin->storyTarget)return skin->storyTarget;
 if(!g_json)return NULL;
 const char *id=g_rows[skin->row].identity;
 for(const char *q=id;*q;q++)if(!((*q>='0'&&*q<='9')||(*q>='A'&&*q<='Z')||(*q>='a'&&*q<='z')||*q=='_'))return NULL;
 wchar_t path[32768];GetModuleFileNameW(g_self,path,32768);wchar_t *tail=wcsrchr(path,L'\\');if(!tail)return NULL;
 wsprintfW(tail+1,L"Assets\\runtime\\story_native\\%S.bin",id);
 HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);
 if(file==INVALID_HANDLE_VALUE)return NULL;
 uint32_t h[4];DWORD got=0;int valid=ReadFile(file,h,16,&got,NULL)&&got==16&&h[0]==0x31545353&&h[1]==1&&h[2]>0&&h[2]<=512&&h[3]>0&&h[3]<=1048576;
 char *buffer=NULL;size_t length=0;
 if(valid){length=(size_t)h[2]*sizeof(StoryContract)+h[3];buffer=HeapAlloc(GetProcessHeap(),0,length+1);valid=buffer&&ReadFile(file,buffer,(DWORD)length,&got,NULL)&&got==length;}
 CloseHandle(file);if(!valid){if(buffer)HeapFree(GetProcessHeap(),0,buffer);return NULL;}
 buffer[length]=0;StoryContract *contracts=(StoryContract *)buffer;char *json=buffer+h[2]*sizeof(StoryContract);
 void *klass=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"","MotionMetadataList");
 void *utility=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_json,"UnityEngine","JsonUtility");
 const char *types[]={"System.String","System.Type"};void *from=utility?pick_method(utility,"FromJson",types,2):NULL;
 void *text=make_string(json);uintptr_t textRoot=ui_root(text);
 void *type=klass?((void *(*)(void *))api[API_TYPE_OBJECT])(((void *(*)(void *))api[API_CLASS_TYPE])(klass)):NULL;
 uintptr_t typeRoot=ui_root(type);void *result=NULL;uintptr_t resultRoot=0;int ok=0;
 if(from&&textRoot&&typeRoot){void *args[]={text,type};result=call_obj(from,NULL,args,&ok);if(ok&&result)resultRoot=ui_root(result);}
 ui_unroot(textRoot);ui_unroot(typeRoot);
 if(!resultRoot)valid=0;
 void *details=resultRoot?rfield(result,"motionList"):NULL;
 int detailCount=details?list_count(details):0;if(detailCount<=0||detailCount>128)valid=0;
 int pinkyOptionalMissing=0;
 for(uint32_t i=0;valid&&i<h[2];i++){
  StoryContract *c=&contracts[i];if(c->detail<0||c->index<0||c->count<=0||c->index>=c->count||!memchr(c->name,0,128)){valid=0;break;}
  int optionalPinky=c->detail==13&&c->index==0&&c->count==1&&!strcmp(id,"story_1318_Pinky_DiscipleAppearance")&&!strcmp(c->name,"Pinky_Disciple_S7_Timeline_1");
  int actual=-1;if(motion_count(skin->app,c->detail,&actual)!=c->count||actual!=c->detail){
   if(optionalPinky){pinkyOptionalMissing=1;continue;}
   valid=0;break;
  }
  int detail=c->detail;uint8_t flag=0;void *ma[]={&detail,&flag};
  g_motionDepth++;void *motion=call_obj(m_getMotion,skin->app,ma,&ok);g_motionDepth--;
  void *timelines=motion?rfield(motion,"timelineAssets"):NULL,*timeline=timelines?list_item(timelines,c->index):NULL;
  void *getName=timeline?find_method(ui_class(timeline),"get_name",0):NULL;
  void *name=getName?call_obj(getName,timeline,NULL,&ok):NULL;char actualName[128];
  if(!ok||!string_ascii(name,actualName,128)||strcmp(actualName,c->name)){
   if(optionalPinky){pinkyOptionalMissing=1;continue;}
   valid=0;break;
  }
  void *durationMethod=find_method(ui_class(timeline),"get_duration",0);
  void *durationBox=durationMethod?call_obj(durationMethod,timeline,NULL,&ok):NULL;
  double duration=ok&&durationBox?*(double *)ui_unbox(durationBox):0;
  if(!isfinite(duration)||duration<=0||duration>600){valid=0;break;}
  void *data=NULL;
  for(int j=0;j<detailCount;j++){
   void *item=list_item(details,j);int value=-1;
   if(item&&story_int(item,"motionDetail",&value)&&value==detail){data=rfield(item,"motionTimelineDatas");break;}
  }
  if(!data||list_count(data)!=c->count){valid=0;break;}
  void *item=list_item(data,c->index);if(!item||!story_scalar(item,"duration",duration)){valid=0;break;}
  /* Native projection requires a real end marker; never write game database objects. */
  void *field=find_field_obj(item,"endMarkerTime");
  if(!field){valid=0;break;}
  void *value=((void *(*)(void *,void *))api[API_FIELD_VALUE])(field,item);
  uintptr_t valueRoot=ui_root(value);
  void *ft=((void *(*)(void *))api[API_FIELD_TYPE])(field);char *tn=((char *(*)(void *))api[API_TYPE_NAME])(ft);
  double end=0;if(value&&tn&&!strcmp(tn,"System.Double"))end=*(double *)ui_unbox(value);
  else if(value&&tn&&!strcmp(tn,"System.Single"))end=*(float *)ui_unbox(value);else valid=0;
  if(tn)((void (*)(void *))api[API_FREE])(tn);
  ui_unroot(valueRoot);
  if(valid&&end<0)valid=story_scalar(item,"endMarkerTime",duration);
 }
 if(valid){
  unsigned char allowed[SR_MOTION_CACHE]={0};
  for(uint32_t i=0;i<h[2];i++)if(contracts[i].detail>=0&&contracts[i].detail<SR_MOTION_CACHE)allowed[contracts[i].detail]=1;
  if(pinkyOptionalMissing){allowed[13]=0;bootlog("Pinky S7 duplicate resolved to unavailable motion; remaining contracts validated");}
  sr_story_attack_mask(skin->motionCounts,allowed);
 }
 HeapFree(GetProcessHeap(),0,buffer);
 if(!valid){ui_unroot(resultRoot);bootlog("story metadata validation failed; original appearance retained");return NULL;}
 skin->storyTarget=result;skin->storyRoot=resultRoot;bootlog("private story metadata validated");return result;
}
static int normalize_source_name(const char *id,char *name){
 if(!id||!name||strlen(id)!=5)return 0;
 for(int i=0;i<5;i++)if(id[i]<'0'||id[i]>'9')return 0;
 if(strncmp(name,id,5)||name[5]!='_')return 0;
 char *suffix=strstr(name,"(Clone)");if(suffix&&suffix[7]==0)*suffix=0;
 int len=(int)strlen(name);while(len>0&&name[len-1]==' ')name[--len]=0;
 return len>6;
}
/* Attack-like duel slots do not have attack timing contracts. Query the native
   motion itself once at prewarm/switch, including timeline-less Spine defenses. */
static void cache_clash_roles(Skin *skin){
 for(int d=0;d<SR_MOTION_CACHE;d++){
  if(d!=4&&!defenseMotions[d]&&!is_parry_detail(d)&&!(d>=20&&d<=22)&&d!=32&&d!=33&&!sr_clash_role(skin->look,d))continue;
  uint8_t flag=0;int requested=d,ok=0;void *args[]={&requested,&flag};
  g_motionDepth++;void *motion=call_obj(m_getMotion,skin->app,args,&ok);g_motionDepth--;
  int available=0,actual=-1;
  if(ok&&motion){
   int count=timeline_count(motion,&actual);
   if(actual==d){
    if(count>0&&count<=1024){
     void *list=rfield(motion,"timelineAssets");int valid=0;
     for(int k=0;k<count;k++)if(list_item(list,k))valid++;
     skin->clashCount[d]=(short)count;
     if(valid==count)available=1;
     else if(valid)skin->clashSparse[d]=list;
    }
    void *f=find_field_obj(motion,"isSpineAnim");
    if(f&&*(uint8_t *)((char*)motion+((size_t (*)(void*))api[API_FIELD_OFFSET])(f)))available=1;
   }
  }
  skin->chapterRole[d]=available?1:-1;
 }
}
static void *skin_metadata(Unit *u,Skin *s){
  const SrChapterActor *actor=u&&g_rows[s->row].story&&!strcmp(s->look,g_rows[s->row].appearance_name)?
   sr_chapter_actor(u->baseName,s->look):NULL;
  if(s->meta&&s->chapterActor==actor)return s->meta;
  if(!u||(!actor&&!g_metadataDB))return NULL;
  void *getter=!actor?find_method(ui_class(g_metadataDB),"GetMotionMetadataList",1):NULL;
  if(!actor&&!getter)return NULL;
  int ok=1;void *source=NULL;
  if(!actor){
   void *name=make_string(u->baseName);uintptr_t nameRoot=ui_root(name);
   void *args[]={name};
   source=call_obj(getter,g_metadataDB,args,&ok);ui_unroot(nameRoot);
   if((!ok||!source)&&strlen(u->baseName)==5){
    void *gg=find_method(ui_class(u->baseApp),"get_gameObject",0);int good=1;
    void *go=gg?call_obj(gg,u->baseApp,NULL,&good):NULL;
    void *gn=go?find_method(ui_class(go),"get_name",0):NULL;
    void *sv=gn?call_obj(gn,go,NULL,&good):NULL;char fullname[128]={0};
    if(good&&sv&&string_ascii(sv,fullname,sizeof(fullname))&&normalize_source_name(u->baseName,fullname)){
     void *fallback=make_string(fullname);uintptr_t root=ui_root(fallback);void *fa[]={fallback};ok=1;
     source=call_obj(getter,g_metadataDB,fa,&ok);ui_unroot(root);
     if(ok&&source){lstrcpynA(u->baseName,fullname,sizeof(u->baseName));bootlog("metadata: resolved source from native GameObject name");}
    }
   }
   if(!ok||!source){char line[160];wsprintfA(line,"metadata: source missing base=%.40s",u->baseName);bootlog(line);return NULL;}
  }
  void *target=NULL;
  if(g_rows[s->row].story){target=private_story_metadata(s);ok=target!=NULL;}
  else{
   void *targetName=make_string(s->look);uintptr_t targetRoot=ui_root(targetName);
   void *targs[]={targetName};target=call_obj(getter,g_metadataDB,targs,&ok);ui_unroot(targetRoot);
  }
  if(!ok||!target){char line[160];wsprintfA(line,"metadata: target missing look=%.40s",s->look);bootlog(line);return NULL;}
  void *container=ui_new(c_containerClass);
  if(!container)return NULL;
  uintptr_t root=ui_root(container);
  void *ctor=find_method(ui_class(container),".ctor",2);
  /* For chapter pairs, native relative-speed evaluation compares the enemy
     clip with itself. The shared game metadata database stays untouched. */
  void *cargs[]={actor?target:source,target};
  if(!call_exc(ctor,container,cargs)){bootlog("metadata: container ctor failed");ui_unroot(root);return NULL;}

  ui_unroot(s->metaRoot);s->meta=container;s->metaRoot=root;s->chapterActor=actor;
  return container;
}

/* ---------------- presentation ---------------- */
static int release_owned_appearance_camera(void *app);
static void *m_cameraSingleton;
static void *g_duelCameraBoundary;
static void *camera_manager(void){
 if(!m_cameraSingleton){
  void *k=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"","BattleCamManager");
  m_cameraSingleton=k?find_method(k,"get_Instance",0):NULL;
 }
 int ok=0;return m_cameraSingleton?call_obj(m_cameraSingleton,NULL,NULL,&ok):NULL;
}
static int camera_scope_active(void){
 if(!m_cameraSingleton){
  void *k=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"","BattleCamManager");
  m_cameraSingleton=k?find_method(k,"get_Instance",0):NULL;
 }
 int ok=0;void *manager=m_cameraSingleton?call_obj(m_cameraSingleton,NULL,NULL,&ok):NULL;
 /* If the authoritative scope cannot be queried, retain conservative protection. */
 if(!ok||!manager)return g_anyViewerActive;
 if(rfield(manager,"_zoomActorAloneV2Owner"))return 1;
 void *current=rfield(manager,"_curCam");if(!current)return 0;
 for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used&&!g_units[i].dead){
  Unit *u=&g_units[i];void *now=rfield(u->view,"_curAppearance");Skin *held=held_appearance(u);
  void *apps[]={now,u->baseApp,held?held->app:NULL};
  for(int j=0;j<3;j++){
   void *app=apps[j];if(!app)continue;
   int duplicate=0;for(int k=0;k<j;k++)duplicate|=apps[k]==app;if(duplicate)continue;
   void *controller=rfield(app,"_camController");if(!controller)continue;
   if(current==rfield(controller,"camera_Actor")||current==rfield(controller,"camera_Enemy"))return 1;
  }
 }
 return 0;
}
static void *m_directorState;
static int director_playing(void *app){
 void *director=rfield(app,"_playableDirector");if(!director)return 0;
 if(!m_directorState)m_directorState=find_method(ui_class(director),"get_state",0);
 return m_directorState&&call_int(m_directorState,director,NULL)==1;
}
/* End evidence is scoped to the exact native playback generation/director. */
static void playback_begin(void *app){
 Unit *u=unit_for_app(app);if(!u)return;
 ++u->playbackGeneration;u->endedApp=NULL;u->endedDirector=NULL;
}
static int presentation_busy(void *app){
  if(!app)return 0;
  void *flag=find_field_obj(app,"_isRunningTimeline");
  if(flag && *(uint8_t *)((char *)app+((size_t (*)(void *))api[API_FIELD_OFFSET])(flag)))return 1;
  if(rfield(app,"_curAction"))return 1;
  if(rfield(app,"_activeTimelineDelayReleaseCallback"))return 1;
  if(director_playing(app))return 1;
  return 0;
}
static void finish_presentation(void *app){
  if(!app)return;
  if(!release_owned_appearance_camera(app))bootlog("appearance camera cleanup deferred; owner check failed");
  if(m_cancelDelay)call_exc(m_cancelDelay,app,NULL);
  if(m_resetTimeline)call_exc(m_resetTimeline,app,NULL);
}
static int set_active(void *go,uint8_t value){
  if(!go||!m_setActive)return 0;
  void *args[]={&value};return call_exc(m_setActive,go,args);
}
static int go_active_self(void *go){return go?call_bool(m_getActiveSelf,go,NULL):-1;}
/* Visual-only donors keep the source timeline alive; hide only the source
   Spine renderers and restore the exact prior enabled state on exit. */
#include "static_appearance_policy.h"
#include "visible_attack.inc"
static void *app_go(void *app);

static void static_restore_renderers(Unit *u){
 if(!u||!u->staticHidden)return;
 for(size_t i=0;i<u->staticRendererCount;i++){
  void *r=u->staticRenderers[i];
  void *set=find_method(ui_class(r),"set_forceRenderingOff",1);
  uint8_t old=u->staticRendererEnabled[i];void *args[]={&old};call_exc(set,r,args);
 }
 HeapFree(GetProcessHeap(),0,u->staticRendererEnabled);u->staticRendererEnabled=NULL;u->staticRenderers=NULL;
 ui_unroot(u->staticArrayRoot);u->staticArrayRoot=0;
 u->staticHidden=0;u->staticRendererCount=0;
}
static int mask_renderer_array(Unit *u,void *array){
 uintptr_t n=((uintptr_t *)array)[3];
 u->staticArrayRoot=ui_root(array);if(!u->staticArrayRoot)return 0;
 u->staticRendererEnabled=HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,n?n:1);
 if(!u->staticRendererEnabled){ui_unroot(u->staticArrayRoot);u->staticArrayRoot=0;return 0;}
 u->staticRenderers=(void **)array+4;
 u->staticHidden=1;
 for(uintptr_t i=0;i<n;i++){
  void *r=((void **)array)[4+i];
  void *get=r?find_method(ui_class(r),"get_forceRenderingOff",0):NULL;
  void *set=r?find_method(ui_class(r),"set_forceRenderingOff",1):NULL;
  int old=get?call_bool(get,r,NULL):-1;
  uint8_t off=1;void *values[]={&off};
  if(old<0||!set||!call_exc(set,r,values)){static_restore_renderers(u);return 0;}
  u->staticRendererEnabled[u->staticRendererCount++]=(uint8_t)old;
 }
 return 1;
}
static int static_hide_renderers(Unit *u){
 if(u->staticHidden)return 1;
 void *go=app_go(u->baseApp);if(!go)return 0;
 const char *types[]={"System.Type","System.Boolean"};
 void *getAll=pick_method(ui_class(go),"GetComponentsInChildren",types,2);
 void *klass=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_core,"UnityEngine","Renderer");if(!klass||!getAll)return 0;
 void *type=((void *(*)(void *))api[API_TYPE_OBJECT])(((void *(*)(void *))api[API_CLASS_TYPE])(klass));
 uint8_t includeInactive=1;void *args[]={type,&includeInactive};
 void *array=call_obj(getAll,go,args,NULL);if(!array)return 0;
 return mask_renderer_array(u,array);
}
static void *app_go(void *app){
  if(!app)return NULL;
  void *getter=find_method(ui_class(app),"get_gameObject",0);
  int ok=1;return call_obj(getter,app,NULL,&ok);
}
static void sync_visibility(Unit *u){
  if(!u||!u->view)return;
  if(g_presentationGate&&enabled_now())return;
  void *current=rfield(u->view,"_curAppearance");
  if(!current)return;
  Skin *visible=skin_for_app(u,current);
  int visualOnly=visible && (g_rows[visible->row].excluded&SR_STATIC_APPEARANCE_FLAG);
  if(visible){static_hide_renderers(u);}else if(!held_appearance(u)||current!=u->baseApp||!enabled_now())static_restore_renderers(u);
  void *apps[SR_SKIN_MAX+1];int total=0;
  apps[total++]=u->baseApp;
  for(int k=0;k<SR_SKIN_MAX;k++)if(u->skins[k].used)apps[total++]=u->skins[k].app;
  for(int i=0;i<total;i++){
    void *app=apps[i];if(!app)continue;
    void *go=app_go(app);if(!go)continue;
    Skin *held=current==u->baseApp&&u->staticHidden&&enabled_now()?held_appearance(u):NULL;
    int show=(app==current)||(visualOnly&&app==u->baseApp)||(held&&app==held->app);
    int active=go_active_self(go);
    /* A native viewer may temporarily use the base/another appearance.
       Never cancel its callbacks or deactivate a playing director. */
    if(!show&&presentation_busy(app))continue;
    if(active!=-1 && (active==1)!=show)set_active(go,show?1:0);
  }
}
static void mark_bad(Unit *u,int row);
static void disable_failed_form(Unit *u,int row,int form);
static void poll_paired_native(Unit *u);
static void *unit_switch(Unit *u,Skin *skin){
  if(!u||!u->view||!m_changeAppearance)return NULL;
  if(g_presentationGate&&enabled_now())return NULL;
  if(skin&&!(g_rows[skin->row].excluded&SR_STATIC_APPEARANCE_FLAG)&&((g_cfg&&g_cfg->mode==1)||g_rows[skin->row].story||(g_rows[skin->row].excluded&SR_AUTO_FLAG))){
    void *metadata=skin_metadata(u,skin);
    if(!metadata||!set_ref(skin->app,"_skinMetadataContainer",metadata)){if(skin->form)disable_failed_form(u,skin->row,skin->form);else mark_bad(u,skin->row);return NULL;}
  }
  void *desired=skin?skin->app:u->baseApp;
  void *current=rfield(u->view,"_curAppearance");
  if(!desired)return NULL;
  int hadMask=u->staticHidden;
  if(skin&&!static_hide_renderers(u)){bootlog("donor switch skipped: could not mask source renderers");return NULL;}
  if(current==desired){if(skin)u->last=(int)(skin-u->skins);return desired;}
  /* A draw can replace the native appearance before the first periodic poll. */
  if(skin&&current&&!u->nativeValid)poll_paired_native(u);
  u->switching=1;
  void *result=NULL;
  /* At a verified duel-owned camera boundary, keep the duel camera alive.
     The caller has required all timeline/delegate flags to be clear. */
  if(current&&!g_duelCameraBoundary)finish_presentation(current);
  const char *text=skin?skin->rid:u->baseName;
  void *name=make_string(text);uintptr_t nameRoot=ui_root(name);
  uint8_t flag=0;void *args[]={name,&flag};
  int ok=call_exc(m_changeAppearance,u->view,args);
  ui_unroot(nameRoot);
  void *actual=rfield(u->view,"_curAppearance");
  if(ok&&actual==desired){
    if(skin&&!(g_rows[skin->row].excluded&SR_STATIC_APPEARANCE_FLAG)&&((g_cfg&&g_cfg->mode==1)||g_rows[skin->row].story||(g_rows[skin->row].excluded&SR_AUTO_FLAG))&&!set_ref(desired,"_skinMetadataContainer",skin->meta)){ok=0;}
    else {result=desired;if(skin)u->last=(int)(skin-u->skins);}
  }
  if(!result&&!hadMask&&actual==u->baseApp)static_restore_renderers(u);
  sync_visibility(u);
  u->switching=0;
  return result;
}

/* The game may select the base skin at action/round end. Repair that on
   the render thread, preserving temporary E.G.O or other special appearances. */
static int motion_busy_mask(void *app);
static void retain_last_appearance(Unit *u){
 Skin *held=held_appearance(u);
 if(!held||introUnit==u||cleanup_pending||!enabled_now())return;
 void *current=rfield(u->view,"_curAppearance");
 if(!rfield(held->app,"m_CachedPtr")){u->last=-1;return;}
 void *action=rfield(u->view,"_currentActionLog");
 int repeated=0; /* Native idle selection may restore the base more than once per action. */
 int isPairedNative=u->nativeValid && current==u->nativeAppearance && held->row>=0 && (uint32_t)held->row<g_rowCount &&
  (sr_counterpart_member(sr_counterpart_form(u->baseName),g_rows[held->row].identity)||
   (!strncmp(u->baseName,"10314",5)&&(!strcmp(g_rows[held->row].identity,"story_1325_Index_Disciple_NormalAppearance")||!strcmp(g_rows[held->row].identity,"story_1325_Index_discipleAppearance"))) ||
   (!strncmp(u->baseName,"10215",5)&&(!strcmp(g_rows[held->row].identity,"story_1319_RingFinger_DiscipleAppearance")||!strcmp(g_rows[held->row].identity,"story_1336_RingFinger_Disciple_CastoffAppearance"))));
 if(!sr_idle_restore_ready(u->viewerActive||g_presentationGate,current==u->baseApp||isPairedNative,
     ((motion_busy_mask(current)&7)!=0),((motion_busy_mask(held->app)&7)!=0),repeated,&u->idleRestoreFrames)){
  static DWORD lastReport[SR_UNIT_MAX];int slot=(int)(u-g_units);DWORD now=GetTickCount();
  if(current!=held->app&&slot>=0&&slot<SR_UNIT_MAX&&(DWORD)(now-lastReport[slot])>=5000){
   lastReport[slot]=now;char line[256];snprintf(line,sizeof(line),"idle blocked sinner=%lu atBase=%d viewer=%d camera=%d currentMask=%d donorMask=%d last=%d",(unsigned long)u->sinner,current==u->baseApp,u->viewerActive,g_presentationGate,motion_busy_mask(current),motion_busy_mask(held->app),u->last);bootlog(line);
  }
  return;
 }
 if(unit_switch(u,held)){
  g_motionDepth++;
 playback_begin(held->app);
  ((void (*)(void *,int,uint8_t,int,uint8_t,void *,uint8_t,void *))orig_changeMotion)(held->app,0,0,0,0,NULL,0,m_changeMotion);
  g_motionDepth--;
  u->retainConsumed=1;u->retainedAction=action;u->retainedApp=held->app;u->idleRestoreFrames=0;
  bootlog("last random appearance retained after viewer and both timelines ended");
 }
}
#include "animation_time_cache.h"
static void cache_ordinary_clips(void *app,uint32_t mask[128],Skin *donor){
 memset(mask,0,128*sizeof(*mask));
 void *list=rfield(app,"motionList");int count=list?list_count(list):0;
 if(count<1||count>1024)return;
 for(int i=0;i<count;i++){
  void *motion=list_item(list,i);int d=-1,n=timeline_count(motion,&d);
  if(!is_skill_detail(d)||defenseMotions[d]||n<1||n>TC_COINS)continue;
  void *assets=rfield(motion,"timelineAssets");
  for(int k=0;k<n;k++){
   void *tl=list_item(assets,k);int ok=0;char name[128];
   void *getter=tl?find_method(ui_class(tl),"get_name",0):NULL;
   void *text=getter?call_obj(getter,tl,NULL,&ok):NULL;
   if(!ok||!string_ascii(text,name,sizeof(name))||!sr_ordinary_timeline(name))continue;
   mask[d]|=UINT32_C(1)<<k;
   if(donor){
    unsigned body=sr_ordinary_body_class(donor->look,d,k);
    if(body){
     if(!donor->ordinaryBodies)donor->ordinaryBodies=HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,sizeof(*donor->ordinaryBodies));
     if(donor->ordinaryBodies)donor->ordinaryBodies->classes[sr_attack_group_slot(d)][k]=body;
    }
   }
  }
 }
}
/* A row can load another resource for a later form. Authored mappings describe
   the named resource and apply only while that resource is on screen. */
static const char *motion_identity(Skin *skin){
 PoolRow *row=&g_rows[skin->row];
 return strcmp(skin->look,row->appearance_name)?"":row->identity;
}
static const char *paired_source(Unit *unit,Skin *skin){
 const SrCounterpartForm *form=sr_counterpart_form(unit->baseName);
 if(unit->nativeValid&&sr_counterpart_member(form,motion_identity(skin)))
  return unit->nativeStage==1?form->alternate:form->normal;
 return unit->baseName;
}
static void cache_skin_motions(Skin *skin){
 void *list=rfield(skin->app,"motionList");int count=list_count(list);
 if(count<0||count>1024)return;
 for(int i=0;i<count;i++){
  void *motion=list_item(list,i);if(!motion)continue;
  int detail=-1,n=timeline_count(motion,&detail);
  if(detail>=0&&detail<SR_MOTION_CACHE&&n>0){
   void *timelines=rfield(motion,"timelineAssets");int complete=1;
   for(int j=0;j<n;j++)if(!list_item(timelines,j)){complete=0;break;}
   if(complete)skin->motionCounts[detail]=n;
  }
 }
}
/* Resolve through the game's own fallback map once, outside playback hooks. */
static void cache_native_motion_map(Skin *skin){
 for(int d=0;d<SR_MOTION_CACHE;d++)skin->nativeMotionDetail[d]=-1;
 for(int d=0;d<SR_MOTION_CACHE;d++){
  if(!((d>=7&&d<=16)||(d>=24&&d<=34)))continue;
  int actual=-1;motion_count(skin->app,d,&actual);
  if(((actual>=7&&actual<=16)||(actual>=24&&actual<=34))&&skin->motionCounts[actual]>0){
   skin->nativeMotionDetail[d]=actual;
   if(actual!=d){char line[192];snprintf(line,sizeof(line),"native motion mapping look=%.63s requested=%d resolved=%d",skin->look,d,actual);bootlog(line);}
  }
 }
}
/* ---------------- skin construction ---------------- */
static void *g_loadBox;static uintptr_t g_loadRoot;static DWORD g_loadStart;static Unit *g_loadUnit;static int g_loadRow;static int g_loadActive;static int g_loadStatus;
static int g_loadForm;
static char g_loadLook[64];
static void *g_loadView;
static int loading_row(Unit *u,int row){return g_loadActive && g_loadUnit==u && g_loadRow==row;}
static int loading_form(Unit *u,int row,int form){return loading_row(u,row)&&g_loadForm==form;}
static int g_creating;
static int g_ready;
typedef struct {void *go;void *handleBox;uintptr_t handleRoot;} Retire;
static Retire g_retire[SR_RETIRE_MAX];
static int g_retireAfter[SR_RETIRE_MAX];
static int g_retireCount;

static void retire_slot(void *go,void *handleBox,uintptr_t handleRoot){
  if(g_retireCount==SR_RETIRE_MAX){bootlog("retire queue full; ownership retained rather than releasing early");return;}
  if(go){void *args[]={go};if(!call_exc(m_destroyObject,NULL,args)){bootlog("Destroy failed; resource root retained");return;}}
  g_retire[g_retireCount]=(Retire){NULL,handleBox,handleRoot};
  g_retireAfter[g_retireCount]=g_frame+2;g_retireCount++;
}
static void retire_skin(Skin *s){
  if(!s->used)return;
  if(s->app)release_owned_appearance_camera(s->app);
  if(s->go){
    int ok=1;void *args[]={s->go};
    call_obj(m_destroyObject,NULL,args,&ok);
  }
  retire_slot(NULL,s->handleBox,s->handleRoot);
  if(s->ordinaryBodies)HeapFree(GetProcessHeap(),0,s->ordinaryBodies);
  ui_unroot(s->appRoot);ui_unroot(s->goRoot);ui_unroot(s->metaRoot);ui_unroot(s->storyRoot);
  memset(s,0,sizeof(*s));
}
static void collect_retire(void){
  for(int i=g_retireCount-1;i>=0;i--){
    if(g_frame<g_retireAfter[i])continue;
    if(g_retire[i].handleBox&&m_releaseGO){
      void *args[]={ui_unbox(g_retire[i].handleBox)};
      if(!call_exc(m_releaseGO,NULL,args)){bootlog("retire Release failed; retaining root for retry");continue;}
    }
    ui_unroot(g_retire[i].handleRoot);
    g_retire[i]=g_retire[g_retireCount-1];
    g_retireAfter[i]=g_retireAfter[g_retireCount-1];
    g_retireCount--;
  }
}

static void mark_bad(Unit *u,int row){
  if(!unit_bad(u,row)&&u->nbad<SR_CAND_MAX)u->bad[u->nbad++]=row;
}
static Skin *replaceable_skin(Unit *u){
 void *current=rfield(u->view,"_curAppearance");
 for(int k=0;k<SR_SKIN_MAX;k++){
  Skin *s=&u->skins[k];
  if(!s->used||s->app==current||k==u->last||presentation_busy(s->app))continue;
  if((s->row==u->pending||s->row==u->wanted)&&s->form==desired_row_form(u,s->row))continue;
  if(g_cfg&&g_cfg->mode==1&&warm_cache_required(u,s->row,s->form))continue;
  int queued=0;for(int j=0;j<u->motionCount;j++)if(u->motions[j].source==s->app||u->motions[j].row==s->row)queued=1;
  if(!queued)return s;
 }
 return NULL;
}
static int build_skin(Unit *u,int row){
  PoolRow *entry=&g_rows[row];
  int ok=1;
  void *handleBox=g_loadBox;
  void *type=ui_class(handleBox);
  void *getResult=find_method(type,"get_Result",0);
  void *prefab=call_obj(getResult,ui_unbox(handleBox),NULL,&ok);
  if(!ok||!prefab){bootlog("skin build: missing result");return 0;}
  uintptr_t prefabRoot=ui_root(prefab);
  void *instArgsBase[3];
  int world=0;
  int pivotOk=1;
  void *pivotParent=call_obj(m_getSkinPivot,u->view,NULL,&pivotOk);
  void *stagingParent=(pivotOk&&pivotParent)?pivotParent:g_stagingTr;
  instArgsBase[0]=prefab;instArgsBase[1]=stagingParent;instArgsBase[2]=&world;
  void *cloneGO=call_obj(m_instantiate,NULL,instArgsBase,&ok);
  if((!ok||!cloneGO)&&stagingParent){
    void *retry[3]={prefab,NULL,&world};
    ok=1;cloneGO=call_obj(m_instantiate,NULL,retry,&ok);
    bootlog("skin build: instantiate retried without staging parent");
  }
  ui_unroot(prefabRoot);
  if(!ok||!cloneGO){
    char line[160];wsprintfA(line,"skin build: instantiate failed method=%d ok=%d go=%d",!!m_instantiate,ok,!!cloneGO);
    bootlog(line);return 0;
  }
  uintptr_t cloneRoot=ui_root(cloneGO);
  set_active(cloneGO,0);
  void *tr=call_obj(m_getTransform,cloneGO,NULL,&ok);
  if(!ok||!tr){bootlog("skin build: transform missing");retire_slot(cloneGO,NULL,0);ui_unroot(cloneRoot);return 0;}
  if(stagingParent!=pivotParent){
    void *pivot=call_obj(m_getSkinPivot,u->view,NULL,&ok);
    if(!ok||!pivot){bootlog("skin build: pivot missing");retire_slot(cloneGO,NULL,0);ui_unroot(cloneRoot);return 0;}
    uint8_t local=0;void *parentArgs[]={pivot,&local};
    int parentOk=call_exc(m_setParent,tr,parentArgs);
    if(!m_setParent||!parentOk){
      char line[192];wsprintfA(line,"skin build: setparent failed method=%d ok=%d tr=%d pivot=%d staging=%d",!!m_setParent,parentOk,!!tr,!!pivot,!!g_stagingTr);
      bootlog(line);
      retire_slot(cloneGO,NULL,0);ui_unroot(cloneRoot);return 0;
    }
  }
  void *compArgs[]={t_appearance};
  void *app=call_obj(m_getComponent,cloneGO,compArgs,&ok);
  if(!ok||!app){bootlog("skin build: appearance missing");retire_slot(cloneGO,NULL,0);ui_unroot(cloneRoot);return 0;}
  uintptr_t appRoot=ui_root(app);
  set_active(cloneGO,1);
  void *spines=rfield(app,"_spineSkins");
  if(spines){
    int count=list_count(spines);
    for(int i=0;i<count&&i<256;i++){
      void *spine=list_item(spines,i);
      if(spine&&!rfield(spine,"_spine_renderer")){
        void *start=find_method(ui_class(spine),"Start",0);
        if(start)call_exc(start,spine,NULL);
      }
    }
  }
  void *initArgs[]={u->view};
  g_creating++;
  int initOk=call_exc(m_init,app,initArgs);
  g_creating--;
  if(!initOk){char line[224];snprintf(line,sizeof(line),"skin build: Initialize exception sinner=%lu row=%d identity=%.40s look=%.64s",(unsigned long)u->sinner,row,entry->identity,entry->appearance_name);bootlog(line);ui_unroot(appRoot);ui_unroot(cloneRoot);retire_slot(cloneGO,NULL,0);return 0;}
  int initialized=0;
  void *flag=find_field_obj(app,"_isInitialized");
  if(flag)initialized=*(uint8_t *)((char *)app+((size_t (*)(void *))api[API_FIELD_OFFSET])(flag));
  void *charInfo=rfield(app,"charInfo");
  {char line[160];wsprintfA(line,"skin build: init ok flag=%d value=%d charInfo=%d spines=%d",!!flag,initialized,!!charInfo,!!rfield(app,"_spineSkins"));bootlog(line);}
  if(!initialized){bootlog("skin build: not initialized");ui_unroot(appRoot);ui_unroot(cloneRoot);retire_slot(cloneGO,NULL,0);return 0;}
  Skin motionProbe={0};
  if(entry->excluded&SR_AUTO_FLAG){
    motionProbe.app=app;cache_skin_motions(&motionProbe);
    if(!motionProbe.motionCounts[7]||!motionProbe.motionCounts[8]||!motionProbe.motionCounts[9]){
      bootlog("automatic identity missing basic attack timelines; rejected");
      ui_unroot(appRoot);ui_unroot(cloneRoot);retire_slot(cloneGO,NULL,0);return 0;
    }
  }
  Skin *slot=skin_count(u)<skin_limit()?skin_alloc(u):NULL;
  if(!slot){
    slot=replaceable_skin(u);
    if(!slot){ui_unroot(appRoot);ui_unroot(cloneRoot);retire_slot(cloneGO,NULL,0);return -1;}
    void *list=rfield(u->view,"_appearances");if(list)list_remove(list,slot->app);
    retire_skin(slot);
  }
  if(!slot){bootlog("skin build: no slot after evict");ui_unroot(appRoot);ui_unroot(cloneRoot);retire_slot(cloneGO,NULL,0);return 0;}
  memset(slot,0,sizeof(*slot));
  slot->used=1;slot->row=row;slot->form=g_loadForm;slot->app=app;slot->go=cloneGO;slot->appRoot=appRoot;slot->goRoot=cloneRoot;
  lstrcpynA(slot->look,g_loadLook,64);
  wsprintfA(slot->rid,"%.40s_SRN_%lu_%d",entry->identity,(unsigned long)g_frame,row);
  void *info=rfield(app,"charInfo");
  if(info){
    void *newID=make_string(slot->rid);
    set_ref(info,"appearanceID",newID);
  }
  set_active(cloneGO,0);
  void *list=rfield(u->view,"_appearances");
  if(!list || !list_add(list,app)){
    bootlog("skin build: list add failed");retire_skin(slot);return 0;
  }
  if(entry->excluded&SR_AUTO_FLAG)memcpy(slot->motionCounts,motionProbe.motionCounts,sizeof(slot->motionCounts));
  else cache_skin_motions(slot);
  if(g_cfg&&g_cfg->mode==1&&!(entry->excluded&SR_STATIC_APPEARANCE_FLAG)){
    /* Build story metadata first: it masks out attacks without valid contracts. */
    if(!skin_metadata(u,slot)||!sr_prewarm_attacks_valid(slot->motionCounts,entry->story)||
       !set_ref(slot->app,"_skinMetadataContainer",slot->meta)){
      list_remove(list,app);retire_skin(slot);bootlog("full-pool prewarm validation failed; candidate skipped");return 0;
    }
  }
  cache_clash_roles(slot);
  cache_native_motion_map(slot);
  if(!(entry->excluded&(SR_STATIC_APPEARANCE_FLAG|2))){
   cache_ordinary_clips(app,slot->ordinaryClips,slot);
   time_record(app,slot->look);
  }
  slot->handleBox=g_loadBox;slot->handleRoot=g_loadRoot;
  auto_detect_skin(slot);
  g_loads++;
  {char line[192];wsprintfA(line,"skin ready sinner=%lu row=%lu look=%.40s cached=%d",(unsigned long)u->sinner,(unsigned long)row,entry->appearance_name,skin_count(u));bootlog(line);}
  return 1;
}

/* ---------------- list helpers (per-object, generic types differ) ---------------- */
static int list_count(void *list){
  if(!list)return -1;
  void *m=find_method(ui_class(list),"get_Count",0);
  return m?call_int(m,list,NULL):-1;
}
static void *list_item(void *list,int index){
  void *m=find_method(ui_class(list),"get_Item",1);
  if(!m)return NULL;
  int ok=1;void *args[]={&index};
  return call_obj(m,list,args,&ok);
}
static int list_add(void *list,void *item){
  void *m=find_method(ui_class(list),"Add",1);
  if(!m)return 0;
  void *args[]={item};
  return call_exc(m,list,args);
}
static int list_remove(void *list,void *item){
  void *m=find_method(ui_class(list),"Remove",1);
  if(!m)return 0;
  void *args[]={item};
  return call_exc(m,list,args);
}

/* Process-lifetime Addressables warm cache. No battle-view objects are created. */
static void *g_startupAssets[SR_ROW_MAX];
static uintptr_t g_startupRoots[SR_ROW_MAX];
static int g_startupCursor,g_startupPending=-1;
static DWORD g_startupAt;
static void startup_assets_clear(void){
 for(int i=0;i<SR_ROW_MAX;i++)if(g_startupAssets[i])retire_slot(NULL,g_startupAssets[i],g_startupRoots[i]);
 memset(g_startupAssets,0,sizeof(g_startupAssets));memset(g_startupRoots,0,sizeof(g_startupRoots));
 g_startupCursor=0;g_startupPending=-1;
}
static void startup_assets_tick(void){
 static DWORD started=0,last=0;DWORD now=GetTickCount();
 if(!started){started=now;return;}
 if((DWORD)(now-started)<30000||(DWORD)(now-last)<250)return;
 last=now;
 if(!g_cfg||!g_cfg->enabled||g_cfg->mode!=1||!m_loadGO||!g_rowCount)return;
 if(g_startupPending>=0){
  int row=g_startupPending;void *box=g_startupAssets[row];void *type=ui_class(box);
  void *done=find_method(type,"get_IsDone",0);
  int ready=done?call_bool(done,ui_unbox(box),NULL):-1;
  if(ready==0&&(DWORD)(GetTickCount()-g_startupAt)<30000)return;
  int status=ready==1?call_int(find_method(type,"get_Status",0),ui_unbox(box),NULL):0;
  char line[192];snprintf(line,sizeof(line),"startup asset identity=%.63s status=%d ready=%d",g_rows[row].identity,status,ready);bootlog(line);
  if(status==1){int ok=1;void *get=find_method(type,"get_Result",0);void *prefab=get?call_obj(get,ui_unbox(box),NULL,&ok):NULL;void *args[]={t_appearance};void *app=prefab?call_obj(m_getComponent,prefab,args,&ok):NULL;if(ok&&app)time_record(app,g_rows[row].appearance_name);}
  if(status!=1){retire_slot(NULL,box,g_startupRoots[row]);g_startupAssets[row]=NULL;g_startupRoots[row]=0;}
  g_startupPending=-1;
 }
 /* Start only while no combat unit is registered; battle preparation has priority. */
 for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used&&!g_units[i].dead)return;
 int budget=0;while((uint32_t)g_startupCursor<g_rowCount&&budget++<2){
  int row=g_startupCursor++;PoolRow *entry=&g_rows[row];
  if(!entry->enabled||entry->weight<=0||g_startupAssets[row])continue;
  if(time_record(NULL,entry->appearance_name))continue; /* No asset load for an already scanned appearance. */
  void *key=make_string(entry->asset_key);uintptr_t root=ui_root(key);void *exc=NULL,*args[]={key};
  void *box=((void *(*)(void *,void *,void **,void **))api[API_INVOKE])(m_loadGO,NULL,args,&exc);ui_unroot(root);
  if(exc||!box){bootlog("startup asset request failed");continue;}
  uintptr_t handle=ui_root(box);if(!handle){retire_slot(NULL,box,0);return;}
  g_startupAssets[row]=box;g_startupRoots[row]=handle;g_startupPending=row;g_startupAt=GetTickCount();return;
 }
}

/* ---------------- loader ---------------- */
#include "auto_forms_runtime.h"
static int workbench_form_count(int row){
 if(row<0||(uint32_t)row>=g_rowCount)return 1;
 if(sr_form_index(g_rows[row].identity)>=0)return 2;
 AutoRuntime *a=auto_for_row(row);return a&&a->value.kind==1?(int)a->value.count:1;
}
#include "loader_probe_policy.h"
static LoaderProbe g_loaderProbe;
static int loader_probe_enabled(void){wchar_t p[32768];DWORD n=GetModuleFileNameW(g_self,p,32768);wchar_t *q=n&&n<32768?wcsrchr(p,L'\\'):NULL;if(!q)return 0;lstrcpyW(q+1,L"loader-observe.enable");DWORD a=GetFileAttributesW(p);return a!=INVALID_FILE_ATTRIBUTES&&!(a&FILE_ATTRIBUTE_DIRECTORY);}
static int loader_start(Unit *u,int row){
  if(!m_loadGO||!u||!u->used||u->dead||row<0||(uint32_t)row>=g_rowCount||g_rows[row].sinner!=u->sinner)return 0;
  int requested=q_poppedForm>=0?q_poppedForm:desired_row_form(u,row);
  if(skin_index_form(u,row,requested)>=0||unit_bad(u,row)||resource_form_failed(u,row,requested))return 1;
  if(skin_count(u)>=skin_limit()&&!replaceable_skin(u))return 1;
  PoolRow *entry=&g_rows[row];
  g_loadForm=requested;
  int catalog=sr_form_index(entry->identity);
  const SrFormResource *resource=g_loadForm && catalog>=0?&sr_forms[catalog]:NULL;
  lstrcpynA(g_loadLook,resource?resource->look:entry->appearance_name,64);
  const char *asset=resource?resource->asset:entry->asset_key;
  AutoRuntime *automatic=auto_for_row(row);
  if(g_loadForm&&automatic&&automatic->value.kind==1&&g_loadForm<(int)automatic->value.count){
    lstrcpynA(g_loadLook,automatic->value.names[g_loadForm],64);asset=automatic->value.assets[g_loadForm];
  }
  {char line[240];snprintf(line,sizeof(line),"load form identity=%.40s form=%d mp=%d asset=%.130s",entry->identity,g_loadForm,u->sanity,asset);bootlog(line);}
  void *key=make_string(asset);uintptr_t keyRoot=ui_root(key);
  void *exc=NULL,*box=NULL;
  void *args[]={key};
  box=((void *(*)(void *,void *,void **,void **))api[API_INVOKE])(m_loadGO,NULL,args,&exc);
  ui_unroot(keyRoot);
  if(exc||!box){return 0;}
  g_loadRoot=ui_root(box);
  if(!g_loadRoot)return 0;
  g_loadView=u->view;g_loadBox=box;g_loadUnit=u;g_loadRow=row;g_loadStart=GetTickCount();g_loadActive=1;g_loadStatus=0;if(loader_probe_enabled())lp_start(&g_loaderProbe,g_loadStart);else lp_stop(&g_loaderProbe);
  return 1;
}
#include "prewarm_runtime.h"
static void disable_failed_form(Unit *u,int row,int form){
  if(!u||row<0||(uint32_t)row>=g_rowCount||form<=0||form>=4)return;
  u->failedFormMask[row]|=(unsigned char)(1u<<form);
  char line[160];snprintf(line,sizeof(line),"alternate asset unavailable identity=%.40s row=%d form=%d",g_rows[row].identity,row,form);bootlog(line);
}
static void loader_cancel(void){
  lp_stop(&g_loaderProbe);
  if(g_loadBox)retire_slot(NULL,g_loadBox,g_loadRoot);
  else ui_unroot(g_loadRoot);
  g_loadBox=NULL;g_loadRoot=0;g_loadActive=0;g_loadUnit=NULL;g_loadRow=-1;
}
static void loader_probe_paused(void){
 if(!g_loadActive||!g_loadBox||!g_loadUnit||!g_loadUnit->used||g_loadUnit->dead||g_loadUnit->view!=g_loadView||!g_loaderProbe.active||!lp_should(&g_loaderProbe,GetTickCount()))return;
 void *type=ui_class(g_loadBox);void *m=type?find_method(type,"get_IsDone",0):NULL;
 int done=m?call_bool(m,ui_unbox(g_loadBox),NULL):-1;
 if(lp_done(&g_loaderProbe,done)){char line[220];snprintf(line,sizeof(line),"loader observe completed while paused sinner=%lu row=%d elapsed_ms=%lu viewer=%d camera=%d",(unsigned long)g_loadUnit->sinner,g_loadRow,(unsigned long)(GetTickCount()-g_loaderProbe.start),g_anyViewerActive,g_presentationGate);bootlog(line);}
}
static void loader_poll(void){
  if(!g_loadActive)return;
  if(!g_loadUnit||!g_loadUnit->used||g_loadUnit->dead||g_loadUnit->view!=g_loadView){loader_cancel();return;}
  void *type=ui_class(g_loadBox);
  void *isDone=find_method(type,"get_IsDone",0);
  int ok=1;
  void *value=isDone?call_obj(isDone,ui_unbox(g_loadBox),NULL,&ok):NULL;
  if(!ok||!value){if(g_loadForm)disable_failed_form(g_loadUnit,g_loadRow,g_loadForm);else mark_bad(g_loadUnit,g_loadRow);bootlog("loader: IsDone failed");loader_cancel();return;}
  if(!*(uint8_t *)ui_unbox(value)){
    if((DWORD)(GetTickCount()-g_loadStart)>30000){if(g_loadForm)disable_failed_form(g_loadUnit,g_loadRow,g_loadForm);else mark_bad(g_loadUnit,g_loadRow);bootlog("loader: timeout");loader_cancel();}
    return;
  }
  void *status=find_method(type,"get_Status",0);
  void *sv=status?call_obj(status,ui_unbox(g_loadBox),NULL,&ok):NULL;
  int state=(!ok||!sv)?0:*(int *)ui_unbox(sv);
  if(state!=1){
    if(g_loadForm)disable_failed_form(g_loadUnit,g_loadRow,g_loadForm);else mark_bad(g_loadUnit,g_loadRow);
    bootlog("loader: load failed");loader_cancel();return;
  }
  int built=build_skin(g_loadUnit,g_loadRow);
  if(built<0){loader_cancel();return;}
  if(!built){
    char line[192];snprintf(line,sizeof(line),"loader: build failed sinner=%lu row=%d identity=%.40s; skipped for unit",(unsigned long)g_loadUnit->sinner,g_loadRow,g_rows[g_loadRow].identity);bootlog(line);
    if(g_loadForm)disable_failed_form(g_loadUnit,g_loadRow,g_loadForm);else mark_bad(g_loadUnit,g_loadRow);
    loader_cancel();
    return;
  }
  lp_stop(&g_loaderProbe);g_loadBox=NULL;g_loadRoot=0;g_loadActive=0;g_loadUnit=NULL;g_loadRow=-1;
}

/* ---------------- unit lifecycle ---------------- */
static int cleanup_pending;
static void cleanup_all(void);
static void fx_plan_close_unit(Unit *u);
static void motion_clear(Unit *u);
static void motion_dispatch(Unit *u,int original_only);
static void unit_release(Unit *u){
  fx_plan_close_unit(u);
  visible_watch_clear(u);visible_attack_end(u);
  static_restore_renderers(u);
  motion_clear(u);
  void *list=(!u->dead && u->view && rfield(u->view,"m_CachedPtr"))?rfield(u->view,"_appearances"):NULL;
  for(int k=0;k<SR_SKIN_MAX;k++)if(u->skins[k].used){
    if(list)list_remove(list,u->skins[k].app);
    retire_skin(&u->skins[k]);
  }
  ui_unroot(u->observedViewerRoot);
  ui_unroot(u->viewRoot);ui_unroot(u->baseRoot);
  memset(u,0,sizeof(*u));
}
static void unit_register(void *app,void *view){
  if(!app||!view)return;
  if(unit_for_app(app))return;
  {char probe[128];
   if(identity_text(app,probe,sizeof(probe))&&strstr(probe,"_SRN_"))return;
   if(!probe[0])return;
  }
  for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used&&g_units[i].view==view){
    Unit *u=&g_units[i];
    if(u->baseApp!=app&&!skin_for_app(u,app)){uintptr_t h=ui_root(app);if(h){static_restore_renderers(u);ui_unroot(u->baseRoot);u->baseRoot=h;u->baseApp=app;identity_text(app,u->baseName,sizeof(u->baseName));rebuild_candidates(u);}}
    return;
  }
  uint32_t sinner=sinner_of(app);
  if(!sinner)return;
  void *list=rfield(view,"_appearances");
  if(!list)return;
  Unit *u=unit_alloc();
  if(!u)return;
  memset(u,0,sizeof(*u));
  u->used=1;u->view=view;u->baseApp=app;u->sinner=sinner;u->last=-1;u->pending=-1;u->wanted=-1;u->stageShown=-1;u->stageWanted=-1;
  u->startupPending=1;u->startupRow=-1;
  u->viewRoot=ui_root(view);u->baseRoot=ui_root(app);
  if(!identity_text(app,u->baseName,sizeof(u->baseName)))lstrcpynA(u->baseName,"unknown",96);
  rebuild_candidates(u);
  {char line[192];wsprintfA(line,"unit registered sinner=%lu base=%.48s candidates=%d",(unsigned long)sinner,u->baseName,u->ncand);bootlog(line);}
  u->preserveSpecial=sr_scissors_suspend(u->baseName,playback_originals[1]!=NULL);
  if(sr_is_scissors_source(u->baseName)&&!u->preserveSpecial)bootlog("10917 random enabled: native playback hook ready; source timing and camera gates retained");
  if(u->preserveSpecial){u->ncand=0;bootlog("special source 10917: preserve original appearance/skill effects; random appearance suspended for this unit");return;}
  int preload=g_cfg&&g_cfg->mode==1?0:(g_cfg&&g_cfg->max_skins? (int)g_cfg->max_skins : 3);
  if(preload>SR_SKIN_MAX)preload=SR_SKIN_MAX;
  for(int i=0;i<preload&&i<u->ncand;i++){
    double random=0;if(!random_double(&random))break;
    int pick=u->cand[(int)(random*u->ncand)];
    queue_push(u,pick);
  }
}

/* ---------------- decision core ---------------- */
static void topup(Unit *u){
  if(!u || !u->used || u->dead || skin_count(u)>=skin_limit()||(g_cfg&&g_cfg->mode==1))return;
  if(g_loadActive && g_loadUnit==u)return;
  for(int tries=0;tries<8;tries++){
    double random;if(!random_double(&random))return;
    int row=unit_draw(u,0,random);if(row<0)return;
    if(skin_index(u,row)>=0)continue;queue_push(u,row);return;
  }
}
static void startup_pool_changed(Unit *u){if(u&&u->startupPending)u->startupRow=-1;}
static int startup_row_valid(Unit *u,int row){
 if(!u||row<0||(uint32_t)row>=g_rowCount||unit_bad(u,row))return 0;
 PoolRow *r=&g_rows[row];if(r->sinner!=u->sinner||!r->enabled||!isfinite(r->weight)||r->weight<=0||r->weight>1000000)return 0;
 for(int i=0;i<u->ncand;i++)if(u->cand[i]==row)return 1;
 return 0;
}
static void stage_commit_source(Unit *u,int row);
static void startup_select(Unit *u){
 if(!u||!u->startupPending||u->dead||u->preserveSpecial||!enabled_now())return;
 if(u->viewerActive||u->wanted>=0||u->motionCount){u->startupPending=0;return;}
 if(!startup_row_valid(u,u->startupRow))u->startupRow=-1;
 if(u->startupRow<0){double r;if(!random_double(&r))return;u->startupRow=unit_draw(u,0,r);if(u->startupRow<0)return;}
 int row=u->startupRow,k=skin_index(u,row);
 if(k<0){
  queue_push(u,row);
  return;
 }
 if(g_anyViewerActive||g_presentationGate||!g_ready)return;
 void *cur=rfield(u->view,"_curAppearance");
 if(!cur||presentation_busy(cur)||(u->baseApp!=cur&&presentation_busy(u->baseApp)))return;
 if(cur==u->skins[k].app||unit_switch(u,&u->skins[k])){
  u->startupPending=0;u->last=k;stage_commit_source(u,row);InterlockedIncrement(&g_switches);
  char line[160];snprintf(line,sizeof(line),"battle start appearance sinner=%lu identity=%.64s",(unsigned long)u->sinner,g_rows[row].identity);bootlog(line);
 }
}
static double timing_speed(Unit *u,Skin *skin,int detail,int mapped,int index,int sourceIndex,int last){
  double cached=cached_time_ratio(u,skin,detail,mapped,sourceIndex,index);if(cached>0)return cached;
  void *container=skin?skin_metadata(u,skin):NULL;
  if(!container)return 0;
  void *method=find_method(ui_class(container),"GetAnimItem",5);
  if(!method){bootlog("timing: GetAnimItem missing");return 0;}
  uint8_t lastFlag=last?1:0;
  void *args[]={&detail,&mapped,&index,&sourceIndex,&lastFlag};
  int ok=1;
  void *item=call_obj(method,container,args,&ok);
  if(!ok||!item){char line[160];snprintf(line,sizeof(line),"timing: GetAnimItem null detail=%d mapped=%d index=%d",detail,mapped,index);bootlog(line);return 0;}
  uintptr_t root=ui_root(item);
  double speed=0;
  int valid=read_number(item,"speed",&speed);
  ui_unroot(root);
  return valid?speed:0;
}
static void set_speed(void *app,float speed){
  if(!app||!m_setAnimSpeed)return;
  void *args[]={&speed};int ok=1;
  call_exc(m_setAnimSpeed,app,args);
}

static void *g_speedApp;static float g_speedValue;
static int g_switchGate[SR_UNIT_MAX];

/* Phase selection belongs to the exact identity and the selected resource. */
static const char *effective_stage_source(Unit *u,const PoolRow *row){
 if(row->kind||!row->story||strncmp(row->identity,"story_",6))return NULL;
 const SrCounterpartForm *form=sr_counterpart_form(u->baseName);
 if(sr_counterpart_member(form,row->identity)){
  int reverse=0;
  const SrCounterpart *pair=sr_find_counterpart(u->baseName,row->identity,&reverse);
  if(pair&&!strcmp(pair->story,row->appearance_name)&&sr_sg_find_id(&g_stageGroups,form->group)>=0)return form->group;
 }
 if(strcmp(row->identity+6,row->appearance_name)||!sr_chapter_actor(u->baseName,row->appearance_name))return NULL;
 char id[32];snprintf(id,sizeof(id),"ch9_%.5s",u->baseName);
 for(int variant=0;variant<2;variant++){
  if(variant)strcat(id,"_alt");
  int n=sr_sg_find_id(&g_stageGroups,id);if(n<0)continue;
  const SrSgGroup *g=&g_stageGroups.group[n];
  for(unsigned j=0;j<g->count;j++)if(!strcmp(g->stage[j].identity,row->identity))return g_stageGroups.id[n];
 }
 return NULL;
}
static void stage_commit_source(Unit *u,int row){
 unsigned kind=0;const char *id=NULL;
 if(row>=0&&(uint32_t)row<g_rowCount){id=effective_stage_source(u,&g_rows[row]);kind=id!=NULL;}
 if(!sr_stage_source_commit(u->stageSource,row,u->stageWanted,kind,id))return;
 u->stageGroup=0;u->stageShown=-1;u->stageChoice=-1;
}

static int visible_stage_form(const Skin *skin){
 const char *id=g_rows[skin->row].identity;
 if(sr_chapter_visual(id)||sr_internal_policy(id)||auto_internal(skin->row)||!strcmp(id,"10312")||!strcmp(id,"10913"))
  return skin->internalStage;
 return skin->form;
}
static int stage_uses_native_pair(Unit *u,const SrSgGroup *g){
 if(!strncmp(u->stageSource,"pair",4))return 1;
 enum SrChapterSignal signal=sr_chapter_signal(u->baseName,u->stageSource);
 if(signal==CH_DON||signal==CH_FAUST)return 1;
 if(g->count!=2)return 0;
 const char *first=g->stage[0].identity,*second=g->stage[1].identity;
 return (!strncmp(u->baseName,"10314",5)&&!strcmp(first,"story_1325_Index_Disciple_NormalAppearance")&&!strcmp(second,"story_1325_Index_discipleAppearance"))||
        (!strncmp(u->baseName,"10215",5)&&!strcmp(first,"story_1319_RingFinger_DiscipleAppearance")&&!strcmp(second,"story_1336_RingFinger_Disciple_CastoffAppearance"));
}
/* Prefer the personality rule, then the first unrestricted row for this sinner. */
static int stage_target_row(const Unit *u,const char *identity,const char *base){
 int fallback=-1;
 for(uint32_t i=0;i<g_rowCount;i++){
  const PoolRow *r=&g_rows[i];
  if(r->sinner!=u->sinner||r->kind||strcmp(r->identity,identity))continue;
  if(!strcmp(r->base_identity,base))return (int)i;
  if(fallback<0&&!r->base_identity[0])fallback=(int)i;
 }
 return fallback;
}
static int stage_keep_visible(Unit *u,int row,int director_owned){
 if(!u||row<0||(uint32_t)row>=g_rowCount)return 0;
 PoolRow *picked=&g_rows[row];int gi=sr_sg_find_id(&g_stageGroups,u->stageSource);
 void *app=rfield(u->view,"_curAppearance");Skin *shown=skin_for_app(u,app);int presented=-1;
 if(gi>=0&&shown&&shown->row>=0&&(uint32_t)shown->row<g_rowCount){
  const char *id=g_rows[shown->row].identity;
  presented=sr_sg_presented(&g_stageGroups.group[gi],id,visible_stage_form(shown),u->stageShown);
 }
 const char *source=effective_stage_source(u,picked);
 return sr_stage_reselect_keep(u->stageSource,source!=NULL,source,director_owned,gi>=0,presented);
}
/* Return -2 for an ordinary draw, -1 if the known stage row is unavailable. */
static void chapter_cached_status(Unit *u,SrSgStatus *state);
static int stage_reselect_row(Unit *u,int row,void *current,int director_owned){
 if(!u||director_owned||row<0||(uint32_t)row>=g_rowCount)return -2;
 int gi=sr_sg_find_id(&g_stageGroups,u->stageSource);
 int valid=gi>=0&&g_stageGroups.group[gi].enabled&&u->stageGroup==gi+1&&u->stageRevision==g_stageGroups.revision;
 int atNative=current==u->baseApp||(u->nativeValid&&u->nativeAppearance==current);
 int selected=u->stageChoice;
 const char *source=effective_stage_source(u,&g_rows[row]);
 if(valid&&atNative&&source&&!strcmp(u->stageSource,source)){
  const SrSgGroup *g=&g_stageGroups.group[gi];
  if(sr_sg_has_native(g)&&stage_uses_native_pair(u,g)){
   SrSgStatus state={u->formHp,u->formMaxHp,u->sanity,u->sanityValid,u->formState.evades,u->nativeStage,u->nativeValid};
   chapter_cached_status(u,&state);
   selected=sr_sg_reselect_stage(g,&state,u->stageChoice,u->stageShown,state.chapterValid||u->nativeAppearance==current);
   if(selected<0){bootlog("stage reselect waiting for current native state");return -1;}
  }
 }
 int choice=sr_stage_reselect_choice(u->stageSource,source!=NULL,source,atNative,valid,valid?g_stageGroups.group[gi].count:0,selected);
 if(choice<0)return -2;
 const char *id=g_stageGroups.group[gi].stage[choice].identity;
 int found=stage_target_row(u,id,g_rows[row].base_identity);
 if(found>=0&&!strcmp(g_rows[found].base_identity,g_rows[row].base_identity)){
  char line[192];snprintf(line,sizeof(line),"stage reselect group=%.40s choice=%d row=%.64s",u->stageSource,choice,id);bootlog(line);
 }
 return found;
}

static void apply_pending(Unit *u,int slot){
  if(!u||!u->view||u->dead||u->switching||introUnit==u)return;
  if(u->preserveSpecial){u->wanted=u->pending=-1;u->stageWanted=-1;return;}
  if(g_cfg&&g_cfg->mode==1&&u->viewerActive)return;
  if(!g_ready||!enabled_now()||!sr_coin_switch_ready(g_anyViewerActive,g_presentationGate,0))return;
  if(!rfield(u->view,"m_CachedPtr"))return;
  if(g_switchGate[slot]&&g_frame<g_switchGate[slot])return;
  if(u->wanted<0)return;
  if(stage_keep_visible(u,u->wanted,u->stageWanted==u->wanted)){
    u->wanted=-1;u->stageWanted=-1;return;
  }
  void *current=rfield(u->view,"_curAppearance");
  if(!current)return;
  int resolved=stage_reselect_row(u,u->wanted,current,u->stageWanted==u->wanted);
  if(resolved==-1){bootlog("stage reselect target missing; discarded pending draw");u->wanted=-1;u->stageWanted=-1;return;}
  int resource=resolved>=0?resolved:u->wanted;
  /* A failed target cannot be loaded again during this unit's lifetime. */
  if(unit_bad(u,resource)){u->wanted=-1;u->stageWanted=-1;return;}
  int k=skin_index(u,resource);
  if(k<0){queue_push(u,resource);return;}
  if(current==u->skins[k].app){if(resolved<0)stage_commit_source(u,u->wanted);u->wanted=-1;u->stageWanted=-1;u->last=k;return;}
  Skin *held=held_appearance(u);
  int busy=presentation_busy(current);
  if(!busy&&u->baseApp!=current)busy=presentation_busy(u->baseApp);
  if(!busy&&held&&held->app!=current&&held->app!=u->baseApp)busy=presentation_busy(held->app);
  if(!sr_coin_switch_ready(g_anyViewerActive,g_presentationGate,busy))return;
  Skin *before=skin_for_app(u,current);
  if(!before && u->nativeValid && u->nativeAppearance==current && !strncmp(u->baseName,"10314",5)) before=held;
  int stageIntro=u->stageWanted==u->wanted && before && before->row>=0 && (uint32_t)before->row<g_rowCount &&
    !strcmp(g_rows[before->row].identity,"story_1325_Index_Disciple_NormalAppearance") &&
    !strcmp(g_rows[u->skins[k].row].identity,"story_1325_Index_discipleAppearance");
  void *applied=unit_switch(u,&u->skins[k]);
  if(!applied){u->wanted=-1;u->stageWanted=-1;return;}
  if(stageIntro){u->stageIntroPending=1;u->stageIntroRow=u->skins[k].row;}
  if(resolved<0)stage_commit_source(u,u->wanted);u->wanted=-1;u->stageWanted=-1;
  g_switchGate[slot]=g_frame+1; /* At most one switch/frame; no 15-frame coin lock. */
  InterlockedIncrement(&g_switches);
  {char line[192];snprintf(line,sizeof(line),"apply look=%.64s unit=%d frame=%d form=%d mp=%d sourceCoin=%d",u->skins[k].look,slot,g_frame,u->skins[k].form,u->sanity,u->wantedSourceCoin);bootlog(line);}
  topup(u);
}

static void decide_and_apply(void **pself,int *pdetail,int *pindex){
  Unit *u=unit_for_app(*pself);
  if(!u||u->preserveSpecial||u->switching||cleanup_pending||introUnit==u)return;
  int detail=*pdetail,index=*pindex;
  Coin coin={u->coinKnown,u->coinLast,u->coinTier,u->coinMotion,u->coinIndex};
  int isAttack=is_skill_detail(detail)||((detail==20||detail==21||detail==22)&&coin.known&&coin.skillMotion==detail);
  int action=0;
  if((detail>=0&&detail<128&&defenseMotions[detail])||(u->coinDefense&&coin.known&&detail==coin.skillMotion))action=1;
  else if(isAttack)action=2;
  else if(is_prep_detail(detail))action=4;
  else if(is_parry_detail(detail)&&!u->clashDepth&&!g_clashBoundary)action=8;
  int idle=(detail==0||detail==18);
  if(!action&&!idle)return;

  int row=-1;
  if(action){
    void *attackAction=action==2?rfield(u->view,"_currentActionLog"):NULL;
    int sourceCoin=index>=0?index:u->coinIndex;
    if(action==2&&attackAction&&attackAction==u->observedAction&&u->observedViewer&&u->observedCoinField){
      int live=*(int *)((char *)u->observedViewer+u->observedCoinOffset);
      if(live>=0&&live<1024)sourceCoin=live;
    }
    int reuseAttack=action==2&&attackAction&&sourceCoin>=0&&u->attackDrawValid&&
      u->attackDrawAction==attackAction&&u->attackDrawViewer==u->observedViewer&&u->attackDrawIndex==sourceCoin;
    void *defenseAction=action==1?rfield(u->view,"_currentActionLog"):NULL;
    int reuseDefense=action==1&&u->defenseDrawLatched&&
      (!defenseAction||defenseAction==u->lastDefenseDrawAction);
    if(reuseAttack)row=u->attackDrawRow;
    else if(reuseDefense)row=u->defensePickedRow;
    else if((action==2||action==4)&&u->pending>=0)row=u->pending;
    else{
      double random=0;
      if(!random_double(&random))return;
      row=unit_draw(u,(uint32_t)action,random);
    }
    if(action==2){
      u->pending=-1;
      if(attackAction&&sourceCoin>=0){u->attackDrawValid=1;u->attackDrawAction=attackAction;u->attackDrawViewer=u->observedViewer;u->attackDrawIndex=sourceCoin;u->attackDrawRow=row;}
    }
    else if(action==4||action==8)u->pending=row;
    if(row<0){bootlog("no eligible identity for action");return;}
    if(action==1){
      u->lastDefenseDrawAction=defenseAction;u->defenseDrawLatched=1;u->defensePickedRow=row;
    }
    /* Keep a cold-cache selection as the wanted donor; do not lose it while
       waiting for its asset to load. */
    u->stageWanted=-1;u->wanted=row;u->wantedSourceCoin=action==2?sourceCoin:-1;
    int slot=skin_index(u,row);
    if(action==2&&!reuseAttack){char line[208];snprintf(line,sizeof(line),"coin draw sinner=%lu coin=%d identity=%.63s cached=%d",(unsigned long)u->sinner,sourceCoin,g_rows[row].identity,slot>=0);bootlog(line);}
    if(slot<0){queue_push(u,row);return;}
    Skin *skin=&u->skins[slot];
    int mappedDetail=detail,mappedIndex=index;
    /* Switching inside a native motion call tears the timeline that the game
       is about to start. Only queue the choice here; the render callback applies
       it on a later frame when the unit is idle. */
    u->stageWanted=-1;u->wanted=row;
    {char line[224];snprintf(line,sizeof(line),"decision detail=%d->%d index=%d->%d coinLast=%d tier=%d look=%.40s",detail,mappedDetail,index,mappedIndex,coin.last,coin.tier,skin->look);bootlog(line);}
    return;
  }
  /* idle: keep the currently shown appearance; nothing to do */
  u->pending=-1;
  return;
}
typedef struct {void *app;int sourceDetail,sourceIndex,segmentDetail;} ProjectionContext;
static ProjectionContext g_projection;
static _Thread_local void *hiddenTimingApp;
static void keep_hidden_timing_active(Unit *u){
 if(!u->staticHidden)return;
 void *go=app_go(u->baseApp);if(go&&go_active_self(go)==0)set_active(go,1);
}
#include "fx_plan_support.inc"
static void *m_motionAnimItem,*orig_motionAnimItem;
static int team_returns(void *method,const char *expected);
static _Thread_local void *g_chapterPlaybackApp;
static _Thread_local int g_chapterPlaybackDetail;
typedef struct {void *app;int mapped,source,index,chapter;} ClashPlayback;
static _Thread_local ClashPlayback g_clashPlayback;
static int clash_raw(void *app,int detail){
 return app&&g_clashPlayback.app==app&&g_clashPlayback.mapped==detail;
}
static void *motion_anim_item_hook(void *retbuf,void *app,int sourceDetail,int donorDetail,int donorIndex,int sourceIndex,uint8_t last,void *mi){
 if(enabled_now()&&clash_raw(app,donorDetail)){
  if(g_clashPlayback.chapter){sourceDetail=donorDetail;sourceIndex=donorIndex;}
  else{
   sourceDetail=g_clashPlayback.source;
   if(g_clashPlayback.index>=0)sourceIndex=g_clashPlayback.index;
  }
 }else if(enabled_now()&&g_chapterPlaybackApp==app&&donorDetail==g_chapterPlaybackDetail){
  sourceDetail=donorDetail;
  sourceIndex=donorIndex;
 }else if(enabled_now()&&g_projection.app==app){
  sourceDetail=g_projection.sourceDetail;
  /* EvaluateRelativeSpeed reads default metadata at startIndex, donor at i. */
  if(g_projection.sourceIndex>=0)sourceIndex=g_projection.sourceIndex;
 }
 void *result=((void *(*)(void *,void *,int,int,int,int,uint8_t,void *))orig_motionAnimItem)(retbuf,app,sourceDetail,donorDetail,donorIndex,sourceIndex,last,mi);
 if(enabled_now()&&g_projection.app==app){char line[192];snprintf(line,sizeof(line),"projection sourceDetail=%d sourceIndex=%d donorDetail=%d donorIndex=%d nativeReturn=%s",sourceDetail,sourceIndex,donorDetail,donorIndex,result?"buffer":"null");bootlog(line);}
 return result;
}
static void forward_projected_motion(void *app,int detail,uint8_t a1,int index,uint8_t a3,void *cb,uint8_t a5,void *mi,int sourceDetail,int sourceIndex,int coin,int validAction){
 ProjectionContext saved=g_projection;
 Unit *u=unit_for_app(app);
 Skin *skin=u?skin_for_app(u,app):NULL;int chosen=-1;
 if(u&&skin&&enabled_now()&&!cleanup_pending&&!g_motionDepth&&u->staticHidden&&!u->coinDefense&&
    !(g_rows[skin->row].excluded&2)&&is_skill_detail(sourceDetail)&&
    !sr_verified_attack_count(skin->motionCounts)){
  visible_attack_begin(u,skin,sourceDetail,coin);keep_hidden_timing_active(u);
  app=u->baseApp;skin=NULL;detail=sourceDetail;index=sourceIndex;
 }
 int specialDetail=-1,specialIndex=-1;
 if(enabled_now()&&!cleanup_pending&&!g_motionDepth&&skin&&introApp!=app&&validAction&&
    !u->preserveSpecial&&!u->coinDefense&&u->coinKnown&&is_skill_detail(sourceDetail)&&
    sourceIndex>=0&&sourceIndex<TC_COINS&&(u->ordinarySourceClips[sourceDetail]&(UINT32_C(1)<<sourceIndex))&&
    !(g_rows[skin->row].excluded&(SR_STATIC_APPEARANCE_FLAG|2))&&
    coin>=0&&coin<SR_VARIETY_COINS&&u->observedAction&&u->observedViewer&&u->viewerActive&&
    sr_verified_paired_attack(skin->motionCounts,paired_source(u,skin),motion_identity(skin),sourceDetail,-1)<0&&
    !sr_salvador_s3(skin->motionCounts,u->baseName,motion_identity(skin),sourceDetail,coin,&specialDetail,&specialIndex)){
  SrSegmentLatch *l=&u->segmentLatch;
  if(sr_segment_scope(l,u->observedAction,u->observedViewer,app,skin->internalStage))u->segmentSequence++;
  TimeRecord *src=NULL,*dst=NULL;
  if(!l->seen[coin]){
   for(int k=0;k<g_timeCount;k++){
    if(!strcmp(g_timeRecords[k]->look,u->baseName))src=g_timeRecords[k];
    if(!strcmp(g_timeRecords[k]->look,skin->look))dst=g_timeRecords[k];
    if(src&&dst)break;
   }
  }
  if(sr_segment_pick(l,coin,u->segmentSequence-1,src?src->seconds[sourceDetail][sourceIndex]:0,
                     dst?dst->seconds:NULL,skin->motionCounts,skin->ordinaryClips,skin->ordinaryBodies,&detail,&index))chosen=detail;
 }
 if(u&&skin&&validAction&&coin>=0&&is_skill_detail(sourceDetail)){char msg[256];snprintf(msg,sizeof(msg),"segment actual look=%.95s source=%d:%d coin=%d target=%d:%d planned=%d",skin->look,sourceDetail,sourceIndex,coin,detail,index,chosen);bootlog(msg);}
 if(u&&skin&&is_skill_detail(sourceDetail))g_projection=(ProjectionContext){app,sourceDetail,sourceIndex,chosen};
 if(u)fx_plan_close_app(app,0);
 playback_begin(app);
 FxPlaybackPlan *savedCapture=g_fxCapture;uint64_t savedOwner=g_fxCaptureOwner;
 g_fxCapture=NULL;g_fxCaptureOwner=0;
 if(g_fxExperiment&&enabled_now()&&!cleanup_pending&&!g_motionDepth&&u&&skin&&validAction&&coin>=0&&index>=0){
  FxPlaybackPlan *prepared=fx_plan_open(app,u,skin,detail,index);
  if(prepared){AcquireSRWLockShared(&g_fxSlotsLock);g_fxCapture=prepared;g_fxCaptureOwner=prepared->owner;ReleaseSRWLockShared(&g_fxSlotsLock);}
 }
 void *savedTiming=hiddenTimingApp;
 if(u&&app==u->baseApp&&u->staticHidden)hiddenTimingApp=app;
 if(u&&skin&&is_skill_detail(sourceDetail)&&enabled_now()&&!cleanup_pending&&!g_motionDepth&&!u->coinDefense&&
    !(g_rows[skin->row].excluded&2))
  visible_watch_begin(u,skin,sourceDetail,coin);
 ((void (*)(void *,int,uint8_t,int,uint8_t,void *,uint8_t,void *))orig_changeMotion)(app,detail,a1,index,a3,cb,a5,mi);
 hiddenTimingApp=savedTiming;g_fxCapture=savedCapture;g_fxCaptureOwner=savedOwner;
 g_projection=saved;
}
#include "coin_diagnostics.h"
static int current_attack_coin(Unit *u){
 if(!u||!u->viewerActive||!u->observedViewer||!u->observedCoinField||!u->observedAction||
    rfield(u->view,"_currentActionLog")!=u->observedAction)return -1;
 int coin=*(int *)((char *)u->observedViewer+u->observedCoinOffset);
 return coin>=0&&coin<1024?coin:-1;
}
static int single_skin_cycle_index(Unit *u,Skin *skin,int coin,int count,int *out){
 if(!u||!skin||!out||coin<0||count<=0||!u->observedAction)return 0;
 const char *look=skin->look;
 if(!u->cycleValid||u->cycleAction!=u->observedAction||u->cycleViewer!=u->observedViewer||coin<u->cycleCoin){
  u->cycleValid=1;u->cycleAction=u->observedAction;u->cycleViewer=u->observedViewer;
  u->cycleOrdinal=0;snprintf(u->cycleLook,sizeof(u->cycleLook),"%s",look);
 }else if(strcmp(u->cycleLook,look)){
  u->cycleOrdinal=0;snprintf(u->cycleLook,sizeof(u->cycleLook),"%s",look);
 }else if(coin!=u->cycleCoin)u->cycleOrdinal++;
 u->cycleCoin=coin;*out=u->cycleOrdinal%count;return 1;
}
#include "native_order_runtime.h"
static int counterpart_part(Unit *u,Skin *skin,void *action,int coin,int detail,int donorCount,int index,int last){
 if(index<0||donorCount<=0)return index;
 int src=sr_counterpart_source_parts(paired_source(u,skin),motion_identity(skin),detail);
 if(src==donorCount&&index<donorCount)return index;
 int part=0;
 if(native_order_index(u,action,coin,donorCount,&part)&&part>=-1&&part<donorCount)return part;
 return sr_counterpart_fallback_part(index,src,donorCount,last);
}
/* ParryingOnly returns the game's original decision. Only its visible
   receiver and the authored visual slot may change. Keep scope receiver-local. */
static _Thread_local void *g_clashOwner;
static _Thread_local int g_clashRole;
static unsigned char clashResults[32];
static void bind_clash_results(void *method){
 if(!method)return;
 void *pt=((void *(*)(void *,uint32_t))api[API_PARAM])(method,0);
 void *type=pt?((void *(*)(void *))api[API_TYPE_OBJECT])(pt):NULL;
 uintptr_t root=ui_root(type);if(!root)return;
 int ok=0;void *nm=find_method(ui_class(type),"GetEnumNames",0),*vm=find_method(ui_class(type),"GetEnumValues",0);
 void *names=nm?call_obj(nm,type,NULL,&ok):NULL;uintptr_t nr=ui_root(names);
 void *values=vm?call_obj(vm,type,NULL,&ok):NULL;uintptr_t vr=ui_root(values);
 if(nr&&vr&&ok){
  uintptr_t n=*(uintptr_t *)((char *)names+24),v=*(uintptr_t *)((char *)values+24);
  if(n==v&&n<512)for(uintptr_t i=0;i<n;i++){
   int value=((int *)((char *)values+32))[i];char name[128];
   if(value<0||value>=32||!string_ascii(((void **)((char *)names+32))[i],name,128))continue;
   if(!_stricmp(name,"Win")||!_stricmp(name,"Victory"))clashResults[value]=2;
   if(!_stricmp(name,"Lose")||!_stricmp(name,"Loss")||!_stricmp(name,"Defeat"))clashResults[value]=3;
  }
 }
 ui_unroot(vr);ui_unroot(nr);ui_unroot(root);
}
#include "clash_render.inc"
#include "chapter_nine_runtime.inc"
#include "coin_boundary_runtime.h"
/* ---------------- generic binding ---------------- */
static void *close_generic(void *definition,void *declaring,void *elementClass,void *elementType){
  if(!definition||!declaring||!elementClass||!elementType)return NULL;
  uintptr_t refs[3]={0};
  void *result=NULL;
  void *reflection=((void *(*)(void *,void *))api[API_METHOD_OBJECT])(definition,declaring);
  if(!reflection)return NULL;
  refs[0]=ui_root(reflection);if(!refs[0])return NULL;
  void *array=((void *(*)(void *,uintptr_t))api[API_ARRAY_NEW])(c_typeClass,1);
  if(!array)goto done;
  refs[1]=ui_root(array);if(!refs[1])goto done;
  ((void (*)(void *,void **,void *))api[API_WBARRIER])(array,(void **)((char *)array+32),elementType);
  void *make=NULL;
  for(void *c=ui_class(reflection);c&&!make;c=ui_parent(c))make=((void *(*)(void *,const char *,int))api[API_METHOD])(c,"MakeGenericMethod",1);
  if(!make)goto done;
  {void *exc=NULL,*args[]={array};
   void *closed=((void *(*)(void *,void *,void **,void **))api[API_INVOKE])(make,reflection,args,&exc);
   if(exc||!closed)goto done;
   refs[2]=ui_root(closed);if(!refs[2])goto done;
   result=((void *(*)(void *))api[API_FROM_REFLECTION])(closed);}
done:
  for(int i=2;i>=0;i--)if(refs[i])ui_unroot(refs[i]);
  return result;
}

/* Dedicated skin viewer callbacks keep their original game logic. Only a
   cached, existing donor motion of the same native skill tier may replace
   an unavailable playback detail. No Unity hierarchy calls in these detours. */

static LONG playback_fallbacks;
static int special_playback(int slot,void *viewer,int detail,void *mi){
 int original=((int (*)(void *,int,void *))playback_originals[slot])(viewer,detail,mi);
 if(!enabled_now()||cleanup_pending)return original;
 void *app=rfield(viewer,"_curAppearance");Unit *u=unit_for_app(app);
 Skin *skin=u?skin_for_app(u,app):NULL;if(!skin&&u&&app==u->baseApp&&u->staticHidden)skin=held_appearance(u);
 if(!skin||(g_rows[skin->row].excluded&(2|SR_STATIC_APPEARANCE_FLAG)))return original;
 /* Keep source detail through the viewer. The final motion hook maps a
    verified pair once, with source detail intact for timing projection. */
 if(skin->chapterActor||sr_verified_paired_attack(skin->motionCounts,paired_source(u,skin),motion_identity(skin),original,-1)>=0)return original;
 int mapped=sr_resolve_attack(skin->motionCounts,original,u->coinKnown,u->coinTier,u->coinMotion,u->coinDefense,introApp==app);
 mapped=sr_native_motion_detail(skin->motionCounts,skin->nativeMotionDetail,original,mapped);
 mapped=sr_verified_paired_attack(skin->motionCounts,paired_source(u,skin),motion_identity(skin),original,mapped);
 if(mapped!=original)InterlockedIncrement(&playback_fallbacks);
 return mapped;
}
#define PLAYBACK_WRAPPER(N) static int playback##N(void *self,int detail,void *mi){return special_playback(N,self,detail,mi);}
PLAYBACK_WRAPPER(0) PLAYBACK_WRAPPER(1) PLAYBACK_WRAPPER(2) PLAYBACK_WRAPPER(3)
static void *playback_detours[]={playback0,playback1,playback2,playback3};
/* ---------------- hooks ---------------- */
static void hook_canvas(void *mi);
static volatile LONG g_busy;

static int g_visualEventDepth;
static void change_motion_hook(void *self,int detail,uint8_t a1,int index,uint8_t a3,void *callback,uint8_t a5,void *mi){
  if(enabled_now()&&!g_creating&&!g_motionDepth&&!cleanup_pending){
   Unit *u=unit_for_app(self);int role=u?clash_request(u,detail):0;
   if(u&&!u->switching&&!u->dead&&!u->preserveSpecial&&introUnit!=u&&
      (clash_raw(self,detail)||role)){
    void *app=clash_visible(u,self);Skin *skin=skin_for_app(u,app);
    if(clash_raw(self,detail)||skin){
     int mapped=detail,sourceIndex=index;
     if(!clash_raw(self,detail)&&skin){
      if(is_parry_detail(detail)&&!g_visualEventDepth&&!g_clashBoundary&&!g_clashOwner&&!InterlockedCompareExchange(&g_busy,1,0)){
       int requested=detail,part=index;void *receiver=app;
       decide_and_apply(&receiver,&requested,&part);InterlockedExchange(&g_busy,0);
      }
      mapped=clash_indexed_slot(skin,detail,role,&index);
      if(mapped<0)mapped=clash_fallback(u,skin,&app,detail,role);
     }
     if(skin&&mapped!=detail){char line[180];snprintf(line,sizeof(line),"clash pose look=%.63s requested=%d played=%d part=%d role=%d",skin->look,detail,mapped,index,role);bootlog(line);}
     if(role==7)observe_defense(u,detail);
     ClashPlayback saved=g_clashPlayback;
     if(!clash_raw(app,mapped))g_clashPlayback=(ClashPlayback){app,mapped,detail,sourceIndex,skin&&skin->app==app&&skin->chapterActor};
     else if(saved.index<0)g_clashPlayback.index=sourceIndex;
     playback_begin(app);
     ((void (*)(void *,int,uint8_t,int,uint8_t,void *,uint8_t,void *))orig_changeMotion)(app,mapped,a1,index,a3,callback,a5,mi);
     g_clashPlayback=saved;return;
    }
   }
  }
  void *target=self;int targetDetail=detail,targetIndex=index;
  if(g_visualEventDepth&&enabled_now()&&detail!=0&&detail!=18){
   Unit *owner=unit_for_app(self);void *current=owner?rfield(owner->view,"_curAppearance"):NULL;
   if(current&&unit_for_app(current)==owner)target=current;
  }
  if(target==self&&enabled_now()&&!cleanup_pending&&!g_creating&&!g_motionDepth){
   Unit *owner=unit_for_app(self);
   if(owner&&self==owner->baseApp&&!owner->switching&&!owner->coinDefense&&!owner->preserveSpecial&&introUnit!=owner&&
      sr_attack_detail(detail,owner->coinKnown,owner->coinMotion,0,0)){
    void *current=rfield(owner->view,"_curAppearance");
    Skin *shown=skin_for_app(owner,current);
    if(!shown&&current==owner->baseApp&&owner->staticHidden)shown=held_appearance(owner);
    if(shown&&!(g_rows[shown->row].excluded&2))target=shown->app;
   }
  }
  if(introApp==self&&!g_motionDepth){
   if(introHasSecond&&detail==21){introPart=1;introStarted=GetTickCount();introFrame=g_frame;}
   else if(detail!=20&&detail!=0&&detail!=18)introInterrupted=1;
  }
  int decided=0;
  void *speedApp=NULL;float speedValue=1;
  if(enabled_now()&&!g_visualEventDepth&&!g_motionDepth&&!InterlockedCompareExchange(&g_busy,1,0)){
    g_speedApp=NULL;
    decide_and_apply(&target,&targetDetail,&targetIndex);decided=1;
    speedApp=g_speedApp;speedValue=g_speedValue;g_speedApp=NULL;
    InterlockedExchange(&g_busy,0);
  }
  if(enabled_now()&&!g_motionDepth&&!g_creating)observe_defense(unit_for_app(target),detail);
  if(enabled_now()&&!g_visualEventDepth&&!g_motionDepth&&!g_creating&&g_cfg&&g_cfg->mode==1){
    Unit *u=unit_for_app(target);
    if(u&&!u->switching&&!u->dead){
      if(!decided)decide_and_apply(&target,&targetDetail,&targetIndex);
      if(motion_capture(target,targetDetail,a1,targetIndex,a3,callback,a5,mi))return;
    }
  }
  /* Idle calls keep their native receiver: a special S3 viewer may use
     the base while a donor timeline is still finishing. Repair idle later. */
  /* Resolve every donor attack, including enhanced/follow-up paths that do
     not pass through a dedicated GetPlaybackMotion override. */
  Unit *current_unit=unit_for_app(target);Skin *current_skin=current_unit?skin_for_app(current_unit,target):NULL;
  if(enabled_now()&&!g_motionDepth&&current_skin&&(g_rows[current_skin->row].excluded&SR_STATIC_APPEARANCE_FLAG)&&
     sr_attack_detail(detail,current_unit->coinKnown,current_unit->coinMotion,current_unit->coinDefense,0)){
    visible_attack_begin(current_unit,current_skin,detail,current_unit->coinIndex);
    forward_projected_motion(current_unit->baseApp,detail,a1,index,a3,callback,a5,mi,detail,index,-1,0);
    return;
  }
  if(enabled_now()&&!cleanup_pending&&!g_motionDepth&&current_skin&&current_skin->chapterActor){
   chapter_forward(current_unit,current_skin,detail,index,chapter_skill_id(current_unit,current_unit->observedAction),current_unit->observedAction,current_attack_coin(current_unit),
                  current_unit->coinKnown&&current_unit->coinLast,a1,a3,callback,a5,mi);
   return;
  }
  if(enabled_now()&&!cleanup_pending&&!g_motionDepth&&current_skin&&!current_unit->coinDefense&&
     sr_attack_detail(targetDetail,current_unit->coinKnown,current_unit->coinMotion,current_unit->coinDefense,introApp==target)){
    int requested=targetDetail;
    targetDetail=sr_resolve_attack(current_skin->motionCounts,requested,current_unit->coinKnown,current_unit->coinTier,current_unit->coinMotion,current_unit->coinDefense,0);
    if(g_rows[current_skin->row].story)targetDetail=sr_donor_tier_detail(current_skin->motionCounts,targetDetail,current_unit->coinTier);
    targetDetail=sr_native_motion_detail(current_skin->motionCounts,current_skin->nativeMotionDetail,requested,targetDetail);
    if(g_rows[current_skin->row].story)targetDetail=sr_donor_coin_fit(current_skin->motionCounts,targetDetail,native_order_coin_count(current_unit));
    int paired=sr_verified_paired_attack(current_skin->motionCounts,paired_source(current_unit,current_skin),motion_identity(current_skin),requested,-1);
    if(paired>=0)targetDetail=paired;
    if(paired>=0)targetIndex=counterpart_part(current_unit,current_skin,current_unit->observedAction,current_unit->coinIndex,requested,current_skin->motionCounts[paired],index,current_unit->coinKnown&&current_unit->coinLast);
    else if(paired<0&&current_unit->coinKnown&&!current_unit->coinDefense&&index>=0&&single_skin_cycle_index(current_unit,current_skin,current_unit->coinIndex,current_skin->motionCounts[targetDetail],&targetIndex)){}
    else if(!native_order_index(current_unit,current_unit->observedAction,current_unit->coinIndex,current_skin->motionCounts[targetDetail],&targetIndex))
      targetIndex=sr_playback_index(targetIndex,current_skin->motionCounts[targetDetail],current_unit->coinKnown&&current_unit->coinLast);
    if(current_unit->coinKnown)sr_salvador_s3(current_skin->motionCounts,current_unit->baseName,motion_identity(current_skin),detail,current_unit->coinIndex,&targetDetail,&targetIndex);
    unsigned bit=1u<<(requested%32);int word=requested/32;
    unsigned *seen=targetDetail!=requested?current_skin->motionMapped:current_skin->motionMissing;
    if((targetDetail!=requested||!current_skin->motionCounts[targetDetail])&&!(seen[word]&bit)){
      seen[word]|=bit;char line[224];
      snprintf(line,sizeof(line),"attack playback %s look=%.63s detail=%d->%d index=%d->%d known=%d tier=%d",targetDetail!=requested?"fallback":"unavailable",current_skin->look,requested,targetDetail,index,targetIndex,current_unit->coinKnown,current_unit->coinTier);bootlog(line);
    }
  }
  forward_projected_motion(target,targetDetail,a1,targetIndex,a3,callback,a5,mi,detail,index,current_attack_coin(current_unit),current_unit&&current_unit->coinKnown);
  if(enabled_now()&&current_unit&&!g_motionDepth&&detail!=0&&detail!=18&&detail!=5){
   char line[320];snprintf(line,sizeof(line),"motion forwarded sinner=%lu source=%p receiver=%p visible=%p detail=%d->%d index=%d->%d coin=%d viewer=%d eventDepth=%d camera=%d",(unsigned long)current_unit->sinner,self,target,rfield(current_unit->view,"_curAppearance"),detail,targetDetail,index,targetIndex,current_unit->coinIndex,current_unit->viewerActive,g_visualEventDepth,g_presentationGate);bootlog(line);
  }
  /* Visibility and speed changes are confined to the render pump. */
}
static Unit *event_unit_for_view(void *view){
 for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used&&!g_units[i].dead&&g_units[i].view==view)return &g_units[i];return NULL;
}
static void trace_event(const char *event,Unit *u,int coin,const char *reason){
 char line[384];void *current=u?rfield(u->view,"_curAppearance"):NULL;
 snprintf(line,sizeof(line),"event=%s unit=%ld coin=%d result=%s camera=%d viewer=%d queue=%d mask=%d current=%p last=%d depth=%d",event,u?(long)u->sinner:0,coin,reason,g_presentationGate,u?u->viewerActive:0,u?u->motionCount:0,current?motion_busy_mask(current):0,current,u?u->last:-1,g_visualEventDepth);bootlog(line);
}
static int event_select(Unit *u,int action,int coin,void *viewer){
 const char *event=action==2?"attack":action==8?"clash":"defense";
 const char *reason=!u?"unregistered":!enabled_now()?"disabled":cleanup_pending?"cleanup":u->preserveSpecial?"special":u->switching?"switching":introUnit==u?"intro":u->motionCount?"queued-motion":g_presentationGate?"camera":NULL;
 if(reason){trace_event(event,u,coin,reason);return 0;}
 void *current=rfield(u->view,"_curAppearance");
 if(motion_busy_mask(current)&(g_duelCameraBoundary?15:7)){trace_event(event,u,coin,"presentation-busy");return 0;}
 void *log=action==2?rfield(u->view,"_currentActionLog"):NULL;
 int reuse=viewer&&log&&coin>=0&&u->attackDrawValid&&u->attackDrawAction==log&&
          u->attackDrawViewer==viewer&&u->attackDrawIndex==coin;
 int row;
 if(reuse)row=u->attackDrawRow;
 else{
  double value=0;if(!random_double(&value)){trace_event(event,u,coin,"rng-failed");return 0;}
  row=unit_draw(u,action,value);
  if(viewer&&log&&coin>=0){
   u->attackDrawAction=log;u->attackDrawViewer=viewer;u->attackDrawIndex=coin;
   u->attackDrawRow=row;u->attackDrawValid=1;
  }
 }
 int keep=stage_keep_visible(u,row,0);Skin *visible=keep?skin_for_app(u,current):NULL;
 int resolved=stage_reselect_row(u,row,current,0);
 if(resolved==-1){trace_event(event,u,coin,"stage-row-missing");return 0;}
 if(resolved>=0)keep=1;else resolved=row;
 int slot=visible?(int)(visible-u->skins):(resolved>=0?skin_index(u,resolved):-1);if(slot<0){if(resolved>=0)queue_push(u,resolved);trace_event(event,u,coin,resolved>=0?"resource-not-ready":"no-eligible-row");return 0;}
 Skin *skin=&u->skins[slot];void *shown=current==skin->app?current:unit_switch(u,skin);
 if(!shown){trace_event(event,u,coin,"switch-failed");return 0;}
 u->last=slot;
 if(current!=shown)InterlockedIncrement(&g_switches);
 u->stageWanted=-1;if(!keep)stage_commit_source(u,row);
 u->wanted=u->pending=-1;u->wantedSourceCoin=coin;
 if(action==1){u->defenseDrawLatched=1;u->lastDefenseDrawAction=rfield(u->view,"_currentActionLog");u->defensePickedRow=row;}
 char line[224];snprintf(line,sizeof(line),"visual event action=%d sinner=%lu coin=%d selected=%.63s shown=%d",action,(unsigned long)u->sinner,coin,g_rows[row].identity,shown==skin->app);bootlog(line);
 return 1;
}
static void *m_sourceCoin,*orig_sourceCoin,*m_evadeEvent,*orig_evadeEvent;
static void source_coin_hook(void *viewer,int coin,void *mi){
 int selected=0;
 if(enabled_now()&&!g_visualEventDepth){
  g_presentationGate=camera_scope_active();
  Unit *u=event_unit_for_view(rfield(viewer,"_actor"));
  if(!u)u=event_unit_for_view(rfield(viewer,"_hasSkillUnitView"));
  int defense=skill_is_defense(rfield(viewer,"_currentSkillModel"));
  if(u&&defense&&coin>=0)count_form_defense(u,"skill-coin");
  if(!defense)selected=event_select(u,2,coin,viewer);
 }
 /* A rejected early selection must not suppress the later native motion
    decision/capture path. v43 suppressed it even when no donor was chosen. */
 g_visualEventDepth+=selected;((void (*)(void *,int,void *))orig_sourceCoin)(viewer,coin,mi);g_visualEventDepth-=selected;
}
static void evade_event_hook(void *behaviour,int targetId,void *mi){
 int selected=0;
 if(enabled_now()&&!g_visualEventDepth){
  Unit *target=NULL;
  for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used&&!g_units[i].dead){
   void *view=g_units[i].view,*f=find_field_obj(view,"_instanceID");
   if(f&&*(int *)((char *)view+((size_t (*)(void *))api[API_FIELD_OFFSET])(f))==targetId){target=&g_units[i];break;}
  }
  count_form_defense(target,"evade");
  g_presentationGate=camera_scope_active();selected=event_select(target,1,-1,NULL);
 }
 g_visualEventDepth+=selected;((void (*)(void *,int,void *))orig_evadeEvent)(behaviour,targetId,mi);g_visualEventDepth-=selected;
}
static void *m_evadeResult,*orig_evadeResult,*m_updateCointoss,*orig_updateCointoss;
static int g_evadeResultDepth;
static void evade_result_hook(void *viewer,void *log,void *mi){
 ++g_evadeResultDepth;
 ((void (*)(void *,void *,void *))orig_evadeResult)(viewer,log,mi);
 --g_evadeResultDepth;
}
static uint8_t update_cointoss_hook(void *view,int coin,int power,uint8_t a2,uint8_t a3,void *mi){
 /* The result callback resolves the evading unit from BattleLog_Evade.
    Use that resolved receiver, not the enemy attacker's skill viewer. */
 if(g_evadeResultDepth&&enabled_now()){
  g_presentationGate=camera_scope_active();event_select(event_unit_for_view(view),1,coin,NULL);
 }
 return ((uint8_t (*)(void *,int,int,uint8_t,uint8_t,void *))orig_updateCointoss)(view,coin,power,a2,a3,mi);
}
static void *m_afterCointoss,*orig_afterCointoss;
static void clash_prepare_info(void *info){
 void *view=info?rfield(info,"view"):NULL;if(!view)return;
 event_select(event_unit_for_view(view),8,-1,NULL);
}
static int duel_owns_camera(void *manager,void *duel,void *owner){
 if(!manager||!duel||!owner)return 0;
 if(owner==duel)return 1;
 void *flag=find_field_obj(manager,"_zoomActorAloneV2UseDuelViewerSmoothReturn");
 if(!flag||!*(uint8_t *)((char *)manager+((size_t (*)(void *))api[API_FIELD_OFFSET])(flag)))return 0;
 const char *names[]={"_duelView1","_duelView2"};
 for(int i=0;i<2;i++){
  void *info=rfield(duel,names[i]),*view=info?rfield(info,"view"):NULL;
  if(view&&rfield(view,"_currentDuelViewer")==duel&&rfield(view,"_cameraZoomV2Owner")==owner)return 1;
 }
 return 0;
}
static void after_cointoss_hook(void *self,void *mi){
 bootlog("clash boundary entered");
 int outer=g_clashBoundary++;
 if(!outer&&enabled_now()&&!cleanup_pending&&!g_creating&&!g_motionDepth&&!g_timelineEndDepth){
  g_presentationGate=camera_scope_active();
  /* Viewer lifetime is not a live camera or timeline. Evaluate actual
     presentation state per participant; never disable the camera guard. */
  {
   int savedGate=g_presentationGate;void *savedBoundary=g_duelCameraBoundary;
   void *manager=camera_manager(),*cameraOwner=manager?rfield(manager,"_zoomActorAloneV2Owner"):NULL;
   int ownsCamera=duel_owns_camera(manager,self,cameraOwner);
   /* Ask the game to retire a completed duel zoom using its own ownership
      rules. A rejected request retains all existing camera guards. */
   if(savedGate&&!ownsCamera&&manager){
    void *release=find_method(ui_class(manager),"TryReleaseZoomActorAloneV2ForDuelViewer",0);
    if(release&&call_bool(release,manager,NULL)==1){
     g_presentationGate=camera_scope_active();savedGate=g_presentationGate;
     bootlog("clash camera native duel-release accepted");
    }
   }
   if(ownsCamera){g_duelCameraBoundary=self;g_presentationGate=0;}
   if(savedGate){char line[192];snprintf(line,sizeof(line),"clash camera owner=%p viewer=%p owned=%d",cameraOwner,self,ownsCamera);bootlog(line);}
   void *one=rfield(self,"_duelView1"),*two=rfield(self,"_duelView2");
   clash_prepare_info(one);if(two!=one)clash_prepare_info(two);
   g_duelCameraBoundary=savedBoundary;g_presentationGate=savedGate;
  }
 }
 ((void (*)(void *,void *))orig_afterCointoss)(self,mi);
 --g_clashBoundary;
}
static void *m_parryPlayback,*orig_parryPlayback;
static unsigned g_parryTrace;
static void parry_playback_hook(void *self,int detail,void *mi){
 Unit *u=unit_for_app(self);
 if(enabled_now()&&u&&!u->switching){
  char line[256];snprintf(line,sizeof(line),"clash playback sinner=%lu event=%u depth=%d detail=%d wanted=%d current=%d mask=%d camera=%d",(unsigned long)u->sinner,g_parryTrace,u->clashDepth,detail,u->wanted,rfield(u->view,"_curAppearance")==self,motion_busy_mask(self),g_presentationGate);bootlog(line);
 }
 void *app=enabled_now()?clash_visible(u,self):self;
 Skin *skin=u?skin_for_app(u,app):NULL;
 int role=skin&&enabled_now()?clash_request(u,detail):0,mapped=detail;
 if(skin&&enabled_now()&&!role&&clash_native_response(detail))role=7;
 if(role&&!u->switching&&!u->dead&&!u->preserveSpecial&&!cleanup_pending&&introUnit!=u){
  mapped=sr_clash_slot(skin->look,skin->chapterRole,detail,role);
  if(mapped<0)mapped=clash_fallback(u,skin,&app,detail,role);
 }
 ClashPlayback saved=g_clashPlayback;
 if(role)g_clashPlayback=(ClashPlayback){app,mapped,detail,-1,skin&&skin->app==app&&skin->chapterActor};
 playback_begin(app);
 ((void (*)(void *,int,void *))orig_parryPlayback)(app,mapped,mi);
 g_clashPlayback=saved;
}
static int parry_hook(void *self,int result,float delay,uint8_t a2,int close,int defense,int detail,uint8_t a6,void *mi){
  Unit *owner=enabled_now()?unit_for_app(self):NULL;
  void *target=clash_visible(owner,self);int entered=0;
  if(enabled_now()&&!g_visualEventDepth&&!g_clashBoundary&&!InterlockedCompareExchange(&g_busy,1,0)){
    Unit *u=unit_for_app(self);
    if(u&&!u->switching){
      double random=0;
      if(random_double(&random)){
        int row=unit_draw(u,8,random);
        if(row>=0){
          u->stageWanted=-1;u->wanted=row;
          if(skin_index(u,row)<0)queue_push(u,row);
          u->pending=row;
        }
      }
      u->clashDepth++;entered=1;
    }
    InterlockedExchange(&g_busy,0);
  }
  if(enabled_now()){Unit *u=unit_for_app(self);if(u){char line[256];snprintf(line,sizeof(line),"clash begin sinner=%lu event=%u result=%d close=%d defense=%d detail=%d delay=%g wanted=%d mask=%d",(unsigned long)u->sinner,++g_parryTrace,result,close,defense,detail,(double)delay,u->wanted,motion_busy_mask(self));bootlog(line);}}
 void *savedOwner=g_clashOwner;int savedRole=g_clashRole;
 g_clashOwner=owner;g_clashRole=result>=0&&result<32?clashResults[result]:0;
 playback_begin(target);
  int value=((int (*)(void *,int,float,uint8_t,int,int,int,uint8_t,void *))orig_parryOnly)(target,result,delay,a2,close,defense,detail,a6,mi);
  g_clashOwner=savedOwner;g_clashRole=savedRole;
  if(entered&&owner)owner->clashDepth--;
  if(enabled_now()&&unit_for_app(self)){char line[96];snprintf(line,sizeof(line),"clash return event=%u detail=%d mask=%d",g_parryTrace,value,motion_busy_mask(self));bootlog(line);}
  return value;
}
static void skill_start_hook(void *self,void *mi){
  void *target=self;
  if(enabled_now()&&g_cfg->mode!=1&&!InterlockedCompareExchange(&g_busy,1,0)){
    Unit *u=unit_for_app(self);
    if(u&&!u->switching){
      double random=0;
      if(random_double(&random)){
        int row=u->pending>=0?u->pending:unit_draw(u,16,random);
        if(row>=0){
          u->stageWanted=-1;u->wanted=row;
          if(skin_index(u,row)<0)queue_push(u,row);
          u->pending=row;
        }
      }
    }
    InterlockedExchange(&g_busy,0);
  }
  ((void (*)(void *,void *))orig_skillStart)(target,mi);
}
static void start_duel_hook(void *self,void *mi){
  void *target=self;
  if(enabled_now()&&g_cfg->mode!=1&&!InterlockedCompareExchange(&g_busy,1,0)){
    Unit *u=unit_for_app(self);
    if(u&&!u->switching){
      double random=0;
      if(random_double(&random)){
        int row=u->pending>=0?u->pending:unit_draw(u,8,random);
        if(row>=0){
          u->stageWanted=-1;u->wanted=row;
          if(skin_index(u,row)<0)queue_push(u,row);
          u->pending=row;
        }
      }
    }
    InterlockedExchange(&g_busy,0);
  }
  ((void (*)(void *,void *))orig_startDuel)(target,mi);
}
static void *get_motion_hook(void *self,int detail,uint8_t flag,void *mi){
  if(enabled_now()&&!cleanup_pending&&!g_motionDepth&&!g_creating){
   Unit *owner=unit_for_app(self);
   if(owner&&self!=hiddenTimingApp&&self==owner->baseApp&&owner->view&&!owner->switching&&!owner->coinDefense&&
      !owner->preserveSpecial&&introUnit!=owner&&sr_attack_detail(detail,owner->coinKnown,owner->coinMotion,0,0)){
    void *current=rfield(owner->view,"_curAppearance");Skin *shown=skin_for_app(owner,current);
    if(!shown&&current==self&&owner->staticHidden)shown=held_appearance(owner);
    if(shown&&!(g_rows[shown->row].excluded&(SR_STATIC_APPEARANCE_FLAG|2)))self=shown->app;
   }
  }
  if(clash_raw(self,detail))return ((void *(*)(void *,int,uint8_t,void *))orig_getMotion)(self,detail,flag,mi);
  if(enabled_now()&&!cleanup_pending&&!g_creating&&!g_motionDepth){
   Unit *u=unit_for_app(self);Skin *skin=u?skin_for_app(u,self):NULL;
   int role=skin?clash_request(u,detail):0;
   if(role){
    int mapped=sr_clash_slot(skin->look,skin->chapterRole,detail,role);
    return ((void *(*)(void *,int,uint8_t,void *))orig_getMotion)(self,mapped>=0?mapped:detail,flag,mi);
   }
  }
  /* Only change the scalar request to an existing cached donor attack.
     One native call, no recursion, allocations, resource loads or reflection. */
  if(enabled_now()&&!cleanup_pending&&!g_creating&&!g_motionDepth){
    Unit *u=unit_for_app(self);Skin *skin=u?skin_for_app(u,self):NULL;
    if(skin){
     if(skin->chapterActor){
      /* Nested GetMotion receives the donor detail already selected at entry. */
      if(g_chapterPlaybackApp!=self){
       int verified=0,mapped=chapter_group(u,skin,detail,chapter_skill_id(u,u->observedAction),&verified);
       if(mapped>=0)detail=mapped;
       else {
        int fallback=verified==5?0:sr_playback_detail(skin->motionCounts,detail,u->coinTier);
        detail=fallback>=0&&fallback<SR_MOTION_CACHE&&skin->motionCounts[fallback]>0?fallback:0;
       }
      }
      return ((void *(*)(void *,int,uint8_t,void *))orig_getMotion)(self,detail,flag,mi);
     }
     if(g_rows[skin->row].excluded&SR_STATIC_APPEARANCE_FLAG){
      int attack=sr_attack_detail(detail,u->coinKnown,u->coinMotion,u->coinDefense,introApp==self);
      detail=sr_static_lookup_detail(g_rows[skin->row].excluded,attack,detail);
      return ((void *(*)(void *,int,uint8_t,void *))orig_getMotion)(self,detail,flag,mi);
     }
     if(g_projection.app==self){int mapped=-1,index=-1;
      if(g_projection.segmentDetail>=0&&detail==g_projection.segmentDetail)
       return ((void *(*)(void *,int,uint8_t,void *))orig_getMotion)(self,detail,flag,mi);
      if(sr_salvador_s3(skin->motionCounts,u->baseName,motion_identity(skin),g_projection.sourceDetail,u->coinIndex,&mapped,&index)&&detail==mapped)
       return ((void *(*)(void *,int,uint8_t,void *))orig_getMotion)(self,detail,flag,mi);
     }
     if(g_projection.app==self&&sr_verified_paired_attack(skin->motionCounts,paired_source(u,skin),motion_identity(skin),g_projection.sourceDetail,-1)>=0)
      return ((void *(*)(void *,int,uint8_t,void *))orig_getMotion)(self,detail,flag,mi);
     int requested=detail;
     int attack=!u->coinDefense&&sr_attack_detail(detail,u->coinKnown,u->coinMotion,0,introApp==self);
     if(!attack)return ((void *(*)(void *,int,uint8_t,void *))orig_getMotion)(self,detail,flag,mi);
     detail=sr_resolve_attack(skin->motionCounts,detail,u->coinKnown,u->coinTier,u->coinMotion,u->coinDefense,introApp==self);
     if(attack&&g_rows[skin->row].story)detail=sr_donor_tier_detail(skin->motionCounts,detail,u->coinTier);
     if(attack)detail=sr_native_motion_detail(skin->motionCounts,skin->nativeMotionDetail,requested,detail);
     if(attack&&g_rows[skin->row].story)detail=sr_donor_coin_fit(skin->motionCounts,detail,native_order_coin_count(u));
     if(attack)detail=sr_verified_paired_attack(skin->motionCounts,paired_source(u,skin),motion_identity(skin),requested,detail);
    }
  }
  return ((void *(*)(void *,int,uint8_t,void *))orig_getMotion)(self,detail,flag,mi);
}
static void initialize_hook(void *app,void *view,void *mi){
  ((void (*)(void *,void *,void *))orig_init)(app,view,mi);
  if(g_creating||!enabled_now()||cleanup_pending)return;
  if(InterlockedCompareExchange(&g_busy,1,0))return;
  unit_register(app,view);
  InterlockedExchange(&g_busy,0);
}
/* Observe the deployed view only. No model or Spine calls in this hook. */
static void form_round_hook(void *view,void *mi){
 ((void (*)(void *,void *))orig_formRound)(view,mi);
 if(!enabled_now()||cleanup_pending)return;
 for(int i=0;i<SR_UNIT_MAX;i++){
  Unit *u=&g_units[i];
  if(u->used&&!u->dead&&u->view==view){
   /* Coalesce callbacks before the next render observation. */
   if(!u->roundPending){u->observedRound++;u->roundPending=1;u->lastDefenseAction=NULL;u->lastDefenseDrawAction=NULL;u->defenseDrawLatched=0;u->defenseLatch=0;}
   /* BattleUnitView.OnRoundStart is the view-level counterpart of the boss
      UnitScript OnRoundStart_View rows, so the trigger name carries over.
      Rows that map to several keys stay silent, and the dedupe window keeps
      the repeated callbacks inside one round from speaking twice. */
   /* A single voice key does not establish the boss's native round/state
      conditions. Only independently verified rules may request playback. */
   break;
  }
 }
}
/* Exact audited ABI: model, two references, three Int32 and Boolean.
   Read native integer getters only; no managed invocation or model mutation. */
static int form_hp_value(void *method,void *model){
 if(!method||!model)return -1;
 void *fn=*(void **)method;
 return fn?((int (*)(void *,void *))fn)(model,method):-1;
}
static void form_hit_hook(void *model,void *action,void *coin,int damage,int realDamage,int timing,uint8_t flag,void *mi){
 Unit *unit=NULL;
 if(enabled_now()&&!cleanup_pending)for(int i=0;i<SR_UNIT_MAX;i++){
  Unit *u=&g_units[i];if(u->used&&!u->dead&&u->observedModel==model){unit=u;break;}
 }
 int before=unit?form_hp_value(m_formHp,model):-1;
 ((void (*)(void *,void *,void *,int,int,int,uint8_t,void *))orig_formHit)(model,action,coin,damage,realDamage,timing,flag,mi);
 if(unit&&!unit->dead){
  int after=form_hp_value(m_formHp,model),max=form_hp_value(m_formMaxHp,model);
  unit->formHp=after;unit->formMaxHp=max;unit->formHpAt=GetTickCount();
  /* OnTakeAttackDamage can run on both sides of the model's damage step.
     A zero-damage notification must not activate a health threshold. */
  if(after>0&&(damage>0||realDamage>0)){
   sr_form_survived_hit(&unit->formState,before,max);
   sr_form_survived_hit(&unit->formState,after,max);
  }
 }
}
static void view_destroy_hook(void *view,void *mi){
  sr_voice_cancel_view(view);
  if(!g_quitting&&InterlockedCompareExchange(&g_busy,1,0)==0){
    Unit *u=NULL;
    for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used&&g_units[i].view==view){u=&g_units[i];break;}
    if(u)u->dead=1;
    InterlockedExchange(&g_busy,0);
  }
  ((void (*)(void *,void *))orig_viewDestroy)(view,mi);
}
/* BattleUnitView.OnDie: 8 managed args plus MethodInfo.
   Only the real-death call is forwarded to the voice queue; the over-kill and
   no-motion variants reuse the same entry point. */
/* The replacement is currently verified only for Priest 8378.  Keep the
   accepted state for this registered unit, not merely the queue time window. */
#include "verified_voice_rules.h"
static int death_voice_accept(Unit *u,int enabled,int playbackAvailable){
 if(!enabled||!playbackAvailable||!u)return 0;
 if(u->deathVoiceAccepted)return 1;
 const SrVerifiedVoiceRule *rule=sr_verified_voice_rule(u->voiceBoss,"OnDie_View",NULL);
 if(!rule)return 0;
 char key[SR_VOICE_LEN];
 if(!sr_voice_single(u->voiceBoss,rule->trigger,key,sizeof(key))||strcmp(key,rule->key))return 0;
 if(!sr_voice_request(u->view,u->voiceBoss,rule->trigger))return 0;
 u->deathVoiceAccepted=1;return 1;
}
static void die_hook(void *view,uint8_t real,uint8_t over,float ratio,void *skill,
                     int overrideDir,uint8_t setVoice,uint8_t noneMotion,
                     uint8_t noneEffect,void *mi){
  int accepted=0;Unit *u=NULL;
  if(view&&real&&!g_quitting){
    for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used&&g_units[i].view==view){u=&g_units[i];break;}
        int active=enabled_now()&&!cleanup_pending;
    accepted=death_voice_accept(u,active,m_playMultiVoice!=NULL&&m_revive!=NULL);
    /* Unverified boss scripts may gate death voice on a fake-death or other
       state. Leave their native sound untouched until their rule is audited. */
    char line[160];snprintf(line,sizeof(line),"die: view=%p boss=%u over=%d ratio=%.2f replacement=%d",view,u?u->voiceBoss:0,(int)over,(double)ratio,accepted);bootlog(line);
  }
  ((void (*)(void *,uint8_t,uint8_t,float,void *,int,uint8_t,uint8_t,uint8_t,void *))orig_die)
    (view,real,over,ratio,skill,overrideDir,accepted?0:setVoice,noneMotion,noneEffect,mi);
}
static void revive_hook(void *view,uint8_t produce,void *mi){
 sr_voice_cancel_view(view);
 ((void (*)(void *,uint8_t,void *))orig_revive)(view,produce,mi);
 for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used&&g_units[i].view==view){g_units[i].deathVoiceAccepted=0;break;}
}
/* Only exact source appearance names provide a native form signal. */
static int paired_native_stage(const char *base, const char *observed){
 if(!base||!observed)return -1;
 const char *normal=NULL,*alternate=NULL;
 if(!strncmp(base,"10314",5)){normal="10314_Donquixote_Index_DiscipleAppearance";alternate="10314_Donquixote_Index_Disciple_AwakenAppearance";}
 else if(!strncmp(base,"10215",5)){normal="10215_Faust_Ring_DiscipleAppearance";alternate="10215_Faust_Ring_Disciple_CastOffAppearance";}
 if(!normal){
  const SrCounterpartForm *f=sr_counterpart_form(base);
  if(!f)return -1;
  normal=f->normal;alternate=f->alternate;
 }
 size_t len=strlen(observed);const char *suffix="(Clone)";size_t tail=strlen(suffix);
 if(len>=tail&&!strcmp(observed+len-tail,suffix))len-=tail;
 while(len && observed[len-1]==' ')len--;
 if(strlen(normal)==len&&!strncmp(observed,normal,len))return 0;
 if(strlen(alternate)==len&&!strncmp(observed,alternate,len))return 1;
 return -1;
}
static int object_native_stage(const char *base,void *actual,char identity[128],char objectName[128]){
 int stage=identity_text(actual,identity,128)?paired_native_stage(base,identity):-1;
 if(stage>=0)return stage;
 void *getter=find_method(ui_class(actual),"get_gameObject",0);int ok=1;
 void *go=getter?call_obj(getter,actual,NULL,&ok):NULL;
 void *getName=go?find_method(ui_class(go),"get_name",0):NULL;
 void *name=getName?call_obj(getName,go,NULL,&ok):NULL;
 return ok&&name&&string_ascii(name,objectName,128)?paired_native_stage(base,objectName):-1;
}
static void change_appearance_hook(void *view,void *name,uint8_t flag,void *mi){
  void *previous=view?rfield(view,"_curAppearance"):NULL;
  ((void (*)(void *,void *,uint8_t,void *))orig_changeAppearance)(view,name,flag,mi);
  /* Derive voice only from the appearance actually committed by the game.
     Failed requests must preserve the old selection; returning to the base or
     a non-story skin must clear the previous boss. */
  if(!view||g_quitting)return;
  for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used&&g_units[i].view==view){
    Unit *u=&g_units[i];
    void *actual=rfield(view,"_curAppearance");
    if(!u->switching && actual && !skin_for_app(u,actual) && (!strncmp(u->baseName,"10314",5)||!strncmp(u->baseName,"10215",5)||sr_counterpart_form(u->baseName))){
      char requested[128]={0},identity[128]={0},objectName[128]={0};
      int native=-1;
      if(string_ascii(name,requested,sizeof(requested)) && actual!=previous)native=paired_native_stage(u->baseName,requested);
      if(native<0)native=object_native_stage(u->baseName,actual,identity,objectName);
      {char line[512];snprintf(line,sizeof(line),"source form observed base=%.64s request=%.100s identity=%.100s object=%.100s stage=%d",u->baseName,requested,identity,objectName,native);bootlog(line);}
      if(native>=0){u->nativeStage=native;u->nativeValid=1;u->nativeAppearance=actual;}

    }
    if(enabled_now()&&!cleanup_pending&&!u->switching&&actual==u->baseApp&&u->staticHidden){
     Skin *held=held_appearance(u);if(held&&held->go)set_active(held->go,1);
    }
    Skin *skin=actual?skin_for_app(u,actual):NULL;
    u->voiceBoss=voice_skin_owner(skin);
    break;
  }
}

/* ---------------- main thread tick ---------------- */
static int g_metadataPhase;
static DWORD g_metadataStart;
static void setup_staging(void){
  if(g_staging)return;
  void *goClass=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_core,"UnityEngine","GameObject");
  if(!goClass)return;
  g_staging=ui_new(goClass);
  if(!g_staging)return;
  g_stagingRoot=ui_root(g_staging);
  void *ctor=find_method(ui_class(g_staging),".ctor",1);
  void *name=make_string("SinnersNative_Staging");uintptr_t nameRoot=ui_root(name);
  if(ctor){int ok=1;void *args[]={name};call_obj(ctor,g_staging,args,&ok);}
  ui_unroot(nameRoot);
  set_active(g_staging,0);
  void *dontDestroy=find_method(goClass,"DontDestroyOnLoad",1);
  if(dontDestroy){int ok=1;void *args[]={g_staging};call_obj(dontDestroy,NULL,args,&ok);}
  int ok=1;
  g_stagingTr=call_obj(m_getTransform,g_staging,NULL,&ok);
  {char line[128];wsprintfA(line,"staging ready transform=%d ok=%d",!!g_stagingTr,ok);bootlog(line);}
}
static void metadata_begin(void){
 if(!m_loadMeta){g_metadataPhase=2;bootlog("metadata: method missing; appearance preparation blocked");return;}
 if(!g_metaBox){
  void *key=make_string("Skin/MotionMetadataDB.asset");uintptr_t keyRoot=ui_root(key);
  void *exc=NULL,*args[]={key};
  void *box=((void *(*)(void *,void *,void **,void **))api[API_INVOKE])(m_loadMeta,NULL,args,&exc);ui_unroot(keyRoot);
  if(exc||!box){g_metadataPhase=2;bootlog("metadata: request failed; appearance preparation blocked");return;}
  g_metaBox=box;g_metaBoxRoot=ui_root(box);g_metadataPhase=1;
  if(!g_metaBoxRoot){g_metadataPhase=2;return;}
 }
 void *type=ui_class(g_metaBox),*value=ui_unbox(g_metaBox);
 void *done=find_method(type,"get_IsDone",0);
 if(!done||call_bool(done,value,NULL)!=1)return;
 void *status=find_method(type,"get_Status",0);
 if(!status||call_int(status,value,NULL)!=1){g_metadataPhase=2;bootlog("metadata: asynchronous load failed; pool not blacklisted");return;}
 int ok=1;void *result=find_method(type,"get_Result",0);
 void *db=result?call_obj(result,value,NULL,&ok):NULL;
 if(!ok||!db){g_metadataPhase=2;bootlog("metadata: Result unavailable; pool not blacklisted");return;}
 g_metaDBRoot=ui_root(db);if(!g_metaDBRoot){g_metadataPhase=2;return;}
 void *init=find_method(ui_class(db),"InitRuntimeMotionDict",0);
 if(init&&!call_exc(init,db,NULL)){g_metadataPhase=2;bootlog("metadata: InitRuntimeMotionDict exception; preparation blocked");return;}
 g_metadataDB=db;g_metadataPhase=3;bootlog("metadata: asynchronously ready");
}

static void register_existing(void){
  if(!m_findAll)return;
  void *args[]={t_appearance};int ok=1;
  void *array=call_obj(m_findAll,NULL,args,&ok);
  if(!ok||!array)return;
  uintptr_t root=ui_root(array);
  uintptr_t count=*(uintptr_t *)((char *)array+24);
  if(count>20000)count=0;
  int registered=0;
  for(uintptr_t i=0;i<count;i++){
    void *app=((void **)((char *)array+32))[i];
    if(!app)continue;
    void *flag=find_field_obj(app,"_isInitialized");
    if(!flag||!*(uint8_t *)((char *)app+((size_t (*)(void *))api[API_FIELD_OFFSET])(flag)))continue;
    void *view=rfield(app,"_battleUnitView");
    if(!view||!rfield(view,"m_CachedPtr"))continue;
    int before=0;for(int k=0;k<SR_UNIT_MAX;k++)if(g_units[k].used)before++;
    unit_register(app,view);
    int after=0;for(int k=0;k<SR_UNIT_MAX;k++)if(g_units[k].used)after++;
    if(after>before)registered++;
  }
  ui_unroot(root);
  if(registered>0){char line[128];wsprintfA(line,"existing scan registered=%d",registered);bootlog(line);}
}

static void *pick_method(void *klass,const char *name,const char **types,int count);
/* Use the appearance's own parameter list; never search the scene.
   Only audited visual-controller classes with an explicit two-state map. */
static const char *visual_group_class(const char *id){
 if(!strcmp(id,"10515")||!strcmp(id,"10715"))return "CharacterAppearanceUB_ChangeSDAnimTrack";
 if(!strcmp(id,"10816"))return "CharacterAppearanceUB_10816";
 if(!strcmp(id,"10312"))return "CharacterAppearanceUB_10312";
 if(!strcmp(id,"10913"))return "CharacterAppearanceUB_10913";
 return NULL;
}
static int apply_visual_group(void *app,const char *id,int stage){
 const char *expected=visual_group_class(id);if(!expected)return 1;
 void *parameters=rfield(app,"_parameterList");int n=parameters?list_count(parameters):0;
 if(n<=0||n>128)return 0;
 const char *types[]={"System.Int32","System.Boolean"};
 for(int i=0;i<n;i++){
  void *item=list_item(parameters,i);if(!item)continue;
  void *matched=ui_class(item);
  while(matched){
   const char *name=((const char *(*)(void *))api[API_CLASS_NAME])(matched);
   if(name&&!strcmp(name,expected))break;
   matched=ui_parent(matched);
  }
  if(!matched)continue;
  void *method=NULL;
  for(void *c=ui_class(item);c&&!method;c=ui_parent(c))method=pick_method(c,"SetRankEffect",types,2);
  if(!method)return 0;
  int rank=stage;uint8_t init=0;void *args[]={&rank,&init};
  if(!call_exc(method,item,args))return 0;
  /* Some subclasses implement their track mapping in ChangeGroup. */
  void *group=find_method(ui_class(item),"ChangeGroup",0);
  return !group||call_exc(group,item,NULL);
 }
 return 0;
}
static void *compose_head_weapon(void *data,void *weapon,uintptr_t *root){
 *root=0;if(!data||!weapon)return NULL;
 void *find=find_method(ui_class(data),"FindSkin",1);
 void *headName=make_string("head_on");uintptr_t nameRoot=ui_root(headName);
 if(!nameRoot)return NULL;
 int ok=0;void *headArgs[]={headName};void *head=find?call_obj(find,data,headArgs,&ok):NULL;
 ui_unroot(nameRoot);if(!ok||!head)return NULL;
 const char *stringType[]={"System.String"},*skinType[]={"Spine.Skin"};
 void *klass=ui_class(weapon),*ctor=pick_method(klass,".ctor",stringType,1),*add=pick_method(klass,"AddSkin",skinType,1);
 if(!ctor||!add)return NULL;
 void *combined=ui_new(klass);*root=ui_root(combined);if(!*root)return NULL;
 void *label=make_string("FaustNativeComposite");nameRoot=ui_root(label);
 if(!nameRoot)goto failed;
 void *ctorArgs[]={label};ok=call_exc(ctor,combined,ctorArgs);ui_unroot(nameRoot);
 if(!ok)goto failed;
 void *headAdd[]={head},*weaponAdd[]={weapon};
 if(!call_exc(add,combined,headAdd)||!call_exc(add,combined,weaponAdd))goto failed;
 return combined;
failed:
 ui_unroot(*root);*root=0;return NULL;
}
/* Render-pump only. Never call a donor passive or mutate combat resources. */
/* Only the controller currently owning the camera may reset global focus.
   Other retired controllers may clear their own local pivots only. */
static int release_owned_appearance_camera(void *app){
 if(!app||!rfield(app,"m_CachedPtr"))return 1;
 void *controller=rfield(app,"_camController");if(!controller||!rfield(controller,"m_CachedPtr"))return 1;
 void *managerClass=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"","BattleCamManager");
 void *get=managerClass?find_method(managerClass,"get_Instance",0):NULL;
 int ok=0;void *manager=get?call_obj(get,NULL,NULL,&ok):NULL;
 if(!ok||!manager)return 0;
 int ownsZoom=rfield(manager,"_zoomActorAloneV2AppearanceCamController")==controller||
              rfield(manager,"_zoomActorAloneV2TriggerSource")==controller;
 void *owner=ownsZoom?rfield(manager,"_zoomActorAloneV2Owner"):NULL;
 if(owner){
  void *complete=find_method(ui_class(manager),"CompleteZoomActorAloneV2",1);void *args[]={owner};
  if(!complete||!call_exc(complete,manager,args))return 0;
  void *view=rfield(app,"_battleUnitView");
  if(view&&rfield(view,"_cameraZoomV2Owner")==owner){
   complete=find_method(ui_class(view),"CompleteCameraZoomV2",1);
   if(complete&&!call_exc(complete,view,args))return 0;
  }
 }
 void *current=rfield(manager,"_curCam");
 int ownsCamera=current&&(current==rfield(controller,"camera_Actor")||current==rfield(controller,"camera_Enemy"));
 int foreignZoom=rfield(manager,"_zoomActorAloneV2Owner")&&!ownsZoom;
 if(ownsCamera&&!foreignZoom){
  void *end=find_method(ui_class(controller),"OnCameraEnd",0);
  return end&&call_exc(end,controller,NULL);
 }
 void *flag=find_field_obj(controller,"isActiveCam");
 if(flag){
  size_t offset=((size_t (*)(void *))api[API_FIELD_OFFSET])(flag);
  if(*(uint8_t *)((char *)controller+offset)){
   void *clear=find_method(ui_class(controller),"ClearZoomV2FovSync",0);
   if(!clear||!call_exc(clear,controller,NULL))return 0;
   void *actor=rfield(controller,"camPivot_Actor"),*enemy=rfield(controller,"camPivot_Enemy");
   if(actor)set_active(actor,0);if(enemy)set_active(enemy,0);
   *(uint8_t *)((char *)controller+offset)=0;
  }
 }
 return 1;
}
static int intro_supported(const char *id){
 return !strcmp(id,"10215")||!strcmp(id,"10314")||!strcmp(id,"10710")||!strcmp(id,"10915")||!strcmp(id,"10816");
}
static void stop_transform_intro(int reset){
 if(introApp&&rfield(introApp,"m_CachedPtr")){
  if(reset)finish_presentation(introApp);
  else if(!introInterrupted&&!release_owned_appearance_camera(introApp))bootlog("intro camera cleanup could not confirm owner");
 }
 ui_unroot(introRoot);introRoot=0;introUnit=NULL;introApp=NULL;introInterrupted=0;
}
static void play_intro_part(int detail){
 introStarted=GetTickCount();introFrame=g_frame;
 g_motionDepth++;
 playback_begin(introApp);
 ((void (*)(void *,int,uint8_t,int,uint8_t,void *,uint8_t,void *))orig_changeMotion)(introApp,detail,0,0,0,NULL,0,m_changeMotion);
 g_motionDepth--;
}
static void pump_transform_intro(void){
 if(introUnit){
  int valid=introUnit->used&&!introUnit->dead&&introUnit->view&&rfield(introUnit->view,"m_CachedPtr")&&
   rfield(introUnit->view,"_curAppearance")==introApp;
  if(!enabled_now()||!valid||introInterrupted){stop_transform_intro(0);return;}
  if((DWORD)(GetTickCount()-introStarted)>15000){bootlog("intro timeout; restoring owned camera");stop_transform_intro(1);return;}
  if(g_frame<=introFrame+2)return;
  if(!presentation_busy(introApp)){
   if(introHasSecond&&!introPart){introPart=1;play_intro_part(21);return;}
   stop_transform_intro(1);
  }
  return;
 }
 if(!enabled_now()||cleanup_pending||g_presentationGate||g_anyViewerActive)return;
 for(int i=0;i<SR_UNIT_MAX;i++){
  Unit *u=&g_units[i];if(!u->used||u->dead||!u->stageIntroPending||u->switching)continue;
  void *app=u->view?rfield(u->view,"_curAppearance"):NULL;Skin *skin=skin_for_app(u,app);
  if(!skin||skin->row!=u->stageIntroRow){u->stageIntroPending=0;continue;}
  if(u->wanted>=0||presentation_busy(app))continue;
  int actual=-1,count=motion_count(app,20,&actual);
  u->stageIntroPending=0;if(count<1||actual!=20){bootlog("stage transition motion unavailable; appearance retained");continue;}
  uintptr_t root=ui_root(app);if(!root)continue;
  introUnit=u;introApp=app;introRoot=root;introInterrupted=0;introPart=0;introHasSecond=0;
  bootlog("stage transition intro start identity=story_1325_Index_discipleAppearance");
  play_intro_part(20);return;
 }
 for(int i=0;i<SR_UNIT_MAX;i++){
  Unit *u=&g_units[i];if(!u->used||u->dead||!u->introPending||u->switching)continue;
  int row=u->introRow;if(row<0||(uint32_t)row>=g_rowCount){u->introPending=0;continue;}
  const char *id=g_rows[row].identity;
  if(!intro_supported(id)){u->introPending=0;continue;}
  int catalog=sr_form_index(id),stage=desired_row_form(u,row);
  if(!strcmp(id,"10816"))stage=sr_form_stage(&u->formState,id,2,u->sanity,u->sanityValid);
  if(!stage)continue;
  unsigned bit=1u<<(catalog>=0?catalog:16);
  if(u->introPlayed&bit){u->introPending=0;continue;}
  if(u->wanted>=0&&u->wanted!=row){u->introPending=0;continue;}
  void *app=rfield(u->view,"_curAppearance");Skin *skin=skin_for_app(u,app);
  if(!skin||skin->row!=row){if(u->wanted<0)u->introPending=0;continue;}
  if((catalog>=0&&skin->form!=stage)||(!strcmp(id,"10816")&&skin->internalStage!=stage)||presentation_busy(app))continue;
  int actual=-1,count=motion_count(app,20,&actual);
  u->introPending=0;if(count<1||actual!=20){bootlog("intro motion unavailable; appearance retained");continue;}
  uintptr_t root=ui_root(app);if(!root)continue;
  introUnit=u;introApp=app;introRoot=root;introInterrupted=0;introPart=0;
  int second=-1;introHasSecond=!strcmp(id,"10314")&&motion_count(app,21,&second)>0&&second==21;
  u->introPlayed|=bit;
  char line[128];snprintf(line,sizeof(line),"transform intro start identity=%.12s parts=%d",id,introHasSecond?2:1);bootlog(line);
  play_intro_part(20);return;
 }
}
#include "chapter_forms_runtime.inc"
static void apply_internal_form(Unit *u){
 if(!u||u->dead||u->switching||!u->view||g_presentationGate||g_anyViewerActive)return;
 /* Do not let legacy form rules alter the current form when a newly selected
    group cannot yet evaluate its conditions. */
 if(u->stageGroup>0&&u->stageRevision==g_stageGroups.revision&&u->stageChoice<0)return;
 void *app=rfield(u->view,"_curAppearance");Skin *skin=skin_for_app(u,app);
 if(!skin||(u->wanted>=0&&u->wanted!=skin->row))return;
 if(stage_waiting_for_other_appearance(u,g_rows[skin->row].identity))return;
 const SrChapterVisual *chapter=sr_chapter_visual(g_rows[skin->row].identity);
 if(chapter){chapter_internal(u,skin,chapter);return;}
 const SrInternalForm *policy=sr_internal_policy(g_rows[skin->row].identity);
 if(!policy)policy=auto_internal(skin->row);
 if(!policy){
  const char *id=g_rows[skin->row].identity;
  if(strcmp(id,"10312")&&strcmp(id,"10913"))return;
  if(!u->roundSanityValid&&!sr_wf_has_override(&g_workbenchForms,(uint32_t)strtoul(id,NULL,10))&&!(u->stageGroup>0&&u->stageRevision==g_stageGroups.revision))return;
  int stage=u->roundSanityValid?sr_form_stage(&u->formState,id,2,u->roundSanity,1):skin->internalStage;
  stage=workbench_form_stage(u,id,stage,2);
  if(stage==skin->internalStage||(skin->internalFailed&(1u<<stage))||presentation_busy(app))return;
  if(apply_visual_group(app,id,stage)){
   skin->internalStage=stage;
   char line[160];snprintf(line,sizeof(line),"sanity visual group identity=%.12s stage=%d roundMp=%d",id,stage,u->roundSanity);bootlog(line);
  }else{apply_visual_group(app,id,skin->internalStage);skin->internalFailed|=1u<<stage;bootlog("sanity visual controller unavailable for selected stage");}
  return;
 }
 int stage=sr_form_stage(&u->formState,policy->id,policy->count,u->sanity,u->sanityValid);
 stage=workbench_form_stage(u,policy->id,stage,policy->count);
 if(stage==skin->internalStage||(skin->internalFailed&(1u<<stage))||presentation_busy(app))return;
 const char *name=policy->skins[stage];
 void *spines=rfield(app,"_spineSkins");int count=spines?list_count(spines):0;
 struct {void *skeleton,*set,*setup,*previous;uintptr_t previousRoot;} undo[256];
 if(count>256){skin->internalFailed|=1u<<stage;return;}
 int changed=0,failed=0;
 for(int i=0;i<count;i++){
  void *spine=list_item(spines,i);void *anim=spine?rfield(spine,"_spine_Animation"):NULL;
  if(!anim)continue;
  void *getter=find_method(ui_class(anim),"get_Skeleton",0);
  int ok=0;void *skeleton=getter?call_obj(getter,anim,NULL,&ok):NULL;
  if(!ok||!skeleton)continue;
  void *dataMethod=find_method(ui_class(skeleton),"get_Data",0);
  void *data=dataMethod?call_obj(dataMethod,skeleton,NULL,&ok):NULL;
  if(!ok||!data)continue;
  void *find=find_method(ui_class(data),"FindSkin",1);
  void *text=make_string(name);uintptr_t textRoot=ui_root(text);
  if(!textRoot){failed=1;break;}
  void *exc=NULL,*args[]={text};void *target=find?ui_invoke(find,data,args,&exc):NULL;
  ui_unroot(textRoot);
  /* A spine with no matching skin belongs to another body part. */
  if(!find||exc){failed=1;break;}
  if(!target)continue;
  const char *types[]={"Spine.Skin"};
  void *set=pick_method(ui_class(skeleton),"SetSkin",types,1);
  void *setup=find_method(ui_class(skeleton),"SetSlotsToSetupPose",0);
  void *previousMethod=find_method(ui_class(skeleton),"get_Skin",0);
  if(!set||!setup||!previousMethod){failed=1;break;}
  void *previous=ui_invoke(previousMethod,skeleton,NULL,&exc);
  if(exc){failed=1;break;}
  uintptr_t compositeRoot=0;
  if(!strcmp(policy->id,"11115")){
   target=compose_head_weapon(data,target,&compositeRoot);
   if(!target){failed=1;break;}
  }
  uintptr_t previousRoot=previous?ui_root(previous):0;
  if(previous&&!previousRoot){ui_unroot(compositeRoot);failed=1;break;}
  undo[changed].skeleton=skeleton;undo[changed].set=set;undo[changed].setup=setup;
  undo[changed].previous=previous;undo[changed].previousRoot=previousRoot;changed++;
  void *setArgs[]={target};
  int applied=call_exc(set,skeleton,setArgs)&&call_exc(setup,skeleton,NULL);
  ui_unroot(compositeRoot);
  if(!applied){failed=1;break;}
 }
 if(!failed&&changed&&!apply_visual_group(app,policy->id,stage)){
  apply_visual_group(app,policy->id,skin->internalStage);failed=1;
 }
 for(int i=changed-1;i>=0;i--){
  if(failed){
   void *restoreArgs[]={undo[i].previous};
   if(!call_exc(undo[i].set,undo[i].skeleton,restoreArgs)||!call_exc(undo[i].setup,undo[i].skeleton,NULL))
    bootlog("internal form: spine rollback failed");
  }
  ui_unroot(undo[i].previousRoot);
 }
 if(!failed&&changed){
  skin->internalStage=stage;
  char line[160];snprintf(line,sizeof(line),"internal form identity=%.12s stage=%d skin=%.40s spines=%d",policy->id,stage,name,changed);bootlog(line);
 }else{
  skin->internalFailed|=1u<<stage;
  char line[160];snprintf(line,sizeof(line),"internal form unavailable identity=%.12s skin=%.40s stage=%d",policy->id,name,stage);bootlog(line);
 }
}
/* Opt-in metadata-only diagnostics. Never invokes discovered methods or reads
   fields; future live probing must separately validate signatures and values. */
static void source_diag_methods(Unit *u,void *model){
 static int enabled=-1,done=0;if(enabled<0){wchar_t path[32768];enabled=0;
  if(GetModuleFileNameW(g_self,path,32768)){wchar_t *s=wcsrchr(path,L'\\');if(s){lstrcpyW(s+1,L"source-form-diagnostics.enabled");DWORD a=GetFileAttributesW(path);enabled=a!=INVALID_FILE_ATTRIBUTES&&!(a&FILE_ATTRIBUTE_DIRECTORY);}}}
 if(!enabled||done||!u||!model||strncmp(u->baseName,"10115",5)||(u->baseName[5]&&u->baseName[5]!='_'))return;
 done=1;void *objects[]={model,u->baseApp};const char *labels[]={"model","baseAppearance"};
 for(int x=0;x<2;x++){if(!objects[x])continue;int total=0;
  for(void *k=ui_class(objects[x]);k&&total<160;k=ui_parent(k)){
   const char *cls=((const char *(*)(void *))api[API_CLASS_NAME])(k);void *it=NULL,*m;
   while(total<160&&(m=((void *(*)(void *,void **))api[API_METHODS])(k,&it))){
    const char *name=((const char *(*)(void *))api[API_METHOD_NAME])(m);if(!sr_source_diag_name(name))continue;
    void *rt=((void *(*)(void *))api[API_RETURN_TYPE])(m);char *type=rt?((char *(*)(void *))api[API_TYPE_NAME])(rt):NULL;
    char line[512];snprintf(line,sizeof(line),"source-form diagnostic %s class=%.100s method=%.140s argc=%u return=%.140s",labels[x],cls?cls:"?",name,(unsigned)((uint32_t (*)(void *))api[API_PARAM_COUNT])(m),type?type:"?");bootlog(line);
    if(type)((void (*)(void *))api[API_FREE])(type);total++;
   }
  }
 }
 bootlog("source-form diagnostic: metadata enumeration complete; no game values read");
}
static void update_sanity(Unit *u){
 u->sanityValid=0;
 void *model=rfield(u->view,"_unitModel");source_diag_methods(u,model);u->observedModel=model;void *m=model?find_method(ui_class(model),"get_Mp",0):NULL;
 int needHp=0;for(uint32_t i=0;i<g_workbenchForms.count;i++)if(g_workbenchForms.rules[i].mode==3){needHp=1;break;}
 if(!needHp)needHp=g_stageNeedsHp;
 DWORD now=GetTickCount();
 if(needHp&&(DWORD)(now-u->formHpAt)>=250){
  u->formHp=model?form_hp_value(m_formHp,model):-1;
  u->formMaxHp=model?form_hp_value(m_formMaxHp,model):-1;u->formHpAt=now;
 }
 void *exc=NULL,*v=m?ui_invoke(m,model,NULL,&exc):NULL;
 if(!exc&&v){int mp=*(int *)ui_unbox(v);if(mp>=-45&&mp<=45){u->sanity=mp;u->sanityValid=1;}}
}
/* Group changes share the existing async loader and wait for the normal idle
   switch gate. Group state is scoped to the currently displayed appearance. */
static void poll_paired_native(Unit *u){
 if(!u||!u->used||u->dead||!u->view||u->switching||(strncmp(u->baseName,"10314",5) && strncmp(u->baseName,"10215",5)&&!sr_counterpart_form(u->baseName)))return;
 void *actual=rfield(u->view,"_curAppearance");
 if(!actual||skin_for_app(u,actual))return;
 char identity[128]={0},objectName[128]={0};
 int native=object_native_stage(u->baseName,actual,identity,objectName);
 if(native>=0){if(!u->nativeValid||u->nativeStage!=native||u->nativeAppearance!=actual){char line[300];snprintf(line,sizeof(line),"source form polled base=%.60s identity=%.80s object=%.80s stage=%d",u->baseName,identity,objectName,native);bootlog(line);}u->nativeValid=1;u->nativeStage=native;u->nativeAppearance=actual;}
 else {static DWORD last[SR_UNIT_MAX];int slot=(int)(u-g_units);DWORD now=GetTickCount();if(slot>=0&&slot<SR_UNIT_MAX&&(DWORD)(now-last[slot])>=10000){last[slot]=now;char line[300];snprintf(line,sizeof(line),"source form poll unmatched base=%.60s identity=%.80s object=%.80s",u->baseName,identity,objectName);bootlog(line);}}
}
static void update_stage_group(Unit *u){
 if(!u||u->dead||u->preserveSpecial||!u->view||u->switching)return;
 void *app=rfield(u->view,"_curAppearance");Skin *skin=skin_for_app(u,app);
 int nativeCurrent=u->nativeValid&&u->nativeAppearance==app;
 int atBase=app&&app==u->baseApp;
 if(!skin&&(nativeCurrent||(atBase&&u->stageSource[0])))skin=held_appearance(u);
 int gi=-1;
 if(skin){
  gi=g_stageGroups.count&&g_stageGroups.id[0][0]?sr_sg_find_id(&g_stageGroups,u->stageSource):sr_sg_find(&g_stageGroups,g_rows[skin->row].identity);
 }
 if(gi<0){if(u->stageWanted>=0&&u->wanted==u->stageWanted)u->wanted=-1;u->stageWanted=-1;u->stageGroup=0;u->stageShown=-1;return;}
 const SrSgGroup *g=&g_stageGroups.group[gi];
 if(u->stageGroup!=gi+1||u->stageRevision!=g_stageGroups.revision){
  if(u->stageWanted>=0&&u->wanted==u->stageWanted)u->wanted=-1;
  u->stageWanted=-1;u->stageShown=-1;u->stageGroup=gi+1;u->stageChoice=-1;u->stageRevision=g_stageGroups.revision;
 }
 const char *id=g_rows[skin->row].identity;
 int visibleForm=visible_stage_form(skin);
 u->stageShown=sr_sg_presented(g,id,visibleForm,u->stageShown);
 /* A separately selected appearance always owns its own pending request. */
 if(u->wanted>=0&&u->wanted!=u->stageWanted)return;
 int nativePair=stage_uses_native_pair(u,g);
 SrSgStatus v={u->formHp,u->formMaxHp,u->sanity,u->sanityValid,u->formState.evades,u->nativeStage,u->nativeValid&&nativePair};
 chapter_status(u,&v);
 if(!nativePair)v.nativeValid=0;
 int stage=sr_sg_select(g,&v,u->stageShown);
 if(stage<0){if(u->stageWanted>=0&&u->wanted==u->stageWanted)u->wanted=-1;u->stageWanted=-1;u->stageChoice=u->stageShown;return;}
 const SrSgStage *target=&g->stage[stage];
 int targetRow=stage_target_row(u,target->identity,g_rows[skin->row].base_identity);
 if(targetRow<0){static DWORD missingAt[SR_UNIT_MAX];int slot=(int)(u-g_units);DWORD now=GetTickCount();if(slot>=0&&slot<SR_UNIT_MAX&&(DWORD)(now-missingAt[slot])>=5000){missingAt[slot]=now;char line[192];snprintf(line,sizeof(line),"stage target missing group=%.40s target=%.64s",u->stageSource,target->identity);bootlog(line);}if(u->stageWanted>=0&&u->wanted==u->stageWanted)u->wanted=-1;u->stageWanted=-1;u->stageChoice=u->stageShown;return;}
 /* The loader marks permanently unavailable rows bad.  Do not requeue a
    target that has already failed; leave the currently displayed skin alone. */
 if(unit_bad(u,targetRow)||resource_form_failed(u,targetRow,(int)target->form)){if(u->stageWanted>=0&&u->wanted==u->stageWanted)u->wanted=-1;u->stageWanted=-1;u->stageChoice=u->stageShown;return;}
 if(stage!=u->stageChoice){char line[192];snprintf(line,sizeof(line),"stage choice base=%.44s group=%.40s stage=%d native=%d valid=%d",u->baseName,u->stageSource,stage,u->nativeStage,u->nativeValid);bootlog(line);}
 u->stageChoice=stage;
 int needsSwitch=nativeCurrent||atBase||skin->row!=targetRow||skin->form!=desired_row_form(u,targetRow);
 if(sr_sg_cancel_wanted(u->wanted,u->stageWanted,targetRow,skin->row,needsSwitch)){u->wanted=-1;u->stageWanted=-1;}
 if(!needsSwitch&&target->form==(uint32_t)visibleForm)u->stageShown=stage;
 if(needsSwitch){
  u->wanted=targetRow;u->stageWanted=targetRow;queue_push(u,targetRow);
 }
}
/* Alternate resources share the existing asynchronous loader and bounded cache.
   Selection policies remain opt-in; failures are isolated by identity and unit. */
static void update_donor_form(Unit *u){
 if(!u||u->dead||u->wanted>=0)return;
 if(u->stageGroup>0&&u->stageRevision==g_stageGroups.revision&&u->stageChoice<0)return;
 void *current=rfield(u->view,"_curAppearance");Skin *skin=skin_for_app(u,current);
 if(!skin||(sr_form_index(g_rows[skin->row].identity)<0&&!auto_for_row(skin->row)))return;
 if(stage_waiting_for_other_appearance(u,g_rows[skin->row].identity))return;
 int desired=desired_row_form(u,skin->row);
 if(skin->form==desired)return;
 u->stageWanted=-1;u->wanted=skin->row;queue_push(u,skin->row);
}
static PoolRow reload_rows[SR_ROW_MAX];
static uint32_t reload_seen;
static int incoming_for_old[SR_ROW_MAX];
static int hot_pool_compatible(const PoolRow *rows,uint32_t count){
 if(count<g_rowCount||count>SR_ROW_MAX)return 0;
 for(uint32_t i=0;i<count;i++){
  const PoolRow *r=&rows[i];
  if(!memchr(r->identity,0,64)||!memchr(r->asset_key,0,128)||!memchr(r->appearance_name,0,64)||!memchr(r->base_identity,0,64)||!isfinite(r->weight)||r->weight<0||r->weight>1000000)return 0;
  if(sr_pool_find_key(rows,i,r)>=0)return 0;
  int old=sr_pool_find_key(g_rows,g_rowCount,r);
  if(old<0){
   int catalogMatch=0;
   for(uint32_t j=0;j<g_rowCount;j++){
    const PoolRow *base=&g_rows[j];
    if(sr_pool_catalog_binding(base,r)){catalogMatch=1;break;}
   }
   if(catalogMatch)continue;
   char asset[128];snprintf(asset,sizeof(asset),"SD_Personality/%s.prefab",r->appearance_name);
   int id=0;for(int c=0;c<5;c++){if(r->identity[c]<'0'||r->identity[c]>'9')return 0;id=id*10+r->identity[c]-'0';}
   if(strlen(r->identity)!=5||!(r->excluded&SR_AUTO_FLAG)||r->story||strcmp(asset,r->asset_key)||!sr_auto_identity(id,(int)r->sinner-100,r->appearance_name,0))return 0;
  }else{
   const PoolRow *o=&g_rows[old];
   if(r->sinner!=o->sinner||r->story!=o->story||strcmp(r->base_identity,o->base_identity)||strcmp(r->asset_key,o->asset_key)||strcmp(r->appearance_name,o->appearance_name))return 0;
  }
 }
 for(uint32_t old=0;old<g_rowCount;old++){
  incoming_for_old[old]=sr_pool_find_key(rows,count,&g_rows[old]);
  if(incoming_for_old[old]<0)return 0;
 }
 return 1;
}
static void reload_probabilities(void){
 if(!g_cfg)return;
 uint32_t revision=g_cfg->reserved[0];if(!revision||revision==reload_seen)return;
 wchar_t path[32768];GetModuleFileNameW(g_self,path,32768);
 wchar_t *tail=wcsrchr(path,L'\\');if(!tail)return;
 lstrcpyW(tail+1,L"native_pools.bin");
 HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);
 if(f==INVALID_HANDLE_VALUE)return;
 uint32_t newCount=0;
 int ok=pool_read(f,reload_rows,&newCount);
 CloseHandle(f);reload_seen=revision;
 if(!ok||!hot_pool_compatible(reload_rows,newCount)){bootlog("probability reload rejected; retaining last valid weights");return;}
 for(uint32_t i=0;i<g_rowCount;i++){
  PoolRow *r=&reload_rows[incoming_for_old[i]];
  g_rows[i].enabled=r->enabled;g_rows[i].excluded=r->excluded;g_rows[i].weight=r->weight;
 }
 candidateOrderCount=0;
 for(uint32_t i=0;i<newCount;i++){
  int old=sr_pool_find_key(g_rows,g_rowCount,&reload_rows[i]);
  if(old<0){old=(int)g_rowCount;g_rows[g_rowCount++]=reload_rows[i];}
  candidateOrder[candidateOrderCount++]=old;
 }
 auto_forms_load();
 q_head=q_tail=0;
 for(int i=0;i<SR_UNIT_MAX;i++){
  Unit *u=&g_units[i];if(!u->used||u->dead)continue;
  u->pending=u->wanted=-1;u->stageWanted=-1;u->attackDrawValid=0;u->ncand=0;u->warmCursor=0;
  if(u->preserveSpecial)continue;
  rebuild_candidates(u);
  startup_pool_changed(u);
 }
 g_cfg->reserved[1]=revision;
 bootlog("probability reload applied; membership and weights active for next decision");
}
static int resume_pending_cleanup(void){
 if(cleanup_pending&&enabled_now()){
  /* Disposal has not started while cleanup is pending. Re-enabling keeps
     the still-owned caches and resumes dispatch instead of locking forever. */
  cleanup_pending=0;bootlog("pending cleanup cancelled: randomization re-enabled");return 1;
 }
 return 0;
}
#include "voice_dispatch.h"

static void tick(void){
  if(g_quitting)return;
  int frame=m_frameCount?call_int(m_frameCount,NULL,NULL):-1;
  if(frame<0){fatal("Unity frame count unavailable",7);return;}
  if(frame==g_lastUnityFrame)return;g_lastUnityFrame=frame;g_frame=frame;
  collect_retire();
  for(int k=0;k<SR_UNIT_MAX;k++){
   if(visibleWatches[k].app)visible_watch_tick(&g_units[k],GetTickCount());
   if(visibleAttacks[k].root)visible_attack_tick(&g_units[k],GetTickCount());
  }
  if(enabled_now()&&!cleanup_pending)voice_pump();else sr_voice_clear();
  draw_rules_tick();
  sr_wf_poll(g_self);
  sr_sg_poll(g_self);
  discovery_tick();
  if(g_rowCount)reload_probabilities();
  startup_assets_tick();
  if(!g_ready){
    if(!g_cfg||!(g_cfg->enabled)||(DWORD)(GetTickCount()-g_cfg->heartbeat)>=3000)return;
    setup_staging();
    if(!g_metadataPhase||g_metadataPhase==1)metadata_begin();
    if(!g_staging||g_metadataPhase!=3)return;
    register_existing();
    g_ready=1;
    say("Sinners native ready: rows=%lu characters=%d hooks=8 mode=%lu",(unsigned long)g_rowCount,g_rowCount?1:0,(unsigned long)(g_cfg?g_cfg->mode:0));
    MemoryBarrier();g_cfg->state=1;g_cfg->error=0;
    bootlog("ready");
  }
  resume_pending_cleanup();
  if(!enabled_now()){
    if(introUnit)stop_transform_intro(1);
    if(!cleanup_pending&&g_cfg&&g_cfg->enabled==0)cleanup_pending=1;
    if(cleanup_pending){
      int busy=0;
      for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used&&!g_units[i].dead){
        Unit *u=&g_units[i];motion_dispatch(u,1);
        if(u->motionCount||presentation_busy(rfield(u->view,"_curAppearance")))busy=1;
      }
      if(busy)return; /* Let native callbacks finish before disposing cached models. */
      cleanup_all();
      cleanup_pending=0;g_ready=0;
    }
    return;
  }

  g_anyViewerActive=0;
  for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used&&!g_units[i].dead){
    Unit *u=&g_units[i];
    if(!u->view||!rfield(u->view,"m_CachedPtr"))continue;
    Coin coin;coin_info(u,&coin);
    u->coinKnown=coin.known;u->coinLast=coin.last;u->coinTier=coin.tier;u->coinMotion=coin.skillMotion;u->coinIndex=coin.coinIndex;
    if(u->viewerActive)g_anyViewerActive=1;
  }
  {int live=0;for(int k=0;k<SR_UNIT_MAX;k++)if(g_units[k].used&&!g_units[k].dead){live=1;break;}
   g_presentationGate=live?camera_scope_active():0;}
  if(!g_presentationGate&&!g_anyViewerActive)for(int i=0;i<SR_UNIT_MAX;i++){
    Unit *u=&g_units[i];if(!u->used||u->dead||u->ncand<1)continue;
    if((LONG)(GetTickCount()-u->segmentPrewarmAfter)<0)continue;
    if(!u->segmentPrewarmAttempted){
     if(time_record(u->baseApp,u->baseName)){cache_ordinary_clips(u->baseApp,u->ordinarySourceClips,NULL);u->segmentPrewarmAttempted=1;}
     else u->segmentPrewarmAfter=GetTickCount()+10000;
     break;
    }
  }
  if(introUnit)pump_transform_intro();
  /* Keep Unity model construction out of a skill's close-up. In-flight
     Addressables operations remain asynchronous and rooted until safe. */
  for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used)motion_dispatch(&g_units[i],0);
  for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used)startup_select(&g_units[i]);
  if(!g_presentationGate&&!g_anyViewerActive)loader_poll();
  else if(g_loadActive){loader_probe_paused();g_loadStart=GetTickCount();} /* Presentation pauses do not consume the loader timeout. */
  for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used)warm_enqueue(&g_units[i]);
  if(!g_loadActive&&!g_presentationGate){
    Unit *u;int row;
    if(queue_pop(&u,&row)){
      if(!loader_start(u,row)){
        if(q_poppedForm>0)disable_failed_form(u,row,q_poppedForm);else if(u&&u->used)mark_bad(u,row);
        char line[128];wsprintfA(line,"loader start failed row=%d",row);bootlog(line);
      }
      q_poppedForm=-1;
    }
  }
  for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used){
    Unit *u=&g_units[i];
    if(introUnit==u&&u->dead)stop_transform_intro(0);
    if(u->dead || !rfield(u->view,"m_CachedPtr")){unit_release(u);continue;}

    /* A viewer can reset only the native receiver while the presentation is busy.
       Keep the held donor drawn until the safe appearance rebind. */
    if(u->staticHidden&&rfield(u->view,"_curAppearance")==u->baseApp){
     Skin *held=held_appearance(u);
     if(held&&held->go&&go_active_self(held->go)==0)set_active(held->go,1);
    }
    update_sanity(u);
    if(g_frame%15==0)poll_paired_native(u);
    update_stage_group(u);
    if(u->roundPending||!u->formState.round_seen){u->roundSanity=u->sanity;u->roundSanityValid=u->sanityValid;}
    if(u->roundPending){sr_form_round(&u->formState,u->observedRound,u->sanity,u->sanityValid);u->roundPending=0;}
    if(!g_presentationGate&&!u->motionCount)apply_pending(u,i);
    if(!g_presentationGate&&!u->viewerActive)retain_last_appearance(u);
    if(!g_presentationGate&&!g_anyViewerActive){update_donor_form(u);apply_internal_form(u);}
    else u->idleRestoreFrames=0;
  }
  pump_transform_intro();
  {static DWORD scanAt;DWORD now=GetTickCount();int live=0;for(int k=0;k<SR_UNIT_MAX;k++)if(g_units[k].used&&!g_units[k].dead){live=1;break;}
   if(live?g_frame%60==0:(DWORD)(now-scanAt)>=1000){scanAt=now;register_existing();}}
  if(g_frame%30==0){
    for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used&&!g_units[i].switching)sync_visibility(&g_units[i]);
    if(g_cfg->hits!=(uint32_t)g_switches)g_cfg->hits=(uint32_t)g_switches;
    say("Sinners native: switches=%ld loads=%ld fallbacks=%ld",g_switches,g_loads,g_fallbacks);
    warm_publish();
  }
}
static void cleanup_all(void){
  fx_plan_close_all();
  sr_voice_clear();
  startup_assets_clear();
  g_presentationGate=0;g_anyViewerActive=0;
  stop_transform_intro(1);
  discovery_abort();
  for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used){
    Unit *u=&g_units[i];
    void *current=rfield(u->view,"_curAppearance");
    if(current&&current!=u->baseApp)unit_switch(u,NULL);
    unit_release(u);
  }
  loader_cancel();q_head=q_tail=0;
  if(g_metaBox && m_releaseMeta){void *args[]={ui_unbox(g_metaBox)};
    if(call_exc(m_releaseMeta,NULL,args)){ui_unroot(g_metaBoxRoot);ui_unroot(g_metaDBRoot);g_metaBox=NULL;g_metaBoxRoot=g_metaDBRoot=0;g_metadataDB=NULL;g_metadataPhase=0;}
    else bootlog("metadata release failed; roots retained");
  }
  bootlog("cleanup complete");
}
static _Thread_local int ur_in_canvas;
static void canvas_tick(void *mi){
  orig_canvas(mi);
  if(InterlockedCompareExchange(&g_busy,1,0))return;

  if(g_cfg&&enabled_now()==0&&g_cfg->enabled==0)cleanup_pending=1;
  ur_in_canvas=1;tick();ur_in_canvas=0;
  InterlockedExchange(&g_busy,0);
}

/* ---------------- hook installation ---------------- */
#define HOOK_MAX 64
static void *g_targets[HOOK_MAX];
static void *g_detours[HOOK_MAX];
static void **g_originals[HOOK_MAX];
static int g_hookCount;

static int add_hook(void *method,void *detour,void **original){
  if(g_hookCount==HOOK_MAX)return 0;
  if(!method||!*(void **)method)return 0;
  for(int i=0;i<g_hookCount;i++)if(g_targets[i]==*(void **)method)return 1;
  g_targets[g_hookCount]=*(void **)method;
  g_detours[g_hookCount]=detour;
  g_originals[g_hookCount]=original;
  g_hookCount++;
  return 1;
}
static void *m_applicationQuit,*orig_applicationQuit;
#include "sprite_observe_filter.h"
static void *m_observeSpriteCallback,*orig_observeSpriteCallback,*m_observeGetSprite,*m_observeObjectName;
static volatile LONG g_spriteObserveCount;
static _Thread_local int g_spriteObserving;
/* Observation only: original callback always runs; no sprite is changed. */
static void sprite_callback_observe(void *app,void *renderer,void *mi){
 ((void (*)(void *,void *,void *))orig_observeSpriteCallback)(app,renderer,mi);
 if(g_spriteObserving||!enabled_now()||!renderer)return;
 Unit *unit=unit_for_app(app);Skin *skin=unit?skin_for_app(unit,app):NULL;
 if(!unit||!skin||!sprite_observe_target(unit->baseName,skin->look))return;
 LONG sequence=InterlockedIncrement(&g_spriteObserveCount);if(sequence>100)return;
 g_spriteObserving=1;int ok=0;void *sprite=call_obj(m_observeGetSprite,renderer,NULL,&ok);uintptr_t sr=sprite?ui_root(sprite):0;
 void *name=(sprite&&sr)?call_obj(m_observeObjectName,sprite,NULL,&ok):NULL;uintptr_t nr=name?ui_root(name):0;char text[128]={0};
 if(name&&nr)string_ascii(name,text,sizeof(text));
 char line[320];snprintf(line,sizeof(line),"sprite callback observed n=%ld app=%p renderer=%p sprite=%p name=%.110s detail=%d coin=%d",sequence,app,renderer,sprite,text,unit->coinMotion,unit->coinIndex);bootlog(line);
 if(nr)ui_unroot(nr);if(sr)ui_unroot(sr);g_spriteObserving=0;
}
static void application_quit_hook(void *mi){
 InterlockedExchange(&g_quitting,1);
 /* No Destroy, Addressables release, managed calls or disk flush during shutdown. */
 ((void (*)(void *))orig_applicationQuit)(mi);
}
/* Opt-in observation of verified static linked binding methods. */
static void *orig_link_matches,*orig_link_resolve;
static void *method_by_types_one(void *klass,const char *name,const char **types,int count);
static int linked_is_static(void *klass,void *method){
 void *obj=((void *(*)(void *,void *))api[API_METHOD_OBJECT])(method,klass);if(!obj)return 0;uintptr_t root=ui_root(obj);
 void *get=find_method(ui_class(obj),"get_IsStatic",0);int result=get?call_bool(get,obj,NULL):0;ui_unroot(root);return result==1;
}
static int team_instance_method(void *klass,void *method){
 void *obj=((void *(*)(void *,void *))api[API_METHOD_OBJECT])(method,klass);if(!obj)return 0;
 uintptr_t root=ui_root(obj);if(!root)return 0;void *get=find_method(ui_class(obj),"get_IsStatic",0);
 int value=get?call_bool(get,obj,NULL):-1;ui_unroot(root);return value==0;
}
static int team_returns(void *method,const char *expected){
 void *t=((void *(*)(void *))api[API_RETURN_TYPE])(method);char *n=t?((char *(*)(void *))api[API_TYPE_NAME])(t):NULL;
 int ok=n&&!strcmp(n,expected);if(n)((void (*)(void *))api[API_FREE])(n);return ok;
}
#include "wedge_identity.h"
static int visible_wedge_role(Unit *u){
 if(!u||!u->used||u->dead||!u->view)return 0;
 Skin *skin=skin_for_app(u,rfield(u->view,"_curAppearance"));
 if(!skin||skin->row<0||(uint32_t)skin->row>=g_rowCount)return 0;
 const PoolRow *row=&g_rows[skin->row];
 if(strcmp(skin->look,row->appearance_name))return 0;
 return wedge_role(u->baseName,row->identity);
}
static uint8_t linked_matches_hook(void *app,int id,uint8_t flag,void *mi){
 uint8_t matched=((uint8_t (*)(void *,int,uint8_t,void *))orig_link_matches)(app,id,flag,mi);
 if(matched||!enabled_now()||cleanup_pending||!wedge_role_id(id))return matched;
 return visible_wedge_role(unit_for_app(app))==id;
}
static void *linked_resolve_hook(void *app,int id,void *mi){
 void *stock=((void *(*)(void *,int,void *))orig_link_resolve)(app,id,mi);
 if(stock||!enabled_now()||cleanup_pending||!wedge_role_id(id))return stock;
 Unit *owner=unit_for_app(app);
 if(!owner||!owner->used||owner->dead||!owner->view)return NULL;
 void *visible=rfield(owner->view,"_curAppearance");
 if(!wedge_native_actor(owner->baseName)||!visible||(visible!=owner->baseApp&&!visible_wedge_role(owner)))return NULL;
 void *match=NULL;
 for(int i=0;i<SR_UNIT_MAX;i++){
  Unit *u=&g_units[i];if(visible_wedge_role(u)!=id)continue;
  if(match)return NULL;
  match=rfield(u->view,"_curAppearance");
 }
 return match;
}
static int install_hooks(void){
  MH_STATUS status=MH_Initialize();
  if(status!=MH_OK&&status!=MH_ERROR_ALREADY_INITIALIZED)return 0;
  void *canvasClass=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_ui,"UnityEngine","Canvas");
  void *canvasMethod=canvasClass?((void *(*)(void *,const char *,int))api[API_METHOD])(canvasClass,"SendWillRenderCanvases",0):NULL;
  if(!canvasMethod)return 0;
  void *application=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_core,"UnityEngine","Application");
  m_applicationQuit=application?find_method(application,"Internal_ApplicationQuit",0):NULL;
  if(!m_applicationQuit||!add_hook(m_applicationQuit,application_quit_hook,&orig_applicationQuit))return 0;
  add_hook(canvasMethod,canvas_tick,(void **)&orig_canvas);
  add_hook(m_init,initialize_hook,&orig_init);
  add_hook(m_changeMotion,change_motion_hook,&orig_changeMotion);
  add_hook(m_parryOnly,parry_hook,&orig_parryOnly);
  if(!add_hook(m_sourceCoin,source_coin_hook,&orig_sourceCoin)||!add_hook(m_evadeEvent,evade_event_hook,&orig_evadeEvent))return 0;
  if(!add_hook(m_evadeResult,evade_result_hook,&orig_evadeResult)||!add_hook(m_updateCointoss,update_cointoss_hook,&orig_updateCointoss))return 0;
  if(!add_hook(m_motionAnimItem,motion_anim_item_hook,&orig_motionAnimItem))return 0;
  if(!add_hook(m_afterCointoss,after_cointoss_hook,&orig_afterCointoss))return 0;
  if(!add_hook(m_parryPlayback,parry_playback_hook,&orig_parryPlayback))return 0;
  add_hook(m_skillStart,skill_start_hook,&orig_skillStart);
  add_hook(m_startDuel,start_duel_hook,&orig_startDuel);
  add_hook(m_getMotion,get_motion_hook,&orig_getMotion);
  add_hook(m_endTimeline,timeline_end_hook,&orig_endTimeline);
  add_hook(m_viewDestroy,view_destroy_hook,&orig_viewDestroy);
  if(m_die)add_hook(m_die,die_hook,&orig_die);
  if(m_setViewVoice&&m_checkVoiceIndex&&add_hook(m_setViewVoice,voice_view_hook,&orig_setViewVoice))bootlog("battle voice view registered");
  if(m_registerAppearanceVoice&&m_addMultiVoice&&add_hook(m_registerAppearanceVoice,voice_timeline_hook,&orig_registerAppearanceVoice))
    bootlog("native appearance voice segments registered");
  if(m_printBubble && m_checkVoiceIndex && add_hook(m_checkVoiceIndex,voice_index_hook,&orig_checkVoiceIndex))
    bootlog("battle voice resource lookup registered");
  if(m_printBubble&&m_playMultiVoice&&m_addMultiVoice&&add_hook(m_addMultiVoice,voice_add_hook,&orig_addMultiVoice)){
    voicePairReady=add_hook(m_playMultiVoice,voice_multi_hook,&orig_multiVoice);
    if(voicePairReady)bootlog("battle voice event ownership registered");
  }
  if(m_printBubble)bootlog(add_hook(m_printBubble,print_bubble_hook,&orig_printBubble)?"base bubble hook installed":"base bubble hook failed; native bubbles retained");
  else bootlog("base bubble method unavailable; native bubbles retained");
  if(m_revive&&!add_hook(m_revive,revive_hook,&orig_revive))m_revive=NULL;
  if(m_formRound)add_hook(m_formRound,form_round_hook,&orig_formRound);
  if(m_formHit)add_hook(m_formHit,form_hit_hook,&orig_formHit);
  add_hook(m_changeAppearance,change_appearance_hook,&orig_changeAppearance);
  for(int i=0;i<4;i++)if(native_order_methods[i]&&!add_hook(native_order_methods[i],native_order_detours[i],&native_order_originals[i]))return 0;
  for(int i=0;i<4;i++)if(playback_methods[i])add_hook(playback_methods[i],playback_detours[i],&playback_originals[i]);
  {
   void *appearance=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"SD","CharacterAppearance");
   void *renderer=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_core,"UnityEngine","SpriteRenderer");
   void *object=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_core,"UnityEngine","Object");
   m_observeSpriteCallback=appearance?find_method(appearance,"OnSpriteChangeCallback",1):NULL;
   m_observeGetSprite=renderer?find_method(renderer,"get_sprite",0):NULL;
   m_observeObjectName=object?find_method(object,"get_name",0):NULL;
   int unique=m_observeSpriteCallback&&m_observeGetSprite&&m_observeObjectName&&*(void**)m_observeSpriteCallback;
   for(int i=0;i<g_hookCount&&unique;i++)if(g_targets[i]==*(void**)m_observeSpriteCallback)unique=0;
   if(unique&&add_hook(m_observeSpriteCallback,sprite_callback_observe,&orig_observeSpriteCallback))bootlog("sprite callback observation registered");
  }
  {
   void *k=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"","LinkedSkillUnitBinding");
   const char *mt[]={"SD.CharacterAppearance","System.Int32","System.Boolean"},*rt[]={"SD.CharacterAppearance","System.Int32"};
   void *m=k?method_by_types_one(k,"Matches",mt,3):NULL,*r=k?method_by_types_one(k,"Resolve",rt,2):NULL;
   int distinct=m&&r&&*(void**)m&&*(void**)r&&*(void**)m!=*(void**)r;
   for(int i=0;i<g_hookCount&&distinct;i++)if(g_targets[i]==*(void**)m||g_targets[i]==*(void**)r)distinct=0;
   int ms=m?linked_is_static(k,m):0,rs=r?linked_is_static(k,r):0; char dbg[160];snprintf(dbg,sizeof(dbg),"linked hook check class=%d matches=%d resolve=%d distinct=%d static=%d/%d used=%d cap=%d",k!=NULL,m!=NULL,r!=NULL,distinct,ms,rs,g_hookCount,HOOK_MAX);bootlog(dbg); if(distinct&&ms&&rs&&g_hookCount+2<=HOOK_MAX){
    if(add_hook(m,linked_matches_hook,&orig_link_matches)&&add_hook(r,linked_resolve_hook,&orig_link_resolve))bootlog("matched Wedge appearance aliases registered");
   }else bootlog("linked binding diagnostic hooks skipped: static ABI or capacity unavailable");
  }

  if(g_fxExperiment&&m_fxStart&&m_fxEvaluate){int unique=*(void**)m_fxStart&&*(void**)m_fxEvaluate&&*(void**)m_fxStart!=*(void**)m_fxEvaluate;for(int i=0;i<g_hookCount&&unique;i++)if(g_targets[i]==*(void**)m_fxStart||g_targets[i]==*(void**)m_fxEvaluate)unique=0;if(unique&&add_hook(m_fxStart,fx_start_hook,&orig_fxStart)&&add_hook(m_fxEvaluate,fx_evaluate_hook,&orig_fxEvaluate))bootlog("fx plan hooks registered");else{g_fxExperiment=0;bootlog("fx plan hooks unavailable");}}
  if(g_hookCount<4)return 0;
  int created=0;
  for(int i=0;i<g_hookCount;i++){
    if(MH_CreateHook(g_targets[i],g_detours[i],g_originals[i])!=MH_OK)break;
    created++;
  }
  if(created!=g_hookCount){
    for(int i=0;i<created;i++)MH_RemoveHook(g_targets[i]);
    return 0;
  }
  for(int i=0;i<g_hookCount;i++)if(MH_EnableHook(g_targets[i])!=MH_OK){
    for(int j=0;j<i;j++)MH_DisableHook(g_targets[j]);
    for(int j=0;j<g_hookCount;j++)MH_RemoveHook(g_targets[j]);
    return 0;
  }
  return 1;
}


/* ---------------- setup ---------------- */
static void *method_by_types_one(void *klass,const char *name,const char **types,int count){
  void *it=NULL,*m;
  while((m=((void *(*)(void *,void **))api[API_METHODS])(klass,&it))){
    if(strcmp(((const char *(*)(void *))api[API_METHOD_NAME])(m),name))continue;
    if((int)((uint32_t (*)(void *))api[API_PARAM_COUNT])(m)!=count)continue;
    int ok=1;
    for(int i=0;i<count;i++){
      void *param=((void *(*)(void *,uint32_t))api[API_PARAM])(m,(uint32_t)i);
      char *tn=param?((char *(*)(void *))api[API_TYPE_NAME])(param):NULL;
      if(!tn||strcmp(tn,types[i]))ok=0;
      if(tn)((void (*)(void *))api[API_FREE])(tn);
      if(!ok)break;
    }
    if(ok)return m;
  }
  return NULL;
}
static void *method_by_types(void *klass,const char *name,const char **types,int count){
  for(void *c=klass;c;c=ui_parent(c)){
    void *m=method_by_types_one(c,name,types,count);
    if(m)return m;
  }
  return NULL;
}
#include "unity_raw_il2cpp.inc"
static void *c_goClass,*c_transform;

static int is_generic_definition(void *method,void *declaring){
  void *reflection=((void *(*)(void *,void *))api[API_METHOD_OBJECT])(method,declaring);
  if(!reflection)return 0;
  uintptr_t root=ui_root(reflection);
  if(!root)return 0;
  void *getter=NULL;
  for(void *c=ui_class(reflection);c&&!getter;c=ui_parent(c))getter=find_method(c,"get_IsGenericMethodDefinition",0);
  int result=0;
  if(getter){
    int ok=1;
    void *value=call_obj(getter,reflection,NULL,&ok);
    if(ok&&value)result=*(uint8_t *)ui_unbox(value)?1:0;
  }
  ui_unroot(root);
  return result;
}

static int bind_addressable(const char *name,void *elementClass,void **out){
  void *addr=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_addr,"UnityEngine.AddressableAssets","Addressables");
  if(!addr||!elementClass)return 0;
  void *wanted=((void *(*)(void *))api[API_TYPE_OBJECT])(((void *(*)(void *))api[API_CLASS_TYPE])(elementClass));
  uintptr_t root=ui_root(wanted);
  if(!root)return 0;
  void *it=NULL,*m;int loads=0,generics=0;
  while((m=((void *(*)(void *,void **))api[API_METHODS])(addr,&it))){
    if(strcmp(((const char *(*)(void *))api[API_METHOD_NAME])(m),name))continue;
    if(((uint32_t (*)(void *))api[API_PARAM_COUNT])(m)!=1)continue;
    loads++;
    void *param=((void *(*)(void *,uint32_t))api[API_PARAM])(m,0);
    char *tn=param?((char *(*)(void *))api[API_TYPE_NAME])(param):NULL;
    int match=tn&&(!strcmp(tn,"System.Object")||strstr(tn,"AsyncOperationHandle"));
    if(tn)((void (*)(void *))api[API_FREE])(tn);
    if(!match)continue;
    if(!is_generic_definition(m,addr))continue;
    generics++;
    void *closed=close_generic(m,addr,c_typeClass,wanted);
    if(closed){*out=closed;ui_unroot(root);return 1;}
  }
  ui_unroot(root);
  {char line[160];wsprintfA(line,"bind %s failed candidates=%d generic=%d",name,loads,generics);bootlog(line);}
  return 0;
}

static void *pick_method(void *klass,const char *name,const char **types,int count){
  for(void *k=klass;k;k=ui_parent(k)){
    void *it=NULL,*m;
    while((m=((void *(*)(void *,void **))api[API_METHODS])(k,&it))){
      if(strcmp(((const char *(*)(void *))api[API_METHOD_NAME])(m),name))continue;
      if((int)((uint32_t (*)(void *))api[API_PARAM_COUNT])(m)!=count)continue;
      int ok=1;
      for(int i=0;i<count;i++){
        void *param=((void *(*)(void *,uint32_t))api[API_PARAM])(m,(uint32_t)i);
        char *tn=param?((char *(*)(void *))api[API_TYPE_NAME])(param):NULL;
        if(!tn||strcmp(tn,types[i]))ok=0;
        if(tn)((void (*)(void *))api[API_FREE])(tn);
        if(!ok)break;
      }
      if(ok)return m;
    }
  }
  return NULL;
}

#include "callback_match.h"
/* Resolve reflection metadata without assuming MethodInfo internal layout. */
static int sr_method_is_static(void *method,void *declaring){
 void *obj=((void *(*)(void *,void *))api[API_METHOD_OBJECT])(method,declaring);
 uintptr_t root=ui_root(obj);if(!root)return -1;
 void *getter=find_method(ui_class(obj),"get_IsStatic",0),*exc=NULL;
 void *value=getter?ui_invoke(getter,obj,NULL,&exc):NULL;
 int result=(!exc&&value&&ui_unbox(value))?(*(uint8_t *)ui_unbox(value)?1:0):-1;
 ui_unroot(root);return result;
}
/* The original method is an instance void callback; only bind a unique ABI
   match, including for the old hard-coded generated name. */
static void *pick_generated_evade(void *klass){
 void *found=NULL;int count=0;const char *prefix="<UpdateCoinTossResultDirect>b__";
 for(void *k=klass;k;k=ui_parent(k)){void *it=NULL,*m;
  while((m=((void *(*)(void *,void **))api[API_METHODS])(k,&it))){
   const char *name=((const char *(*)(void *))api[API_METHOD_NAME])(m);
   if(!name||strncmp(name,prefix,strlen(prefix)))continue;
   unsigned n=((uint32_t (*)(void *))api[API_PARAM_COUNT])(m);
   void *param=n==1?((void *(*)(void *,uint32_t))api[API_PARAM])(m,0):NULL;
   void *ret=((void *(*)(void *))api[API_RETURN_TYPE])(m);
   char *pt=param?((char *(*)(void *))api[API_TYPE_NAME])(param):NULL;
   char *rt=ret?((char *(*)(void *))api[API_TYPE_NAME])(ret):NULL;
   int is_static=sr_method_is_static(m,k);
   int ok=sr_callback_match(name,n,pt,rt,is_static);
   {char line[256];snprintf(line,sizeof(line),"resolve evade candidate %s argc=%u param=%s return=%s static=%d accepted=%d",name,n,pt?pt:"?",rt?rt:"?",is_static,ok);bootlog(line);}
   if(pt)((void (*)(void *))api[API_FREE])(pt);if(rt)((void (*)(void *))api[API_FREE])(rt);
   if(ok){count=sr_callback_accumulate(count,1);found=m;}
  }
 }
 if(count!=1){char line[128];snprintf(line,sizeof(line),"resolve: evade callback candidates=%d; requires exactly one",count);bootlog(line);return NULL;}
 return found;
}

static int resolve_all(void){
  void *(*klass)(void *,const char *,const char *)=api[API_CLASS];
  void *timeClass=klass(g_core,"UnityEngine","Time");m_frameCount=timeClass?find_method(timeClass,"get_frameCount",0):NULL;
  if(!m_frameCount)return 0;
  c_appearance=klass(g_game,"SD","CharacterAppearance");
  c_view=klass(g_game,"","BattleUnitView");
  c_metadataClass=klass(g_game,"","MotionMetadataDB");
  c_containerClass=klass(g_game,"SD","SkinMetadataContainer");
  c_objectClass=klass(g_core,"UnityEngine","Object");
  c_goClass=klass(g_core,"UnityEngine","GameObject");
  c_transform=klass(g_core,"UnityEngine","Transform");
  c_typeClass=klass(g_corlib,"System","Type");
  if(!c_appearance||!c_view||!c_metadataClass||!c_containerClass||!c_objectClass||!c_goClass||!c_transform||!c_typeClass){
    bootlog("resolve: core classes missing");return 0;
  }
  {
    const char *initTypes[1]={"BattleUnitView"};
    m_init=pick_method(c_appearance,"Initialize",initTypes,1);
    if(!m_init)m_init=find_method(c_appearance,"Initialize",1);
    bootlog(m_init?"resolve: Initialize typed":"resolve: Initialize arity-only");
  }
  memset(defenseMotions,0,sizeof(defenseMotions));memset(defenseTypes,0,sizeof(defenseTypes));
  int motionKinds=bind_defense_enum(klass(g_game,"","MOTION_DETAIL"),defenseMotions,128);
  int defenseKinds=bind_defense_enum(klass(g_game,"","DEFENSE_TYPE"),defenseTypes,32);
  defenseMotions[2]=1; /* Previously verified Evade value. */
  {char line[128];snprintf(line,sizeof(line),"defense form enum mapping motionKinds=%d defenseKinds=%d",motionKinds,defenseKinds);bootlog(line);}
  if(!motionKinds){bootlog("defense enum metadata unavailable");return 0;}
  {const char *types[]={"System.Int32"};void *v=klass(g_game,"","BattleSkillViewer"),*b=klass(g_game,"View","BattleBehaviourViewer");
   if(!b)b=klass(g_game,"","BattleBehaviourViewer");
   m_sourceCoin=v?pick_method(v,"Start_Cointoss",types,1):NULL;m_evadeEvent=b?pick_method(b,"Evade",types,1):NULL;
   m_evadeResult=v?pick_generated_evade(v):NULL;
   const char *coinTypes[]={"System.Int32","System.Int32","System.Boolean","System.Boolean"};
   m_updateCointoss=pick_method(c_view,"Update_Cointoss",coinTypes,4);
   const char *animTypes[]={"MOTION_DETAIL","MOTION_DETAIL","System.Int32","System.Int32","System.Boolean"};
   m_motionAnimItem=pick_method(c_appearance,"GetMotionAnimItem",animTypes,5);
   {char line[160];snprintf(line,sizeof(line),"resolve: evade callback=%d cointoss=%d motion-item=%d",!!m_evadeResult,!!m_updateCointoss,!!m_motionAnimItem);bootlog(line);}
   if(!m_evadeResult||!m_updateCointoss||!m_motionAnimItem){bootlog("resolve: evade result or source projection interface unavailable");return 0;}
   if(!m_sourceCoin||!m_evadeEvent){char line[120];snprintf(line,sizeof(line),"resolve: sourceCoin=%d evadeEvent=%d",!!m_sourceCoin,!!m_evadeEvent);bootlog(line);return 0;}}
  m_changeMotion=find_method(c_appearance,"ChangeMotion",6);
  m_parryOnly=find_method(c_appearance,"ChangeMotion_ParryingOnly",7);
  bind_clash_results(m_parryOnly);
  {void *c=klass(g_game,"","BattleDuelViewer");m_afterCointoss=c?find_method(c,"After_Cointoss",0):NULL;if(!m_afterCointoss)return 0;}
  {const char *types[]={"MOTION_DETAIL"};m_parryPlayback=pick_method(c_appearance,"ChangeMotion_Parrying",types,1);if(!m_parryPlayback)return 0;}
  m_skillStart=find_method(c_appearance,"OnSkillStart",0);
  m_startDuel=find_method(c_appearance,"OnStartDuel",0);
  {
    const char *motionTypes[2]={"MOTION_DETAIL","System.Boolean"};
    m_getMotion=pick_method(c_appearance,"GetMotion",motionTypes,2);
    if(!m_getMotion)m_getMotion=find_method(c_appearance,"GetMotion",2);
  }
  {
    const char *speedTypes[1]={"System.Single"};
    m_setAnimSpeed=pick_method(c_appearance,"SetAnimSpeed",speedTypes,1);
    if(!m_setAnimSpeed)m_setAnimSpeed=find_method(c_appearance,"SetAnimSpeed",1);
  }
  m_cancelDelay=find_method(c_appearance,"CancelSkillPresentationDelay",0);
  m_resetTimeline=find_method(c_appearance,"ResetTimeline",0);
  {const char *types[]={"UnityEngine.Playables.PlayableDirector"};
   m_endTimeline=pick_method(c_appearance,"OnEndTimelineCallBack",types,1);
   if(!m_endTimeline)return 0;
  }
  m_getViewer=find_method(c_view,"GetTimelineSkillViewer",0);
  {
    const char *changeTypes[2]={"System.String","System.Boolean"};
    m_changeAppearance=pick_method(c_view,"ChangeAppearance",changeTypes,2);
    if(!m_changeAppearance)m_changeAppearance=find_method(c_view,"ChangeAppearance",2);
    bootlog(m_changeAppearance?"resolve: ChangeAppearance typed":"resolve: ChangeAppearance arity-only");
  }
  m_viewDestroy=find_method(c_view,"OnDestroy",0);
  m_revive=find_method(c_view,"OnReviveView",1);
  m_die=find_method(c_view,"OnDie",8);
  bootlog(m_die?"resolve: OnDie arity 8":"resolve: OnDie missing; boss death voice disabled");
  {
    /* The class sits in a non-default namespace, so go through the raw lookup the
       probe used rather than the two-argument helper. */
    void *vgk=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"","VoiceGenerator");
    if(!vgk)vgk=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"Voice","VoiceGenerator");
    const char *viewVoiceTypes[]={"Voice.BattleCharacterVoiceType","System.Boolean","BattleSkillViewer"};
    m_setViewVoice=pick_method(c_view,"SetPlayVoice",viewVoiceTypes,3);
    if(m_setViewVoice&&(!team_instance_method(c_view,m_setViewVoice)||!team_returns(m_setViewVoice,"System.Void")))m_setViewVoice=NULL;
    void *mixer=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"","FMODCustomEventMixerBehaviour_Voice");
    const char *segmentTypes[]={"SD.CharacterAppearance","FMOD.Studio.EventInstance","FMODVoiceSegmentBehaviour"};
    m_registerAppearanceVoice=mixer?pick_method(mixer,"RegisterAppearanceVoice",segmentTypes,3):NULL;
    if(m_registerAppearanceVoice&&(!team_instance_method(mixer,m_registerAppearanceVoice)||!team_returns(m_registerAppearanceVoice,"System.Boolean")))m_registerAppearanceVoice=NULL;
    if(vgk){
      c_voiceGenerator=vgk;
      const char *bubble[]={"System.Int32","System.String","System.Single","System.Boolean"};
      const char *multi[]={"System.Int32","System.String","BattleUnitView","System.Boolean","System.Boolean","System.Single"};
      const char *lookup[]={"System.String","System.Int32","System.Int32","System.String&","System.String&"};
      const char *add[]={"FMOD.Studio.EventInstance","System.Int32","Voice.VoiceType","System.Single","System.Boolean","System.Single","System.String","System.Boolean","System.String","System.Boolean","System.Boolean"};
      m_printBubble=pick_method(vgk,"PrintSpeechBubble",bubble,4);
      m_playMultiVoice=pick_method(vgk,"PlayMultiVoice",multi,6);
      m_checkVoiceIndex=pick_method(vgk,"CheckVoiceIndex",lookup,5);
      m_addMultiVoice=pick_method(vgk,"AddMultiVoice",add,11);
      if(m_printBubble&&(!linked_is_static(vgk,m_printBubble)||!team_returns(m_printBubble,"System.Void")))m_printBubble=NULL;
      if(m_playMultiVoice&&(!linked_is_static(vgk,m_playMultiVoice)||!team_returns(m_playMultiVoice,"VoiceEventClass")))m_playMultiVoice=NULL;
      if(m_addMultiVoice&&(!linked_is_static(vgk,m_addMultiVoice)||!team_returns(m_addMultiVoice,"VoiceEventClass")))m_addMultiVoice=NULL;
      if(m_checkVoiceIndex&&(!linked_is_static(vgk,m_checkVoiceIndex)||!team_returns(m_checkVoiceIndex,"FMOD.RESULT")))m_checkVoiceIndex=NULL;
    }
    bootlog(m_playMultiVoice?"resolve: VoiceGenerator.PlayMultiVoice":"resolve: PlayMultiVoice missing; boss voice disabled");
  }
  m_formRound=find_method(c_view,"OnRoundStart",0);
  void *formModel=klass(g_game,"","BattleUnitModel");
  const char *hitTypes[]={"BattleActionModel","CoinModel","System.Int32","System.Int32","BATTLE_EVENT_TIMING","System.Boolean"};
  m_formHit=formModel?pick_method(formModel,"OnTakeAttackDamage",hitTypes,6):NULL;
  m_formHp=formModel?find_method(formModel,"get_Hp",0):NULL;
  m_formMaxHp=formModel?find_method(formModel,"get_MaxHp",0):NULL;
  if(!m_formHit||!m_formHp||!m_formMaxHp){bootlog("form HP observation interfaces missing");return 0;}
  if(!m_formRound){bootlog("form round interface missing");return 0;}
  m_getSkinPivot=find_method(c_view,"get_SkinPivot",0);
  m_setActive=find_method(c_goClass,"SetActive",1);
  m_getTransform=find_method(c_goClass,"get_transform",0);
  m_getActiveSelf=find_method(c_goClass,"get_activeSelf",0);
  {
    const char *instantiateTypes[3]={"UnityEngine.Object","UnityEngine.Transform","System.Boolean"};
    m_instantiate=method_by_types(c_objectClass,"Instantiate",instantiateTypes,3);
  }
  {
    const char *setParentTypes[2]={"UnityEngine.Transform","System.Boolean"};
    m_setParent=method_by_types(c_transform,"SetParent",setParentTypes,2);
    if(!m_setParent)m_setParent=find_method(c_transform,"SetParent",2);
    bootlog(m_setParent?"resolve: SetParent bound":"resolve: SetParent missing");
  }
  {
    const char *getComponentTypes[1]={"System.Type"};
    m_getComponent=method_by_types(c_goClass,"GetComponent",getComponentTypes,1);
  }
  {
    const char *destroyTypes[1]={"UnityEngine.Object"};
    m_destroyObject=method_by_types(c_objectClass,"Destroy",destroyTypes,1);
  }
  {
    void *resources=klass(g_core,"UnityEngine","Resources");
    const char *findTypes[1]={"System.Type"};
    m_findAll=resources?method_by_types(resources,"FindObjectsOfTypeAll",findTypes,1):NULL;
    if(!m_findAll)m_findAll=method_by_types(c_objectClass,"FindObjectsOfTypeAll",findTypes,1);
    if(!m_findAll)m_findAll=method_by_types(c_objectClass,"FindObjectsOfType",findTypes,1);
    bootlog(m_findAll?"resolve: scene scan bound":"resolve: scene scan missing");
  }
  t_appearance=((void *(*)(void *))api[API_TYPE_OBJECT])(((void *(*)(void *))api[API_CLASS_TYPE])(c_appearance));
  if(!t_appearance||!m_changeMotion||!m_init||!m_getMotion||!m_changeAppearance){
    bootlog("resolve: required members missing");return 0;
  }
  if(!bind_addressable("LoadAssetAsync",c_goClass,&m_loadGO))return 0;
  if(!bind_addressable("Release",c_goClass,&m_releaseGO))return 0;
  if(!bind_addressable("LoadAssetAsync",c_metadataClass,&m_loadMeta))return 0;
  if(!bind_addressable("Release",c_metadataClass,&m_releaseMeta))return 0;
  const char *order_names[]={"BattleSkillViewSkin","BattleSkillViewSkin_UseLastMotionOnLastCoin","BattleSkillViewSkin_MotionStartOneS3","BattleSkillViewSkin_11016Attack"};
  const char *order_types[]={"System.Int32","System.Int32","System.Int32","System.Boolean"};
  for(int i=0;i<4;i++){
   void *k=klass(g_game,"",order_names[i]);native_order_methods[i]=k?pick_method(k,"BuildMotionOrder",order_types,4):NULL;
   if(!native_order_methods[i]){bootlog("native BuildMotionOrder binding missing");return 0;}
  }
  const char *special_names[]={"BattleSkillViewSkin","BattleSkillViewSkin_10917","BattleSkillViewSkin_11016Attack","BattleSkillViewSkin_11016Counter"};
  const char *motion_type[]={"MOTION_DETAIL"};
  for(int i=0;i<4;i++){
    void *k=klass(g_game,"",special_names[i]);playback_methods[i]=k?pick_method(k,"GetPlaybackMotion",motion_type,1):NULL;
    if(playback_methods[i]){
      char *tn=((char *(*)(void *))api[API_TYPE_NAME])(((void *(*)(void *))api[API_RETURN_TYPE])(playback_methods[i]));
      if(!tn||strcmp(tn,"MOTION_DETAIL"))playback_methods[i]=NULL;
      if(tn)((void (*)(void *))api[API_FREE])(tn);
    }
    char line[160];snprintf(line,sizeof(line),"resolve playback %s bound=%d",special_names[i],!!playback_methods[i]);bootlog(line);
  }
  bootlog("resolve: bindings complete");
  return 1;
}

/* ---------------- worker ---------------- */
static DWORD WINAPI run(void *unused){
  (void)unused;
  char startup[80];snprintf(startup,sizeof(startup),"native worker started; protocol=%u",SR_PROTOCOL_VERSION);bootlog(startup);
  wchar_t name[96];
  wsprintfW(name,SR_SESSION_TEMPLATE,GetCurrentProcessId());
  HANDLE map=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,name);
  if(!map){bootlog("OpenFileMapping failed");return 0;}
  Config *c=(Config *)MapViewOfFile(map,FILE_MAP_ALL_ACCESS,0,0,sizeof(Config));
  CloseHandle(map);
  if(!c){bootlog("MapViewOfFile failed");return 0;}
  if(c->magic!=0x3152534e||c->version!=SR_PROTOCOL_VERSION||c->bytes!=sizeof(Config)){bootlog("protocol validation failed");return 0;}
  g_cfg=c;
  bootlog("protocol validated");
  HMODULE game=GetModuleHandleW(L"GameAssembly.dll");
  if(!game){fatal("GameAssembly missing",1);return 0;}
  static void *table[37];
  for(int i=0;i<37;i++){
    table[i]=(void *)GetProcAddress(game,c->aliases[i]);
    if(!table[i]){c->error=1;lstrcpynA(c->message,c->aliases[i],256);return 0;}
  }
  api=table;
  void *(*domain_get)(void)=api[API_DOMAIN];
  const void **(*assemblies)(void *,size_t *)=api[API_ASSEMBLIES];
  void *(*image_of)(const void *)=api[API_IMAGE];
  const char *(*image_name)(void *)=api[API_IMAGE_NAME];
  void *(*attach)(void *)=api[API_ATTACH];
  void (*detach)(void *)=api[API_DETACH];
  void *thread=attach(domain_get());
  size_t n=0;
  const void **all=assemblies(domain_get(),&n);
  for(size_t i=0;i<n;i++){
    void *image=image_of(all[i]);
    const char *label=image_name(image);
    if(!label)continue;
    if(!strcmp(label,"Assembly-CSharp.dll"))g_game=image;
    else if(!strcmp(label,"UnityEngine.CoreModule.dll"))g_core=image;
    else if(!strcmp(label,"UnityEngine.UIModule.dll"))g_ui=image;
    else if(!strcmp(label,"UnityEngine.JSONSerializeModule.dll"))g_json=image;
    else if(!strcmp(label,"Unity.Addressables.dll"))g_addr=image;
    else if(!strcmp(label,"mscorlib.dll")||!strcmp(label,"System.Private.CoreLib.dll"))g_corlib=image;
  }
  int ok=g_game&&g_core&&g_corlib&&g_addr&&g_ui;
  if(!ok){fatal("assembly resolution failed",2);detach(thread);return 0;}
  sprite_log_methods(g_game,g_core);
  if(!pool_load()){fatal("pool snapshot invalid",3);detach(thread);return 0;}
  auto_forms_load();
  if(!resolve_all()){fatal("class/method resolution incomplete",6);detach(thread);return 0;}
  {wchar_t path[32768];DWORD len=GetModuleFileNameW(g_self,path,32768);wchar_t *slash=len&&len<32768?wcsrchr(path,L'\\'):NULL;
   if(slash){lstrcpyW(slash+1,L"fx-active.bin");HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    if(f!=INVALID_HANDLE_VALUE){DWORD size=GetFileSize(f,NULL),got=0;unsigned char *buf=(size>0&&size<=FX_PLAN_MAX_BYTES)?(unsigned char *)HeapAlloc(GetProcessHeap(),0,size):NULL;
     if(buf&&ReadFile(f,buf,size,&got,NULL)&&got==size&&fx_plan_parse(buf,size,g_fxRows,FX_PLAN_MAX_ROWS,&g_fxRowCount)&&g_fxRowCount){
      for(size_t i=0;i<n;i++){void *im=image_of(all[i]);const char *name=im?image_name(im):NULL;if(name&&!strcmp(name,"Unity.Timeline.dll")){void *k=((void *(*)(void *,const char *,const char *))api[API_CLASS])(im,"UnityEngine.Timeline","RuntimeClip");void *field=k?((void *(*)(void *,const char *))api[API_FIELD])(k,"m_Clip"):NULL;if(field)g_fxRuntimeClipOffset=((size_t (*)(void *))api[API_FIELD_OFFSET])(field);if(k&&g_fxRuntimeClipOffset==24){m_fxStart=find_method(k,"get_start",0);m_fxEvaluate=find_method(k,"EvaluateAt",2);}break;}}
      g_fxExperiment=m_fxStart&&m_fxEvaluate;bootlog(g_fxExperiment?"fx plan loaded":"fx plan runtime unavailable");
     }else bootlog("fx plan snapshot rejected");if(buf)HeapFree(GetProcessHeap(),0,buf);CloseHandle(f);
    }
   }
  }
  if(!install_hooks()){fatal("hook installation failed",4);detach(thread);return 0;}
  say("Sinners native: hooks installed; waiting for battle");
  bootlog("hooks installed");
  detach(thread);
  return 0;
}

BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,void *reserved){
  (void)reserved;
  if(reason==DLL_PROCESS_ATTACH){
    g_self=module;
    DisableThreadLibraryCalls(module);
    HANDLE t=CreateThread(NULL,0,run,NULL,0,NULL);
    if(t)CloseHandle(t);
  }else if(reason==DLL_PROCESS_DETACH&&logHandle!=INVALID_HANDLE_VALUE){
    CloseHandle(logHandle);
  }
  return TRUE;
}
