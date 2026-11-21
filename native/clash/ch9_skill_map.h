/* Generated from game skill definitions, localized skill names and native enemy slots. */
#ifndef CH9_SKILL_MAP_H
#define CH9_SKILL_MAP_H
#include <string.h>
typedef struct {int id; const char *look; int source,target;} Ch9SkillMapping;
static const Ch9SkillMapping ch9BySkill[]={
 {1011505,"1347_Index_fatherAppearance",9,7},
 {1021501,"1319_RingFinger_DiscipleAppearance",7,7},
 {1021501,"1336_RingFinger_Disciple_CastoffAppearance",7,7},
 {1021502,"1319_RingFinger_DiscipleAppearance",8,10},
 {1021503,"1319_RingFinger_DiscipleAppearance",9,11},
 {1021505,"1319_RingFinger_DiscipleAppearance",7,7},
 {1021505,"1336_RingFinger_Disciple_CastoffAppearance",7,7},
 {1021507,"1336_RingFinger_Disciple_CastoffAppearance",9,11},
 {1031401,"1325_Index_Disciple_NormalAppearance",7,7},
 {1031401,"1325_Index_discipleAppearance",7,7},
 {1031406,"1325_Index_Disciple_NormalAppearance",8,8},
 {1031406,"1325_Index_discipleAppearance",8,8},
 {1031407,"1325_Index_Disciple_NormalAppearance",9,9},
 {1031407,"1325_Index_discipleAppearance",9,9},
 {1041501,"1322_Pinky_Father2pAppearance",7,8},
 {1041501,"1322_Pinky_FatherAppearance",7,8},
 {1041503,"1322_Pinky_FatherAppearance",9,11},
 {1041506,"1322_Pinky_Father2pAppearance",10,12},
 {1041508,"1322_Pinky_FatherAppearance",15,15},
 {1061401,"1331_RingFinger_FatherAppearance",7,8},
 {1061402,"1331_RingFinger_FatherAppearance",8,9},
 {1061403,"1331_RingFinger_FatherAppearance",9,10},
 {1061407,"1331_RingFinger_FatherAppearance",10,13},
 {1061408,"1331_RingFinger_FatherAppearance",13,7},
 {1071601,"1306_Thumb_DiscipleAppearance",7,7},
 {1071602,"1306_Thumb_DiscipleAppearance",8,8},
 {1071603,"1306_Thumb_DiscipleAppearance",9,9},
 {1071604,"1306_Thumb_DiscipleAppearance",11,11},
 {1071606,"1306_Thumb_DiscipleAppearance",10,10},
 {1081401,"1328_MiddleFinger_discipleAppearance",7,8},
 {1081402,"1328_MiddleFinger_discipleAppearance",8,10},
 {1081403,"1328_MiddleFinger_discipleAppearance",9,11},
 {1091601,"1314_Thumb_FatherAppearance",7,7},
 {1091603,"1314_Thumb_FatherAppearance",9,12},
 {1091605,"1314_Thumb_FatherAppearance",11,9},
 {1091606,"1314_Thumb_FatherAppearance",12,10},
 {1091607,"1314_Thumb_FatherAppearance",13,13},
 {1101503,"1318_Pinky_DiscipleAppearance",9,13},
 {1111501,"1327_MiddleFinger_fatherAppearance",7,7},
 {1111501,"1327_MiddleFinger_father_Phase4Appearance",7,7},
 {1111503,"1327_MiddleFinger_fatherAppearance",9,9},
 {1111503,"1327_MiddleFinger_father_Phase4Appearance",9,9},
 {1111506,"1327_MiddleFinger_fatherAppearance",12,8},
 {1111506,"1327_MiddleFinger_father_Phase4Appearance",12,8},
 {1111507,"1327_MiddleFinger_fatherAppearance",13,9},
 {1111507,"1327_MiddleFinger_father_Phase4Appearance",13,9},
};
static const Ch9SkillMapping ch9ByIdentity[]={
 {10215,"1319_RingFinger_DiscipleAppearance",7,7},
 {10215,"1336_RingFinger_Disciple_CastoffAppearance",7,7},
 {10415,"1322_Pinky_Father2pAppearance",7,8},
 {10415,"1322_Pinky_Father2pAppearance",10,12},
 {10415,"1322_Pinky_FatherAppearance",7,8},
 {10415,"1322_Pinky_FatherAppearance",9,11},
 {10415,"1322_Pinky_FatherAppearance",15,15},
 {10614,"1331_RingFinger_FatherAppearance",7,8},
 {10614,"1331_RingFinger_FatherAppearance",8,9},
 {10614,"1331_RingFinger_FatherAppearance",9,10},
 {10614,"1331_RingFinger_FatherAppearance",10,13},
 {10614,"1331_RingFinger_FatherAppearance",13,7},
 {10716,"1306_Thumb_DiscipleAppearance",7,7},
 {10716,"1306_Thumb_DiscipleAppearance",8,8},
 {10716,"1306_Thumb_DiscipleAppearance",9,9},
 {10716,"1306_Thumb_DiscipleAppearance",10,10},
 {10716,"1306_Thumb_DiscipleAppearance",11,11},
 {10814,"1328_MiddleFinger_discipleAppearance",7,8},
 {10814,"1328_MiddleFinger_discipleAppearance",8,10},
 {10916,"1314_Thumb_FatherAppearance",7,7},
 {10916,"1314_Thumb_FatherAppearance",9,12},
 {10916,"1314_Thumb_FatherAppearance",11,9},
 {10916,"1314_Thumb_FatherAppearance",12,10},
 {10916,"1314_Thumb_FatherAppearance",13,13},
 {11015,"1318_Pinky_DiscipleAppearance",9,13},
 {11115,"1327_MiddleFinger_fatherAppearance",7,7},
 {11115,"1327_MiddleFinger_fatherAppearance",12,8},
 {11115,"1327_MiddleFinger_father_Phase4Appearance",7,7},
 {11115,"1327_MiddleFinger_father_Phase4Appearance",12,8},
};
static int ch9_mapped_slot(const Ch9SkillMapping *rows,size_t count,int id,const char *look,int source){
 if(!look)return -1;
 if(!strncmp(look,"story_",6))look+=6;
 for(size_t i=0;i<count;i++)
  if(rows[i].id==id&&rows[i].source==source&&!strcmp(rows[i].look,look))return rows[i].target;
 return -1;
}
static int ch9_exact_motion(int playerSkill,const char *donorLook,int sourceDetail){
 return ch9_mapped_slot(ch9BySkill,sizeof(ch9BySkill)/sizeof(*ch9BySkill),playerSkill,donorLook,sourceDetail);
}
static int ch9_unambiguous_motion(int identity,const char *donorLook,int sourceDetail){
 return ch9_mapped_slot(ch9ByIdentity,sizeof(ch9ByIdentity)/sizeof(*ch9ByIdentity),identity,donorLook,sourceDetail);
}
#endif
