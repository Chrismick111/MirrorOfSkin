
#include <stdio.h>
#include <string.h>
#include <windows.h>
#include "voice_lookup.h"

/* Every boss that carries a death-time voice row, plus the trigger names the
   product now tries in order. Prints one line per boss so the coverage is
   visible without launching the game. */
typedef struct { unsigned boss; const char *expect; } Expect;

int main(void){
  static const char *const deathTriggers[] = {"OnDie_View","OnDeadVoice"};
  const Expect known[] = {
    {1128,   NULL},          /* ambiguous: 7SV-BV-025|026, must NOT play */
    {1135,   "8SV-036"},
    {1136,   "8SV-042"},
    {1318,   "9SV-BAT4-04"},
    {1337,   "9SV-BAT18-26"},
    {1338,   "9SV-BAT4-02"},
    {1488,   "10SV-107"},
    {1496,   "10SV-099"},
    {8378,   "7SV-100"},
    {400008, "9SV-BAT5-05"},
    {10310,  NULL},          /* ambiguous: three react keys */
    {10312,  "battle_dead_hysteric_10312_1"},
    {10910,  "battle_devai_10910_1-04"},
    {11016,  "battle_dead"},
  };
  int n = (int)(sizeof(known)/sizeof(known[0]));
  int pass = 0, fail = 0;
  printf("boss      trigger             resolved                 expected\n");
  printf("--------------------------------------------------------------------\n");
  for(int i=0;i<n;i++){
    char hit[64] = "";
    const char *used = "";
    for(int t=0;t<2;t++){
      char k[64];
      if(sr_voice_single(known[i].boss,deathTriggers[t],k,sizeof(k))){
        lstrcpynA(hit,k,sizeof(hit));
        used = deathTriggers[t];
        break;
      }
    }
    int ok;
    if(known[i].expect==NULL) ok = (hit[0]==0);           /* must stay silent */
    else ok = (hit[0]!=0 && !strcmp(hit,known[i].expect));
    printf("%-9u %-19s %-24s %s\n", known[i].boss,
           hit[0]?used:"(none)",
           hit[0]?hit:"-",
           ok?"PASS":"FAIL");
    if(ok) pass++; else fail++;
  }
  printf("--------------------------------------------------------------------\n");
  printf("pass=%d fail=%d of %d death-voice bosses\n", pass, fail, n);
  return fail ? 1 : 0;
}
