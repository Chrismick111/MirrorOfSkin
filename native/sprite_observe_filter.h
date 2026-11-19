#ifndef SPRITE_OBSERVE_FILTER_H
#define SPRITE_OBSERVE_FILTER_H
#include <string.h>
static int sprite_observe_target(const char *base,const char *look){
 return base&&look&&!strncmp(base,"10315",5)&&(base[5]==0||base[5]=='_')&&strstr(look,"Sancho")!=0;
}
#endif
