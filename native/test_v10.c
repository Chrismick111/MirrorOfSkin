#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"
static void *fake_invoke(void *m,void *o,void **a,void **e){(void)m;(void)o;(void)a;*e=NULL;return NULL;}
static void *fake_exception(void *m,void *o,void **a,void **e){(void)m;(void)o;(void)a;*e=(void *)1;return NULL;}
int main(void){
 static void *table[37];api=table;table[API_INVOKE]=fake_invoke;
 assert(call_exc((void *)1,NULL,NULL)==1);
 int ok=1;assert(call_obj((void *)1,NULL,NULL,&ok)==NULL && !ok);
 assert(!call_exc(NULL,NULL,NULL));table[API_INVOKE]=fake_exception;assert(!call_exc((void *)1,NULL,NULL));
 memset(g_units,0,sizeof(g_units));memset(g_rows,0,sizeof(g_rows));
 Unit *u=&g_units[0];u->used=1;u->sinner=101;u->ncand=2;u->cand[0]=0;u->cand[1]=1;
 g_rows[0]=(PoolRow){.sinner=101,.enabled=1,.weight=1};g_rows[1]=(PoolRow){.sinner=101,.enabled=1,.weight=3};
 int counts[2]={0};for(int i=0;i<10000;i++)counts[unit_draw(u,2,(i+.5)/10000.)]++;
 assert(counts[0]==2500 && counts[1]==7500);
 g_rows[0].excluded=1;assert(unit_draw(u,1,0)==1);
 assert(sizeof(Config)==2688 && sizeof(PoolRow)==280);
 g_rowCount=2;m_loadGO=(void *)1;
 q_head=q_tail=0;g_loadActive=1;g_loadUnit=u;g_loadRow=0;
 queue_push(u,0);assert(q_head==q_tail);
 queue_push(u,1);queue_push(u,1);assert(q_tail==1);
 g_loadActive=0;u->skins[0].used=1;u->skins[0].row=1;
 assert(loader_start(u,1)==1 && g_loadActive==0);
 mark_bad(u,1);mark_bad(u,1);assert(u->nbad==1 && unit_draw(u,2,.9)==0);
 Config cfg={0};cfg.max_skins=2;g_cfg=&cfg;assert(skin_limit()==2);
 cfg.max_skins=99;assert(skin_limit()==SR_SKIN_MAX);
 puts("PASS production semantics, weights, in-flight/queued/cached dedup, bad-row filtering and cache limits");
}
