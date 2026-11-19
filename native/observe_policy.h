#ifndef WEDGE_OBSERVE_POLICY_H
#define WEDGE_OBSERVE_POLICY_H
typedef struct {void (*observe)(void*,int);unsigned char (*original)(void*);} ObservePolicy;
static unsigned char observe_policy_run(void *ctx,int enabled,const ObservePolicy*ops){
 if(enabled)ops->observe(ctx,0);unsigned char ret=ops->original(ctx);if(enabled)ops->observe(ctx,1);return ret;
}
#endif
