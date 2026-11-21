#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "verified_voice_rules.h"
int main(void){
 assert(sr_verified_voice_rule(8378,"OnDie_View","7SV-100"));
 assert(!sr_verified_voice_rule(8378,"OnRoundStart_View","7SV-100"));
 assert(!sr_verified_voice_rule(8378,"OnDie_View","wrong"));
 assert(!sr_verified_voice_rule(90172,"OnDie_View","7SV-100"));
 puts("PASS only explicitly verified boss event and key enabled");
}
