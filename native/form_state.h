#ifndef SR_FORM_STATE_H
#define SR_FORM_STATE_H
#include <stdint.h>
#include <string.h>

/* Pure appearance policy. Never applies combat passives or changes model stats.
   Events must be observations of the deployed unit, not donor callbacks. */
typedef struct {
 unsigned evades;
 int index_awake, kcorp_helmet;
 uint64_t last_round;
 int round_seen;
} SrFormState;
static void sr_form_evade(SrFormState *s){
 if(s && s->evades<65535u)s->evades++;
}
static void sr_form_round(SrFormState *s,uint64_t round,int mp,int valid){
 if(!s || (s->round_seen&&s->last_round==round))return;
 s->round_seen=1;s->last_round=round;
 if(!valid||mp < -45||mp > 45)return;
 if(!s->evades){s->index_awake=0;return;}
 if(mp>=25)s->index_awake=1;
 else if(mp<=0)s->index_awake=0;
}
static void sr_form_survived_hit(SrFormState *s,int hp,int maxhp){
 if(s&&hp>0&&maxhp>0&&hp<=maxhp && (int64_t)hp*5<=maxhp)s->kcorp_helmet=1;
}
static int sr_form_stage(const SrFormState *s,const char *id,int stages,int mp,int mp_valid){
 if(!s||!id||stages<2)return 0;
 if(!strcmp(id,"10314"))return s->index_awake?1:0;
 if(!strcmp(id,"10605"))return s->kcorp_helmet?1:0;
 /* Sanity at the original round boundary is supplied by the caller. */
 if(!strcmp(id,"10312")||!strcmp(id,"10913"))return mp_valid&&mp>=-45&&mp<=45&&mp<0?1:0;
 if(!strcmp(id,"11009"))return mp_valid&&mp==45?1:0;
 unsigned cap=(unsigned)(stages-1);
 return (int)(s->evades<cap?s->evades:cap);
}
#endif
