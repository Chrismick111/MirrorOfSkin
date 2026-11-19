#ifndef WEDGE_METADATA_GATE_H
#define WEDGE_METADATA_GATE_H
static void wedge_metadata_once(int enabled,int *done,void (*emit)(void*),void *context){if(!enabled||!done||*done||!emit)return;*done=1;emit(context);}
#endif
