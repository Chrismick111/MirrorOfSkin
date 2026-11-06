#ifndef SR_FORM_CATALOG_H
#define SR_FORM_CATALOG_H
#include <string.h>
typedef struct { const char *identity, *look, *asset; } SrFormResource;
static const SrFormResource sr_forms[] = {
  {"10215","10215_Faust_Ring_Disciple_CastOffAppearance","SD_Personality/10215_Faust_Ring_Disciple_CastOffAppearance.prefab"},
  {"10314","10314_Donquixote_Index_Disciple_AwakenAppearance","SD_Personality/10314_Donquixote_Index_Disciple_AwakenAppearance.prefab"},
  {"10401","10401_Ryoshu_Base_CP9Appearance","SD_Personality/10401_Ryoshu_Base_CP9Appearance.prefab"},
  {"10701","10701_Heathclif_Base_C6Appearance","SD_Personality/10701_Heathclif_Base_C6Appearance.prefab"},
  {"10710","10710_Heathclif_WHunt_RideAppearance","SD_Personality/10710_Heathclif_WHunt_RideAppearance.prefab"},
  {"10915","10915_Rodion_RingFinger_FauvismeDocent_MaskAppearance","SD_Personality/10915_Rodion_RingFinger_FauvismeDocent_MaskAppearance.prefab"},
  {"11009","11009_Sinclair_Philip_AwakenAppearance","SD_Personality/11009_Sinclair_Philip_AwakenAppearance.prefab"},
  {"11016","11016_Sinclair_Buffet_PerfectAppearance","SD_Personality/11016_Sinclair_Buffet_PerfectAppearance.prefab"},
};
static int sr_form_index(const char *identity){
 if(identity)for(unsigned i=0;i<sizeof(sr_forms)/sizeof(sr_forms[0]);i++)if(!strcmp(identity,sr_forms[i].identity))return (int)i;
 return -1;
}
#endif
