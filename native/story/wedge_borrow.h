#ifndef WEDGE_BORROW_H
#define WEDGE_BORROW_H
#include <string.h>
typedef struct {void *receiver,*base;int detail,hits;} WedgeBorrow;
static int wedge_borrow_allowed(const char *base,const char *identity,int detail,const void *receiver,const void *original){return base&&identity&&!strncmp(base,"11116",5)&&(base[5]==0||base[5]=='_')&&(detail==15||detail==16||(detail==11&&strcmp(identity,"story_1583_OscarAppearance")))&&receiver&&original&&receiver!=original;}
static int wedge_borrow_index(int index,int count,int last){if(count<=0||index<0)return -1;if(index<count)return index;return last?count-1:-1;}
static int wedge_borrow_match(const WedgeBorrow *b,const void *receiver,int detail){return b&&b->receiver==receiver&&b->base&&b->detail==detail;}
#endif
