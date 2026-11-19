/* Play the player's authored timeline on the visible counterpart. The enemy
   prefab supplies the body and its own facing transform. Resolve sprite objects
   once while both prefabs are resident, before entering playback callbacks. */
#include "wedge_identity.h"
typedef struct {
 int role;
 const char *sourceName,*donorName,*sourceTexture,*donorTexture;
 float sourceRect[4],donorRect[4];
} WedgePose;
#include "wedge_pose_data.inc"
#define WEDGE_POSES (sizeof(wedge_poses)/sizeof(*wedge_poses))
typedef struct {void *source,*donor;uintptr_t sourceRoot,donorRoot;} WedgePair;
struct WedgePlayback {
 WedgePlayback *next;Unit *unit;Skin *skin;
 int role,active,frame,counts[50],attempts,retry,reverseS2;
 DWORD retryAfter;
 unsigned dispatched[50],painted[50];
 int part;
 void *renderer,*get,*set,*baseline,*last;
 uintptr_t baselineRoot;
 WedgePair poses[WEDGE_POSES];
};
static int wedge_read_name(void *getter,void *obj,char *out,int size){
 int ok=0;void *s=obj?call_obj(getter,obj,NULL,&ok):NULL;
 return ok&&string_ascii(s,out,size);
}
static int wedge_rect_equal(const float *a,const float *b){
 for(int i=0;i<4;i++)if(fabsf(a[i]-b[i])>.01f)return 0;
 return 1;
}
static int wedge_named_parts(void *app,int detail,const char *first,const char *second){
 uint8_t flag=0;void *args[]={&detail,&flag};int ok=0,actual=-1;
 g_motionDepth++;void *motion=call_obj(m_getMotion,app,args,&ok);g_motionDepth--;
 if(!ok||timeline_count(motion,&actual)!=2||actual!=detail)return 0;
 void *list=rfield(motion,"timelineAssets");char n[128];
 for(int i=0;i<2;i++){
  void *asset=list_item(list,i);
  void *name=asset?find_method(ui_class(asset),"get_name",0):NULL;
  if(!name||!wedge_read_name(name,asset,n,sizeof(n))||strcmp(n,i?second:first))return 0;
 }
 return 1;
}
static int wedge_missing(const WedgePlayback *w,int detail,int *required){
 int missing=0;*required=0;
 for(size_t j=0;j<sizeof(wedge_required)/sizeof(*wedge_required);j++){
  if(wedge_required[j].role!=w->role||wedge_required[j].detail!=detail)continue;
  (*required)++;int found=0;
  for(size_t i=0;i<WEDGE_POSES;i++)if(wedge_poses[i].role==w->role&&
     !strcmp(wedge_poses[i].sourceName,wedge_required[j].name)&&w->poses[i].source&&w->poses[i].donor){found=1;break;}
  if(!found)missing++;
 }
 return missing;
}
static void wedge_end(Skin *skin){
 WedgePlayback *w=skin?skin->wedge:NULL;if(!w||!w->active)return;
 w->active=0;
 if(w->baseline&&w->last&&rfield(w->renderer,"m_CachedPtr")){
  int ok=0;void *sprite=call_obj(w->get,w->renderer,NULL,&ok);
  if(ok&&sprite==w->last){void *args[]={w->baseline};call_exc(w->set,w->renderer,args);}
 }
 ui_unroot(w->baselineRoot);w->baselineRoot=0;w->baseline=w->last=NULL;
}
static void wedge_dispose(Skin *skin){
 WedgePlayback *w=skin->wedge;if(!w)return;
 WedgePlayback **p=&wedgeHead;while(*p&&*p!=w)p=&(*p)->next;if(*p)*p=w->next;
 wedge_end(skin);
 for(size_t i=0;i<WEDGE_POSES;i++){ui_unroot(w->poses[i].sourceRoot);ui_unroot(w->poses[i].donorRoot);}
 HeapFree(GetProcessHeap(),0,w);skin->wedge=NULL;
}
static void wedge_prepare(Unit *u,Skin *skin){
 int role=wedge_role(u->baseName,motion_identity(skin));
 if(!role)return;
 WedgePlayback *w=skin->wedge;
 if(!w){
  w=HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,sizeof(*w));if(!w)return;
  skin->wedge=w;w->unit=u;w->skin=skin;w->next=wedgeHead;wedgeHead=w;
 }
 w->role=role;w->attempts++;w->retry=w->attempts<3;w->retryAfter=GetTickCount()+15000;
 if(role==1583)w->reverseS2=wedge_named_parts(u->baseApp,8,"Outis_Oscar_S4_Timeline_2","Outis_Oscar_S4_Timeline_1")&&
                            wedge_named_parts(skin->app,10,"Oscar_S4_Timeline_1","Oscar_S4_Timeline_2");
 if(!m_findAll){bootlog("Wedge stock sprites: resource scan unavailable");return;}
 void *klass=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_core,"UnityEngine","Sprite");
 void *renderer=rfield(skin->app,"sprenderer_charactermotion");
 if(!klass||!renderer){bootlog("Wedge stock sprites: body renderer unavailable");return;}
 void *name=find_method(c_objectClass,"get_name",0),*texture=find_method(klass,"get_texture",0),*rect=find_method(klass,"get_rect",0);
 void *type=((void *(*)(void *))api[API_TYPE_OBJECT])(((void *(*)(void *))api[API_CLASS_TYPE])(klass));
 if(!name||!texture||!rect||!type){bootlog("Wedge stock sprites: sprite accessors unavailable");return;}
 int ok=0;void *args[]={type},*arr=call_obj(m_findAll,NULL,args,&ok);
 uintptr_t ar=ok?ui_root(arr):0;if(!ar){bootlog("Wedge stock sprites: resource scan unavailable");return;}
 w->role=role;w->renderer=renderer;w->get=find_method(ui_class(renderer),"get_sprite",0);w->set=find_method(ui_class(renderer),"set_sprite",1);
 uintptr_t count=*(uintptr_t *)((char*)arr+24);
 for(uintptr_t k=0;w->set&&w->get&&count<=1000000&&k<count;k++){
  void *sprite=((void**)((char*)arr+32))[k];char n[128],tn[256];int read=0;float bounds[4];
  if(!wedge_read_name(name,sprite,n,sizeof(n)))continue;
  for(size_t i=0;i<WEDGE_POSES;i++){
   const WedgePose *p=&wedge_poses[i];if(p->role!=role)continue;
   int source=!strcmp(n,p->sourceName),donor=!strcmp(n,p->donorName);
   if(!source&&!donor)continue;
   if(!read){
    void *t=call_obj(texture,sprite,NULL,&ok);
    if(!ok||!wedge_read_name(name,t,tn,sizeof(tn)))break;
    void *box=call_obj(rect,sprite,NULL,&ok);if(!ok||!box)break;
    const void *value=ui_unbox(box);if(!value)break;
    memcpy(bounds,value,sizeof(bounds));read=1;
   }
   WedgePair *pair=&w->poses[i];
   if(source&&!pair->sourceRoot&&!strcmp(tn,p->sourceTexture)&&wedge_rect_equal(bounds,p->sourceRect)){
    pair->sourceRoot=ui_root(sprite);if(pair->sourceRoot)pair->source=sprite;
   }
   if(donor&&!pair->donorRoot&&!strcmp(tn,p->donorTexture)&&wedge_rect_equal(bounds,p->donorRect)){
    pair->donorRoot=ui_root(sprite);if(pair->donorRoot)pair->donor=sprite;
   }
  }
 }
 ui_unroot(ar);w->retry=0;
 for(int d=0;d<50;d++)if(wedge_stock_detail(role,d)){
  int required=0,missing=wedge_missing(w,d,&required);
  int actual=-1,n=motion_count(u->baseApp,d,&actual);
  w->counts[d]=required&&!missing&&actual==d&&n>0?n:0;
  if(!w->counts[d])w->retry=w->attempts<3;
  char line[160];snprintf(line,sizeof(line),"Wedge stock role=%d detail=%d ready=%d resolved=%d/%d attempt=%d",role,d,w->counts[d],required-missing,required,w->attempts);bootlog(line);
 }
}
static Skin *wedge_selected(Unit *u,void *receiver,int detail,int index){
 if(!wedgeHead||(detail!=8&&detail!=9&&detail!=49)||!u||u->dead||u->switching||u->preserveSpecial||
    !enabled_now()||cleanup_pending||g_creating||g_motionDepth)return NULL;
 void *visible=rfield(u->view,"_curAppearance");
 if(receiver!=u->baseApp&&receiver!=visible)return NULL;
 Skin *skin=skin_for_app(u,visible);
 if(!skin||!skin->wedge||skin->row<0||(uint32_t)skin->row>=g_rowCount||
    wedge_role(u->baseName,motion_identity(skin))!=skin->wedge->role||
    skin->wedge->counts[detail]<=0||index>=skin->wedge->counts[detail])return NULL;
 return skin;
}
static void wedge_note(WedgePlayback *w,unsigned *seen,const char *event){
 unsigned bit=w->part>=0&&w->part<30?1u<<w->part:1u<<30;
 if(seen[w->active]&bit)return;
 seen[w->active]|=bit;
 char line[144];snprintf(line,sizeof(line),"Wedge stock %s role=%d detail=%d part=%d",event,w->role,w->active,w->part);bootlog(line);
}
static void wedge_begin(Skin *skin,int detail,int part){
 wedge_end(skin);
 WedgePlayback *w=skin->wedge;int ok=0;
 void *sprite=call_obj(w->get,w->renderer,NULL,&ok);
 if(ok&&sprite){w->baselineRoot=ui_root(sprite);if(w->baselineRoot)w->baseline=sprite;}
 w->active=detail;w->part=part;w->frame=g_frame;
 wedge_note(w,w->dispatched,"dispatch");
}
static void wedge_body(WedgePlayback *w){
 int ok=0;void *sprite=call_obj(w->get,w->renderer,NULL,&ok);
 if(!ok||!sprite||sprite==w->last)return;
 for(size_t i=0;i<WEDGE_POSES;i++)if(w->poses[i].source==sprite&&w->poses[i].donor){
  void *args[]={w->poses[i].donor};w->last=w->poses[i].donor;
  if(!call_exc(w->set,w->renderer,args))w->last=NULL;
  else wedge_note(w,w->painted,"body");
  return;
 }
}
static void wedge_tick(void){
 int retried=0;
 for(WedgePlayback *w=wedgeHead;w;w=w->next){
   Unit *u=w->unit;Skin *skin=w->skin;
   if(!w->active){
    if(w->retry&&!retried&&!u->dead&&!u->switching&&enabled_now()&&!cleanup_pending&&!g_anyViewerActive&&!g_presentationGate&&
       (LONG)(GetTickCount()-w->retryAfter)>=0&&rfield(u->view,"_curAppearance")==skin->app){
     w->retryAfter=GetTickCount()+15000;wedge_prepare(u,skin);retried=1;
    }
    continue;
   }
   if(u->dead||!enabled_now()||cleanup_pending||rfield(u->view,"_curAppearance")!=skin->app||
      (g_frame>w->frame+1&&!presentation_busy(skin->app)))wedge_end(skin);
   else wedge_body(w);
 }
}
