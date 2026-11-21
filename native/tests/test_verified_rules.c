/* Gate test for the verified-rule allowlist.
   Two things must hold, and both are cheap to check without the game:
     1. Every rule points at a key the table actually resolves to on its own.
        A typo here would silence the boss instead of speaking it.
     2. Every boss that has a death row but no rule stays rejected, so the
        product keeps the native sound instead of guessing. */
#include <stdio.h>
#include <string.h>
#include <windows.h>
#include "voice_lookup.h"
#include "verified_voice_rules.h"

int main(void){
  int pass=0,fail=0;
  unsigned nRules=(unsigned)(sizeof(sr_verified_voice_rules)/sizeof(sr_verified_voice_rules[0]));

  printf("=== rule <-> table consistency ===\n");
  printf("%-7s %-14s %-22s %-22s %s\n","boss","trigger","rule key","table key","verdict");
  printf("----------------------------------------------------------------------------\n");
  for(unsigned i=0;i<nRules;i++){
    const SrVerifiedVoiceRule *r=&sr_verified_voice_rules[i];
    char table[64]="";
    int single=sr_voice_single(r->boss,r->trigger,table,sizeof(table));
    int ok=single&&!strcmp(table,r->key);
    printf("%-7u %-14s %-22s %-22s %s\n",r->boss,r->trigger,r->key,
           single?table:"(unresolved)",ok?"PASS":"FAIL");
    if(ok)pass++;else fail++;
  }

  /* Bosses that carry a death row but no audited rule. They must be rejected,
     which is what makes the product leave their native death sound alone. */
  const unsigned unaudited[]={1128,1318,1338,1135,1136,1488,1496,400008};
  printf("\n=== unaudited bosses must stay rejected ===\n");
  printf("%-7s %-22s %s\n","boss","table key","verdict");
  printf("----------------------------------------------------------------------------\n");
  for(unsigned i=0;i<sizeof(unaudited)/sizeof(unaudited[0]);i++){
    unsigned b=unaudited[i];
    char table[64]="";
    int single=sr_voice_single(b,"OnDie_View",table,sizeof(table));
    int rejected=sr_verified_voice_rule(b,"OnDie_View",NULL)==NULL;
    printf("%-7u %-22s %s\n",b,single?table:"(none)",rejected?"PASS":"FAIL");
    if(rejected)pass++;else fail++;
  }

  printf("\n=== lookup behaviour ===\n");
  /* A rule must be findable by (boss,trigger) and by the full triple, and a
     wrong key must not match even when boss and trigger are right. */
  const SrVerifiedVoiceRule *a=sr_verified_voice_rule(8378,"OnDie_View",NULL);
  const SrVerifiedVoiceRule *b=sr_verified_voice_rule(8378,"OnDie_View","7SV-100");
  const SrVerifiedVoiceRule *c=sr_verified_voice_rule(8378,"OnDie_View","9SV-BAT18-26");
  struct { const char *name; int ok; } checks[]={
    {"find by boss+trigger",       a!=NULL},
    {"find by full triple",        b!=NULL},
    {"wrong key is rejected",      c==NULL},
    {"unknown boss is rejected",   sr_verified_voice_rule(9999,"OnDie_View",NULL)==NULL},
  };
  for(unsigned i=0;i<sizeof(checks)/sizeof(checks[0]);i++){
    printf("%-28s %s\n",checks[i].name,checks[i].ok?"PASS":"FAIL");
    if(checks[i].ok)pass++;else fail++;
  }

  printf("----------------------------------------------------------------------------\n");
  printf("pass=%d fail=%d  rules=%u\n",pass,fail,nRules);
  return fail?1:0;
}
