#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"
static int forwarded;
static void quit_native(void *mi){assert(mi==(void *)123);assert(g_quitting);assert(!enabled_now());tick();forwarded++;}
int main(void){Config c={0};c.enabled=1;c.heartbeat=GetTickCount();g_cfg=&c;assert(enabled_now());orig_applicationQuit=quit_native;application_quit_hook((void *)123);assert(forwarded==1&&!enabled_now());puts("PASS quit forwards exactly once; disables work before native teardown; tick exits without invoking Unity");return 0;}
