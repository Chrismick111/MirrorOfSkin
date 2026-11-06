#ifndef SR_VERIFIED_VOICE_RULES_H
#define SR_VERIFIED_VOICE_RULES_H
/* Each row requires an independently audited native condition and key.
   A single literal appearing in a method is not, by itself, a rule. */
typedef struct { unsigned boss; const char *trigger; const char *key; } SrVerifiedVoiceRule;
static const SrVerifiedVoiceRule sr_verified_voice_rules[]={
 {8378,"OnDie_View","7SV-100"} /* UnitScript_8378.OnDie_View: once-only flag */
};
static const SrVerifiedVoiceRule *sr_verified_voice_rule(unsigned boss,const char *trigger,const char *key){
 for(unsigned i=0;i<sizeof(sr_verified_voice_rules)/sizeof(sr_verified_voice_rules[0]);i++){
  const SrVerifiedVoiceRule *r=&sr_verified_voice_rules[i];
  if(r->boss==boss&&(!trigger||!strcmp(trigger,r->trigger))&&(!key||!strcmp(key,r->key)))return r;
 }
 return NULL;
}
#endif
