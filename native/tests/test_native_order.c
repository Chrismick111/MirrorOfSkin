#undef NDEBUG
#include <assert.h>
#include "sinners_native.c"
static void *owner=(void*)0x1234,*result=(void*)0x5678;static int calls;
static void *mock_order(void *self,int a,int b,int c,uint8_t d,void *mi){
 if(self!=owner||a!=3||b!=0||c!=2||d!=1||mi!=(void*)0x9)return NULL;calls++;return result;
}
static void test_chapter_repeated_parts(void){
 Unit *unit=&g_units[0];
 int action,next_action,part;
 for(int coin=0;coin<3;coin++){
  part=0;
  assert(chapter_replay_avoid(unit,&action,coin,9,&part,3,0)==(coin!=0));
  assert(part==coin);
  part=0;
  assert(chapter_replay_avoid(unit,&action,coin,9,&part,3,0)==(coin!=0));
  assert(part==coin);
 }
 part=0;
 assert(!chapter_replay_avoid(unit,&action,3,9,&part,3,1)&&part==0);
 assert(!chapter_replay_avoid(unit,&action,3,8,&part,3,0)&&part==0);
 assert(!chapter_replay_avoid(unit,&next_action,1,9,&part,3,0)&&part==0);
 assert(!chapter_replay_avoid(unit,&next_action,2,0,&part,3,0)&&part==0);
}
int main(void){
 test_chapter_repeated_parts();
 for(int i=0;i<4;i++){native_order_originals[i]=mock_order;if(native_order_forward(i,owner,3,0,2,1,(void*)0x9)!=result)return 1;}
 if(calls!=4)return 2;
 NativeOrderObservation *o=&native_order_observations[native_order_serial%SR_ORDER_OBSERVATIONS];
 if(o->self!=owner||o->allCoin!=3||o->startIndex!=0||o->motionCount!=2||o->oneBased!=1)return 3;
 /* Actual base native BuildMotionOrder(3,0,2,true) observed from audited body. */
 int nativeValues[]={-1,1,2},idx=99;
 if(!native_order_value(nativeValues,3,0,&idx)||idx!=-2)return 4;
 if(!native_order_value(nativeValues,3,1,&idx)||idx!=0)return 5;
 if(!native_order_value(nativeValues,3,2,&idx)||idx!=1)return 6;
 if(native_order_value(nativeValues,3,3,&idx))return 7;
 puts("PASS source BuildMotionOrder forwarding all four hooks, scalar capture, native one-based indexes and negative sentinels");return 0;
}
