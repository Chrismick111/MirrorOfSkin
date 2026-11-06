#ifndef SR_INTERNAL_FORM_POLICY_H
#define SR_INTERNAL_FORM_POLICY_H
#include <string.h>
typedef struct {const char *id;const char *skins[4];int count;} SrInternalForm;
static const SrInternalForm sr_internal_forms[]={
 {"11115",{"weapon1","weapon2","weapon3","weapon4"},4},
 {"10605",{"1_helmet_off","2_helmet_on"},2},
 {"10515",{"off","on"},2},
 {"10412",{"head_off","head_on"},2},
 {"10506",{"off","on"},2},
 {"10703",{"head","helmet"},2},
 {"11113",{"hat_on","hat_off"},2},
 {"11114",{"off","on"},2},
 {"10914",{"off","on"},2},
 {"10513",{"nomal","blood"},2},
 {"10514",{"rifle","shotgun"},2},
 {"10814",{"off","on"},2},
 {"10715",{"off","on"},2},
 {"10615",{"off","on"},2},
 {"10911",{"1","2","3"},3},
 {"11111",{"lv1","lv2","lv3"},3},
 {"11210",{"1","2","3"},3},
 {"10410",{"1st","2nd","3rd"},3}
};
static const SrInternalForm *sr_internal_policy(const char *id){
 if(id)for(unsigned i=0;i<sizeof(sr_internal_forms)/sizeof(sr_internal_forms[0]);i++)if(!strcmp(id,sr_internal_forms[i].id))return &sr_internal_forms[i];
 return 0;
}
#endif
