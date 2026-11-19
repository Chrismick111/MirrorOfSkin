#ifndef SR_CHAPTER_FORMS_H
#define SR_CHAPTER_FORMS_H
#include <string.h>

enum SrChapterSignal { CH_NONE, CH_MASK, CH_SWORD, CH_WIRE, CH_ECHO, CH_EYE, CH_AURA, CH_DON, CH_FAUST };
typedef struct {const char *id; enum SrChapterSignal signal;} SrChapterSignalOwner;
static enum SrChapterSignal sr_chapter_signal(const char *base,const char *group){
 static const SrChapterSignalOwner owners[]={{"10115",CH_MASK},{"11115",CH_SWORD},{"10814",CH_WIRE},
  {"10314",CH_DON},{"10215",CH_FAUST},{"10415",CH_ECHO},{"10916",CH_EYE},{"11015",CH_AURA}};
 if(!base||!group||strncmp(group,"ch9_",4))return CH_NONE;
 for(unsigned i=0;i<sizeof(owners)/sizeof(owners[0]);i++){
  if((!strncmp(group+4,owners[i].id,5)&&(!group[9]||!strcmp(group+9,"_alt")))&&!strncmp(base,owners[i].id,5)&&(base[5]==0||base[5]=='_'))return owners[i].signal;
 }
 return CH_NONE;
}
static int sr_chapter_buff_rank(enum SrChapterSignal s,const char *key,int stack){
 if(s==CH_DON&&!strcmp(key,"Blandishment"))return 1;
 if(s==CH_FAUST&&!strcmp(key,"SilverOpportunity"))return 1;
 if(s==CH_MASK&&!strcmp(key,"BurningWoundYisang"))return 1;
 if(s==CH_WIRE&&!strcmp(key,"HeatingWireIshmael"))return stack>=1;
 if(s==CH_ECHO&&!strcmp(key,"SojiRyoshuEchoPast"))return stack>=5;
 if(s==CH_EYE&&!strcmp(key,"FutureEyeOffRodion"))return 1;
 if(s==CH_SWORD){
  if(!strcmp(key,"MiddleFatherSwordFourOutis"))return 3;
  if(!strcmp(key,"MiddleFatherSwordThreeOutis"))return 2;
  if(!strcmp(key,"MiddleFatherSwordTwoOutis"))return 1;
 }
 return 0;
}
typedef struct {const char *look,*klass;int count;} SrChapterVisual;
static const SrChapterVisual *sr_chapter_visual(const char *look){
 static const SrChapterVisual list[]={
  {"story_1327_MiddleFinger_fatherAppearance","CharacterAppearanceUB_a1c9p2_1",3},
  {"story_1328_MiddleFinger_discipleAppearance","CharacterAppearanceUB_1328",2},
  {"story_1318_Pinky_DiscipleAppearance","CharacterAppearanceUB_1318",2},
  {"story_1314_Thumb_FatherAppearance","CharacterAppearanceUB_1314",2}
 };
 if(look)for(unsigned i=0;i<sizeof(list)/sizeof(list[0]);i++)if(!strcmp(look,list[i].look))return &list[i];
 return NULL;
}
#endif
