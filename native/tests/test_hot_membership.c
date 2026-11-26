#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"

static PoolRow imported_fixture(void){
 PoolRow r={0};r.sinner=101;r.enabled=1;r.weight=1;
 strcpy(r.appearance_name,"WBImp_0123456789abcdef01234567");
 snprintf(r.identity,sizeof(r.identity),"story_%s",r.appearance_name);
 snprintf(r.asset_key,sizeof(r.asset_key),"Imported/%s.prefab",r.appearance_name);
 return r;
}

static int has_candidate(const Unit *u,const char *identity){
 for(int i=0;i<u->ncand;i++)
  if(!strcmp(g_rows[u->cand[i]].identity,identity))return 1;
 return 0;
}

static int replay(const char *appdata,const char *startup,int sinner,const char *base,const char *identity,uint32_t revision){
 assert(SetEnvironmentVariableA("APPDATA",appdata));
 HANDLE f=CreateFileA(startup,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
 assert(f!=INVALID_HANDLE_VALUE);
 assert(pool_read(f,g_rows,&g_rowCount));
 CloseHandle(f);
 uint32_t rowsBefore=g_rowCount;
 static Config config;
 g_cfg=&config;g_cfg->reserved[0]=revision;
 Unit *u=&g_units[0];u->used=1;u->sinner=sinner;
 assert(strlen(base)<sizeof(u->baseName));
 strcpy(u->baseName,base);
 rebuild_candidates(u);
 int candidatesBefore=u->ncand;
 assert(!has_candidate(u,identity));
 reload_probabilities();
 assert(g_cfg->reserved[1]==revision&&g_rowCount>rowsBefore&&has_candidate(u,identity));
 printf("PASS pool replay: rows %lu -> %lu; revision %lu; sinner %d candidates %d -> %d; selected %s\n",
        (unsigned long)rowsBefore,(unsigned long)g_rowCount,(unsigned long)revision,
        sinner,candidatesBefore,u->ncand,identity);
 return 0;
}

int main(int argc,char **argv){
 if(argc!=1){
  if(argc!=7){
   fputs("usage: test_hot_membership [test-appdata startup-snapshot sinner base target-id revision]\n",stderr);
   return 2;
  }
  int sinner=atoi(argv[3]);uint32_t revision=(uint32_t)strtoul(argv[6],NULL,10);
  if(sinner<101||sinner>112||!revision)return 2;
  return replay(argv[1],argv[2],sinner,argv[4],argv[5],revision);
 }
 g_rowCount=2;memset(g_rows,0,sizeof(g_rows));
 g_rows[0].sinner=101;strcpy(g_rows[0].identity,"10101");strcpy(g_rows[0].asset_key,"a");strcpy(g_rows[0].appearance_name,"A");
 g_rows[1].sinner=102;g_rows[1].story=1;strcpy(g_rows[1].identity,"boss");strcpy(g_rows[1].asset_key,"b");strcpy(g_rows[1].appearance_name,"B");
 PoolRow rows[3];memcpy(rows,g_rows,sizeof(PoolRow)*2);rows[2]=g_rows[1];rows[2].sinner=101;rows[2].weight=7;
 assert(hot_pool_compatible(rows,3));rows[2].asset_key[0]='x';assert(!hot_pool_compatible(rows,3));rows[2]=g_rows[1];rows[2].sinner=101;
 assert(!hot_pool_compatible(rows,1));rows[2].identity[0]='x';assert(!hot_pool_compatible(rows,3));
 rows[2]=imported_fixture();
 assert(hot_pool_compatible(rows,3));
 rows[2].enabled=0;rows[2].weight=0;assert(hot_pool_compatible(rows,3));
 rows[2]=imported_fixture();strcpy(rows[2].base_identity,"10115");assert(hot_pool_compatible(rows,3));
 strcpy(rows[2].base_identity,"../10115");assert(!hot_pool_compatible(rows,3));
 rows[2]=imported_fixture();rows[2].story=1;assert(!hot_pool_compatible(rows,3));
 rows[2]=imported_fixture();rows[2].excluded=SR_AUTO_FLAG;assert(!hot_pool_compatible(rows,3));
 rows[2]=imported_fixture();rows[2].kind=1;strcpy(rows[2].group_id,"test");assert(!hot_pool_compatible(rows,3));
 rows[2]=imported_fixture();rows[2].asset_key[0]='i';assert(!hot_pool_compatible(rows,3));
 rows[2]=imported_fixture();rows[2].identity[35]='8';assert(!hot_pool_compatible(rows,3));
 rows[2]=imported_fixture();rows[2].appearance_name[16]='A';assert(!hot_pool_compatible(rows,3));
 rows[2]=imported_fixture();rows[2].appearance_name[29]=0;assert(!hot_pool_compatible(rows,3));
 puts("PASS cross-role Boss addition, retained row identity, canonical imported membership and unknown resource rejection");
 return 0;
}
