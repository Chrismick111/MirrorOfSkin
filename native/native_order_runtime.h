#include <limits.h>
/* Native base BuildMotionOrder is scalar-only in the audited game binary.
   Observation detours forward source arguments/result unchanged. */
#define SR_ORDER_LIMIT 128
#define SR_ORDER_OBSERVATIONS 64
#define SR_ORDER_CACHE 16
typedef struct {void *self;int allCoin,startIndex,motionCount;uint8_t oneBased;unsigned serial;} NativeOrderObservation;
typedef struct {void *action,*viewer;unsigned serial;int donorCount,count,values[SR_ORDER_LIMIT];} NativeOrderCache;
static NativeOrderObservation native_order_observations[SR_ORDER_OBSERVATIONS];
static unsigned native_order_serial;
static NativeOrderCache native_order_cache[SR_UNIT_MAX][SR_ORDER_CACHE];
static void *native_order_methods[4],*native_order_originals[4];
static void native_order_record(void *self,int allCoin,int startIndex,int motionCount,uint8_t oneBased){
 unsigned serial=++native_order_serial;if(!serial)serial=++native_order_serial;
 NativeOrderObservation *r=&native_order_observations[serial%SR_ORDER_OBSERVATIONS];
 *r=(NativeOrderObservation){self,allCoin,startIndex,motionCount,oneBased,serial};
}
static void *native_order_forward(int slot,void *self,int allCoin,int startIndex,int motionCount,uint8_t oneBased,void *mi){
 void *result=((void *(*)(void *,int,int,int,uint8_t,void *))native_order_originals[slot])(self,allCoin,startIndex,motionCount,oneBased,mi);
 native_order_record(self,allCoin,startIndex,motionCount,oneBased);return result;
}
#define SR_ORDER_HOOK(N) static void *native_order_hook##N(void *self,int a,int b,int c,uint8_t d,void *mi){return native_order_forward(N,self,a,b,c,d,mi);}
SR_ORDER_HOOK(0) SR_ORDER_HOOK(1) SR_ORDER_HOOK(2) SR_ORDER_HOOK(3)
static void *native_order_detours[]={native_order_hook0,native_order_hook1,native_order_hook2,native_order_hook3};
static int native_order_value(const int *values,int count,int coin,int *out){
 if(!values||!out||coin<0||coin>=count||count<1||count>SR_ORDER_LIMIT)return 0;
 if(values[coin]==INT_MIN)return 0;
 *out=values[coin]-1;return 1;
}
static int native_order_index(Unit *u,void *action,int coin,int donorCount,int *index){
 if(!u||!u->observedViewer||u->observedAction!=action||coin<0||donorCount<=0||!native_order_originals[0])return 0;
 void *viewer=rfield(u->observedViewer,"_skillViewBase");if(!viewer)return 0;
 NativeOrderObservation *obs=NULL;
 for(int i=0;i<SR_ORDER_OBSERVATIONS;i++)if(native_order_observations[i].self==viewer&&(!obs||native_order_observations[i].serial>obs->serial))obs=&native_order_observations[i];
 if(!obs||obs->allCoin<=0||obs->allCoin>SR_ORDER_LIMIT||coin>=obs->allCoin)return 0;
 int unit=(int)(u-g_units);if(unit<0||unit>=SR_UNIT_MAX)return 0;
 NativeOrderCache *cache=NULL;
 for(int i=0;i<SR_ORDER_CACHE;i++){
  NativeOrderCache *c=&native_order_cache[unit][i];
  if(c->action==action&&c->viewer==viewer&&c->serial==obs->serial&&c->donorCount==donorCount){cache=c;break;}
 }
 if(!cache){
  cache=&native_order_cache[unit][donorCount%SR_ORDER_CACHE];memset(cache,0,sizeof(*cache));
  void *list=((void *(*)(void *,int,int,int,uint8_t,void *))native_order_originals[0])(viewer,obs->allCoin,obs->startIndex,donorCount,1,native_order_methods[0]);
  uintptr_t root=ui_root(list);if(!root)return 0;
  int count=list_count(list);void *items=rfield(list,"_items");
  if(count!=obs->allCoin||count<1||count>SR_ORDER_LIMIT||!items){ui_unroot(root);return 0;}
  uintptr_t length=*(uintptr_t *)((char *)items+24);if(length<(unsigned)count){ui_unroot(root);return 0;}
  memcpy(cache->values,(char *)items+32,(size_t)count*sizeof(int));ui_unroot(root);
  cache->action=action;cache->viewer=viewer;cache->serial=obs->serial;cache->donorCount=donorCount;cache->count=count;
  char line[192];snprintf(line,sizeof(line),"native order policy=base allCoin=%d startIndex=%d donorCount=%d sourceOverride=%d",obs->allCoin,obs->startIndex,donorCount,obs->motionCount);bootlog(line);
 }
 if(coin>=cache->count)return 0;
 return native_order_value(cache->values,cache->count,coin,index);
}
