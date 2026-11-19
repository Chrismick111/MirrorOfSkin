#ifndef SR_PLAYBACK_POLICY
#define SR_PLAYBACK_POLICY
#define SR_MOTION_CACHE 128
#include <string.h>
/* Match an exact known identity or its complete five-digit ID. */
static int sr_pair_base(const char *actual,const char *full){return actual&&full&&(!strcmp(actual,full)||(strlen(actual)==5&&!strncmp(actual,full,5)));}
/* Exact timeline matches validated against the target contract. */
static int sr_verified_paired_attack(const int *counts,const char *base,const char *identity,int requested,int fallback){
 if(!counts||!base||!identity)return fallback;
 int target=-1,expected=0;
 if(sr_pair_base(base,"10916_Rodion_Thumb_FatherAppearance")&&!strcmp(identity,"story_1314_Thumb_FatherAppearance")){
  static const int targets[]={7,11,12,8,9,10,13};
  static const int lengths[]={2,3,4,2,2,3,5};
  if(requested>=7&&requested<=13){target=targets[requested-7];expected=lengths[requested-7];}
 }else if(sr_pair_base(base,"10115_YiSang_Index_FatherAppearance")&&(!strcmp(identity,"story_1347_Index_fatherAppearance")||!strcmp(identity,"story_1348_Index_father_Phase2Appearance"))){
  if(requested>=7&&requested<=16){target=requested;expected=requested==16?1:3;}
 }else if(sr_pair_base(base,"11115_Outis_Middle_FatherAppearance")&&!strcmp(identity,"story_1327_MiddleFinger_fatherAppearance")){
  if(requested==7){target=7;expected=2;}else if(requested==8){target=10;expected=3;}else if(requested==9){target=9;expected=4;}else if(requested==10){target=11;expected=2;}else if(requested==14){target=12;expected=4;}
 }else if(sr_pair_base(base,"11115_Outis_Middle_FatherAppearance")&&!strcmp(identity,"story_1327_MiddleFinger_father_Phase4Appearance")){
  if(requested==11){target=7;expected=2;}else if(requested==12){target=8;expected=5;}else if(requested==13){target=9;expected=5;}else if(requested==16){target=11;expected=1;}
 }else if(sr_pair_base(base,"11116_Outis_Wedge_OscarAppearance")&&!strcmp(identity,"story_1583_OscarAppearance")){
  static const int targets[]={7,10,9,8,11};
  static const int lengths[]={3,2,1,2,3};
  if(requested>=7&&requested<=11){target=targets[requested-7];expected=lengths[requested-7];}
 }else if(sr_pair_base(base,"10316_Donquixote_WedgeAppearance")&&!strcmp(identity,"story_1585_PamelaAppearance")){
  static const int lengths[]={2,2,3,2,3,3};
  if(requested>=7&&requested<=12){target=requested;expected=lengths[requested-7];}
 }else if(sr_pair_base(base,"11017_Sinclair_WedgeAppearance")&&!strcmp(identity,"story_1584_PamelyAppearance")){
  static const int lengths[]={2,3,4,3,4};
  if(requested>=7&&requested<=11){target=requested;expected=lengths[requested-7];}
 }else if(sr_pair_base(base,"10216_Faust_YunaAppearance")&&!strcmp(identity,"story_1581_YunaAppearance")){
  static const int lengths[]={3,0,5,2,5,5,2};
  if(requested>=7&&requested<=13&&lengths[requested-7]){target=requested;expected=lengths[requested-7];}
 }else if(sr_pair_base(base,"10715_Heathcliff_MiddleFinger_RicardoAppearance")&&(!strcmp(identity,"story_8099_MiddleFinger_RicardoAppearance")||!strcmp(identity,"story_8099_MiddleFinger_Ricardo_2Appearance"))){
  if(requested==7){target=7;expected=3;}
 }else if(sr_pair_base(base,"10614_Honglu_RingFinger_FatherAppearance")&&!strcmp(identity,"story_1331_RingFinger_FatherAppearance")){
  if(requested==11||requested==13){target=requested;expected=requested==11?1:2;}
 }else if(sr_pair_base(base,"10716_Heathcliff_Thumb_DiscipleAppearance")&&!strcmp(identity,"story_1306_Thumb_DiscipleAppearance")){
  static const int lengths[]={2,3,3,4,2};
  if(requested>=7&&requested<=11){target=requested;expected=lengths[requested-7];}
 }
 return target>=0&&counts[target]==expected?target:fallback;
}

