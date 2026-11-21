#ifndef WEDGE_DIRECTOR_IDENTITY_H
#define WEDGE_DIRECTOR_IDENTITY_H
#include <stdint.h>

/* Pure identity policy: arguments are caller-authenticated live objects and
   rooted by the caller. It makes no Unity calls and cannot prove marker binding. */
typedef struct {uintptr_t app,director,timeline;uint64_t generation;} DiCapture;
typedef struct {uintptr_t app,timeline;uint64_t generation;int pending;} DiPending;
static int di_begin(DiPending *pending,uintptr_t app,uintptr_t expected_timeline,uint64_t generation){
 if(!pending||pending->pending||!app||!expected_timeline||!generation)return 0;
 *pending=(DiPending){app,expected_timeline,generation,1};return 1;
}
static int di_capture(DiCapture *out,uintptr_t app,uintptr_t director,
                      uintptr_t expected_timeline,uintptr_t actual_asset,uint64_t generation){
 if(!out||out->generation||!app||!director||!expected_timeline||actual_asset!=expected_timeline||!generation)return 0;
 *out=(DiCapture){app,director,expected_timeline,generation};return 1;
}
/* Call only after the original ChangeMotion returns. Consume the pending
   identity even on failure, preventing a later unrelated asset from matching. */
static int di_after(DiPending *pending,DiCapture *out,uintptr_t current_app,
                    uintptr_t current_director,uintptr_t current_asset,uint64_t current_generation){
 if(!pending||!pending->pending||!out)return 0;
 DiPending saved=*pending;*pending=(DiPending){0};
 if(saved.app!=current_app||saved.generation!=current_generation)return 0;
 return di_capture(out,current_app,current_director,saved.timeline,current_asset,current_generation);
}
/* A stale callback for a prior generation must not clear the next action. */
static int di_interrupt(DiPending *pending,DiCapture *capture,uintptr_t app,uint64_t generation){
 if(!app||!generation)return 0;int changed=0;
 if(pending&&pending->pending&&pending->app==app&&pending->generation==generation){*pending=(DiPending){0};changed=1;}
 if(capture&&capture->generation==generation&&capture->app==app){*capture=(DiCapture){0};changed=1;}
 return changed;
}
static int di_matches(const DiCapture *c,uintptr_t app,uintptr_t director,
                      uintptr_t asset,uint64_t generation){
 return c&&c->generation&&c->app==app&&c->director==director&&c->timeline==asset&&c->generation==generation;
}
static int di_finish(DiCapture *c,uintptr_t app,uintptr_t director,
                     uintptr_t asset,uint64_t generation){
 if(!di_matches(c,app,director,asset,generation))return 0;
 *c=(DiCapture){0};return 1;
}
#endif
