#include "sinners_native.c"
#include <assert.h>
int main(void){Unit u={0};Skin s={0};int out=-1;u.observedAction=(void*)1;strcpy(g_rows[0].appearance_name,"A");strcpy(g_rows[1].appearance_name,"B");int rows[]={0,0,0,1,1,0},want[]={0,1,0,0,1,0};
for(int i=0;i<6;i++){s.row=rows[i];assert(single_skin_cycle_index(&u,&s,i,2,&out)&&out==want[i]);assert(single_skin_cycle_index(&u,&s,i,2,&out)&&out==want[i]);}u.observedAction=(void*)2;u.coinLast=1;assert(single_skin_cycle_index(&u,&s,0,2,&out)&&out==0);for(int i=1;i<5;i++)assert(single_skin_cycle_index(&u,&s,i,2,&out)&&out==i%2);assert(!single_skin_cycle_index(&u,&s,-1,2,&out));puts("PASS repeated donor sequence, switch reset, action reset, same coin dedup and last coin");return 0;}