/* Candidate: concatenate Salvador S3 and S4 two-clip attack groups. */
static int sr_salvador_s3(const int *counts,const char *base,const char *identity,int source,int coin,int *detail,int *index){
 if(!counts||!sr_pair_base(base,"11216_Gregor_SalvadorAppearance")||!identity||strcmp(identity,"story_1580_SalvadorAppearance")||(source!=9&&source!=10)||coin<0||coin>3||counts[9]!=2||counts[10]!=2)return 0;
 *detail=coin<2?9:10; *index=coin%2; return 1;
}
static int sr_preserve_oscar_link_index(const char *base,const char *identity,int requested,int target,int index,int count){
 return sr_pair_base(base,"11116_Outis_Wedge_OscarAppearance")&&identity&&!strcmp(identity,"story_1583_OscarAppearance")&&requested==11&&target==11&&count==3&&index>=0&&index<count;
}
/* Serialized story metadata may cover only a subset of a boss prefab.
   Never select an attack that has no validated metadata contract. */
static void sr_story_attack_mask(int *counts,const unsigned char *allowed){
 if(!counts||!allowed)return;
 for(int d=0;d<SR_MOTION_CACHE;d++)if(((d>=7&&d<=16)||(d>=24&&d<=34))&&!allowed[d])counts[d]=0;
}
/* Story counts have already been masked by the verified metadata contract. */
static int sr_verified_attack_count(const int *counts){
 int n=0;if(!counts)return 0;
 for(int d=7;d<=16;d++)if(counts[d]>0)n++;
 for(int d=24;d<=34;d++)if(counts[d]>0)n++;
 return n;
}
static int sr_prewarm_attacks_valid(const int *counts,int story){
 if(!counts)return 0;
 return story?sr_verified_attack_count(counts)>0:counts[7]>0&&counts[8]>0&&counts[9]>0;
}
/* A special motion number belongs to its source identity. A donor having
   the same number does not make that motion the same skill. */
static int sr_donor_tier_detail(const int *counts,int requested,int tier){
 if(!counts||tier<1||tier>3)return requested;
 if(counts[6+tier]>0)return 6+tier;
 if(requested>=0&&requested<SR_MOTION_CACHE&&counts[requested]>0)return requested;
 /* Enemy appearances can have fewer skill tiers than sinners. Select only
    a real cached attack; source timing remains in ProjectionContext. */
 for(int d=7;d<=16;d++)if(counts[d]>0)return d;
 for(int d=24;d<=34;d++)if(counts[d]>0)return d;
 return requested;
}
/* Prefer an available timeline set that covers the source skill's coin count.
   Preserve the ordinary donor choice when it already covers the skill. */
static int sr_donor_coin_fit(const int *counts,int fallback,int coins){
 if(!counts||coins<1||coins>128||fallback<0||fallback>=SR_MOTION_CACHE)return fallback;
 if(counts[fallback]>=coins)return fallback;
 int best=fallback,bestCount=counts[fallback];
 for(int d=7;d<SR_MOTION_CACHE;d++){
  if(!((d<=16)||(d>=24&&d<=34)))continue;
  int n=counts[d];if(n<=0)continue;
  if(bestCount>=coins){if(n>=coins&&n<bestCount){best=d;bestCount=n;}}
  else if(n>bestCount){best=d;bestCount=n;}
 }
 return best;
}
/* Cached native GetMotion result; only trust a verified playable target. */
static int sr_native_motion_detail(const int *counts,const int *resolved,int requested,int fallback){
 /* A chosen donor skill detail must not be replaced by a source identity's
    coincidentally equal special-motion number. Resolve the donor request. */
 int request=fallback!=requested?fallback:requested;
 if(counts&&resolved&&request>=0&&request<SR_MOTION_CACHE){
  int d=resolved[request];if(((d>=7&&d<=16)||(d>=24&&d<=34))&&counts[d]>0)return d;
 }
 return fallback;
}
static int sr_attack_detail(int detail,int known,int skillMotion,int defense,int intro){
 if(intro)return 0;
 if((detail>=7&&detail<=16)||(detail>=24&&detail<=34))return 1;
 return known&&!defense&&detail>=20&&detail<=22&&detail==skillMotion;
}
/* Never invent a motion or return a fallback for an unknown skill tier. */
static int sr_playback_detail(const int *counts,int original,int tier){
 if(!counts||original<0||original>=SR_MOTION_CACHE)return original;
 if(counts[original]>0)return original;
 if(tier>=1&&tier<=3&&counts[6+tier]>0)return 6+tier;
 return original;
}
static int sr_playback_index(int index,int count,int last){
 if(count<=0||index<0)return index;
 if(last)return count-1;
 return index>=0?index%count:index;
}
/* Same resolver for motion queries and playback; no managed calls or scans. */
static int sr_resolve_attack(const int *counts,int detail,int known,int tier,int skillMotion,int defense,int intro){
 if(!sr_attack_detail(detail,known,skillMotion,defense,intro))return detail;
 return sr_playback_detail(counts,detail,known?tier:0);
}
#endif



