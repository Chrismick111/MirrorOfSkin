#ifndef LINK_VISUAL_CLOCK_H
#define LINK_VISUAL_CLOCK_H
#include <math.h>

typedef struct {
 int started, frame, directorAdvanced;
 double elapsed, director, scaled, tailStart, frameDelta;
 int inTail,shortCoin;
} LinkVisualClock;

/* A link can be presented while the native director reports zero throughout.
   Advance on scaled game frames then. When the director advances, follow its
   actual sample without counting the same frame's delta a second time. */
static double link_clock_step(LinkVisualClock *clock,int frame,double delta,double director){
 int sampled=isfinite(director)&&director>=0;
 /* The first displayed frame can be framed before any coin time elapses. */
 clock->frameDelta=frame>=0&&(!clock->started||frame!=clock->frame)&&isfinite(delta)&&delta>0?delta:0;
 if(!clock->started){
  clock->started=1;clock->frame=frame;
  clock->directorAdvanced=sampled&&director>0&&(!clock->shortCoin||director>=1./60);
  clock->elapsed=sampled?director:0;clock->director=sampled?director:-1;
  return clock->elapsed;
 }
 clock->scaled+=clock->frameDelta;
 /* A tiny initial position alone cannot distinguish a running short coin
    from a parked playhead. Confirm movement before handing it the clock. */
 int moving=!clock->shortCoin||director>=1./60||clock->director>0;
 if(sampled&&director>clock->director+1e-7&&director>0&&moving){
  clock->directorAdvanced=1;
  clock->elapsed=fmax(clock->elapsed,director);
 }else if(!sampled||!clock->directorAdvanced){
  clock->elapsed+=clock->frameDelta;
 }
 if(sampled)clock->director=director;
 clock->frame=frame;
 return clock->elapsed;
}
/* A completed director may hold its final sample until the next coin. */
static int link_clock_tail_done(LinkVisualClock *clock,double t,double end){
 if(!clock->inTail){clock->inTail=1;clock->tailStart=clock->scaled-fmax(0.,t-end);}
 return clock->scaled-clock->tailStart>=.60;
}
#endif
