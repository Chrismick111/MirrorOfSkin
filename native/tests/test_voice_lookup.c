#include "voice_lookup.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>

int main(void){
  char buf[64];

  /* The one path proven to make sound in game. */
  assert(sr_voice_single(8378,"OnDie_View",buf,sizeof(buf)));
  assert(!strcmp(buf,"7SV-100"));

  /* Same boss, different trigger, must not return the death key. */
  const char *round=sr_voice_keys(8378,"OnRoundStart_View");
  assert(round&&sr_voice_key_count(round)>1);
  assert(!strstr(round,"7SV-100"));

  /* Ambiguous triggers refuse to resolve rather than guess. */
  assert(!sr_voice_single(8378,"OnRoundStart_View",buf,sizeof(buf)));

  /* Generic keys carry no boss number; they still resolve for their boss. */
  assert(sr_voice_single(11016,"OnDeadVoice",buf,sizeof(buf)));
  assert(!strcmp(buf,"battle_dead"));

  /* Unknown boss and unknown trigger are both absent. */
  assert(!sr_voice_keys(999999,"OnDie_View"));
  assert(!sr_voice_keys(8378,"NoSuchTrigger"));

  /* Every row must have a non-empty trigger and at least one key. */
  for(int i=0;i<SR_VOICE_ROW_COUNT;i++){
    assert(sr_voice_rows[i].trigger&&*sr_voice_rows[i].trigger);
    assert(sr_voice_key_count(sr_voice_rows[i].keys)>=1);
  }

  /* Count the distribution so the numbers are visible, not assumed. */
  int single=0,multi=0;
  for(int i=0;i<SR_VOICE_ROW_COUNT;i++){
    if(sr_voice_key_count(sr_voice_rows[i].keys)==1)single++;else multi++;
  }
  printf("rows=%d single=%d multi=%d\n",SR_VOICE_ROW_COUNT,single,multi);
  printf("ok\n");
  return 0;
}
