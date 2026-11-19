#ifndef LOADER_PROBE_POLICY_H
#define LOADER_PROBE_POLICY_H
#include <stdint.h>
typedef struct {uint32_t start,last;int active,reported;} LoaderProbe;
static void lp_start(LoaderProbe *p,uint32_t now){p->start=now;p->last=now;p->active=1;p->reported=0;}
static int lp_should(LoaderProbe *p,uint32_t now){if(!p->active||p->reported||(uint32_t)(now-p->last)<250)return 0;p->last=now;return 1;}
static int lp_done(LoaderProbe *p,int done){if(done==1&&!p->reported){p->reported=1;return 1;}return 0;}
static void lp_stop(LoaderProbe *p){p->active=0;}
#endif
