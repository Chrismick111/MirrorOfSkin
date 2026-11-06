#define main legacy_test_main
#include "test_camera_lifecycle.c"
#undef main
static void empty_end(void *app,void *director,void *mi){}
static void reentrant_end(void *app,void *director,void *mi){playback_begin(app);}
int main(void){
 legacy_test_main();reset();memset(g_units,0,sizeof(g_units));
 Unit *u=&g_units[0];u->used=1;u->view=&view;u->baseApp=&app;
 app.field[18]=(uintptr_t)&owner;view.field[13]=(uintptr_t)&app;
 PendingMotion m={0};m.source=&app;m.coin=0;m.action=&manager;
 g_presentationGate=0;orig_endTimeline=empty_end;
 assert(!motion_completed_tail(u,&m,&app,8));
 timeline_end_hook(&app,&owner,NULL);
 assert(motion_completed_tail(u,&m,&app,8)); /* first/single coin */
 assert(!(u->deliveredValid && u->deliveredApp==m.source && m.action && u->deliveredAction==m.action && m.coin>u->deliveredCoin && u->observedAction==m.action && u->observedViewer)); /* v55 predicate rejects this exact fixture. */
 assert(!motion_completed_tail(u,&m,&foreign,8));
 for(int mask=9;mask<16;mask++)assert(!motion_completed_tail(u,&m,&app,mask));
 g_presentationGate=1;assert(!motion_completed_tail(u,&m,&app,8));g_presentationGate=0;
 app.field[18]=(uintptr_t)&foreign;assert(!motion_completed_tail(u,&m,&app,8));app.field[18]=(uintptr_t)&owner;
 playback_begin(&app);assert(!motion_completed_tail(u,&m,&app,8));
 orig_endTimeline=reentrant_end;timeline_end_hook(&app,&owner,NULL);assert(!motion_completed_tail(u,&m,&app,8));
 orig_endTimeline=empty_end;app.field[16]=(uintptr_t)&manager;timeline_end_hook(&app,&owner,NULL);assert(!motion_completed_tail(u,&m,&app,8));
 puts("PASS first/single coin completed director handoff; live flags/camera/wrong director/reentrant/new playback reject stale evidence");
 return 0;
}

