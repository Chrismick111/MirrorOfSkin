#ifndef SR_SOURCE_DIAGNOSTICS_H
#define SR_SOURCE_DIAGNOSTICS_H
#include <string.h>
#include <ctype.h>
static int sr_source_diag_name(const char *name){
 if(!name)return 0;char low[256];size_t i=0;for(;i<sizeof(low)-1&&name[i];i++)low[i]=(char)tolower((unsigned char)name[i]);low[i]=0;
 return strstr(low,"buf")||strstr(low,"liberat")||strstr(low,"release")||strstr(low,"stage")||strstr(low,"stack")||strstr(low,"skin")||strstr(low,"appear");
}
#endif
