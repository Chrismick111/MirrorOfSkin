#ifndef SR_VOICE_OWNER_FIELD_H
#define SR_VOICE_OWNER_FIELD_H

#include <stdlib.h>
#include <string.h>

/* Voice keys identify the speaker with the first standalone numeric field. */
static const char *battle_voice_speaker(const char *key,unsigned owner){
 if(!owner||(strncmp(key,"battle_",7)&&strncmp(key,"battleentry_",12)))return NULL;
 const char *field=key;
 while((field=strchr(field,'_'))){
  const char *start=++field;
  size_t digits=strspn(start,"0123456789");
  if(!digits||(start[digits]&&start[digits]!='_'))continue;
  return digits<=8&&*start!='0'&&strtoul(start,NULL,10)==owner?start:NULL;
 }
 return NULL;
}
#endif
