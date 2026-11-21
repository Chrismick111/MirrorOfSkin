#ifndef VISIBLE_RESOLVE_H
#define VISIBLE_RESOLVE_H
#include <string.h>
typedef struct {void *(*original)(void *,int,void *);void *(*lookup)(void *);void *(*base)(void *);void *(*visible)(void *);int (*valid_skin)(void *,void *);int (*scope)(void *);} VisibleResolveOps;
static void *visible_resolve(const VisibleResolveOps *o,void *caller,int id,void *mi,int enabled){
 void *result=o->original(caller,id,mi);
 if(!enabled||!result||!o->scope(caller))return result;
 void *u=o->lookup(result);if(!u||o->base(u)!=result)return result;
 void *shown=o->visible(u);if(!shown||shown==result||o->lookup(shown)!=u||!o->valid_skin(u,shown))return result;
 return shown;
}
#endif
