#ifndef FX_RUNTIME_REGISTRY_H
#define FX_RUNTIME_REGISTRY_H
#include <stdint.h>
#include <math.h>
#define FX_RUNTIME_MAX 128
/* Registry is called under an external lock. Runtime roots are owned by the
   caller until returned by take_owner; it never dereferences Unity objects. */
typedef struct {void *runtime,*clip;uintptr_t root;uint64_t owner;double delta;} FxRuntimeEntry;
typedef struct {FxRuntimeEntry rows[FX_RUNTIME_MAX];} FxRuntimeRegistry;
static int fx_registry_add(FxRuntimeRegistry *r,void *runtime,void *clip,uintptr_t root,uint64_t owner,double before,double after){
 if(!r||!runtime||!clip||!root||!owner||!isfinite(before)||!isfinite(after)||before<0||after<0)return 0;
 int free_index=-1;
 for(int i=0;i<FX_RUNTIME_MAX;i++){if(r->rows[i].runtime==runtime)return 0;if(!r->rows[i].runtime&&free_index<0)free_index=i;}
 if(free_index<0)return 0;
 r->rows[free_index]=(FxRuntimeEntry){runtime,clip,root,owner,after-before};return 1;
}
static int fx_registry_delta(const FxRuntimeRegistry *r,const void *runtime,const void *clip,double *delta){
 if(!r||!runtime||!clip||!delta)return 0;
 for(int i=0;i<FX_RUNTIME_MAX;i++)if(r->rows[i].runtime==runtime&&r->rows[i].clip==clip){*delta=r->rows[i].delta;return 1;}
 return 0;
}
static uintptr_t fx_registry_take_owner(FxRuntimeRegistry *r,uint64_t owner){
 if(!r||!owner)return 0;
 for(int i=0;i<FX_RUNTIME_MAX;i++)if(r->rows[i].owner==owner){uintptr_t root=r->rows[i].root;r->rows[i]=(FxRuntimeEntry){0};return root;}
 return 0;
}
#endif
