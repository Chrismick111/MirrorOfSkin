#ifndef SR_SPECIAL_POLICY
#define SR_SPECIAL_POLICY
#include <string.h>
static int sr_dawn_form(int mp,int valid){return !valid||mp < -45||mp > 45?-1:mp>=45?1:0;}
static int sr_is_scissors_source(const char *name){return name&&!strncmp(name,"10917",5);}
static int sr_scissors_suspend(const char *name,int ready){return sr_is_scissors_source(name)&&!ready;}
static int sr_dawn_spine_name(const char *name,int awake){
 if(!name || !strstr(name,"11009") || !strstr(name,"Philip"))return 0;
 int is_awake=strstr(name,"Awaken")!=NULL;return is_awake==!!awake;
}
#endif
