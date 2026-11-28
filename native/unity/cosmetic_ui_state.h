#ifndef COSMETIC_UI_STATE_H
#define COSMETIC_UI_STATE_H

#include <stddef.h>

typedef enum { COSMETIC_UI_KEEP, COSMETIC_UI_APPLY, COSMETIC_UI_RESTORE } CosmeticUIChange;

static CosmeticUIChange cosmetic_ui_change(const void *current,const void *owned,const void *replacement){
 if(replacement)return current==replacement?COSMETIC_UI_KEEP:COSMETIC_UI_APPLY;
 return owned&&current==owned?COSMETIC_UI_RESTORE:COSMETIC_UI_KEEP;
}

static int cosmetic_ui_tier(int model_tier,int display_tier){
 if(model_tier>=1&&model_tier<=3)return model_tier;
 return display_tier>=1&&display_tier<=3?display_tier:0;
}

#endif
