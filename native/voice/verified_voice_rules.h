#ifndef SR_VERIFIED_VOICE_RULES_H
#define SR_VERIFIED_VOICE_RULES_H
/* Each row requires an independently audited native condition and key.
   A single literal appearing in a method is not, by itself, a rule. */
typedef struct { unsigned boss; const char *trigger; const char *key; } SrVerifiedVoiceRule;
static const SrVerifiedVoiceRule sr_verified_voice_rules[]={
 /* UnitScript_8378.OnDie_View @0x118fb30:
      cmp byte [rbx+0x75],0 / jne .end / call 0x118f620 / mov byte [rbx+0x75],1
    A once-only flag around a single call: the boss speaks exactly once. */
 {8378,"OnDie_View","7SV-100"},
 /* UnitScript_1337.OnDie_View @0x1071260: same shape, flag at +0x73, virtual
    call through [r8+0x668] with length 2.0s and cooldown 10.0s. The flag is
    the authority; the cooldown never survives to a second death. */
 {1337,"OnDie_View","9SV-BAT18-26"}
};
static const SrVerifiedVoiceRule *sr_verified_voice_rule(unsigned boss,const char *trigger,const char *key){
 for(unsigned i=0;i<sizeof(sr_verified_voice_rules)/sizeof(sr_verified_voice_rules[0]);i++){
  const SrVerifiedVoiceRule *r=&sr_verified_voice_rules[i];
  if(r->boss==boss&&(!trigger||!strcmp(trigger,r->trigger))&&(!key||!strcmp(key,r->key)))return r;
 }
 return NULL;
}
#endif
