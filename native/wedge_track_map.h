#ifndef WEDGE_TRACK_MAP_H
#define WEDGE_TRACK_MAP_H
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#define WEDGE_MAP_MAX 512
typedef struct {void *ptr;uintptr_t root;int owner;char path[80];char name[100];} WedgeTrack;
typedef struct {WedgeTrack rows[WEDGE_MAP_MAX];int count;} WedgeMap;
typedef struct {uintptr_t (*root)(void*);void (*unroot)(uintptr_t);void *(*children)(void*);int (*count)(void*);void *(*item)(void*,int);const char *(*name)(void*);} WedgeMapOps;
static void wedge_map_clear(WedgeMap *m,const WedgeMapOps *o){while(m->count){WedgeTrack *x=&m->rows[--m->count];o->unroot(x->root);memset(x,0,sizeof(*x));}}
static int wedge_map_walk(WedgeMap *m,const WedgeMapOps *o,void *node,int owner,const char *path,int depth){
 if(!node||depth>12||m->count>=WEDGE_MAP_MAX)return 0;
 for(int i=0;i<m->count;i++)if(m->rows[i].ptr==node)return 0;
 uintptr_t root=o->root(node);if(!root)return 0;WedgeTrack *row=&m->rows[m->count++];row->ptr=node;row->root=root;
 const char *name=o->name(node);if(!name)return 0;snprintf(row->name,sizeof(row->name),"%s",name);snprintf(row->path,sizeof(row->path),"%s",path);
 if(!strncmp(name,"UnitID_",7)){char *end=NULL;long n=strtol(name+7,&end,10);if(end&&!*end&&n>0&&n<1000000)owner=(int)n;}row->owner=owner;
 void *list=o->children(node);if(!list)return 1;uintptr_t lr=o->root(list);if(!lr)return 0;int n=o->count(list),ok=n>=0&&n<=512;
 for(int i=0;i<n&&ok;i++){char sub[80];int v=snprintf(sub,sizeof(sub),"%s/%d",path,i);if(v<0||v>=(int)sizeof(sub)||!wedge_map_walk(m,o,o->item(list,i),owner,sub,depth+1))ok=0;}
 o->unroot(lr);return ok;
}
static int wedge_map_build(WedgeMap *m,const WedgeMapOps *o,void *list){
 if(!m||!o||!list||m->count)return 0;uintptr_t lr=o->root(list);if(!lr)return 0;int n=o->count(list),ok=n>=0&&n<=512;
 for(int i=0;i<n&&ok;i++){char path[80];snprintf(path,sizeof(path),"%d",i);ok=wedge_map_walk(m,o,o->item(list,i),0,path,0);}
 o->unroot(lr);if(!ok)wedge_map_clear(m,o);return ok;
}
static const WedgeTrack *wedge_map_find(const WedgeMap *m,const void *track){if(m&&track)for(int i=0;i<m->count;i++)if(m->rows[i].ptr==track)return &m->rows[i];return NULL;}
#endif
