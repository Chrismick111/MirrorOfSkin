#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"
static void *fake_invoke(void *m,void *o,void **a,void **e){(void)m;(void)o;(void)a;*e=NULL;return NULL;}
static void *fake_exception(void *m,void *o,void **a,void **e){(void)m;(void)o;(void)a;*e=(void *)1;return NULL;}
int main(void){
 static void *table[37];api=table;table[API_INVOKE]=fake_invoke;
 assert(call_exc((void *)1,NULL,NULL)==1);
 int ok=1;assert(call_obj((void *)1,NULL,NULL,&ok)==NULL && !ok);
 assert(!call_exc(NULL,NULL,NULL));table[API_INVOKE]=fake_exception;assert(!call_exc((void *)1,NULL,NULL));
 memset(g_units,0,sizeof(g_units));memset(g_rows,0,sizeof(g_rows));
 Unit *u=&g_units[0];u->used=1;u->sinner=101;u->ncand=2;u->cand[0]=0;u->cand[1]=1;
 g_rows[0]=(PoolRow){.sinner=101,.enabled=1,.weight=1};g_rows[1]=(PoolRow){.sinner=101,.enabled=1,.weight=3};
 int counts[2]={0};for(int i=0;i<10000;i++)counts[unit_draw(u,2,(i+.5)/10000.)]++;
 assert(counts[0]==2500 && counts[1]==7500);
 g_rows[0].excluded=1;assert(unit_draw(u,1,0)==1);
 assert(sizeof(Config)==2688 && sizeof(PoolRow)==280);
 g_rowCount=2;m_loadGO=(void *)1;
 q_head=q_tail=0;g_loadActive=1;g_loadUnit=u;g_loadRow=0;
 queue_push(u,0);assert(q_head==q_tail);
 queue_push(u,1);queue_push(u,1);assert(q_tail==1);
 g_loadActive=0;u->skins[0].used=1;u->skins[0].row=1;
 assert(loader_start(u,1)==1 && g_loadActive==0);
 mark_bad(u,1);mark_bad(u,1);assert(u->nbad==1 && unit_draw(u,2,.9)==0);
 Config cfg={0};cfg.max_skins=2;g_cfg=&cfg;assert(skin_limit()==2);
 cfg.max_skins=99;assert(skin_limit()==SR_SKIN_MAX);
 g_rowCount=3;strcpy(g_rows[2].identity,"11009");
 memset(u->skins,0,sizeof(u->skins));u->skins[0].used=u->skins[1].used=1;
 u->skins[0].row=u->skins[1].row=2;u->skins[0].form=0;u->skins[1].form=1;
 u->sanityValid=1;u->sanity=45;u->unavailableForms=0;assert(skin_index(u,2)==1);
 u->sanity=44;assert(skin_index(u,2)==0);
 u->sanity=45;u->unavailableForms=1u<<sr_form_index("11009");assert(skin_index(u,2)==0);
 u->unavailableForms=0;u->sanityValid=0;assert(skin_index(u,2)==0);
 for(unsigned i=0;i<sizeof(sr_forms)/sizeof(sr_forms[0]);i++){
 assert(sr_form_index(sr_forms[i].identity)==(int)i);
 assert(strlen(sr_forms[i].look)<64);
 assert(strstr(sr_forms[i].asset,sr_forms[i].look));
}
assert(sr_form_index("unknown")==-1);
u->sanityValid=1;u->sanity=45;u->unavailableForms=1u<<sr_form_index("10215");
assert(skin_index(u,2)==1); /* A Faust resource failure must not disable Dawn. */
g_rowCount=9;
const char *evadeIds[]={"10215","10314","10710","10915"};
for(int i=0;i<4;i++){
 strcpy(g_rows[3+i].identity,evadeIds[i]);
 u->evaded=0;u->formState.index_awake=0;assert(desired_row_form(u,3+i)==0);
 u->evaded=1;u->formState.index_awake=1;u->unavailableForms=0;assert(desired_row_form(u,3+i)==1);
 disable_failed_form(u,3+i);assert(desired_row_form(u,3+i)==0);
 u->unavailableForms=0;
}
const char *alternates[]={"10401","10701"};
for(int i=0;i<2;i++){
 int row=7+i;strcpy(g_rows[row].identity,alternates[i]);
 selected_row(u,row,0);assert(desired_row_form(u,row)==0);
 selected_row(u,row,2);assert(desired_row_form(u,row)==0);
 selected_row(u,row,0);assert(desired_row_form(u,row)==0);
 selected_row(u,row,2);assert(desired_row_form(u,row)==1);
 selected_row(u,row,2);assert(desired_row_form(u,row)==0);
}
assert(defense_name("Guard"));assert(defense_name("Evade"));assert(defense_name("Counter"));
 assert(!defense_name("Attack"));assert(!defense_name("Counter_Prepare"));
 Unit defender={0};defenseMotions[4]=1;defenseMotions[20]=1;
 observe_defense(&defender,4);assert(defender.formState.evades==1);
 observe_defense(&defender,4);observe_defense(&defender,20);assert(defender.formState.evades==1);
 observe_defense(&defender,0);observe_defense(&defender,20);assert(defender.formState.evades==2);
 observe_defense(&defender,18);defender.coinKnown=1;defender.coinMotion=7;defender.coinDefense=1;
 observe_defense(&defender,7);assert(defender.formState.evades==3);
 observe_defense(&defender,7);assert(defender.formState.evades==3);
 memcpy(reload_rows,g_rows,g_rowCount*sizeof(PoolRow));
 assert(hot_pool_compatible(reload_rows,g_rowCount));
 reload_rows[0].weight=999;assert(hot_pool_compatible(reload_rows,g_rowCount));
 reload_rows[0].weight=-1;assert(!hot_pool_compatible(reload_rows,g_rowCount));
 reload_rows[0].weight=NAN;assert(!hot_pool_compatible(reload_rows,g_rowCount));
 reload_rows[0].weight=0;reload_rows[0].identity[0]='x';assert(!hot_pool_compatible(reload_rows,g_rowCount));
 assert(!hot_pool_compatible(reload_rows,g_rowCount-1));
 puts("PASS hot update validation and regressions, 4 evasion-triggered forms, alternating initial appearances, prefetch exclusion and isolated resource fallback");
}
