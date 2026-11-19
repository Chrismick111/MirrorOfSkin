#ifndef SR_CALLBACK_MATCH_H
#define SR_CALLBACK_MATCH_H
#include <string.h>
static int sr_callback_match(const char *name,unsigned n,const char *param,const char *ret,int is_static){
 const char *prefix="<UpdateCoinTossResultDirect>b__";
 return name&&!strncmp(name,prefix,strlen(prefix))&&n==1&&param&&!strcmp(param,"BattleLog_Evade")&&ret&&!strcmp(ret,"System.Void")&&is_static==0;
}
static int sr_callback_accumulate(int matches,int accepted){return matches+(accepted?1:0);}
#endif
