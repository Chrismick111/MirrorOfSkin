#define main legacy_test_main
#include "test_camera_lifecycle.c"
#undef main
int main(void){
 legacy_test_main();reset();memset(g_units,0,sizeof(g_units));memset(g_rows,0,sizeof(g_rows));
 static Config cfg;cfg.enabled=1;cfg.heartbeat=GetTickCount();g_cfg=&cfg;
 Unit *u=&g_units[0];u->used=1;u->view=&view;u->baseApp=&app;strcpy(u->baseName,"10102_YiSang_7Appearance");
 u->skins[0].used=1;u->skins[0].app=&foreign;u->skins[0].row=0;g_rowCount=1;
 strcpy(g_rows[0].identity,"story_8378_Priest_BossAppearance");view.field[13]=(uintptr_t)&foreign;
 assert(base_bubble_suppressed(10102));assert(!base_bubble_suppressed(8378));assert(!base_bubble_suppressed(101));
 Unit *v=&g_units[1];*v=*u;assert(!base_bubble_suppressed(10102));memset(v,0,sizeof(*v));
 strcpy(g_rows[0].identity,"10102");assert(!base_bubble_suppressed(10102));
 strcpy(g_rows[0].identity,"story_8378_Priest_BossAppearance");view.field[13]=(uintptr_t)&app;assert(!base_bubble_suppressed(10102));
 cfg.enabled=0;assert(!base_bubble_suppressed(10102));u->used=0;cfg.enabled=1;assert(!base_bubble_suppressed(10102));
 puts("PASS base bubble suppression only for unique replaced unit; donor/base/disabled pass");return 0;
}
