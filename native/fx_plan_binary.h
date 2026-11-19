#ifndef FX_PLAN_BINARY_H
#define FX_PLAN_BINARY_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <math.h>
#define FX_PLAN_MAX_ROWS 256
#define FX_PLAN_MAX_BYTES (1024u*1024u)
#define FX_PLAN_MAX_DEPTH 16
#define FX_PLAN_STRINGS 11
#define FX_PLAN_FIXED 192

typedef struct {
 int32_t detail,part,clip_index;
 uint8_t depth;
 double original_start,new_start;
 uint8_t game_sha256[32],bundle_sha256[32],bundle_key[32],script_sha256[32],script_key[32];
 uint32_t track_path[FX_PLAN_MAX_DEPTH];
 char strings[FX_PLAN_STRINGS][256];
} FxPlanRow;
static uint32_t fx_le32(const unsigned char *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static uint16_t fx_le16(const unsigned char *p){return (uint16_t)(p[0]|((uint16_t)p[1]<<8));}
static int fx_plan_parse(const unsigned char *bytes,size_t length,FxPlanRow *rows,size_t capacity,size_t *out_count){
 if(out_count)*out_count=0;
 if(!bytes||!rows||!out_count||length<12||length>FX_PLAN_MAX_BYTES||memcmp(bytes,"FXP2",4)||fx_le32(bytes+4)!=2)return 0;
 uint32_t count=fx_le32(bytes+8);if(count>FX_PLAN_MAX_ROWS||count>capacity)return 0;
 size_t off=12;
 for(uint32_t i=0;i<count;i++){
  if(length-off<FX_PLAN_FIXED)return 0;
  FxPlanRow *r=&rows[i];memset(r,0,sizeof(*r));
  r->detail=(int32_t)fx_le32(bytes+off);r->part=(int32_t)fx_le32(bytes+off+4);r->clip_index=(int32_t)fx_le32(bytes+off+8);r->depth=bytes[off+12];
  if(r->detail<0||r->part<0||r->clip_index<0||!r->depth||r->depth>FX_PLAN_MAX_DEPTH||bytes[off+13]||bytes[off+14]||bytes[off+15])return 0;
  memcpy(&r->original_start,bytes+off+16,8);memcpy(&r->new_start,bytes+off+24,8);
  if(!isfinite(r->original_start)||!isfinite(r->new_start)||r->original_start<0||r->new_start<0)return 0;
  memcpy(r->game_sha256,bytes+off+32,32);memcpy(r->bundle_sha256,bytes+off+64,32);memcpy(r->bundle_key,bytes+off+96,32);memcpy(r->script_sha256,bytes+off+128,32);memcpy(r->script_key,bytes+off+160,32);off+=FX_PLAN_FIXED;
  if(length-off<(size_t)r->depth*4)return 0;
  for(int j=0;j<r->depth;j++){r->track_path[j]=fx_le32(bytes+off);if(r->track_path[j]>0x7fffffffU)return 0;off+=4;}
  for(int j=0;j<FX_PLAN_STRINGS;j++){
   if(length-off<2)return 0;uint16_t n=fx_le16(bytes+off);off+=2;
   if((!n&&j!=7)||n>255||length-off<n||memchr(bytes+off,0,n))return 0;
   memcpy(r->strings[j],bytes+off,n);r->strings[j][n]=0;off+=n;
  }
  for(uint32_t k=0;k<i;k++){
   FxPlanRow *a=&rows[k];
   if(a->detail==r->detail&&a->part==r->part&&a->clip_index==r->clip_index&&a->depth==r->depth&&
      !memcmp(a->track_path,r->track_path,r->depth*sizeof(uint32_t))&&!strcmp(a->strings[0],r->strings[0])&&
      !strcmp(a->strings[1],r->strings[1])&&!strcmp(a->strings[3],r->strings[3]))return 0;
  }
 }
 if(off!=length)return 0;*out_count=count;return 1;
}
#endif
