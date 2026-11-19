#ifndef FOLLOWERS_OBSERVE_H
#define FOLLOWERS_OBSERVE_H
typedef struct {int (*count)(void *); void *(*item)(void *,int); void (*log)(void *,int,int,void *); void (*original)(void *);} FollowersOps;
static void followers_run(void *ctx, FollowersOps *ops) {
 for(int phase=0;phase<2;phase++){
  if(phase==1)ops->original(ctx);
  int n=ops->count(ctx);int limit=n<0?0:(n>8?8:n);
  for(int i=0;i<limit;i++)ops->log(ctx,phase,i,ops->item(ctx,i));
  ops->log(ctx,phase,-1,(void *)(intptr_t)n);
 }
}
#endif

