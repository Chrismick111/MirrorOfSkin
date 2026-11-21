#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"
static PoolRow fixture(const char *id,const char *look){
 PoolRow r={0};r.sinner=101;r.enabled=1;r.weight=1;r.excluded=SR_AUTO_FLAG;
 strcpy(r.identity,id);strcpy(r.appearance_name,look);snprintf(r.asset_key,128,"SD_Personality/%s.prefab",look);return r;
}
int main(void){
 assert(sizeof(SrAutoForm)==840);
 assert(sr_auto_identity(10118,1,"10118_NewAppearance",0));
 assert(!sr_auto_identity(10118,2,"10118_NewAppearance",0));
 assert(!sr_auto_identity(10118,1,"10118_NewAppearance",1));
 assert(!sr_auto_identity(10118,1,"10118_New/Appearance",0));
 char names[5][64]={"default","3rd","1st","2nd"},out[4][64];
 assert(sr_auto_skins(names,4,out)==3&&!strcmp(out[0],"1st")&&!strcmp(out[2],"3rd"));
 strcpy(names[4],"head_on");assert(!sr_auto_skins(names,5,out));
 char pair[2][64]={"on","off"};assert(sr_auto_skins(pair,2,out)==2&&!strcmp(out[0],"off"));
 char gap[2][64]={"1","3"};assert(!sr_auto_skins(gap,2,out));
 memset(g_rows,0,sizeof(g_rows));g_rowCount=2;
 g_rows[0]=fixture("10118","10118_NewAppearance");g_rows[1]=fixture("10119","10119_NextAppearance");
 SrAutoForm p={0};strcpy(p.identity,"10118");p.kind=1;p.count=3;
 strcpy(p.names[0],"10118_NewAppearance");strcpy(p.names[1],"10118_New_Stage1Appearance");strcpy(p.names[2],"10118_New_Stage2Appearance");
 for(unsigned i=0;i<p.count;i++)snprintf(p.assets[i],128,"SD_Personality/%s.prefab",p.names[i]);
 assert(auto_form_valid(&p)&&auto_assign(0,&p));
 Unit u={0};assert(auto_desired(&u,0)==0);sr_form_evade(&u.formState);assert(auto_desired(&u,0)==1);
 sr_form_evade(&u.formState);sr_form_evade(&u.formState);assert(auto_desired(&u,0)==2);
 disable_failed_form(&u,0);assert(auto_desired(&u,0)==0);
 SrAutoForm internal={0};strcpy(internal.identity,"10119");internal.kind=2;internal.count=2;strcpy(internal.names[0],"off");strcpy(internal.names[1],"on");
 assert(auto_form_valid(&internal)&&auto_assign(1,&internal));assert(auto_internal(1)->count==2);
 strcpy(internal.names[1],"arbitrary");assert(!auto_form_valid(&internal));
 PoolRow incoming[3]={g_rows[1],g_rows[0],fixture("10120","10120_LatestAppearance")};incoming[0].weight=0;
 assert(hot_pool_compatible(incoming,3));assert(incoming_for_old[0]==1&&incoming_for_old[1]==0);
 incoming[2].excluded=0;assert(!hot_pool_compatible(incoming,3));incoming[2].excluded=SR_AUTO_FLAG;
 strcpy(incoming[2].identity,"10119");assert(!hot_pool_compatible(incoming,3));
 assert(!hot_pool_compatible(incoming,1));
 strcpy(g_rows[0].identity,"11009");strcpy(p.identity,"11009");assert(!auto_assign(0,&p));
 puts("PASS automatic identity/form schema, complete stage detection, defense progression, failure isolation, stable live row mapping, append validation, explicit policy priority");
}
