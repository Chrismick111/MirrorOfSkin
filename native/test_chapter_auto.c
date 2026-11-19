#undef NDEBUG
#include "sinners_native.c"
#include <assert.h>
static void check_short_group(void){
 SYSTEM_INFO system;GetSystemInfo(&system);SIZE_T page=system.dwPageSize;
 char *pages=VirtualAlloc(NULL,2*page,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
 assert(pages);DWORD old;assert(VirtualProtect(pages+page,page,PAGE_NOACCESS,&old));
 char *group=pages+page-sizeof("pair10710"),dest[64];strcpy(group,"pair10710");
 assert(sr_stage_source_commit(dest,0,-1,1,group)&&!strcmp(dest,group));
 VirtualFree(pages,0,MEM_RELEASE);
}
static void check_hunt_pool(Unit *u){
 const SrCounterpartForm *form=sr_counterpart_form("10710");
 assert(form);u->sinner=107;strcpy(u->baseName,form->normal);g_rowCount=3;
 for(int i=0;i<3;i++){
  PoolRow *r=&g_rows[i];memset(r,0,sizeof(*r));r->story=1;r->sinner=107;r->enabled=1;r->weight=1;
  strcpy(r->identity,i==0?form->first:i==1?form->second:"story_8380_SanchoAppearance");
  strcpy(r->appearance_name,r->identity+6);
 }
 rebuild_candidates(u);assert(u->ncand==2&&u->cand[0]==0&&u->cand[1]==1);
 strcpy(u->baseName,form->alternate);rebuild_candidates(u);assert(u->ncand==2);
 strcpy(g_rows[2].base_identity,"10710");rebuild_candidates(u);assert(!u->ncand);
}
int main(int argc,char **argv){
 assert(argc==2);FILE *f=fopen(argv[1],"rb");assert(f);
 static unsigned char bytes[16+SR_SG_MAX*(64+sizeof(SrSgGroup))];
 size_t length=fread(bytes,1,sizeof(bytes),f);fclose(f);
 assert(sr_sg_parse(&g_stageGroups,bytes,length));
 Unit *u=&g_units[0];u->stageWanted=-1;
 unsigned matched=0;
 for(unsigned i=0;i<sizeof(sr_chapter_actors)/sizeof(sr_chapter_actors[0]);i++){
  const SrChapterActor *actor=&sr_chapter_actors[i];
  for(int k=0;k<4&&actor->look[k];k++){
   PoolRow *r=&g_rows[0];g_rowCount=1;memset(r,0,sizeof(*r));r->story=1;
   strcpy(r->appearance_name,actor->look[k]);snprintf(r->identity,sizeof(r->identity),"story_%s",actor->look[k]);
   strcpy(u->baseName,actor->base);stage_commit_source(u,0);
   assert(!strncmp(u->stageSource,"ch9_",4)&&!strncmp(u->stageSource+4,actor->base,5));
   if(!strncmp(r->appearance_name,"135",3))assert(strstr(u->stageSource,"_alt"));
   r->kind=1;strcpy(r->group_id,"merged_fixture");
   assert(!effective_stage_source(u,r));
   strcpy(r->group_id,"my_group");assert(!effective_stage_source(u,r));
   r->kind=0;strcpy(u->baseName,"10501");stage_commit_source(u,0);assert(!u->stageSource[0]);
   strcpy(u->baseName,actor->base);strcpy(r->appearance_name,"8380_SanchoAppearance");
   stage_commit_source(u,0);assert(!u->stageSource[0]);matched++;
  }
 }
 printf("Verified %u exact appearance pairings across 10 personalities\n",matched);
 for(const SrCounterpartForm *form=sr_counterpart_forms;form->normal;form++){
  PoolRow *r=&g_rows[0];memset(r,0,sizeof(*r));r->story=1;
  strcpy(u->baseName,form->normal);
  assert(paired_native_stage(form->normal,form->normal)==0);
  assert(paired_native_stage(form->normal,form->alternate)==1);
  assert(paired_native_stage(form->normal,"unrelated")==-1);
  char observed[144];snprintf(observed,sizeof(observed),"%s(Clone)",form->alternate);
  assert(paired_native_stage(form->normal,observed)==1);
  for(int phase=0;phase<2;phase++){
   strcpy(r->identity,phase?form->second:form->first);
   int reverse=0;
   const SrCounterpart *pair=sr_find_counterpart(form->normal,r->identity,&reverse);
   assert(pair&&!reverse);strcpy(r->appearance_name,pair->story);
   assert(!strcmp(effective_stage_source(u,r),form->group));
   int gi=sr_sg_find_id(&g_stageGroups,form->group);
   assert(gi>=0);SrSgStatus status={0};status.nativeValid=1;status.nativeStage=phase;
   assert(sr_sg_select(&g_stageGroups.group[gi],&status,1-phase)==phase);
   status.nativeValid=0;assert(sr_sg_select(&g_stageGroups.group[gi],&status,phase)==-1);
  }
  strcpy(u->baseName,"10501");assert(!effective_stage_source(u,r));
 }
 check_short_group();check_hunt_pool(u);
 u->sinner=107;g_rowCount=4;memset(g_rows,0,4*sizeof(*g_rows));
 for(unsigned i=0;i<g_rowCount;i++){strcpy(g_rows[i].identity,"fixture");g_rows[i].sinner=107;}
 g_rows[0].sinner=106;g_rows[1].kind=1;strcpy(g_rows[3].base_identity,"10710");
 assert(stage_target_row(u,"fixture","10710")==3);
 assert(stage_target_row(u,"fixture","10701")==2);
 assert(stage_target_row(u,"fixture","")==2);
 assert(stage_target_row(u,"missing","10710")==-1);
 puts("Native phase group names and Wild Hunt candidate selection passed");
 return 0;
}
