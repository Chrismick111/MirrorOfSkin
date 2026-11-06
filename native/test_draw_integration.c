#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"
int main(void){
 Unit *u=&g_units[0];u->sinner=101;u->ncand=3;g_rowCount=3;
 for(int i=0;i<3;i++){u->cand[i]=i;g_rows[i].enabled=1;g_rows[i].weight=1;}
 drawModes[0][0]=1;drawModes[0][1]=2;drawModes[0][2]=2;
 assert(unit_draw(u,2,0)==0);assert(unit_draw(u,2,0)==1);
 assert(unit_draw(u,8,0)==0);assert(unit_draw(u,1,0)==0);
 assert(unit_draw(u,2,0)==2);assert(unit_draw(u,2,0)==0);
 assert(unit_draw(u,8,0)==1);assert(unit_draw(u,1,0)==1);
 g_rows[2].excluded=8;assert(unit_draw(u,8,0)==0);
 g_rows[1].weight=0;assert(unit_draw(u,1,0)==0);
 candidateOrderCount=3;candidateOrder[0]=2;candidateOrder[1]=0;candidateOrder[2]=1;for(int i=0;i<3;i++){g_rows[i].sinner=101;g_rows[i].weight=1;}u->skins[0].row=1;rebuild_candidates(u);assert(u->cand[0]==2&&u->cand[1]==0&&u->cand[2]==1&&u->skins[0].row==1);assert(unit_draw(u,1,0)==2);Unit fresh={0};fresh.sinner=101;rebuild_candidates(&fresh);assert(fresh.cand[0]==2);
 puts("PASS real unit_draw action-isolated cycles, round reset, excluded actions and changed weights");return 0;
}
