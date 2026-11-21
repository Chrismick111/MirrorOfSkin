
#include <stdio.h>
#include <string.h>
#include <windows.h>
#include "voice_lookup.h"

/* Mirrors what the product now asks for: death-time triggers first, then the
   round-start trigger. A boss plays at least one of them when any row resolves
   to a single key. */
static int resolve(unsigned boss, char *out, int cap, const char **used){
  static const char *const death[] = {"OnDie_View","OnDeadVoice"};
  static const char *const roundStart[] = {"OnRoundStart_View"};
  for(int i=0;i<2;i++){
    char k[64];
    if(sr_voice_single(boss,death[i],k,sizeof(k))){ lstrcpynA(out,k,cap); *used=death[i]; return 1; }
  }
  for(int i=0;i<1;i++){
    char k[64];
    if(sr_voice_single(boss,roundStart[i],k,sizeof(k))){ lstrcpynA(out,k,cap); *used=roundStart[i]; return 1; }
  }
  return 0;
}

int main(void){
  unsigned bosses[] = {
    /* death */
    1135,1136,1318,1337,1338,1488,1496,8378,400008,10312,10910,11016,
    /* round start adds these */
    1127,1306,1319,1345,1482,1483,1484,10115,10213,10414,10513,10515,
    10617,10814,10815,11011,11015,11214,11215,400006,400037,
    /* must stay silent: ambiguous on every wired trigger */
    1128,10310,1079,1082,1314,400012
  };
  int n = (int)(sizeof(bosses)/sizeof(bosses[0]));
  int playable=0, silent=0;
  printf("%-9s %-22s %-30s %s\n","boss","trigger","key","class");
  printf("------------------------------------------------------------------------------\n");
  for(int i=0;i<n;i++){
    char key[64]=""; const char *used="";
    int ok = resolve(bosses[i], key, sizeof(key), &used);
    const char *cls = (i < 12) ? "death" : (i < 33 ? "round" : "silent");
    printf("%-9u %-22s %-30s %s\n", bosses[i],
           ok?used:"(none)", ok?key:"-", cls);
    if(ok) playable++; else silent++;
  }
  printf("------------------------------------------------------------------------------\n");
  printf("playable=%d silent=%d total=%d\n", playable, silent, n);
  return 0;
}
