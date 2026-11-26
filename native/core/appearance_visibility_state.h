#ifndef SR_APPEARANCE_VISIBILITY_STATE_H
#define SR_APPEARANCE_VISIBILITY_STATE_H
/* A game-owned hide of the selected donor must not be undone by the idle
   visibility repair. The game can explicitly show it again, or select a
   different appearance. Plugin-owned changes are deliberately ignored. */
static void sr_visibility_event(void **hidden, void *selected, void *changed,
                                int active, int plugin_change){
 if(!hidden||plugin_change||!changed)return;
 if(active){if(*hidden==changed)*hidden=0;}
 else if(selected==changed)*hidden=changed;
}
static void sr_visibility_selection(void **hidden,void *selected){
 if(hidden&&*hidden&&*hidden!=selected)*hidden=0;
}
static int sr_visibility_suspended(void *hidden,void *selected){
 return hidden&&hidden==selected;
}
/* Unknown state leaves the last confirmed decision intact. */
static int sr_retreat_next(int previous,int observed){
 return observed==0||observed==1?observed:previous;
}
static int sr_retreat_hide_ready(int viewer,int busy,unsigned elapsed){
 return (!viewer&&!busy)||elapsed>=5000u;
}
#endif
