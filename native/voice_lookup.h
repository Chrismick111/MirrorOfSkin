#ifndef SR_VOICE_LOOKUP
#define SR_VOICE_LOOKUP
#include <stddef.h>
#include "voice_table.h"

/* The table stores several keys joined with '|' when one trigger point holds
   more than one recording. Picking among them needs runtime state the table
   cannot see, so this layer reports the count and lets the caller decide. */

static int sr_voice_key_count(const char *keys){
  if(!keys||!*keys)return 0;
  int n=1;
  for(const char *p=keys;*p;p++)if(*p=='|')n++;
  return n;
}

/* Index of keys for this boss and trigger, or -1. */
static int sr_voice_row_index(unsigned boss,const char *trigger){
  if(!trigger||!*trigger)return -1;
  for(int i=0;i<SR_VOICE_ROW_COUNT;i++){
    if(sr_voice_rows[i].boss!=boss)continue;
    const char *t=sr_voice_rows[i].trigger;
    const char *a=t,*b=trigger;
    while(*a&&*a==*b){a++;b++;}
    if(!*a&&!*b)return i;
  }
  return -1;
}

/* Keys for one trigger point, or NULL. May hold several separated by '|'. */
static const char *sr_voice_keys(unsigned boss,const char *trigger){
  int i=sr_voice_row_index(boss,trigger);
  return i<0?NULL:sr_voice_rows[i].keys;
}

/* Copies the key into out when the trigger resolves to exactly one recording.
   Returns 0 when absent or ambiguous, so a caller never plays a guess. */
static int sr_voice_single(unsigned boss,const char *trigger,char *out,int cap){
  const char *keys=sr_voice_keys(boss,trigger);
  if(!keys||sr_voice_key_count(keys)!=1)return 0;
  int n=0;
  while(keys[n]&&keys[n]!='|'&&n<cap-1){out[n]=keys[n];n++;}
  out[n]=0;
  return n>0;
}

#endif
