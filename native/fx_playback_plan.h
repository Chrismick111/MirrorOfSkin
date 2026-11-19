#ifndef FX_PLAYBACK_PLAN_H
#define FX_PLAYBACK_PLAN_H
#include <stddef.h>
#include "fx_runtime_registry.h"
#define FX_PLAYBACK_CLIPS 64
typedef struct {void *clip;uintptr_t root;double before,after;} FxPlaybackClip;
typedef struct {uint64_t owner;int closing;unsigned bound_start,bound_eval,unbound_start,unbound_eval;void *unbound_runtime;FxPlaybackClip clips[FX_PLAYBACK_CLIPS];FxRuntimeRegistry runtimes;} FxPlaybackPlan;
/* All calls require a caller-held lock. The caller creates and releases every
   root; failures do not consume it, take returns exactly one owned handle. */
static int fx_playback_begin(FxPlaybackPlan *p,uint64_t owner){if(!p||!owner||p->owner)return 0;p->bound_start=0;p->bound_eval=0;p->unbound_start=0;p->unbound_eval=0;p->unbound_runtime=NULL;p->owner=owner;return 1;}
static int fx_playback_note_unbound(FxPlaybackPlan *p,void *runtime,int eval){if(!p||!p->owner||p->closing||!runtime)return 0;if(eval)p->unbound_eval++;else p->unbound_start++;if(!p->unbound_runtime)p->unbound_runtime=runtime;return 1;}
static int fx_playback_add_clip(FxPlaybackPlan *p,void *clip,uintptr_t root,double before,double after){
 if(!p||!p->owner||p->closing||!clip||!root||!isfinite(before)||!isfinite(after)||before<0||after<0)return 0;
 int free_index=-1;for(int i=0;i<FX_PLAYBACK_CLIPS;i++){if(p->clips[i].clip==clip)return 0;if(!p->clips[i].clip&&free_index<0)free_index=i;}
 if(free_index<0)return 0;p->clips[free_index]=(FxPlaybackClip){clip,root,before,after};return 1;
}
static int fx_playback_capture(FxPlaybackPlan *p,void *runtime,void *clip,uintptr_t root,double *delta){
 if(!p||!p->owner||p->closing||!delta)return 0;
 for(int i=0;i<FX_PLAYBACK_CLIPS;i++){FxPlaybackClip *c=&p->clips[i];if(c->clip==clip&&clip){
  if(!fx_registry_add(&p->runtimes,runtime,clip,root,p->owner,c->before,c->after))return 0;
  *delta=c->after-c->before;return 1;
 }}return 0;
}
static int fx_playback_lookup(const FxPlaybackPlan *p,const void *runtime,const void *clip,double *delta){return p&&p->owner&&!p->closing&&fx_registry_delta(&p->runtimes,runtime,clip,delta);}
static uintptr_t fx_playback_take(FxPlaybackPlan *p){
 if(!p||!p->owner)return 0;p->closing=1;uintptr_t root=fx_registry_take_owner(&p->runtimes,p->owner);if(root)return root;
 for(int i=0;i<FX_PLAYBACK_CLIPS;i++)if(p->clips[i].clip){root=p->clips[i].root;p->clips[i]=(FxPlaybackClip){0};return root;}
 p->owner=0;p->closing=0;return 0;
}
#endif
