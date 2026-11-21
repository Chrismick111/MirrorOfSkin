#ifndef WEDGE_RAW_UPLOAD_POLICY_H
#define WEDGE_RAW_UPLOAD_POLICY_H
#include <stdint.h>
#include <stddef.h>
#include <limits.h>

/* Mockable IL2CPP runtime-invoke adapter; methods must be uniquely resolved as
   nonstatic void Texture2D.LoadRawTextureData(IntPtr,Int32) and
   nonstatic void Texture2D.Apply(Boolean,Boolean) before use. Caller roots the
   texture and owns the pixel memory until the synchronous invocation returns. */
typedef struct {
 int (*is_unity_thread)(void *ctx);
 int (*invoke_void)(void *ctx,void *method,void *instance,void **arguments);
} RawUploadOps;
static int raw_upload_rgba(const RawUploadOps *ops,void *ctx,void *texture,
                           void *load_method,void *apply_method,const uint8_t *pixels,
                           size_t size,uint32_t width,uint32_t height){
 if(!ops||!ops->is_unity_thread||!ops->invoke_void||!texture||!load_method||!apply_method||!pixels||!width||!height)return 0;
 if(width>(uint32_t)INT_MAX/4||height>(uint32_t)INT_MAX/(width*4))return 0;
 size_t required=(size_t)width*height*4;
 if(size!=required||size>INT_MAX||!ops->is_unity_thread(ctx))return 0;
 void *pointer=(void*)pixels;int32_t count=(int32_t)size;
 void *load_args[]={&pointer,&count};
 if(!ops->invoke_void(ctx,load_method,texture,load_args))return 0;
 uint8_t mipmaps=0,no_longer_readable=0;void *apply_args[]={&mipmaps,&no_longer_readable};
 return ops->invoke_void(ctx,apply_method,texture,apply_args)!=0;
}
#endif
