#ifndef LINK_COIN_FRAMES_H
#define LINK_COIN_FRAMES_H
#include <math.h>
#include <string.h>
#include "link_sprite_curves.h"
#include "link_body_phase.h"

/* Some atlases combine several skills in one AnimationClip. Named poses
   such as s1_3 and skill2_4 identify the skill within that packed clip. */
static int link_pose_family(const char *name){
 if(!strncmp(name,"skill",5))name+=5;
 else if(*name=='s')name++;
 else return 0;
 int family=0;
 while(*name>='0'&&*name<='9'&&family<1000)family=family*10+*name++-'0';
 return *name=='_'?family:0;
}
static void link_coin_frame_range(int first,int count,double *in,double *span){
 double start=*in,end=start+*span,bestStart=start,bestEnd=end,runStart=start;
 int best=0,poses=0,family=0,runFirst=first;
 for(int j=first;j<first+count;j++){
  double a=fmax(start,link_sprite_samples[j].t);
  double b=j+1<first+count?fmin(end,link_sprite_samples[j+1].t):end;
  if(b-a<1e-5)continue;
  int key=link_sprite_samples[j].key,next=key>=0?link_pose_family(link_sprite_keys[key].name):0;
  if(!next){family=poses=0;continue;}
  int repeated=0;
  if(next==family&&j>runFirst&&link_sprite_samples[j-1].key!=key){
   for(int k=runFirst;k<j;k++)if(link_sprite_samples[k].key==key){repeated=1;break;}
  }
  if(next!=family||repeated){
   if(best>=2)break;
   runStart=a;runFirst=j;poses=0;family=next;
  }
  if(j==runFirst||link_sprite_samples[j-1].key!=key)poses++;
  if(poses>best||(poses==best&&runStart==bestStart)){best=poses;bestStart=runStart;bestEnd=b;}
 }
 if(best>=2){*in=bestStart;*span=bestEnd-bestStart;}
}

/* Select one uninterrupted forward swing from the verified attack-body curves
   for this appearance. A clip may also contain other skills, an idle sprite,
   a reverse cut, or an intentionally empty renderer. Each ends the run. */
typedef struct {int first,count;const char *clip;} LinkSwing;
static int link_attack_ordinal(const char *name,int *ordinal){
 const char *p=!strncmp(name,"skill",5)?name+5:*name=='s'?name+1:NULL;
 if(!p)return 0;
 int family=0;while(*p>='0'&&*p<='9')family=family*10+*p++-'0';
 if(*p++!='_'||*p<'0'||*p>'9')return 0;
 *ordinal=0;while(*p>='0'&&*p<='9')*ordinal=*ordinal*10+*p++-'0';
 return (*p==0||*p==',')?family+1:0;
}
/* A two-key body may select a donor cut containing only a held pose. Find
   an adjacent forward pair, preferring the same pose, family and clip. */
