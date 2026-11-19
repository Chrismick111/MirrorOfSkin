#undef NDEBUG
#define main test_existing_voice_dispatch
#include "test_voice_dispatch.c"
#undef main
#ifdef NDEBUG
#error This regression test requires assertions
#endif

static uint8_t original_match;
static void *original_target;
static uint8_t stock_match(void *app,int id,uint8_t flag,void *mi){return original_match;}
static void *stock_resolve(void *app,int id,void *mi){return original_target;}
static void *drawn,*expectedReceiver,*expectedBase;
static int expectedDetail,expectedPart,motionCalls,metadataCalls;
static void *sprite_io(void *method,void *o,void **args,void **exc){
 assert(o&&exc);
 if(method==(void*)1)return drawn;
 assert(method==(void*)2);drawn=args[0];return NULL;
}
static void *stock_motion_lookup(void *app,int detail,uint8_t flag,void *mi){
 assert(app==expectedBase&&detail==expectedDetail&&flag==1&&mi==(void*)5);return (void*)7;
}
static void *stock_item(void *ret,void *app,int src,int donor,int part,int srcPart,uint8_t last,void *mi){
 assert(app==expectedBase&&src==expectedDetail&&donor==src&&part==expectedPart&&srcPart==part&&last==1&&mi==(void*)5);
 metadataCalls++;return ret;
}
static void stock_change(void *app,int detail,uint8_t a1,int index,uint8_t a3,void *cb,uint8_t a5,void *mi){
 assert(app==expectedReceiver&&detail==expectedDetail&&index==expectedPart&&a1==1&&a3==2&&a5==3&&cb==(void*)4&&mi==(void*)5);
 assert(get_motion_hook(app,detail,1,mi)==(void*)7);
 assert(motion_anim_item_hook(cb,app,detail,detail,index,index,1,mi)==cb);
 motionCalls++;
}
static void check_native_sequences(Unit *u,TestView *v){
 static TestView renderer;renderer.cached=&renderer;
 WedgePlayback w={0};Skin *s=&u->skins[0];
 api[API_INVOKE]=sprite_io;api[API_ROOT]=root_stub;api[API_UNROOT]=unroot_stub;
 orig_changeMotion=stock_change;orig_getMotion=stock_motion_lookup;orig_motionAnimItem=stock_item;
 w.renderer=&renderer;w.get=(void*)1;w.set=(void*)2;s->wedge=&w;wedgeHead=&w;w.unit=u;w.skin=s;
 w.role=wedge_role(u->baseName,motion_identity(s));assert(w.role>=1583&&w.role<=1585);
 if(w.role==1583){w.reverseS2=1;
  assert(counterpart_part(u,s,NULL,0,8,2,0,0)==1);
  assert(counterpart_part(u,s,NULL,1,8,2,1,1)==0);
 }
 for(size_t i=0;i<WEDGE_POSES;i++){w.poses[i].source=(void*)(i+128);w.poses[i].donor=(void*)(i+512);}
 for(int d=0;d<50;d++)if(wedge_stock_detail(w.role,d)){
  int required=0;assert(wedge_missing(&w,d,&required)==0&&required>0);
  int omitted=0;
  for(size_t i=0;i<WEDGE_POSES;i++){void *prior=w.poses[i].donor;w.poses[i].donor=NULL;
   int missing=wedge_missing(&w,d,&required);w.poses[i].donor=prior;
   if(missing){assert(missing==1);omitted=1;break;}
  }
  assert(omitted);
  w.counts[d]=d==8?2:1;expectedBase=u->baseApp;expectedReceiver=s->app;expectedDetail=d;
  for(int k=0;k<w.counts[d];k++){
   expectedPart=k;drawn=(void*)10;
   /* Both entry paths must retain the source slot even after a tentative generic remap. */
   void *receiver=k?u->baseApp:s->app;
   g_projection=(ProjectionContext){s->app,10,0,-1};
   forward_projected_motion(receiver,10,1,1-k,2,(void*)4,3,(void*)5,d,k,k,1);
   assert(g_projection.app==s->app);g_projection=(ProjectionContext){0};
   assert(w.active==d);
   drawn=w.poses[0].source;wedge_body(&w);assert(drawn==w.poses[0].donor);
   playback_begin(s->app);assert(drawn==(void*)10&&!w.active&&!roots);
   assert(!wedge_selected(u,(void*)5,d,k)&&!wedge_selected(u,s->app,d,w.counts[d]));
  }
 }
 assert(!wedge_selected(u,s->app,10,0));v->appearance=u->baseApp;
 assert(!wedge_selected(u,s->app,49,0));v->appearance=s->app;s->wedge=NULL;wedgeHead=NULL;
}

int main(void){
 if(test_existing_voice_dispatch()!=0)return 1;
 memset(g_units,0,sizeof(g_units));
 static void *functions[37];api=functions;
 functions[API_OBJECT_CLASS]=object_class;functions[API_PARENT]=no_parent;
 functions[API_FIELD]=field_named;functions[API_FIELD_OFFSET]=field_offset;
 Config config={0};config.enabled=1;config.heartbeat=GetTickCount();g_cfg=&config;
 orig_link_matches=stock_match;orig_link_resolve=stock_resolve;
 int base[4],look[4];TestView view[4]={0};g_rowCount=3;
 for(int i=0;i<3;i++){
  const char *id=wedge_pairs[i].appearance;
  Unit *u=&g_units[i];u->used=1;u->baseApp=&base[i];u->view=&view[i];
  view[i].appearance=&look[i];strcpy(u->baseName,wedge_pairs[i].base);
  Skin *s=&u->skins[0];s->used=1;s->app=&look[i];s->row=i;strcpy(s->look,id+6);
  strcpy(g_rows[i].identity,id);strcpy(g_rows[i].appearance_name,id+6);
  assert(linked_matches_hook(&look[i],wedge_pairs[i].role,0,NULL));
  assert(!linked_matches_hook(&look[i],999,0,NULL));
  assert(linked_resolve_hook(&look[0],wedge_pairs[i].role,NULL)==&look[i]);
  check_native_sequences(u,&view[i]);
 }
 assert(motionCalls==6&&metadataCalls==6);
 original_target=&base[3];assert(linked_resolve_hook(&look[0],1583,NULL)==original_target);original_target=NULL;
 original_match=1;assert(linked_matches_hook(NULL,999,0,NULL));original_match=0;
 strcpy(g_units[0].skins[0].look,"8380_SanchoAppearance");
 assert(!linked_matches_hook(&look[0],1583,0,NULL));
 assert(!linked_resolve_hook(&look[0],1584,NULL));
 view[0].appearance=&base[0];assert(linked_resolve_hook(&base[0],1584,NULL)==&look[1]);
 g_units[3]=g_units[1];assert(!linked_resolve_hook(&base[0],1584,NULL));
 g_units[3].used=0;g_units[1].dead=1;assert(!linked_resolve_hook(&base[0],1584,NULL));
 puts("Matched Wedge identities and stock resolution passed");
 return 0;
}
