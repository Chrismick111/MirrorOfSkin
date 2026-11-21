#ifndef WEDGE_PAIR_TIMELINE_IDENTITY_H
#define WEDGE_PAIR_TIMELINE_IDENTITY_H
#include <string.h>
static int outis_follower_role(int motion,int id){
 if(motion==15)return id==11216;
 if(motion!=11&&motion!=12&&motion!=16)return 0;
 return id==10316||id==11017||(motion!=11&&(id==10216||id==11216));
}
static int outis_visual_asset(int motion,int part,const char *name){
 static const char *three[]={"11116_S5_Link_01","11116_S5_Link_02","11116_S5_Link_03"};
 static const char *five[]={"11116_S10_Link_01","11116_S10_Link_02","11116_S10_Link_03"};
 static const char *six[]={"11116_S6_Link_01","11116_S6_Link_02","11116_S6_Link_03"};
 if(!name||part<0)return 0;
 if(motion==15)return part==0&&!strcmp(name,"11116_S9_Link");
 return part<3&&((motion==11&&!strcmp(name,three[part]))||(motion==12&&!strcmp(name,six[part]))||(motion==16&&!strcmp(name,five[part])));
}
static int pair_partner_identity(const char *base){
 if(!base||strlen(base)<5||(base[5]&&base[5]!='_'))return 0;
 if(!strncmp(base,"10316",5))return 11017;
 if(!strncmp(base,"11017",5))return 10316;
 return 0;
}
/* BindFollowers receives the solo S1/S3 motion when a cosmetic partner is
   present in _candidates but the game's native presentation mask is zero. */
static int pair_visual_motion(const char *base,int bound,int requested){
 if(bound!=requested||!pair_partner_identity(base))return -1;
 if(requested==7)return 10;
 if(requested==9)return 11;
 if(requested>=10&&requested<=12)return requested;
 return -1;
}
/* Asset identities verified in the local 2026-11-12 appearance exports.
   Classification alone does not prove live action ownership or authorize a
   timeline substitution. Reject unknown names and ordinary S3 timelines. */
static int pair_timeline_identity(const char *base,const char *name){
 static const char *don[]={"10316_S1_Link_01 1","10316_S1_Link_02 1","10316_S3_Link_01 1","10316_S3_Link_02 1","10316_S3_Link_03 1","10316_S4_Link_01","10316_S4_Link_03","10316_S4_Link_04"};
 static const char *sin[]={"11017_S1_Link_01 1","11017_S1_Link_01 2","11017_S1_Link_01 3","11017_S3_Link_01 1","11017_S3_Link_02 1","11017_S3_Link_03 1","11017_S3_Link_04 1","11017_S4_Link_01","11017_S4_Link_02","11017_S4_Link_03_1","11017_S4_Link_04_1"};
 if(!base||!name||strlen(base)<5||(base[5]&&base[5]!='_'))return 0;
 const char **list=0;unsigned count=0;
 if(!strncmp(base,"10316",5)){list=don;count=sizeof(don)/sizeof(don[0]);}
 else if(!strncmp(base,"11017",5)){list=sin;count=sizeof(sin)/sizeof(sin[0]);}
 for(unsigned i=0;i<count;i++)if(!strcmp(name,list[i]))return 1;
 return 0;
}
#endif
