#ifndef WEDGE_UNITY_PNG_QUEUE_H
#define WEDGE_UNITY_PNG_QUEUE_H
#include "unity_png_factory.h"
#define URQ_MAX_CAPACITY 4096
typedef struct {UrImage image;uint64_t generation;int used;} UrQueueSlot;
typedef struct {UrQueueSlot *slots;size_t capacity;uint64_t next;int poisoned;} UrQueue;
typedef struct {int index;uint64_t generation;} UrToken;
typedef enum {URQ_REJECTED,URQ_READY,URQ_RETRY_RELEASE,URQ_CAPACITY_EXHAUSTED,URQ_ORPHANED} UrQueueResult;
/* Caller owns zeroed storage for the queue lifetime; live storage is never
   overwritten by initialization. */
static int urq_init(UrQueue*q,UrQueueSlot*storage,size_t capacity){
 if(!q||q->slots||!storage||!capacity||capacity>URQ_MAX_CAPACITY)return 0;
 for(size_t i=0;i<capacity;i++)if(storage[i].used||storage[i].image.texture||storage[i].image.sprite||storage[i].image.texture_root||storage[i].image.sprite_root||storage[i].image.orphaned)return 0;
 q->slots=storage;q->capacity=capacity;q->next=0;return 1;
}
/* Reserve capacity before creating anything, including failed creations. Caller
   retains queue until every slot is successfully released on Unity thread. */
static UrQueueResult urq_create(UrQueue*q,const UrOps*o,void*c,const UrMethods*m,const void*png,size_t n,int flip,uint32_t w,uint32_t h,float px,float py,float ppu,UrToken*token){
 if(!q||!q->slots||q->poisoned||!o||!o->is_unity_thread||!o->is_unity_thread(c)||!token)return URQ_REJECTED;
 size_t i;for(i=0;i<q->capacity;i++)if(!q->slots[i].used)break;if(i==q->capacity)return URQ_CAPACITY_EXHAUSTED;if(q->next==UINT64_MAX)return URQ_REJECTED;
 UrQueueSlot *s=&q->slots[i];s->used=1;s->generation=++q->next;*token=(UrToken){(int)i,s->generation};
 if(up_create(o,c,m,png,n,flip,w,h,px,py,ppu,&s->image))return URQ_READY;
 if(s->image.orphaned){q->poisoned=1;return URQ_ORPHANED;}
 if(s->image.sprite||s->image.texture||s->image.sprite_root||s->image.texture_root)return URQ_RETRY_RELEASE;
 s->used=0;*token=(UrToken){-1,0};return URQ_REJECTED;
}
static int urq_release(UrQueue*q,const UrOps*o,void*c,UrToken token){
 if(!q||!q->slots||!o||!o->is_unity_thread||!o->is_unity_thread(c)||token.index<0||(size_t)token.index>=q->capacity)return 0;
 UrQueueSlot*s=&q->slots[token.index];if(!s->used||s->generation!=token.generation)return 0;
 if(!ur_release(o,c,&s->image))return 0;s->used=0;return 1;
}
#endif
