#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"
int main(void){
 Config cfg={0};g_cfg=&cfg;cfg.heartbeat=GetTickCount();cleanup_pending=1;
 assert(!resume_pending_cleanup()&&cleanup_pending==1);
 cfg.enabled=1;assert(resume_pending_cleanup()&&cleanup_pending==0);
 assert(!resume_pending_cleanup());cleanup_pending=1;cfg.heartbeat=GetTickCount()-4000;
 assert(!resume_pending_cleanup()&&cleanup_pending==1);cfg.heartbeat=GetTickCount();g_quitting=1;
 assert(!resume_pending_cleanup()&&cleanup_pending==1);
 puts("PASS disable then re-enable cancels pending cleanup; disabled, expired heartbeat and quit preserve cleanup");return 0;
}
