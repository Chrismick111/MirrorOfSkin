#define main legacy_test_main
#include "test_camera_lifecycle.c"
#undef main
static void fake_revive(void *view,uint8_t produce,void *mi){assert(view!=NULL&&produce==1);}
int main(void){
 legacy_test_main();reset();sr_voice_clear();memset(g_units,0,sizeof(g_units));
 Unit *u=&g_units[0];u->used=1;u->view=&view;u->voiceBoss=8378;
 assert(!death_voice_accept(u,0,1));assert(!death_voice_accept(u,1,0));assert(!u->deathVoiceAccepted);
 assert(death_voice_accept(u,1,1));assert(u->deathVoiceAccepted&&g_voicePendingCount==1);
 u->voiceBoss=0;assert(death_voice_accept(u,1,1));assert(g_voicePendingCount==1);
 assert(!death_voice_accept(u,0,1));orig_revive=fake_revive;revive_hook(&view,1,NULL);assert(!u->deathVoiceAccepted);sr_voice_clear();
 memset(u,0,sizeof(*u));u->used=1;u->view=&view;u->voiceBoss=90172;
 assert(!death_voice_accept(u,1,1));assert(!u->deathVoiceAccepted);
 u->voiceBoss=8378;for(int i=0;i<SR_VOICE_PENDING;i++)g_voicePending[i].view=&foreign;
 assert(!death_voice_accept(u,1,1));assert(!u->deathVoiceAccepted);
 memset(g_voicePending,0,sizeof(g_voicePending));
 puts("PASS death voice accepted once, repeat latch, disabled, unknown, queue full");return 0;
}