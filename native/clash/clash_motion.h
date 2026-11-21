#ifndef SR_CLASH_MOTION_H
#define SR_CLASH_MOTION_H
#include "named_clash_slots.h"
static int sr_clash_role(const char *source,int detail){
 switch(detail){
 case 36:return 1;
 case 37:return 2;
 case 38:case 23:return 3;
 case 17:return 4;
 case 19:return 5;
 case 41:case 42:case 43:return 6;
 }
 for(unsigned i=0;i<sizeof(sr_named_clashes)/sizeof(*sr_named_clashes);i++)
  if(detail==sr_named_clashes[i].detail&&source&&!strcmp(source,sr_named_clashes[i].look))return sr_named_clashes[i].role;
 return 0;
}
static int sr_clash_slot(const char *look,const signed char *available,int requested,int role){
 static const int standard[]={-1,36,37,38,17};
 if(role==7)return requested>=0&&requested<128&&available[requested]>0?requested:-1;
 if(role==6)return -1; /* Choreography requiring a counterpart stays with its source. */
 if(role==5)return available[19]>0?19:sr_clash_slot(look,available,17,4);
 if(role<1||role>4)return -1;
 if(requested>=0&&requested<128&&available[requested]>0&&sr_clash_role(look,requested)==role)return requested;
 if(requested==standard[role]&&available[standard[role]]>0)return standard[role];
 for(int i=0;;i++){
  int d=sr_named_clash_slot(look,role,i);
  if(d<0)break;
  if(available[d]>0)return d;
 }
 /* A neutral clash may stand in for the outcome pose, never for preparation. */
 if(role==2||role==3)return sr_clash_slot(look,available,17,4);
 return -1;
}
#endif
