#ifndef SR_AUTO_POLICY_H
#define SR_AUTO_POLICY_H
#include <stdio.h>
#include <string.h>
#define SR_AUTO_FLAG 0x80000000u
#define SR_AUTO_MAX 512
typedef struct {
 char identity[64];
 unsigned kind,count; /* 1: independent prefabs, 2: single-skeleton stages */
 char names[4][64];
 char assets[4][128];
} SrAutoForm;
static int sr_auto_name(const char *s){
 if(!s||!*s)return 0;
 for(;*s;s++)if(!((*s>='a'&&*s<='z')||(*s>='A'&&*s<='Z')||(*s>='0'&&*s<='9')||*s=='_'))return 0;
 return 1;
}
static int sr_auto_identity(int id,int character,const char *look,int hidden){
 if(hidden||character<1||character>12||id/100!=100+character||!sr_auto_name(look)||strlen(look)>=64)return 0;
 char prefix[8];snprintf(prefix,sizeof(prefix),"%05d_",id);
 return !strncmp(look,prefix,6);
}
/* Accept complete, unambiguous stage sets only. Never alphabetically sort
   unrelated attachments or combine head/weapon skins by guessing. */
static int sr_auto_skins(char names[][64],int n,char out[4][64]){
 memset(out,0,4*64);
 const char *pairs[][2]={{"off","on"},{"head_off","head_on"},{"hat_on","hat_off"},{"head","helmet"},{"rifle","shotgun"},{"nomal","blood"}};
 char filtered[4][64];int count=0;
 for(int i=0;i<n;i++){
  if(!strcmp(names[i],"default"))continue;
  if(!sr_auto_name(names[i])||count==4)return 0;
  for(int j=0;j<count;j++)if(!strcmp(filtered[j],names[i]))return 0;
  strcpy(filtered[count++],names[i]);
 }
 if(count<2)return 0;
 if(count==2)for(unsigned p=0;p<sizeof(pairs)/sizeof(pairs[0]);p++){
  int a=0,b=0;for(int j=0;j<count;j++){a|=!strcmp(filtered[j],pairs[p][0]);b|=!strcmp(filtered[j],pairs[p][1]);}
  if(a&&b){strcpy(out[0],pairs[p][0]);strcpy(out[1],pairs[p][1]);return 2;}
 }
 const char *numbered[][4]={{"1","2","3","4"},{"1st","2nd","3rd","4th"},{"lv1","lv2","lv3","lv4"}};
 for(int p=0;p<3;p++){
  int good=1;
  for(int i=0;i<count;i++){int found=0;for(int j=0;j<count;j++)found|=!strcmp(filtered[j],numbered[p][i]);if(!found)good=0;}
  if(good){for(int i=0;i<count;i++)strcpy(out[i],numbered[p][i]);return count;}
 }
 return 0;
}
#endif
