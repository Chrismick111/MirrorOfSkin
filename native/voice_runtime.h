#ifndef SR_VOICE_RUNTIME
#define SR_VOICE_RUNTIME
#include "voice_lookup.h"

#ifndef SR_VOICE_DELAY_MS
/* The appearance swap settles over a few frames; speaking on the same frame as
   the death callback races the timeline that owns the audio source. */
#define SR_VOICE_DELAY_MS 400
#endif

/* Boss voice playback.

   The engine resolves SetPlayVoice through the view's own personality, which for
   a swapped sinner is their own id, so a boss recording never matches. Boss
   voices must go through VoiceGenerator.PlayMultiVoice, which takes the
   personality id explicitly. 8378's OnDie_View does exactly that with a
   hardcoded 0x20ba, which is why it is audible while SetPlayVoice stayed silent.

   Hooks only record intent. Playback runs on the main thread from tick(), the
   same place every other managed call in this file happens. */

#define SR_VOICE_PENDING 8
#define SR_VOICE_LEN 48

/* The engine reports one death through more than one entry point (the view's own
   callback plus the unit-level forward), 400-600ms apart. The pending-slot check
   below cannot catch the second one once the first has played, so remember what
   was already queued and swallow the repeat. */
#ifndef SR_VOICE_DEDUPE_MS
#define SR_VOICE_DEDUPE_MS 1500
#endif

typedef struct {
  void *view;
  uintptr_t viewRoot;
  unsigned boss;
  char trigger[48];
  char key[SR_VOICE_LEN];
  DWORD due;
} SrVoicePending;

static SrVoicePending g_voicePending[SR_VOICE_PENDING];
static volatile LONG g_voicePendingCount;
static volatile LONG g_voiceLock;
static int sr_voice_cancel_for_appearance(const char *trigger,int stillWorn){
  return !stillWorn&&!strcmp(trigger,"OnRoundStart_View");
}

typedef struct {
  void *view;
  unsigned boss;
  char trigger[48];
  DWORD at;
} SrVoiceRecent;

static SrVoiceRecent g_voiceRecent[SR_VOICE_PENDING];
static volatile LONG g_voiceRecentNext;

/* story_8378_Priest_BossAppearance -> 8378 ; 0 when no id is present.
   The separator check keeps story_123x from matching. */
static unsigned sr_boss_id_from_appearance(const char *id){
  if(!id)return 0;
  const char *p=strstr(id,"story_");
  if(!p)return 0;
  p+=6;
  unsigned v=0;int n=0;
  while(*p>='0'&&*p<='9'&&n<9){v=v*10+(unsigned)(*p-'0');p++;n++;}
  if(n<3)return 0;
  if(*p!='_'&&*p!=0)return 0;
  return v;
}

/* Managed string -> byte buffer. Non-ascii becomes '?' because appearance ids
   and voice keys are ascii. */
static int sr_voice_string_text(void *s,char *out,int cap){
  if(!s||cap<=0)return 0;
  int32_t len=*(int32_t *)((char *)s+16);
  if(len<=0||len>=cap)return 0;
  const uint16_t *chars=(const uint16_t *)((char *)s+20);
  for(int i=0;i<len;i++)out[i]=(chars[i]<128)?(char)chars[i]:'?';
  out[len]=0;
  return 1;
}

/* True when this exact view already asked for this trigger a moment ago. */
static int sr_voice_seen(void *view,unsigned boss,const char *trigger,DWORD now){
  for(int i=0;i<SR_VOICE_PENDING;i++){
    SrVoiceRecent *r=&g_voiceRecent[i];
    if(r->view!=view||r->boss!=boss||!r->trigger[0])continue;
    if(strcmp(r->trigger,trigger))continue;
    if((DWORD)(now-r->at)>=SR_VOICE_DEDUPE_MS)continue;
    return 1;
  }
  return 0;
}

/* Queue a boss voice for the next main-thread tick. Called from hooks only, so
   it must not touch managed memory beyond reading the already-passed view.
   Returns 1 when the request was accepted, 0 when it was dropped as a repeat. */
static int sr_voice_request_locked(void *view,unsigned boss,const char *trigger){
  if(!view||!boss||!trigger)return 0;
  char key[SR_VOICE_LEN];
  if(!sr_voice_single(boss,trigger,key,sizeof(key)))return 0; /* absent or ambiguous: do not guess */
  DWORD now=GetTickCount();
  if(sr_voice_seen(view,boss,trigger,now))return 0;
  LONG slot=-1;
  for(int i=0;i<SR_VOICE_PENDING;i++){
    if(g_voicePending[i].view==view&&g_voicePending[i].boss==boss&&!strcmp(g_voicePending[i].trigger,trigger)
       &&g_voicePending[i].key[0]){
      g_voicePending[i].due=now+SR_VOICE_DELAY_MS;
      return 0;
    }
    if(!g_voicePending[i].view&&slot<0)slot=i;
  }
  if(slot<0)return 0;
  uintptr_t root=ui_root(view);
  if(!root)return 0;
  SrVoicePending *p=&g_voicePending[slot];
  p->view=view;p->viewRoot=root;p->boss=boss;
  lstrcpynA(p->trigger,trigger,sizeof(p->trigger));
  lstrcpynA(p->key,key,sizeof(p->key));
  p->due=now+SR_VOICE_DELAY_MS;
  MemoryBarrier();
  InterlockedIncrement(&g_voicePendingCount);

  /* Remember it in the same pass that queued it, so the duplicate arriving
     after playback still finds a record. */
  LONG r=(LONG)((unsigned)InterlockedIncrement(&g_voiceRecentNext)-1u)%SR_VOICE_PENDING;
  SrVoiceRecent *rec=&g_voiceRecent[r];
  rec->view=view;rec->boss=boss;rec->at=now;
  lstrcpynA(rec->trigger,trigger,sizeof(rec->trigger));
  MemoryBarrier();
  return 1;
}
static int sr_voice_request(void *view,unsigned boss,const char *trigger){
  if(InterlockedCompareExchange(&g_voiceLock,1,0))return 0;
  int accepted=sr_voice_request_locked(view,boss,trigger);
  InterlockedExchange(&g_voiceLock,0);
  return accepted;
}
static void sr_voice_clear(void){
  if(InterlockedCompareExchange(&g_voiceLock,1,0))return;
  for(int i=0;i<SR_VOICE_PENDING;i++){
    ui_unroot(g_voicePending[i].viewRoot);
    memset(&g_voicePending[i],0,sizeof(g_voicePending[i]));
  }
  memset(g_voiceRecent,0,sizeof(g_voiceRecent));
  g_voicePendingCount=0;g_voiceRecentNext=0;
  InterlockedExchange(&g_voiceLock,0);
}

/* Bosses report the same moment through differently named methods: some expose
   OnDie_View on the view, others only carry OnDeadVoice on their own UnitScript,
   which never runs when a sinner wears the appearance. Try the names in order and
   take the first that resolves to one key; an ambiguous row falls through to the
   next name rather than guessing. */
static int sr_voice_request_any(void *view,unsigned boss,const char *const *triggers,int n){
  for(int i=0;i<n;i++){
    if(sr_voice_row_index(boss,triggers[i])>=0)return sr_voice_request(view,boss,triggers[i]);
  }
  return 0;
}

#endif
