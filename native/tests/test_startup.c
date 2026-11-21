#define main legacy_test_main
#include "test_camera_lifecycle.c"
#undef main
int main(void){
 legacy_test_main();reset();memset(g_units,0,sizeof(g_units));memset(g_rows,0,sizeof(g_rows));
 static Config cfg;cfg.enabled=1;cfg.heartbeat=GetTickCount();g_cfg=&cfg;g_ready=1;g_anyViewerActive=0;g_presentationGate=0;
 Unit *u=&g_units[0];u->used=1;u->sinner=101;u->view=&view;u->baseApp=&app;u->startupPending=1;u->startupRow=-1;u->wanted=-1;u->last=-1;
 u->ncand=2;u->cand[0]=0;u->cand[1]=1;g_rowCount=2;
 g_rows[0]=(PoolRow){.sinner=101,.enabled=1,.weight=0};g_rows[1]=(PoolRow){.sinner=101,.enabled=1,.weight=1};
 q_head=q_tail=0;startup_select(u);assert(u->startupRow==1&&q_head!=q_tail&&q_row[q_head]==1);
 startup_pool_changed(u);assert(u->startupRow==-1);
 u->startupRow=999999;assert(!startup_row_valid(u,u->startupRow));startup_select(u);assert(u->startupRow==1);
 g_rows[1].enabled=0;assert(!startup_row_valid(u,1));g_rows[1].enabled=1;
 u->bad[0]=1;u->nbad=1;g_rows[0].weight=1;q_head=q_tail=0;startup_select(u);assert(u->startupRow==0&&q_row[q_head]==0);
 Unit *v=&g_units[1];*v=*u;v->startupRow=1;v->bad[0]=0;v->sinner=101;
 g_rows[1].weight=1;queue_push(v,1);Unit *picked;int row;
 assert(queue_pop(&picked,&row)&&picked==u&&row==0);
 assert(queue_pop(&picked,&row)&&picked==v&&row==1);
 u->viewerActive=1;startup_select(u);assert(!u->startupPending);
 puts("PASS weighted startup selection, priority queue and viewer cancellation");return 0;
}
