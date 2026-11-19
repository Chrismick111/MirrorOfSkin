/* Isolated candidate: compiled FXP2 plans bound to individual runtime clips.
   This is not installed and requires integration and real battle validation. */
#include "fx_readonly_tree.h"
#include "fx_runtime_clip.h"
#include "fx_plan_match.h"
#include "fx_playback_slots.h"
static FxPlanRow g_fxRows[FX_PLAN_MAX_ROWS];static size_t g_fxRowCount;
static FxPlaybackSlots g_fxSlots;static SRWLOCK g_fxSlotsLock=SRWLOCK_INIT;
static volatile LONG g_fxPlanStarts,g_fxPlanEvals,g_fxPlanCaptures;
static _Thread_local FxPlaybackPlan *g_fxCapture;static _Thread_local uint64_t g_fxCaptureOwner;static _Thread_local int g_fxCapturing;
static void *m_fxStart,*orig_fxStart,*m_fxEvaluate,*orig_fxEvaluate;
static size_t g_fxRuntimeClipOffset;static int g_fxExperiment;
static uintptr_t fx_tree_root(void *o){return o?((uintptr_t (*)(void *,int))api[API_ROOT])(o,1):0;}
static int fx_tree_clip(void *clip,const char *target,double *out){
 void *name=rfield(clip,"m_DisplayName");if(!name)return -1;uintptr_t root=fx_tree_root(name);if(!root)return -1;char buf[256];int valid=string_ascii(name,buf,sizeof(buf));ui_unroot(root);if(!valid)return -1;if(strcmp(buf,target))return 0;
 void *field=find_field_obj(clip,"m_Start");if(!field)return -1;void *type=((void *(*)(void *))api[API_FIELD_TYPE])(field);char *tn=type?((char *(*)(void *))api[API_TYPE_NAME])(type):NULL;int is_double=tn&&!strcmp(tn,"System.Double");if(tn)((void (*)(void *))api[API_FREE])(tn);if(!is_double)return -1;
 void *box=((void *(*)(void *,void *))api[API_FIELD_VALUE])(field,clip);uintptr_t br=fx_tree_root(box);if(!br)return -1;void *raw=ui_unbox(box);if(!raw){ui_unroot(br);return -1;}double v=*(double*)raw;ui_unroot(br);if(!isfinite(v)||v<0)return -1;*out=v;return 1;
}
static int fx_plan_track_class(void *track){
 if(!track||!g_game)return 0;void *expected=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"","EffectActivateTimelineTrack");return expected&&ui_class(track)==expected;
}
static void *fx_plan_find_clip(void *app,const FxPlanRow *r,uintptr_t *held){
 *held=0;if(!r||strcmp(r->strings[6],"Assembly-CSharp")||r->strings[7][0]||strcmp(r->strings[8],"EffectActivateTimelineTrack"))return NULL;
 int detail=r->detail;uint8_t flag=0;void *args[]={&detail,&flag};int ok=0;g_motionDepth++;void *motion=call_obj(m_getMotion,app,args,&ok);g_motionDepth--;
 if(!ok||!motion)return NULL;uintptr_t mr=fx_tree_root(motion);if(!mr)return NULL;
 int actual=-1,count=timeline_count(motion,&actual);if(actual!=detail||r->part<0||r->part>=count){ui_unroot(mr);return NULL;}
 void *list=rfield(motion,"timelineAssets");uintptr_t lr=fx_tree_root(list);void *timeline=lr?list_item(list,r->part):NULL,*selected=NULL;
 if(timeline){FxTreeOps ops={rfield,list_count,list_item,fx_tree_root,ui_unroot,fx_tree_clip,fx_plan_track_class};int path[FX_PLAN_MAX_DEPTH];for(int i=0;i<r->depth;i++)path[i]=(int)r->track_path[i];double start=0;
  int match=fx_read_path(&ops,timeline,path,r->depth,r->clip_index,r->strings[4],&start,&selected,held);
  if(match!=1||fabs(start-r->original_start)>1e-7){ui_unroot(*held);*held=0;selected=NULL;}}
 ui_unroot(lr);ui_unroot(mr);return selected;
}
/* Callers remove registry handles while holding the lock and release outside it. */
static void fx_plan_close(void *app,void *director,uint64_t generation){
 int had=0,reported=0;unsigned bound_start=0,bound_eval=0,misses_start=0,misses_eval=0;void *sample=NULL;
 for(;;){AcquireSRWLockExclusive(&g_fxSlotsLock);FxPlaybackPlan *p=fx_slots_find(&g_fxSlots,app,director,generation);if(p&&!p->closing&&!reported){bound_start=p->bound_start;bound_eval=p->bound_eval;misses_start=p->unbound_start;misses_eval=p->unbound_eval;sample=p->unbound_runtime;reported=1;}uintptr_t root=fx_slots_take(&g_fxSlots,app,director,generation);ReleaseSRWLockExclusive(&g_fxSlotsLock);if(!root)break;had=1;ui_unroot(root);}
 if(reported){char msg[220];snprintf(msg,sizeof(msg),"fx plan calls bound_start=%u bound_eval=%u unbound_start=%u unbound_eval=%u sample=%p",bound_start,bound_eval,misses_start,misses_eval,sample);bootlog(msg);}
 if(had){char msg[160];snprintf(msg,sizeof(msg),"fx plan totals start=%ld eval=%ld runtime=%ld",InterlockedCompareExchange(&g_fxPlanStarts,0,0),InterlockedCompareExchange(&g_fxPlanEvals,0,0),InterlockedCompareExchange(&g_fxPlanCaptures,0,0));bootlog(msg);}
}
static void fx_plan_close_app(void *app,uint64_t except_generation){
 for(;;){void *director=NULL;uint64_t generation=0;AcquireSRWLockShared(&g_fxSlotsLock);
  for(int i=0;i<FX_SLOT_COUNT;i++){FxPlaybackSlot *s=&g_fxSlots.slots[i];if(s->app==app&&s->generation!=except_generation){director=s->director;generation=s->generation;break;}}
  ReleaseSRWLockShared(&g_fxSlotsLock);if(!director||!generation)break;fx_plan_close(app,director,generation);}
}
static void fx_plan_close_all(void){
 for(;;){void *app=NULL;AcquireSRWLockShared(&g_fxSlotsLock);for(int i=0;i<FX_SLOT_COUNT;i++)if(g_fxSlots.slots[i].app){app=g_fxSlots.slots[i].app;break;}ReleaseSRWLockShared(&g_fxSlotsLock);if(!app)break;fx_plan_close_app(app,0);}
}
static void fx_plan_close_unit(Unit *unit){
 if(!unit)return;for(;;){void *app=NULL;AcquireSRWLockShared(&g_fxSlotsLock);
  for(int i=0;i<FX_SLOT_COUNT;i++){void *candidate=g_fxSlots.slots[i].app;if(candidate&&unit_for_app(candidate)==unit){app=candidate;break;}}
  ReleaseSRWLockShared(&g_fxSlotsLock);if(!app)break;fx_plan_close_app(app,0);}
}
static FxPlaybackPlan *fx_plan_open(void *app,Unit *u,Skin *skin,int detail,int part){
 if(!app||!u||!skin||skin->row<0||skin->row>=g_rowCount||!u->playbackGeneration)return NULL;
 size_t indices[FX_PLAN_MAX_ROWS];int count=fx_match_rows(g_fxRows,g_fxRowCount,u->baseName,g_rows[skin->row].identity,skin->look,detail,part,indices,FX_PLAN_MAX_ROWS);
 if(count<=0)return NULL;void *director=rfield(app,"_playableDirector");uint64_t generation=u->playbackGeneration;if(!director)return NULL;
 AcquireSRWLockExclusive(&g_fxSlotsLock);FxPlaybackPlan *p=fx_slots_open(&g_fxSlots,app,director,generation);ReleaseSRWLockExclusive(&g_fxSlotsLock);if(!p)return NULL;
 for(int i=0;i<count;i++){const FxPlanRow *row=&g_fxRows[indices[i]];uintptr_t root=0;void *clip=fx_plan_find_clip(app,row,&root);int accepted=0;
  if(clip&&root){AcquireSRWLockExclusive(&g_fxSlotsLock);if(u->playbackGeneration==generation&&fx_slots_find(&g_fxSlots,app,director,generation)==p)accepted=fx_playback_add_clip(p,clip,root,row->original_start,row->new_start);ReleaseSRWLockExclusive(&g_fxSlotsLock);}
  if(!accepted){ui_unroot(root);fx_plan_close(app,director,generation);bootlog("fx plan target unavailable; playback unchanged");return NULL;}
  char detail_line[280];snprintf(detail_line,sizeof(detail_line),"fx plan target clip=%.100s original=%.9f new=%.9f",row->strings[4],row->original_start,row->new_start);bootlog(detail_line);}
 char line[160];snprintf(line,sizeof(line),"fx plan armed detail=%d part=%d effects=%d",detail,part,count);bootlog(line);return p;
}
static int fx_plan_delta(void *runtime,void *clip,double *delta,int eval){
 if(!runtime||!clip||!delta)return 0;
 AcquireSRWLockExclusive(&g_fxSlotsLock);FxPlaybackPlan *matched=fx_slots_lookup_plan(&g_fxSlots,runtime,clip,delta);int found=matched!=NULL;int candidate=0;if(matched){if(eval)matched->bound_eval++;else matched->bound_start++;}
 if(!found&&g_fxCapture&&g_fxCapture->owner==g_fxCaptureOwner&&!g_fxCapture->closing)for(int i=0;i<FX_PLAYBACK_CLIPS;i++)if(g_fxCapture->clips[i].clip==clip){candidate=1;break;}
 ReleaseSRWLockExclusive(&g_fxSlotsLock);
 if(!found&&candidate&&!g_fxCapturing){g_fxCapturing=1;uintptr_t root=fx_tree_root(runtime);int accepted=0;
  if(root){AcquireSRWLockExclusive(&g_fxSlotsLock);if(g_fxCapture&&g_fxCapture->owner==g_fxCaptureOwner){accepted=fx_playback_capture(g_fxCapture,runtime,clip,root,delta);if(accepted){if(eval)g_fxCapture->bound_eval++;else g_fxCapture->bound_start++;}}ReleaseSRWLockExclusive(&g_fxSlotsLock);}
  if(root&&!accepted)ui_unroot(root);if(accepted)InterlockedIncrement(&g_fxPlanCaptures);g_fxCapturing=0;found=accepted;}
 if(!found){AcquireSRWLockExclusive(&g_fxSlotsLock);FxPlaybackPlan *pending=fx_slots_pending(&g_fxSlots,clip);if(pending)fx_playback_note_unbound(pending,runtime,eval);ReleaseSRWLockExclusive(&g_fxSlotsLock);}
 return found;
}
static double fx_start_hook(void *runtime,void *mi){
 double value=((double (*)(void *,void *))orig_fxStart)(runtime,mi),delta=0;void *clip=fx_runtime_clip(runtime,g_fxRuntimeClipOffset);
 if(isfinite(value)&&fx_plan_delta(runtime,clip,&delta,0)&&isfinite(value+delta)){InterlockedIncrement(&g_fxPlanStarts);return value+delta;}return value;
}
static void fx_evaluate_hook(void *runtime,double time,void *frame,void *mi){
 double delta=0;void *clip=fx_runtime_clip(runtime,g_fxRuntimeClipOffset);if(isfinite(time)&&fx_plan_delta(runtime,clip,&delta,1)&&isfinite(time-delta)){time-=delta;InterlockedIncrement(&g_fxPlanEvals);}
 ((void (*)(void *,double,void *,void *))orig_fxEvaluate)(runtime,time,frame,mi);
}
