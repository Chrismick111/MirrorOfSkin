/* Direct fallback for clips whose body Sprite keys have been read from the installed game's
   packed atlas. Each atlas lookup returns a new Unity Sprite; destroy only these owned copies. */
#include "link_sprite_curves.h"
static void *unity_class_anywhere(const char *,const char *);
#define LINK_SPRITE_COUNT (sizeof(link_sprite_keys)/sizeof(*link_sprite_keys))
static struct {void *sprite;uintptr_t root;int tried;} link_sprite_cache[LINK_SPRITE_COUNT];
static void *link_atlases,*link_get_sprite,*link_get_rect,*link_get_texture,*link_get_name;
static void *link_sprite_class,*link_get_named_sprites,*link_get_sprite_count;
static uintptr_t link_atlas_root;
static int link_atlas_ready;

static int link_frame_key(const char *look,const char *clip,double t){
 if(!look||!clip||!isfinite(t)||t<0)return -1;
 if(!strncmp(look,"story_",6))look+=6;
 for(unsigned i=0;i<sizeof(link_sprite_curves)/sizeof(*link_sprite_curves);i++){
  if(strcmp(look,link_sprite_curves[i].look)||strcmp(clip,link_sprite_curves[i].animation))continue;
  int start=link_sprite_curves[i].first,end=start+link_sprite_curves[i].count;
  for(int j=end-1;j>=start;j--)if(t>=link_sprite_samples[j].t)return link_sprite_samples[j].key;
 }
 return -1;
}
static int link_read_name(void *obj,char *out,int cap){
 int ok=0;void *boxed=obj&&link_get_name?call_obj(link_get_name,obj,NULL,&ok):NULL;
 return ok&&boxed&&string_ascii(boxed,out,cap);
}
static int link_matches_key(void *sprite,const LinkSpriteKey *key){
 if(!sprite||!link_get_texture||!link_get_rect)return 0;
 int ok=0;
 void *tex=call_obj(link_get_texture,sprite,NULL,&ok);
 char name[256];
 if(!ok||!link_read_name(tex,name,sizeof(name))||strcmp(name,key->texture))return 0;
 void *box=call_obj(link_get_rect,sprite,NULL,&ok);
 const float *rect=ok&&box?(const float *)ui_unbox(box):NULL;
 if(!rect)return 0;
 for(int i=0;i<4;i++)if(fabsf(rect[i]-key->rect[i])>.01f)return 0;
 return 1;
}
static void *link_atlas_int_method(void *atlasClass,const char *name,const char **types,int count){
 void *method=method_by_types_one(atlasClass,name,types,count);
 return method&&team_instance_method(atlasClass,method)&&team_returns(method,"System.Int32")?method:NULL;
}
static void link_find_atlases(void){
 if(link_atlas_ready)return;
 link_atlas_ready=1;
 void *ak=unity_class_anywhere("UnityEngine.U2D","SpriteAtlas");
 void *sk=unity_class_anywhere("UnityEngine","Sprite");
 void *uk=unity_class_anywhere("UnityEngine","Object");
 if(!ak||!sk||!uk||!m_findAll||!m_destroyObject)return;
 link_get_name=find_method(uk,"get_name",0);
 link_get_sprite=find_method(ak,"GetSprite",1);
 link_get_texture=find_method(sk,"get_texture",0);
 link_get_rect=find_method(sk,"get_rect",0);
 const char *types[]={"UnityEngine.Sprite[]","System.String"};
 link_sprite_class=sk;
 link_get_named_sprites=link_atlas_int_method(ak,"GetSprites",types,2);
 if(!link_get_named_sprites)link_get_named_sprites=link_atlas_int_method(ak,"GetSpritesWithNameScripting",types,2);
 link_get_sprite_count=link_atlas_int_method(ak,"get_spriteCount",NULL,0);
 if(!link_get_name||!link_get_sprite||!link_get_texture||!link_get_rect)return;
 void *type=((void *(*)(void *))api[API_TYPE_OBJECT])(((void *(*)(void *))api[API_CLASS_TYPE])(ak));
 uintptr_t tr=type?ui_root(type):0;if(!tr)return;
 void *args[]={type};int ok=0;
 void *array=call_obj(m_findAll,NULL,args,&ok);
 link_atlas_root=ok&&array?ui_root(array):0;ui_unroot(tr);
 if(link_atlas_root)link_atlases=array;
}
static void link_destroy_sprite_copy(void *sprite){
 void *args[]={sprite};call_exc(m_destroyObject,NULL,args);
}
static int link_keep_owned_sprite(int k,void *sprite){
 uintptr_t root=ui_root(sprite);
 if(root&&link_matches_key(sprite,&link_sprite_keys[k])){
  link_sprite_cache[k].sprite=sprite;link_sprite_cache[k].root=root;
  return 1;
 }
 link_destroy_sprite_copy(sprite);ui_unroot(root);return 0;
}
static void link_named_sprite_copies(int k,void *atlas,void *name){
 if(!link_get_named_sprites||!link_get_sprite_count||!api[API_ARRAY_NEW])return;
 int ok=0;
 void *boxed=call_obj(link_get_sprite_count,atlas,NULL,&ok);
 int *size=ok&&boxed?(int*)ui_unbox(boxed):NULL;
 if(!size||*size<=0||*size>4096)return;
 int capacity=*size;
 void *array=((void *(*)(void *,uintptr_t))api[API_ARRAY_NEW])(link_sprite_class,(uintptr_t)capacity);
 uintptr_t arrayRoot=ui_root(array);
 if(!arrayRoot)return;
 void *args[]={array,name};
 boxed=call_obj(link_get_named_sprites,atlas,args,&ok);
 int *written=ok&&boxed?(int*)ui_unbox(boxed):NULL;
 int count=written&&*written>=0&&*written<=capacity?*written:0;
 /* An exception can leave a partly populated output array. Every populated slot
    is an owned clone, including those following the selected match. */
 void **copies=(void**)((char*)array+32);
 for(int i=0;i<capacity;i++){
  if(!copies[i])continue;
  if(i<count&&!link_sprite_cache[k].sprite)link_keep_owned_sprite(k,copies[i]);
  else link_destroy_sprite_copy(copies[i]);
 }
 ui_unroot(arrayRoot);
}
static void *link_exact_key(int k,void *current){
 if(k<0||(size_t)k>=LINK_SPRITE_COUNT)return NULL;
 if(link_sprite_cache[k].sprite)return link_sprite_cache[k].sprite;
 link_find_atlases();
 const LinkSpriteKey *key=&link_sprite_keys[k];
 char name[256];
 if(current&&link_read_name(current,name,sizeof(name))&&!strcmp(name,key->name)&&link_matches_key(current,key))return current;
 if(link_sprite_cache[k].tried||!link_atlases)return NULL;
 link_sprite_cache[k].tried=1;
 uintptr_t n=*(uintptr_t*)((char*)link_atlases+24);if(n>4096)return NULL;
 void *arg=make_string(key->name);uintptr_t sr=arg?ui_root(arg):0;if(!sr)return NULL;
 void *args[]={arg};
 for(uintptr_t i=0;i<n;i++){
  void *atlas=((void**)((char*)link_atlases+32))[i];
  if(!link_read_name(atlas,name,sizeof(name))||strcmp(name,key->atlas))continue;
  int ok=0;
  void *sprite=call_obj(link_get_sprite,atlas,args,&ok);
  if(ok&&sprite&&link_keep_owned_sprite(k,sprite))break;
  link_named_sprite_copies(k,atlas,arg);
  if(link_sprite_cache[k].sprite)break;
 }
 ui_unroot(sr);
 return link_sprite_cache[k].sprite;
}
static void *link_exact_sprite(const char *look,const char *clip,double t,void *current){
 return link_exact_key(link_frame_key(look,clip,t),current);
}
static void link_exact_clear(void){
 for(unsigned i=0;i<LINK_SPRITE_COUNT;i++){
  if(link_sprite_cache[i].sprite)link_destroy_sprite_copy(link_sprite_cache[i].sprite);
  ui_unroot(link_sprite_cache[i].root);
 }
 memset(link_sprite_cache,0,sizeof(link_sprite_cache));
 ui_unroot(link_atlas_root);link_atlas_root=0;link_atlases=NULL;link_atlas_ready=0;
}
