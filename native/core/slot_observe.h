#ifndef SLOT_OBSERVE_H
#define SLOT_OBSERVE_H
#include <stdint.h>
typedef void *(*SlotSelectCall)(void*,int*,int*);
typedef void (*SlotSelectLog)(void*,int,int,void*);
static void *slot_select_run(void *c,int enabled,int *a,int *b,SlotSelectCall call,SlotSelectLog log){void *v=call(c,a,b);if(enabled)log(c,a?*a:-1,b?*b:-1,v);return v;}
#endif
