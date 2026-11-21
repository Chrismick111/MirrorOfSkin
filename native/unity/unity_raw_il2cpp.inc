/* Disabled integration draft: include after team_instance_method, team_returns
   and method_by_types_one are declared. Never run prepare off canvas thread. */
#include "unity_png_queue.h"
static void *ur_game_class(const char *full){
 const char *prefix="UnityEngine.";if(strncmp(full,prefix,strlen(prefix)))return NULL;
 return ((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_core,"UnityEngine",full+strlen(prefix));
}
/* Count exact matches instead of method_by_types_one's first-match policy. */
static void *ur_actual_exact(void *ctx,const char *class_name,const char *name,const char *const *types,int count,const char *ret,int is_static){
 (void)ctx;void *klass=ur_game_class(class_name);if(!klass)return NULL;
 void *it=NULL,*method,*matched=NULL;int hits=0;
 while((method=((void *(*)(void *,void **))api[API_METHODS])(klass,&it))){
  const char *method_name=((const char *(*)(void *))api[API_METHOD_NAME])(method);
  if(!method_name||strcmp(method_name,name)||(int)((uint32_t (*)(void *))api[API_PARAM_COUNT])(method)!=count)continue;
  int ok=1;for(int i=0;i<count;i++){void *p=((void *(*)(void *,uint32_t))api[API_PARAM])(method,(uint32_t)i);
   char *n=p?((char *(*)(void *))api[API_TYPE_NAME])(p):NULL;if(!n||strcmp(n,types[i]))ok=0;if(n)((void (*)(void *))api[API_FREE])(n);}
  if(ok&&team_returns(method,ret)&&(is_static?linked_is_static(klass,method):team_instance_method(klass,method))){matched=method;hits++;}
 }
 return hits==1?matched:NULL;
}
static int ur_actual_thread(void *ctx){(void)ctx;return ur_in_canvas!=0;}
static void *ur_actual_new(void *ctx,const char *class_name){(void)ctx;return ui_new(ur_game_class(class_name));}
static uintptr_t ur_actual_root(void *ctx,void *obj){(void)ctx;return ui_root(obj);}
static void ur_actual_unroot(void *ctx,uintptr_t root){(void)ctx;ui_unroot(root);}
static int ur_actual_void(void *ctx,void *method,void *instance,void **args){(void)ctx;return call_exc(method,instance,args);}
static void *ur_actual_object(void *ctx,void *method,void *instance,void **args){(void)ctx;int ok=0;void *obj=call_obj(method,instance,args,&ok);return ok?obj:NULL;}
static int ur_actual_destroy(void *ctx,void *obj){(void)ctx;void *args[]={obj};int ok=m_destroyObject&&call_exc(m_destroyObject,NULL,args);if(!ok)bootlog("raw factory destroy failed; root retained for retry");return ok;}
static const UrOps ur_actual_ops={ur_actual_exact,ur_actual_thread,ur_actual_new,ur_actual_root,ur_actual_unroot,ur_actual_void,ur_actual_object,ur_actual_destroy};
static int ur_rgba32_value(int *value){
 void *klass=ur_game_class("UnityEngine.TextureFormat");void *field=klass?((void *(*)(void *,const char *))api[API_FIELD])(klass,"RGBA32"):NULL;
 void *ft=field?((void *(*)(void *))api[API_FIELD_TYPE])(field):NULL;char *name=ft?((char *(*)(void *))api[API_TYPE_NAME])(ft):NULL;
 int typeok=name&&!strcmp(name,"UnityEngine.TextureFormat");if(name)((void (*)(void *))api[API_FREE])(name);if(!typeok)return 0;
 void *boxed=((void *(*)(void *,void *))api[API_FIELD_VALUE])(field,NULL);uintptr_t root=boxed?ui_root(boxed):0;
 void *p=root?ui_unbox(boxed):NULL;int ok=p!=NULL;if(ok)*value=*(int32_t*)p;if(root)ui_unroot(root);return ok;
}
static int ur_actual_prepare(UrMethods *methods){int format=0;return ur_in_canvas&&ur_rgba32_value(&format)&&ur_resolve(&ur_actual_ops,NULL,format,1,methods);}
