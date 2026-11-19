#ifndef DIRECTOR_STACK_PROBE_H
#define DIRECTOR_STACK_PROBE_H
#include "director_identity.h"
typedef struct {
 uintptr_t (*root)(void *,uintptr_t);void (*unroot)(void *,uintptr_t);
 int (*snapshot)(void *,uintptr_t *,uintptr_t *,uintptr_t *,uint64_t *);
 void (*original)(void *);void (*report)(void *,int,uintptr_t,uintptr_t,uint64_t);
} DiProbeOps;
/* expected_timeline must remain rooted by the caller until return. A local
   pending never survives original(), and nested calls have independent state. */
static void di_probe_run(const DiProbeOps *o,void *ctx,uintptr_t app,uintptr_t expected,uint64_t generation){
 DiPending pending={0};DiCapture capture={0};uintptr_t ar=0,tr=0;
 if(!o||!o->original)return;
 if(o->root&&o->unroot&&o->snapshot&&o->report&&di_begin(&pending,app,expected,generation)){
  ar=o->root(ctx,app);if(ar)tr=o->root(ctx,expected);
  if(!tr)di_interrupt(&pending,&capture,app,generation);
 }
 o->original(ctx);
 if(pending.pending){
  uintptr_t current_app=0,director=0,asset=0;uint64_t current_generation=0;
  int ok=o->snapshot(ctx,&current_app,&director,&asset,&current_generation)&&
         di_after(&pending,&capture,current_app,director,asset,current_generation);
  if(pending.pending)di_interrupt(&pending,&capture,app,generation);
  o->report(ctx,ok,director,asset,current_generation);
 }
 if(tr)o->unroot(ctx,tr);if(ar)o->unroot(ctx,ar);
}
#endif
