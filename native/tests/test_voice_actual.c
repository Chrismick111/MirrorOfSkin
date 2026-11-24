#define main legacy_test_main
#include "test_camera_lifecycle.c"
#undef main
static void fake_change(void *v,void *n,uint8_t f,void *mi){(void)n;(void)f;(void)mi;((Obj*)v)->field[13]=(uintptr_t)desiredAppearance;}
int main(void){
 legacy_test_main(); reset(); memset(g_units,0,sizeof(g_units)); memset(g_rows,0,sizeof(g_rows));
 Unit *u=&g_units[0]; u->used=1;u->view=&view;u->baseApp=&app;u->skins[0].used=1;u->skins[0].app=&foreign;u->skins[0].row=0;
 g_rowCount=1;strcpy(g_rows[0].identity,"story_8378_Priest_BossAppearance");orig_changeAppearance=fake_change;
 desiredAppearance=&foreign;change_appearance_hook(&view,NULL,0,NULL);assert(u->voiceBoss==8378);
 desiredAppearance=&app;change_appearance_hook(&view,NULL,0,NULL);assert(u->voiceBoss==0);
 desiredAppearance=&foreign;change_appearance_hook(&view,NULL,0,NULL);assert(u->voiceBoss==8378);
 desiredAppearance=&foreign;change_appearance_hook(&view,NULL,0,NULL);assert(u->voiceBoss==8378);
 strcpy(g_rows[0].identity,"10201");change_appearance_hook(&view,NULL,0,NULL);assert(u->voiceBoss==10201);
 puts("PASS voice follows committed boss, base, repeated switch and nonboss owner");return 0;
}
