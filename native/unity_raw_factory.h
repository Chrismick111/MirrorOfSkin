#ifndef WEDGE_UNITY_RAW_FACTORY_H
#define WEDGE_UNITY_RAW_FACTORY_H
#include <string.h>
#include <math.h>
#include "raw_upload_policy.h"
typedef struct {float x,y,w,h;} UrRect;
typedef struct {float x,y;} UrVector;
/* exact() must return NULL on missing, duplicate, wrong staticness or return
   type; caller resolves and verifies RGBA32 enum value from game metadata. */
typedef struct {
 void *(*exact)(void *,const char *,const char *,const char *const *,int,const char *,int);
 int (*is_unity_thread)(void *);
 void *(*new_object)(void *,const char *);
 uintptr_t (*root)(void *,void *);
 void (*unroot)(void *,uintptr_t);
 int (*invoke_void)(void *,void *,void *,void **);
 void *(*invoke_object)(void *,void *,void *,void **);
 int (*destroy)(void *,void *);
} UrOps;
typedef struct {void *ctor,*load,*apply,*create;int format;} UrMethods;
typedef struct {void *texture,*sprite;uintptr_t texture_root,sprite_root;int orphaned;} UrImage;
static int ur_resolve(const UrOps *o,void *c,int rgba32,int enum_verified,UrMethods *out){
 static const char *ctor[]={"System.Int32","System.Int32","UnityEngine.TextureFormat","System.Boolean"};
 static const char *load[]={"System.IntPtr","System.Int32"};
 static const char *apply[]={"System.Boolean","System.Boolean"};
 static const char *create[]={"UnityEngine.Texture2D","UnityEngine.Rect","UnityEngine.Vector2","System.Single"};
 if(!o||!o->exact||!enum_verified||!out)return 0;
 UrMethods m={0};m.ctor=o->exact(c,"UnityEngine.Texture2D",".ctor",ctor,4,"System.Void",0);
 m.load=o->exact(c,"UnityEngine.Texture2D","LoadRawTextureData",load,2,"System.Void",0);
 m.apply=o->exact(c,"UnityEngine.Texture2D","Apply",apply,2,"System.Void",0);
 m.create=o->exact(c,"UnityEngine.Sprite","Create",create,4,"UnityEngine.Sprite",1);m.format=rgba32;
 if(!m.ctor||!m.load||!m.apply||!m.create)return 0;*out=m;return 1;
}
/* On failure retain object and its root in x; caller must retry. Texture must
   outlive sprite. A never-constructed object may be passed to destroy. */
static int ur_release(const UrOps *o,void *c,UrImage *x){
 if(!o||!x||!o->destroy||!o->unroot||x->orphaned)return 0;
 if(x->sprite){if(!o->destroy(c,x->sprite)){if(!x->sprite_root){x->sprite=NULL;x->orphaned=1;}return 0;}x->sprite=NULL;}
 if(x->sprite_root){o->unroot(c,x->sprite_root);x->sprite_root=0;}
 if(x->texture){if(!o->destroy(c,x->texture)){if(!x->texture_root){x->texture=NULL;x->orphaned=1;}return 0;}x->texture=NULL;}
 if(x->texture_root){o->unroot(c,x->texture_root);x->texture_root=0;}return 1;
}
static int ur_create(const UrOps *o,void *c,const UrMethods *m,const uint8_t *rgba,size_t size,int w,int h,float px,float py,float ppu,UrImage *out){
 if(!o||!m||!out||out->texture||out->sprite||out->texture_root||out->sprite_root||out->orphaned||!o->is_unity_thread||!o->new_object||!o->root||!o->unroot||!o->destroy||!o->invoke_void||!o->invoke_object||!m->ctor||!m->load||!m->apply||!m->create||!o->is_unity_thread(c)||w<=0||h<=0||!isfinite(px)||!isfinite(py)||!isfinite(ppu)||!(ppu>0))return 0;
 UrImage x={0};x.texture=o->new_object(c,"UnityEngine.Texture2D");if(!x.texture)goto fail;
 x.texture_root=o->root(c,x.texture);if(!x.texture_root)goto fail;
 int32_t width=w,height=h,format=m->format;uint8_t mip=0;void *ctor[]={&width,&height,&format,&mip};
 if(!o->invoke_void(c,m->ctor,x.texture,ctor))goto fail;
 RawUploadOps upload={o->is_unity_thread,o->invoke_void};
 if(!raw_upload_rgba(&upload,c,x.texture,m->load,m->apply,rgba,size,(uint32_t)w,(uint32_t)h))goto fail;
 UrRect rect={0,0,(float)w,(float)h};UrVector pivot={px,py};void *args[]={x.texture,&rect,&pivot,&ppu};
 x.sprite=o->invoke_object(c,m->create,NULL,args);if(!x.sprite)goto fail;
 x.sprite_root=o->root(c,x.sprite);if(!x.sprite_root)goto fail;*out=x;return 1;
fail:*out=x;ur_release(o,c,out);return 0;
}
#endif
