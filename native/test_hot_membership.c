#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"
int main(void){
 g_rowCount=2;memset(g_rows,0,sizeof(g_rows));
 g_rows[0].sinner=101;strcpy(g_rows[0].identity,"10101");strcpy(g_rows[0].asset_key,"a");strcpy(g_rows[0].appearance_name,"A");
 g_rows[1].sinner=102;g_rows[1].story=1;strcpy(g_rows[1].identity,"boss");strcpy(g_rows[1].asset_key,"b");strcpy(g_rows[1].appearance_name,"B");
 PoolRow rows[3];memcpy(rows,g_rows,sizeof(PoolRow)*2);rows[2]=g_rows[1];rows[2].sinner=101;rows[2].weight=7;
 assert(hot_pool_compatible(rows,3));rows[2].asset_key[0]='x';assert(!hot_pool_compatible(rows,3));rows[2]=g_rows[1];rows[2].sinner=101;
 assert(!hot_pool_compatible(rows,1));rows[2].identity[0]='x';assert(!hot_pool_compatible(rows,3));
 puts("PASS cross-role Boss addition, retained row identity, unknown resource rejection");return 0;
}