#ifndef SR_POOL_V5_H
#define SR_POOL_V5_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <math.h>
#define SR_POOL_V5_MAGIC 0x35505253u
#define SR_POOL_V5_MAX 4096u
typedef struct {
 uint32_t sinner,enabled,excluded,story;
 double weight;
 char identity[64],asset_key[128],appearance_name[64],base_identity[64];
 uint32_t kind;
 char group_id[64];
} SrPoolV5Row;
static int sr_pool_v5_id(const char *p){
 size_t i=0;for(;i<64&&p[i];i++){unsigned char c=(unsigned char)p[i];if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-'))return 0;}return i>0&&i<64;
}
static int sr_pool_v5_key_equal(const SrPoolV5Row *a,const SrPoolV5Row *b){
 return a->sinner==b->sinner&&!strcmp(a->base_identity,b->base_identity)&&!strcmp(a->identity,b->identity)&&a->kind==b->kind&&!strcmp(a->group_id,b->group_id);
}
/* Decode field by field: the wire row has no trailing C alignment padding. */
static int sr_pool_v5_parse(SrPoolV5Row *out,uint32_t capacity,uint32_t *count,const void *data,size_t size){
 uint32_t h[4];if(!out||!count||!data||size<16)return 0;memcpy(h,data,16);
 if(h[0]!=SR_POOL_V5_MAGIC||h[1]!=5||h[2]>SR_POOL_V5_MAX||h[2]>capacity||h[3]!=412||size!=16+(size_t)h[2]*412)return 0;
 const unsigned char *p=(const unsigned char *)data+16;
 for(uint32_t i=0;i<h[2];i++,p+=412){
  SrPoolV5Row r;memset(&r,0,sizeof(r));memcpy(&r,p,344);memcpy(&r.kind,p+344,4);memcpy(r.group_id,p+348,64);
  if(r.sinner<101||r.sinner>112||r.enabled>1||r.story>1||!isfinite(r.weight)||r.weight<0||r.weight>1000000||
     !r.identity[0]||!memchr(r.identity,0,64)||!r.asset_key[0]||!memchr(r.asset_key,0,128)||!r.appearance_name[0]||!memchr(r.appearance_name,0,64)||!memchr(r.base_identity,0,64)||
     (r.kind==0&&r.group_id[0])||(r.kind==1&&!sr_pool_v5_id(r.group_id))||r.kind>1)return 0;
  for(uint32_t j=0;j<i;j++)if(sr_pool_v5_key_equal(&r,&out[j]))return 0;
  out[i]=r;
 }
 *count=h[2];return 1;
}
#endif
