#ifndef FX_PLAN_MATCH_H
#define FX_PLAN_MATCH_H
#include "fx_plan_binary.h"
/* Returns count or -1 if output is too small. No implicit first-row fallback. */
static int fx_match_rows(const FxPlanRow *rows,size_t count,const char *base,const char *identity,const char *look,int detail,int part,size_t *out,size_t capacity){
 if(!rows||!base||!identity||!look||!out)return -1;
 size_t n=0;
 for(size_t i=0;i<count;i++){
  const FxPlanRow *r=&rows[i];size_t len=strlen(r->strings[0]);
  if(!len||strncmp(base,r->strings[0],len)||(base[len]&&base[len]!='_')||strcmp(identity,r->strings[1])||strcmp(look,r->strings[2])||detail!=r->detail||part!=r->part)continue;
  if(n>=capacity)return -1;out[n++]=i;
 }
 return (int)n;
}
#endif
