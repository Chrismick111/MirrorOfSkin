#ifndef SR_PLAYBACK_POLICY
#define SR_PLAYBACK_POLICY
#define SR_MOTION_CACHE 128
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
