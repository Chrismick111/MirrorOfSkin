#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <windows.h>

#include "data_paths.h"
static HMODULE g_self;
#include "imported_skin.h"

static int parse(ImportedConfig *policy,const char *bundle,const char *groups,int invalid){
 char roles[129],animator[129],nativeTiming[129],bytes[2048];
 memset(roles,'0',128);memset(animator,'0',128);memset(nativeTiming,'0',128);
 roles[128]=animator[128]=nativeTiming[128]=0;
 roles[3]='7';animator[3]='1';roles[29]='2';nativeTiming[29]='1';
 if(invalid)nativeTiming[8]='1';
 int length=snprintf(bytes,sizeof(bytes),"WBSKIN1\nSD_Enemy/Source.prefab\nAssets/Prefab/Chosen.prefab\n%s\nSourceAppearance\nOtherAppearance\n%s\n%s\n%s\n%s\n",bundle,roles,animator,nativeTiming,groups);
 return bundled_skin_config_parse(bytes,(size_t)length,policy);
}

static int parse_imported(ImportedConfig *policy,const char *routes){
 char flags[129],bytes[4096];
 memset(flags,'0',128);flags[128]=0;
 int length=snprintf(bytes,sizeof(bytes),
  "WBMOD3\nSD_Abnormality/Source.prefab\nAssets/Prefab/Chosen.prefab\n%064d.bundle\nSourceAppearance\n%s\n%s\nR|0|7,8,9,10,24\nS|%s\n",
  0,flags,flags,routes);
 return imported_config_parse(bytes,(size_t)length,policy);
}

int main(void){
 ImportedConfig policy={0};
 assert(!import_prefab_key("SD_AbnormalityBackup/Source.prefab",0));
 assert(!import_prefab_key("SD_Abnormality/../Source.prefab",0));
 assert(parse(&policy,"AnyPack/Appearance.bundle","R|8,25",0));
 assert(!strcmp(policy.bundlePath,"AnyPack/Appearance.bundle"));
 assert(!strcmp(policy.groupSource,"OtherAppearance"));
 assert(!strcmp(policy.layout,"SourceAppearance"));
 assert(policy.groupCount==2&&policy.groups[0]==8&&policy.groups[1]==25);
 assert(policy.animator[3]&&policy.roles[29]==2&&policy.nativeTiming[29]);
 assert(!parse(&policy,"../Appearance.bundle","R|8,25",0));
 assert(!parse(&policy,"AnyPack/Appearance.bundle","R|8,8",0));
 assert(!parse(&policy,"AnyPack/Appearance.bundle","R|8,29",0));
 assert(!parse(&policy,"AnyPack/Appearance.bundle","R|8,25",1));
 assert(parse(&policy,"Appearance.bundle","-",0)&&!policy.groupCount);
 const char *routes="1234501,2,3,8,0;1234502,2,2,10,0;1234503,2,5,24,0;1234504,1,2,7,0;1234505,2,2,9,1;1234502,2,4,24,0";
 assert(parse_imported(&policy,routes));
 int counts[128]={[7]=2,[8]=3,[9]=2,[10]=2,[24]=5};
 assert(imported_route_select(&policy,counts,1234502,2,3)==10);
 assert(imported_route_select(&policy,counts,1234502,2,4)==24);
 assert(imported_route_select(&policy,counts,770001,2,2)==10);
 assert(imported_route_select(&policy,counts,770001,2,3)==8);
 assert(imported_route_select(&policy,counts,770001,2,5)==24);
 assert(imported_route_select(&policy,counts,770001,1,4)==7);
 assert(imported_route_select(&policy,counts,770001,3,3)==-1);
 counts[10]=0;
 assert(imported_route_select(&policy,counts,770001,2,2)==9);
 assert(!parse_imported(&policy,"1234501,2,3,8,0;1234501,2,3,10,10"));
 assert(!parse_imported(&policy,"1234501,2,129,8,0"));
 assert(!parse_imported(&policy,"1234501,2,128,11,0"));
 assert(!parse_imported(&policy,"1234501,2,128,8,256"));
 assert(!parse_imported(&policy,"2147483648,2,128,8,0"));
 assert(parse_imported(&policy,"2147483647,2,128,8,255"));
 puts("PASS bundled skin policy accepts arbitrary appearances and rejects unsafe or conflicting asset declarations");
}
