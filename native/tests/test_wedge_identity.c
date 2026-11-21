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
 }
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
