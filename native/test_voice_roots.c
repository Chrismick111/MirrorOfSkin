#define main legacy_test_main
#include "test_camera_lifecycle.c"
#undef main
int main(void){
 legacy_test_main();reset();sr_voice_clear();roots=0;
 assert(sr_voice_request(&view,8378,"OnDie_View"));assert(g_voicePendingCount==1&&roots==1);
 assert(!sr_voice_request(&view,8378,"OnDie_View"));assert(g_voicePendingCount==1&&roots==1);
 sr_voice_clear();assert(g_voicePendingCount==0&&roots==0);
 assert(sr_voice_request(&view,8378,"OnDie_View"));assert(roots==1);sr_voice_clear();assert(roots==0);
 const char *ambiguous[]={"OnRoundStart_View","OnEndBehaviour_View"};
 assert(!sr_voice_request_any(&view,1079,ambiguous,2));assert(g_voicePendingCount==0&&roots==0);
 const char *duplicate[]={"OnDie_View","OnRoundStart_View"};
 assert(sr_voice_request_any(&view,1135,duplicate,2));
 assert(!sr_voice_request_any(&view,1135,duplicate,2));assert(g_voicePendingCount==1);sr_voice_clear();assert(roots==0);
 assert(sr_voice_cancel_for_appearance("OnRoundStart_View",0));
 assert(!sr_voice_cancel_for_appearance("OnRoundStart_View",1));
 assert(!sr_voice_cancel_for_appearance("OnDie_View",0));
 assert(!sr_voice_cancel_for_appearance("OnDeadVoice",0));
 puts("PASS voice queue roots lifetime, dedupe and cleanup");return 0;
}
