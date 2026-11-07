#include "sinners_native.c"
static void *wantApp,*wantRet;static int seen[5],calls;
static void *mock_item(void *ret,void *app,int sd,int dd,int di,int si,uint8_t last,void *mi){
 if(ret!=wantRet||app!=wantApp)return NULL;seen[0]=sd;seen[1]=dd;seen[2]=di;seen[3]=si;seen[4]=last;calls++;return ret;
}
int main(void){
 Config cfg={0};cfg.enabled=1;cfg.heartbeat=GetTickCount();g_cfg=&cfg;g_quitting=0;
 unsigned char result[40]={0};wantRet=result;wantApp=(void*)0x1234;orig_motionAnimItem=mock_item;
 g_projection=(ProjectionContext){wantApp,9,3};
 if(motion_anim_item_hook(result,wantApp,7,8,2,1,1,NULL)!=result||calls!=1||seen[0]!=9||seen[1]!=8||seen[2]!=2||seen[3]!=3||seen[4]!=1)return 1;
 g_projection.sourceIndex=-1;
 if(motion_anim_item_hook(result,wantApp,7,8,2,-2,0,NULL)!=result||seen[3]!=-2)return 2;
 g_projection.app=(void*)0x5678;
 if(motion_anim_item_hook(result,wantApp,7,8,2,1,0,NULL)!=result||seen[0]!=7||seen[3]!=1)return 3;
 puts("PASS sret buffer, source projection, donor arguments, sentinel and nonmatching context");return 0;
}
