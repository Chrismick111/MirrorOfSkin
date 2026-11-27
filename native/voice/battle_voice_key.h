#ifndef SR_BATTLE_VOICE_KEY_H
#define SR_BATTLE_VOICE_KEY_H
#include "voice_owner_field.h"

/* Combat keys put the personality at the first standalone numeric field.
   A foreign personality mentioned in a clip suffix is never its speaker. */
static const char *battle_voice_owner_field(const char *key,unsigned owner){
 const char *start=battle_voice_speaker(key,owner);
 if(!start)return NULL;
 if(sr_voice_member_index(owner,key)>=0)return start;
 /* Donor packages and alternate variants may predate the game catalog. */
 const size_t prefix=(size_t)(start-key-1);
 for(size_t i=0;i<sizeof(sr_voice_common_events)/sizeof(sr_voice_common_events[0]);i++)
  if(strlen(sr_voice_common_events[i])==prefix&&!strncmp(key,sr_voice_common_events[i],prefix))return start;
 if(!strncmp(key,"battle_",7)&&prefix>8&&strchr("scp",key[7])&&
    strspn(key+8,"0123456789")==prefix-8)return start;
 if(prefix==12&&!strncmp(key,"battle_start",prefix))return start;
 return NULL;
}

static int battle_voice_remap(const char *key,unsigned from,unsigned to,char *out,size_t cap){
 const char *field=battle_voice_owner_field(key,from);
 if(!field||!to)return 0;
 int n=snprintf(out,cap,"%.*s%u%s",(int)(field-key),key,to,field+strspn(field,"0123456789"));
 return n>0&&(size_t)n<cap;
}
#endif
