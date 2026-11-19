#ifndef WEDGE_AUTHORED_TIMING_H
#define WEDGE_AUTHORED_TIMING_H
#include <math.h>
#include <string.h>
typedef struct {const char *timeline;int owner,first,count;} LinkBeatRow;
#include "link_authored_beats.h"
static int link_authored_known(const char *timeline){
 for(unsigned i=0;i<sizeof(linkBeatRows)/sizeof(*linkBeatRows);i++)
  if(!strcmp(linkBeatRows[i].timeline,timeline))return 1;
 return 0;
}
static const LinkBeatRow *link_authored_row(const char *timeline,int owner){
 for(unsigned i=0;i<sizeof(linkBeatRows)/sizeof(*linkBeatRows);i++)
  if(linkBeatRows[i].owner==owner&&!strcmp(linkBeatRows[i].timeline,timeline))return linkBeatRows+i;
 return NULL;
}
/* The game can replace these coins before the final body key, without ever
   advancing their director. Reserve about two 30 Hz frames for the final
   pose inside the shortest captured handoffs (0.348 s and 0.411 s). */
typedef struct {double displayTime,sourceTime;} LinkBodyCue;
typedef struct {double recoveryAt,lastCue,cursor;const LinkBodyCue *cues;int count;} LinkShortBody;
static LinkShortBody link_short_body(const char *scene){
 /* Original key positions are in 60 Hz timeline frames. The display times
    keep successive poses of each participant apart by at least one 15 Hz
    frame, including the recovery before the earliest recorded handoff. */
 static const LinkBodyCue sinclair[]={{0,0},{.068,6./60},{.133,18./60},{.201,25./60},
                                     {.207,29./60},{.275,36./60},{.280,41./60}};
 static const LinkBodyCue outis[]={{0,0},{.255,21./60},{1./3,25./60}};
 LinkShortBody body={0};
 if(!strcmp(scene,"11017_S3_Link_02 1")){body.cues=sinclair;body.count=sizeof(sinclair)/sizeof(*sinclair);}
 else if(!strcmp(scene,"11116_S5_Link_01")){body.cues=outis;body.count=sizeof(outis)/sizeof(*outis);}
 else return body;
 body.recoveryAt=body.cues[body.count-1].displayTime;
 body.lastCue=body.cues[body.count-1].sourceTime;
 return body;
}
/* The partners share a single monotonic sample even on a late takeover. */
static double link_body_sample_time(LinkShortBody *body,double time,int directorAdvanced){
 if(body->lastCue<=body->recoveryAt)return time;
 if(!directorAdvanced&&body->count){
  if(time>=body->recoveryAt)time=fmax(time,body->lastCue);
  else for(int i=1;i<body->count;i++){
   LinkBodyCue a=body->cues[i-1],b=body->cues[i];
   if(time>b.displayTime)continue;
   double fraction=(time-a.displayTime)/(b.displayTime-a.displayTime);
   time=a.sourceTime+fraction*(b.sourceTime-a.sourceTime);break;
  }
 }
 body->cursor=fmax(body->cursor,time);
 return body->cursor;
}
/* Advance only when the original body actually changes sprite. A long exposure,
   silent cut or hit-stop cannot prematurely play the donor's recovery. */
static double link_authored_progress(const LinkBeatRow *row,double t){
 const double *keys=linkBeatTimes+row->first;
 if(t<keys[0]-.000001)return 0.;
 if(row->count==1)return .5;
 int lo=0,hi=row->count;
 while(lo<hi){int mid=lo+(hi-lo)/2;if(keys[mid]<=t+.000001)lo=mid+1;else hi=mid;}
 return lo>1?(double)(lo-1)/(row->count-1):0.;
}
#endif
