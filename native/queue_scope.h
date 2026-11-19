#ifndef SR_QUEUE_SCOPE_H
#define SR_QUEUE_SCOPE_H
static int sr_queue_scope(const void *action,const void *viewer,int coin,int tier,const void *liveAction,const void *liveViewer,int liveCoin,int liveTier){
 return action&&viewer&&action==liveAction&&viewer==liveViewer&&coin==liveCoin&&tier==liveTier;
}
#endif
