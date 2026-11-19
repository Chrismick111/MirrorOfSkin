#ifndef LINK_VISUAL_SEQUENCE_H
#define LINK_VISUAL_SEQUENCE_H
#include <math.h>
#include <stdlib.h>
typedef struct {
 int owner,group,index;
 double start,duration;
} LinkSequencePart;
static int link_sequence_order(const void *a,const void *b){
 const LinkSequencePart *x=a,*y=b;
 if(x->owner!=y->owner)return x->owner-y->owner;
 if(x->start!=y->start)return x->start<y->start?-1:1;
 return x->index-y->index;
}
/* The output references the original window's donor choice through index. */
static int link_sequence_join(LinkSequencePart *p,int count,double end,double gap){
 qsort(p,count,sizeof(*p),link_sequence_order);
 int n=0;
 for(int i=0;i<count;i++){
  LinkSequencePart w=p[i],*last=n?&p[n-1]:NULL;
  if(last&&last->owner==w.owner&&last->group==w.group&&w.start<=last->start+last->duration+gap){
   last->duration=fmax(last->duration,w.start+w.duration-last->start);
  }else p[n++]=w;
 }
 for(int i=0;i<n;i++){
  double limit=i+1<n&&p[i+1].owner==p[i].owner?fmin(end,p[i+1].start):end;
  p[i].duration=fmax(0.,fmin(fmax(.32,p[i].duration),limit-p[i].start));
 }
 return n;
}
static int link_sequence_plan(LinkSequencePart *p,int count,double end){
 return link_sequence_join(p,count,end,.32);
}
/* A linked coin often cuts the same actor's body track into several shots.
   Keep their first entry cue and final exit, sampling just one donor. */
static int link_sequence_coin(LinkSequencePart *p,int count,double end){
 qsort(p,count,sizeof(*p),link_sequence_order);
 int n=0;
 for(int i=0;i<count;i++){
  LinkSequencePart w=p[i];
  if(n&&p[n-1].owner==w.owner){
   LinkSequencePart *one=&p[n-1];one->duration=fmax(one->duration,w.start+w.duration-one->start);
  }else p[n++]=w;
 }
 for(int i=0;i<n;i++)p[i].duration=fmax(0.,fmin(end-p[i].start,fmax(.32,p[i].duration)));
 return n;
}
/* Oscar's three linked timelines reuse exactly the same lead-in attack range.
   Spread the donor's swing across those three coins instead of replaying it
   from the wind-up on each cut. */
static void link_trio_lead_range(int part,double *in,double *span){
 if(part<1||part>3)return;
 double third=*span/3.;
 *in+=third*(part-1);*span=third;
}
#endif
