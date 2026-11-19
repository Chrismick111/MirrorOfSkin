#ifndef FX_PLAYBACK_SLOTS_H
#define FX_PLAYBACK_SLOTS_H
#include <stddef.h>
#include "fx_playback_plan.h"
#define FX_SLOT_COUNT 64
typedef struct {void *app,*director;uint64_t generation;FxPlaybackPlan plan;} FxPlaybackSlot;
typedef struct {uint64_t serial;FxPlaybackSlot slots[FX_SLOT_COUNT];} FxPlaybackSlots;
/* Caller serializes access and owns the lifetime of app and director keys. */
static FxPlaybackSlot *fx_slots_slot(FxPlaybackSlots *s,const void *app,const void *director,uint64_t generation){
 if(!s||!app||!director||!generation)return NULL;
 for(int i=0;i<FX_SLOT_COUNT;i++){FxPlaybackSlot *x=&s->slots[i];if(x->app==app&&x->director==director&&x->generation==generation)return x;}return NULL;
}
static FxPlaybackPlan *fx_slots_find(FxPlaybackSlots *s,const void *app,const void *director,uint64_t generation){FxPlaybackSlot *x=fx_slots_slot(s,app,director,generation);return x?&x->plan:NULL;}
static int fx_slots_lookup(FxPlaybackSlots *s,const void *runtime,const void *clip,double *delta){
 if(!s)return 0;for(int i=0;i<FX_SLOT_COUNT;i++)if(fx_playback_lookup(&s->slots[i].plan,runtime,clip,delta))return 1;return 0;
}
static FxPlaybackPlan *fx_slots_lookup_plan(FxPlaybackSlots *s,const void *runtime,const void *clip,double *delta){
 if(!s)return NULL;for(int i=0;i<FX_SLOT_COUNT;i++)if(fx_playback_lookup(&s->slots[i].plan,runtime,clip,delta))return &s->slots[i].plan;return NULL;
}
/* A shared source clip may be used by several active directors. Never infer
   ownership if more than one candidate playback refers to it. */
static FxPlaybackPlan *fx_slots_pending(FxPlaybackSlots *s,const void *clip){
 if(!s||!clip)return NULL;FxPlaybackPlan *match=NULL;
 for(int i=0;i<FX_SLOT_COUNT;i++){FxPlaybackPlan *p=&s->slots[i].plan;if(!p->owner||p->closing)continue;
  for(int j=0;j<FX_PLAYBACK_CLIPS;j++)if(p->clips[j].clip==clip){if(match&&match!=p)return NULL;match=p;break;}}
 return match;
}
static FxPlaybackPlan *fx_slots_open(FxPlaybackSlots *s,void *app,void *director,uint64_t generation){
 if(!s||!app||!director||!generation||fx_slots_slot(s,app,director,generation))return NULL;
 for(int i=0;i<FX_SLOT_COUNT;i++){FxPlaybackSlot *x=&s->slots[i];if(!x->app){uint64_t serial=++s->serial;if(!serial)serial=++s->serial;
  x->app=app;x->director=director;x->generation=generation;if(!fx_playback_begin(&x->plan,serial)){x->app=NULL;return NULL;}return &x->plan;}}
 return NULL;
}
static uintptr_t fx_slots_take(FxPlaybackSlots *s,const void *app,const void *director,uint64_t generation){
 FxPlaybackSlot *x=fx_slots_slot(s,app,director,generation);if(!x)return 0;
 uintptr_t root=fx_playback_take(&x->plan);if(!root){x->app=NULL;x->director=NULL;x->generation=0;}return root;
}
#endif
