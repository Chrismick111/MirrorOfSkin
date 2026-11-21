#ifndef LINK_BODY_PHASE_H
#define LINK_BODY_PHASE_H
#include <string.h>
/* Phase-labelled clips of one appearance can use entirely different bodies. */
static const char *link_phase_digits(const char *clip){
 if(!clip)return NULL;
 const char *p=strstr(clip,"_Phase");
 if(!p)p=strstr(clip,"_phase");
 if(p&&p[6]>='0'&&p[6]<='9')return p+6;
 return NULL;
}
static int link_matching_body_phase(const char *base,const char *candidate){
 const char *a=link_phase_digits(base),*b=link_phase_digits(candidate);
 if(!a||!b)return a==b;
 size_t n=strspn(a,"0123456789");
 return strspn(b,"0123456789")==n&&!strncmp(a,b,n);
}
#endif
