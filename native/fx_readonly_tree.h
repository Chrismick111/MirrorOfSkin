#ifndef FX_READONLY_TREE_H
#define FX_READONLY_TREE_H
#include <stdint.h>
#include <string.h>
/* Caller implements managed access and temporary rooting. No references escape. */
typedef struct { void *(*field)(void*,const char*); int (*count)(void*); void *(*item)(void*,int); uintptr_t (*root)(void*); void (*unroot)(uintptr_t); int (*clip)(void*,const char*,double*); int (*track)(void*); } FxTreeOps;
typedef struct { int tracks,clips,found,invalid; } FxTreeResult;
static void fx_walk_track(const FxTreeOps *o,void *track,const char *target,int depth,void **seen,int *nseen,FxTreeResult *r){
 if(!track||depth>16||*nseen>=512){r->invalid=1;return;}
 for(int i=0;i<*nseen;i++)if(seen[i]==track){r->invalid=1;return;} seen[(*nseen)++]=track;
 uintptr_t tr=o->root(track);if(!tr){r->invalid=1;return;} r->tracks++;
 void *clips=o->field(track,"m_Clips"); if(clips){uintptr_t lr=o->root(clips);if(!lr){r->invalid=1;}else{int n=o->count(clips);if(n<0||n>512)r->invalid=1;else for(int i=0;i<n;i++){void *clip=o->item(clips,i);if(!clip){r->invalid=1;continue;}uintptr_t cr=o->root(clip);if(!cr){r->invalid=1;continue;}double start=0;int match=o->clip(clip,target,&start);if(match<0)r->invalid=1;else{r->clips++;r->found+=match;}o->unroot(cr);}o->unroot(lr);}}
 void *children=o->field(track,"m_Children");if(children){uintptr_t lr=o->root(children);if(!lr)r->invalid=1;else{int n=o->count(children);if(n<0||n>512)r->invalid=1;else for(int i=0;i<n;i++)fx_walk_track(o,o->item(children,i),target,depth+1,seen,nseen,r);o->unroot(lr);}}
 o->unroot(tr);
}
static FxTreeResult fx_read_tree(const FxTreeOps *o,void *timeline,const char *target){
 FxTreeResult r={0};void *seen[512];int nseen=0;if(!o||!timeline||!target){r.invalid=1;return r;}uintptr_t root=o->root(timeline);if(!root){r.invalid=1;return r;}
 void *tracks=o->field(timeline,"m_Tracks");if(!tracks)r.invalid=1;else{uintptr_t lr=o->root(tracks);if(!lr)r.invalid=1;else{int n=o->count(tracks);if(n<0||n>512)r.invalid=1;else for(int i=0;i<n;i++)fx_walk_track(o,o->item(tracks,i),target,0,seen,&nseen,&r);o->unroot(lr);}}o->unroot(root);return r;
}
/* First clip on the first EffectActivateTimelineTrack, used by the observe build
   so that any skill detail can be watched instead of one hard-coded clip. */
