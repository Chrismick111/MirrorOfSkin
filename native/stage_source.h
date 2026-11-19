#ifndef SR_STAGE_SOURCE_H
#define SR_STAGE_SOURCE_H
#include <string.h>
/* Director-initiated transitions preserve the group that won the draw. */
static int sr_stage_source_commit(char source[64],int wanted,int director_wanted,unsigned kind,const char *group){
 if(wanted==director_wanted)return 0;
 if(kind==1&&group){strncpy(source,group,63);source[63]=0;}else source[0]=0;
 return 1;
}
/* A repeated draw of the same group keeps its actually displayed stage. */
static int sr_stage_reselect_keep(const char *source,unsigned kind,const char *group,int director_owned,int group_valid,int presented){
 return !director_owned && group_valid && presented>=0 && kind==1 && source && source[0] && group && !strcmp(source,group);
}
/* A transient return to the native body must not reset a repeated group draw. */
static int sr_stage_reselect_choice(const char *source,unsigned kind,const char *group,int at_base,int group_valid,unsigned count,int choice){
 if(!at_base || !group_valid || kind!=1 || !source || !source[0] || !group || strcmp(source,group) || choice<0 || (unsigned)choice>=count) return -1;
 return choice;
}
#endif
