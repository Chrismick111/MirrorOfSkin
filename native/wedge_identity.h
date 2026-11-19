#ifndef SR_WEDGE_IDENTITY_H
#define SR_WEDGE_IDENTITY_H
#include "playback_policy.h"

static const struct { const char *base, *appearance; int role; } wedge_pairs[] = {
 {"11116_Outis_Wedge_OscarAppearance","story_1583_OscarAppearance",1583},
 {"11017_Sinclair_WedgeAppearance","story_1584_PamelyAppearance",1584},
 {"10316_Donquixote_WedgeAppearance","story_1585_PamelaAppearance",1585}
};
static int wedge_role_id(int role){return role>=1583 && role<=1585;}
/* 1111602 and 1111603 request S2 and S3. RoundEndAction is detail 49. */
static int wedge_stock_detail(int role,int detail){
 return (wedge_role_id(role)&&detail==49)||(role==1583&&(detail==8||detail==9));
}
static int wedge_role(const char *base,const char *appearance){
 if(!appearance)return 0;
 for(unsigned i=0;i<sizeof(wedge_pairs)/sizeof(wedge_pairs[0]);i++)
  if(sr_pair_base(base,wedge_pairs[i].base)&&!strcmp(appearance,wedge_pairs[i].appearance))return wedge_pairs[i].role;
 return 0;
}
static int wedge_native_actor(const char *base){
 for(unsigned i=0;i<sizeof(wedge_pairs)/sizeof(wedge_pairs[0]);i++)
  if(sr_pair_base(base,wedge_pairs[i].base))return 1;
 return sr_pair_base(base,"10216_Faust_YunaAppearance")||sr_pair_base(base,"11216_Gregor_SalvadorAppearance");
}
#endif