static LinkSwing link_coin_two_pose(const char *look,LinkSwing base){
 if(base.count<=0)return base;
 int first=link_sprite_samples[base.first].key;
 int last=link_sprite_samples[base.first+base.count-1].key;
 int ordinal=0,endOrdinal=0;
 int family=first>=0?link_attack_ordinal(link_sprite_keys[first].name,&ordinal):0;
 if(family&&last>=0&&link_attack_ordinal(link_sprite_keys[last].name,&endOrdinal)==family&&endOrdinal>ordinal)return base;
 LinkSwing best=base;int bestScore=-1;
 for(unsigned i=0;i<sizeof(link_sprite_curves)/sizeof(*link_sprite_curves);i++){
  if(strcmp(look,link_sprite_curves[i].look))continue;
  const char *clip=link_sprite_curves[i].animation;
  if(!link_matching_body_phase(base.clip,clip))continue;
  int begin=link_sprite_curves[i].first,end=begin+link_sprite_curves[i].count;
  for(int j=begin;j+1<end;j++){
   int a=link_sprite_samples[j].key,b=link_sprite_samples[j+1].key;
   if(a<0||b<0||a==b)continue;
   int x=0,y=0,next=link_attack_ordinal(link_sprite_keys[a].name,&x);
   if(!next||link_attack_ordinal(link_sprite_keys[b].name,&y)!=next||x>=y)continue;
   int score=(a==first)*8+(b==first)*4+(family==next)*2+!strcmp(clip,base.clip);
   if(score>bestScore){bestScore=score;best=(LinkSwing){j,2,clip};}
  }
 }
 return best;
}
static LinkSwing link_rank_swing(const char *look,int beats,int coin,LinkSwing base,const char *skip){
 LinkSwing best=base;int bestCovered=base.count,bestGap=beats-base.count,ties=0;
 for(unsigned i=0;i<sizeof(link_sprite_curves)/sizeof(*link_sprite_curves);i++){
  if(strcmp(look,link_sprite_curves[i].look)||(skip&&!strcmp(skip,link_sprite_curves[i].animation))||
     !link_matching_body_phase(skip?skip:base.clip,link_sprite_curves[i].animation))continue;
  int begin=link_sprite_curves[i].first,end=begin+link_sprite_curves[i].count;
  int start=begin,family=0,lastOrdinal=-1;
  for(int j=begin;j<=end;j++){
   int key=j<end?link_sprite_samples[j].key:-1,ordinal=-1;
   int next=key>=0?link_attack_ordinal(link_sprite_keys[key].name,&ordinal):0;
   if(!next||next!=family||ordinal<=lastOrdinal){
    int count=j-start;
    if(family&&count>base.count&&(!skip||count>=3)){
     int covered=count<beats?count:beats;
     int gap=count>beats?count-beats:beats-count;
     /* Longer swings can supply all the authored poses by downsampling.
        Missing beats in a short swing can only repeat an image. */
     if(covered>bestCovered||(covered==bestCovered&&gap<bestGap)){
      bestCovered=covered;bestGap=gap;ties=0;
     }
     if(covered==bestCovered&&gap==bestGap&&(ties++==0||(coin>=0&&coin%ties==ties-1)))
      best=(LinkSwing){start,count,link_sprite_curves[i].animation};
    }
    start=j;
   }
   family=next;lastOrdinal=ordinal;
  }
 }
 return best;
}
static LinkSwing link_coin_swing(const char *look,int beats,int coin,LinkSwing base){
 if(beats<2)return base;
 if(!strncmp(look,"story_",6))look+=6;
 if(beats==2)return link_coin_two_pose(look,base);
 LinkSwing best=beats<=base.count?base:link_rank_swing(look,beats,coin,base,NULL);
 /* An entire linked attack used to select the same longest donor four
    times. Alternate with another complete forward swing on odd coins. */
 if(coin>0&&(coin&1)){
  LinkSwing alt=link_rank_swing(look,beats,coin,(LinkSwing){0},best.clip);
  if(alt.count>=3)return alt;
 }
 return best;
}
static LinkSwing link_coin_base_range(int first,int count,const char *clip,double *in,double *span){
 int last=first+count;
 link_coin_frame_range(first,count,in,span);
 while(first+1<last&&link_sprite_samples[first+1].t<=*in+.000001)first++;
 while(last>first+1&&link_sprite_samples[last-1].t>=*in+*span-.000001)last--;
 return (LinkSwing){first,last-first,clip};
}
static LinkSwing link_coin_donor_swing(const char *look,const char *clip,double in,double span,int beats,int coin){
 if(!strncmp(look,"story_",6))look+=6;
 for(unsigned i=0;i<sizeof(link_sprite_curves)/sizeof(*link_sprite_curves);i++){
  if(strcmp(look,link_sprite_curves[i].look)||strcmp(clip,link_sprite_curves[i].animation))continue;
  LinkSwing base=link_coin_base_range(link_sprite_curves[i].first,link_sprite_curves[i].count,clip,&in,&span);
  return link_coin_swing(look,beats,coin,base);
 }
 return (LinkSwing){0};
}
#endif
