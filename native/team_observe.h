#ifndef TEAM_OBSERVE_H
#define TEAM_OBSERVE_H
#include <string.h>
typedef struct {void *unit;const char *name;} TeamObserveRow;
typedef struct {int (*compare)(void*,void*);void (*log)(const char*,const char*,int);} TeamObserveOps;
static int team_is_wedge(const char *s){return s&&(!strncmp(s,"10316",5)||!strncmp(s,"11017",5)||!strncmp(s,"11116",5))&&(s[5]==0||s[5]=='_');}
static int team_observe_run(int enabled,const TeamObserveRow *rows,int count,const TeamObserveOps *ops){
 if(!enabled||!rows||!ops||!ops->compare||!ops->log||count<2)return 0;
 int logged=0;for(int pass=0;pass<2;pass++)for(int i=0;i<count&&i<16;i++)for(int j=i+1;j<count&&j<16&&logged<32;j++){
  if(!rows[i].unit||!rows[j].unit||rows[i].unit==rows[j].unit)continue;
  int wedge=team_is_wedge(rows[i].name)||team_is_wedge(rows[j].name);if((pass==0)!=wedge)continue;
  int value=ops->compare(rows[i].unit,rows[j].unit);if(value!=0&&value!=1)value=-1;
  ops->log(rows[i].name,rows[j].name,value);logged++;
 }return logged;
}
#endif
