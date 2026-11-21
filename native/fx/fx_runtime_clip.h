#ifndef FX_RUNTIME_CLIP_H
#define FX_RUNTIME_CLIP_H
#include <stddef.h>
#include <string.h>
/* Offset is verified against IL2CPP field metadata before the hook is enabled. */
static void *fx_runtime_clip(const void *runtime,size_t offset){
 if(!runtime||offset!=24)return NULL;
 void *clip=NULL;memcpy(&clip,(const char *)runtime+offset,sizeof clip);return clip;
}
#endif
