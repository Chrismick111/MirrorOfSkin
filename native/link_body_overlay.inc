/* The Animator owns the original renderer. A child at its local origin can
   display one attack for the whole coin even when the original is resampled
   after the canvas. All game callbacks still see the original renderer. */
enum { OVERLAY_FLAGS=6 };
static struct {
 void *klass,*ctor,*add,*type,*setLayer,*getLayer,*force,*setForce,*enabled,*setEnabled;
 void *material,*setMaterial,*get[OVERLAY_FLAGS],*set[OVERLAY_FLAGS];
 uintptr_t typeRoot;
 int attempted,ready;
} overlayApi;
typedef struct {
 void *source,*go,*renderer,*last,*lastMaterial;
 uintptr_t goRoot,rendererRoot;
 uint8_t values[OVERLAY_FLAGS][16],known[OVERLAY_FLAGS];
 int attempted,hidden,visible,frames,failed,poseChanges;
} LinkOverlay;
static LinkOverlay linkOverlays[8];
static const unsigned overlayWidths[OVERLAY_FLAGS]={1,1,4,4,16,4};
static int link_overlay_set(void *method,void *obj,void *value){
 void *a[]={value};return call_exc(method,obj,a);
}
static int link_overlay_api(void){
 if(overlayApi.attempted)return overlayApi.ready;
 overlayApi.attempted=1;
 void *sr=unity_class_anywhere("UnityEngine","SpriteRenderer"),*go=unity_class_anywhere("UnityEngine","GameObject");
 if(!sr||!go||!m_setParent||!m_destroyObject)return 0;
 const char *strType[]={"System.String"},*typeType[]={"System.Type"};
 overlayApi.klass=go;overlayApi.ctor=method_by_types_one(go,".ctor",strType,1);overlayApi.add=method_by_types_one(go,"AddComponent",typeType,1);
 overlayApi.type=((void *(*)(void *))api[API_TYPE_OBJECT])(((void *(*)(void *))api[API_CLASS_TYPE])(sr));
 overlayApi.typeRoot=ui_root(overlayApi.type);
 overlayApi.getLayer=find_method(go,"get_layer",0);overlayApi.setLayer=find_method(go,"set_layer",1);
 overlayApi.force=find_method(sr,"get_forceRenderingOff",0);overlayApi.setForce=find_method(sr,"set_forceRenderingOff",1);
 overlayApi.enabled=find_method(sr,"get_enabled",0);overlayApi.setEnabled=find_method(sr,"set_enabled",1);
 overlayApi.material=find_method(sr,"get_sharedMaterial",0);overlayApi.setMaterial=find_method(sr,"set_sharedMaterial",1);
 const char *properties[]={"flipX","flipY","sortingLayerID","sortingOrder","color","maskInteraction"};
 for(unsigned i=0;i<OVERLAY_FLAGS;i++){
  char name[50];snprintf(name,sizeof(name),"get_%s",properties[i]);overlayApi.get[i]=find_method(sr,name,0);
  snprintf(name,sizeof(name),"set_%s",properties[i]);overlayApi.set[i]=find_method(sr,name,1);
  /* Mask interaction is optional on builds that strip the masking API. */
  if(i<OVERLAY_FLAGS-1&&(!overlayApi.get[i]||!overlayApi.set[i]))return 0;
 }
 overlayApi.ready=overlayApi.typeRoot&&overlayApi.ctor&&overlayApi.add&&overlayApi.getLayer&&overlayApi.setLayer&&
  overlayApi.force&&overlayApi.setForce&&overlayApi.enabled&&overlayApi.setEnabled&&overlayApi.material&&overlayApi.setMaterial;
 return overlayApi.ready;
}
static int link_overlay_create(LinkOverlay *layer,LinkVisualOwner *owner){
 layer->attempted=1;layer->source=owner->renderer;
 if(!link_overlay_api())return 0;
 void *parent=body_get(layer->source,"get_transform"),*sourceGo=body_get(layer->source,"get_gameObject");
 if(!parent||!sourceGo)return 0;
 void *name=make_string("Workbench Link Body Display");uintptr_t label=ui_root(name);
 layer->go=ui_new(overlayApi.klass);layer->goRoot=ui_root(layer->go);
 int ok=label&&layer->goRoot&&link_overlay_set(overlayApi.ctor,layer->go,name);ui_unroot(label);
 if(!ok)return 0;
 void *tr=body_get(layer->go,"get_transform");uint8_t keepWorld=0;void *p[]={parent,&keepWorld};
 int sceneLayer=call_int(overlayApi.getLayer,sourceGo,NULL);
 if(!tr||!call_exc(m_setParent,tr,p)||sceneLayer<0||!link_overlay_set(overlayApi.setLayer,layer->go,&sceneLayer))return 0;
 void *a[]={overlayApi.type};layer->renderer=call_obj(overlayApi.add,layer->go,a,&ok);
 layer->rendererRoot=ok?ui_root(layer->renderer):0;
 uint8_t off=0;return layer->rendererRoot&&link_overlay_set(overlayApi.setEnabled,layer->renderer,&off);
}
static int link_overlay_style(LinkOverlay *layer){
 int ok=0;void *material=call_obj(overlayApi.material,layer->source,NULL,&ok);
 if(!ok||!material)return 0;
 if(layer->lastMaterial!=material){
  if(!link_overlay_set(overlayApi.setMaterial,layer->renderer,material))return 0;
  layer->lastMaterial=material;
 }
 for(unsigned i=0;i<OVERLAY_FLAGS;i++){
  if(!overlayApi.get[i]||!overlayApi.set[i])continue;
  void *box=call_obj(overlayApi.get[i],layer->source,NULL,&ok);
  void *v=ok&&box?ui_unbox(box):NULL;if(!v)return 0;
  size_t n=overlayWidths[i];if(layer->known[i]&&!memcmp(layer->values[i],v,n))continue;
  uint8_t value[16];memcpy(value,v,n);
  if(!link_overlay_set(overlayApi.set[i],layer->renderer,value))return 0;
  memcpy(layer->values[i],value,n);layer->known[i]=1;
 }
 return 1;
}
static void link_overlay_hide(LinkOverlay *layer){
 uint8_t off=0;
 if(layer->visible&&link_overlay_set(overlayApi.setEnabled,layer->renderer,&off))layer->visible=0;
 if(layer->hidden&&link_overlay_set(overlayApi.setForce,layer->source,&off))layer->hidden=0;
}
static int link_overlay_show(LinkOverlay *layer,LinkVisualOwner *owner){
 if(!layer->rendererRoot||call_bool(overlayApi.enabled,layer->source,NULL)!=1)return 0;
 int forced=call_bool(overlayApi.force,layer->source,NULL);
 if(forced<0||(forced&&!layer->hidden))return 0;
 if(!link_overlay_style(layer))return 0;
 if(layer->last!=owner->last){
  if(!link_overlay_set(owner->setter,layer->renderer,owner->last))return 0;
  layer->last=owner->last;layer->poseChanges++;
 }
 uint8_t on=1;
 if(!layer->visible){
  if(!link_overlay_set(overlayApi.setEnabled,layer->renderer,&on))return 0;
  layer->visible=1;
 }
 if(!forced){
  if(!link_overlay_set(overlayApi.setForce,layer->source,&on))return 0;
  layer->hidden=1;
 }
 layer->frames++;return 1;
}
static void link_overlay_tick(void){
 LinkVisualScene *s=&linkVisual;
 if(s->ensembleSize<2||!link_visual_live())return;
 for(unsigned i=0;i<s->ownerCount;i++){
  LinkVisualOwner *o=&s->owners[i];LinkOverlay *layer=&linkOverlays[i];
  if(!o->engaged||!o->lastRoot||!o->rendererRoot){link_overlay_hide(layer);continue;}
  if(!layer->attempted&&!link_overlay_create(layer,o))layer->failed=1;
  if(!layer->failed&&!link_overlay_show(layer,o))link_overlay_hide(layer);
 }
}
static void link_overlay_end(void){
 for(unsigned i=0;i<8;i++){
  LinkOverlay *layer=&linkOverlays[i];if(!layer->attempted)continue;
  link_overlay_hide(layer);
  if(layer->goRoot)link_sampler_destroy(layer->go);
  char line[200];snprintf(line,sizeof(line),"link body overlay owner=%d frames=%d unavailable=%d submittedPoses=%d scene=%.90s",linkVisual.owners[i].id,layer->frames,layer->failed,layer->poseChanges,linkVisual.coinAsset);bootlog(line);
  ui_unroot(layer->rendererRoot);ui_unroot(layer->goRoot);
  memset(layer,0,sizeof(*layer));
 }
}
