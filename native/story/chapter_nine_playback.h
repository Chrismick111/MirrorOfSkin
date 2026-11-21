#ifndef SR_CHAPTER_NINE_PLAYBACK_H
#define SR_CHAPTER_NINE_PLAYBACK_H
#include <string.h>

/* Resource names come from the archive's serialized appearance names. */
typedef struct {
 const char *base,*alternate;
 const char *look[4];
} SrChapterActor;
static const SrChapterActor sr_chapter_actors[]={
 {"10115_YiSang_Index_FatherAppearance",NULL,{"1347_Index_fatherAppearance","1348_Index_father_Phase2Appearance"}},
 {"10215_Faust_Ring_DiscipleAppearance","10215_Faust_Ring_Disciple_CastOffAppearance",{"1319_RingFinger_DiscipleAppearance","1336_RingFinger_Disciple_CastoffAppearance","1354_RingFinger_DiscipleAppearance"}},
 {"10314_Donquixote_Index_DiscipleAppearance","10314_Donquixote_Index_Disciple_AwakenAppearance",{"1325_Index_Disciple_NormalAppearance","1325_Index_discipleAppearance","1355_Index_Disciple_NormalAppearance","1355_Index_DiscipleAppearance"}},
 {"10415_Ryoshu_Pinky_FatherAppearance",NULL,{"1322_Pinky_FatherAppearance","1322_Pinky_Father2pAppearance"}},
 {"10614_Honglu_RingFinger_FatherAppearance",NULL,{"1331_RingFinger_FatherAppearance"}},
 {"10716_Heathcliff_Thumb_DiscipleAppearance",NULL,{"1306_Thumb_DiscipleAppearance"}},
 {"10814_Ishmael_MiddleFinger_DiscipleAppearacne",NULL,{"1328_MiddleFinger_discipleAppearance"}},
 {"10916_Rodion_Thumb_FatherAppearance",NULL,{"1314_Thumb_FatherAppearance"}},
 {"11015_Sinclair_PinkyFinger_DiscipleAppearance",NULL,{"1318_Pinky_DiscipleAppearance","1353_Pinky_DiscipleAppearance"}},
 {"11115_Outis_Middle_FatherAppearance",NULL,{"1327_MiddleFinger_fatherAppearance","1327_MiddleFinger_father_Phase4Appearance"}}
};
static const SrChapterActor *sr_chapter_actor(const char *base,const char *look){
 if(!base||!look)return NULL;
 for(unsigned i=0;i<sizeof(sr_chapter_actors)/sizeof(*sr_chapter_actors);i++){
  const SrChapterActor *a=&sr_chapter_actors[i];
  if(!sr_pair_base(base,a->base)&&(!a->alternate||strcmp(base,a->alternate)))continue;
  for(unsigned k=0;k<4&&a->look[k];k++)if(!strcmp(look,a->look[k]))return a;
 }
 return NULL;
}
typedef struct {const char *source,*target;int sourceDetail,sourceIndex,targetDetail,targetIndex,expectedCount;} SrChapterClip;
#include "chapter_nine_groups.inc"

/* One group per requested skill. Group selection must never depend on the
   current coin or on asynchronously arriving coin-count observations. */
static int sr_chapter_group(const SrChapterActor *actor,const char *source,const char *look,
 const char *identity,const int *counts,int requested,int *verified){
 *verified=0;
 if(!actor||requested<0||requested>=SR_MOTION_CACHE)return requested;
 for(unsigned i=0;i<sizeof(sr_chapter_clips)/sizeof(*sr_chapter_clips);i++){
  const SrChapterClip *g=&sr_chapter_clips[i];
  if(requested==g->sourceDetail&&!strcmp(g->source,source)&&!strcmp(g->target,look)&&counts[g->targetDetail]==g->expectedCount){
   *verified=3;return g->targetDetail;
  }
 }
 int known=sr_verified_paired_attack(counts,source,identity,requested,-1);
 if(known>=0){*verified=1;return known;}
 if(!((requested>=7&&requested<=16)||(requested>=24&&requested<=34)))return requested;
 if(counts[requested]>0)return requested;
 /* A missing tier has no authored equivalent. Choose one available enemy
    group, once for this source detail, without splicing clips across skills. */
 for(int d=7;d<=34;d++)if((d<=16||d>=24)&&counts[d]>0)return d;
 return requested;
}
static int sr_chapter_source_count(const char *source,int detail){
 if(detail<0||detail>=SR_MOTION_CACHE)return 0;
 for(unsigned i=0;i<sizeof(sr_chapter_source_counts)/sizeof(*sr_chapter_source_counts);i++)
  if(!strcmp(sr_chapter_source_counts[i].source,source))return sr_chapter_source_counts[i].counts[detail];
 return 0;
}
static int sr_chapter_exact_part(const char *source,const char *look,int requested,int index,int detail,int count){
 for(unsigned i=0;i<sizeof(sr_chapter_clips)/sizeof(*sr_chapter_clips);i++){
  const SrChapterClip *c=&sr_chapter_clips[i];
  if(c->sourceDetail==requested&&c->sourceIndex==index&&c->targetDetail==detail&&c->expectedCount==count&&
     !strcmp(source,c->source)&&!strcmp(look,c->target))return c->targetIndex;
 }
 return -1;
}
#endif