static void *fx_first_activate_clip(const FxTreeOps *o,void *node,int depth,void **seen,int *nseen,uintptr_t *held){
 if(!o||!node||!held||depth>16||*nseen>=512)return NULL;
 for(int i=0;i<*nseen;i++)if(seen[i]==node)return NULL; seen[(*nseen)++]=node;
 uintptr_t nr=o->root(node);if(!nr)return NULL;void *found=NULL;
 void *clips=o->field(node,"m_Clips");
 if(clips&&o->track&&o->track(node)){uintptr_t lr=o->root(clips);
  if(lr){int n=o->count(clips);if(n>0&&n<=512){void *c=o->item(clips,0);if(c){uintptr_t cr=o->root(c);if(cr){found=c;*held=cr;}}}o->unroot(lr);}}
 if(!found){void *children=o->field(node,"m_Children");
  if(children){uintptr_t lr=o->root(children);
   if(lr){int n=o->count(children);if(n>=0&&n<=512)for(int i=0;i<n&&!found;i++){void *ch=o->item(children,i);if(ch)found=fx_first_activate_clip(o,ch,depth+1,seen,nseen,held);}o->unroot(lr);}}}
 o->unroot(nr);return found;
}
static void *fx_first_clip_entry(const FxTreeOps *o,void *timeline,uintptr_t *held){
 if(held)*held=0;if(!o||!timeline||!held)return NULL;
 void *seen[512];int nseen=0;void *tracks=o->field(timeline,"m_Tracks");if(!tracks)return NULL;
 uintptr_t lr=o->root(tracks);if(!lr)return NULL;void *found=NULL;int n=o->count(tracks);
 if(n>=0&&n<=512)for(int i=0;i<n&&!found;i++){void *t=o->item(tracks,i);if(t)found=fx_first_activate_clip(o,t,0,seen,&nseen,held);}
 o->unroot(lr);if(!found&&held)*held=0;return found;
}
/* Select explicit root/child indices. Names are not inferred from position. */
static int fx_read_path(const FxTreeOps *o,void *timeline,const int *path,int len,int clip_index,const char *target,double *start,void **retained,uintptr_t *handle){
 if(retained)*retained=NULL;if(handle)*handle=0;if(!o||!timeline||!path||len<1||len>16||clip_index<0||!target||!retained||!handle)return -1;
 uintptr_t roots[36]={0};int nroots=0,result=-1;void *obj=timeline;roots[nroots++]=o->root(obj);if(!roots[0])return -1;
 void *list=o->field(obj,"m_Tracks");
 for(int i=0;i<len;i++){
  if(!list||nroots+2>36)goto done;uintptr_t lr=o->root(list);if(!lr)goto done;roots[nroots++]=lr;
  int n=o->count(list);if(n<0||n>512||path[i]<0||path[i]>=n)goto done;
  obj=o->item(list,path[i]);if(!obj)goto done;uintptr_t tr=o->root(obj);if(!tr)goto done;roots[nroots++]=tr;
  if(i+1<len)list=o->field(obj,"m_Children");
 }
 if(o->track&&!o->track(obj))goto done;list=o->field(obj,"m_Clips");if(!list)goto done;{uintptr_t lr=o->root(list);if(!lr)goto done;roots[nroots++]=lr;int n=o->count(list);if(n<0||n>512||clip_index>=n)goto done;void *clip=o->item(list,clip_index);if(!clip)goto done;uintptr_t cr=o->root(clip);if(!cr)goto done;roots[nroots++]=cr;double value=0;result=o->clip(clip,target,&value);if(result==1&&start){*start=value;*retained=clip;*handle=cr;--nroots;}}
 done: while(nroots)o->unroot(roots[--nroots]);return result;
}

/* Temporary pinned identities for the selected timeline; no Unity API inside getter. */
static int fx_collect_nodes(const FxTreeOps *o,void *track,int depth,void **seen,int *ns,void **clips,uintptr_t *roots,int *nc){
 if(!track||depth>16||*ns>=512)return 0;
 for(int i=0;i<*ns;i++)if(seen[i]==track)return 0;
 seen[(*ns)++]=track;uintptr_t tr=o->root(track);if(!tr)return 0;int ok=1;
 void *list=o->field(track,"m_Clips");if(list){uintptr_t lr=o->root(list);if(!lr)ok=0;else{int n=o->count(list);if(n<0||n>512)ok=0;else for(int i=0;i<n;i++){void *c=o->item(list,i);if(!c||*nc>=512){ok=0;break;}uintptr_t r=o->root(c);if(!r){ok=0;break;}clips[*nc]=c;roots[(*nc)++]=r;}o->unroot(lr);}}
 list=o->field(track,"m_Children");if(list&&ok){uintptr_t lr=o->root(list);if(!lr)ok=0;else{int n=o->count(list);if(n<0||n>512)ok=0;else for(int i=0;i<n;i++)if(!fx_collect_nodes(o,o->item(list,i),depth+1,seen,ns,clips,roots,nc)){ok=0;break;}o->unroot(lr);}}
 o->unroot(tr);return ok;
}
static int fx_collect_timeline(const FxTreeOps *o,void *timeline,void **clips,uintptr_t *roots,int *nc){
 *nc=0;void *seen[512];int ns=0;uintptr_t tr=o->root(timeline);if(!tr)return 0;void *list=o->field(timeline,"m_Tracks");int ok=0;
 if(list){uintptr_t lr=o->root(list);if(lr){int n=o->count(list);if(n>=0&&n<=512){ok=1;for(int i=0;i<n;i++)if(!fx_collect_nodes(o,o->item(list,i),0,seen,&ns,clips,roots,nc)){ok=0;break;}}o->unroot(lr);}}
 o->unroot(tr);if(!ok){while(*nc)o->unroot(roots[--*nc]);}return ok;
}

#endif
