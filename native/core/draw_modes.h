#ifndef SR_DRAW_MODES_H
#define SR_DRAW_MODES_H
#include <math.h>
#include <string.h>
#define SR_DRAW_LIMIT 256
typedef struct {int used[SR_DRAW_LIMIT],count,last;} SrDrawState;
/* 0 independent; 1 weighted order without replacement; 2 explicit order.
   Caller keeps one state for each unit and action category. */
static int sr_draw_mode(SrDrawState *s,int mode,const int *ids,const double *weights,int count,double random){
 if(!s||!ids||!weights||count<0||count>SR_DRAW_LIMIT||!isfinite(random)||random<0||random>=1)return -1;
 if(mode==2){
  int start=0;for(int i=0;i<count;i++)if(ids[i]==s->last&&s->count){start=i+1;break;}
  for(int k=0;k<count;k++){int i=(start+k)%count;if(isfinite(weights[i])&&weights[i]>0&&weights[i]<=1000000){s->last=ids[i];s->count=1;return ids[i];}}
  return -1;
 }
 if(mode!=0&&mode!=1)return -1;
 double total=0;
 for(int pass=0;pass<2;pass++){
  total=0;
  for(int i=0;i<count;i++){
   int used=0;if(mode==1)for(int j=0;j<s->count;j++)if(s->used[j]==ids[i])used=1;
   if(!used&&isfinite(weights[i])&&weights[i]>0&&weights[i]<=1000000)total+=weights[i];
  }
  if(total>0)break;
  if(mode!=1||!s->count)return -1;s->count=0;
 }
 if(!(total>0))return -1;
 double cursor=random*total;int selected=-1;
 for(int i=0;i<count;i++){
  int used=0;if(mode==1)for(int j=0;j<s->count;j++)if(s->used[j]==ids[i])used=1;
  if(used||!isfinite(weights[i])||weights[i]<=0||weights[i]>1000000)continue;
  selected=ids[i];cursor-=weights[i];if(cursor<0)break;
 }
 if(mode==1&&selected>=0){if(s->count==SR_DRAW_LIMIT)s->count=0;s->used[s->count++]=selected;}
 return selected;
}
#endif
