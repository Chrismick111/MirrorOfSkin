#ifndef SR_WORKBENCH_FORMS_H
#define SR_WORKBENCH_FORMS_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define SR_WF_MAGIC 0x31464657u
#define SR_WF_MAX 256
typedef struct {uint32_t identity,mode;int32_t threshold;uint32_t stage,compare,reserved[3];} SrWfRule;
typedef struct {uint32_t revision,count;SrWfRule rules[SR_WF_MAX];} SrWfConfig;
static int sr_wf_has_override(const SrWfConfig *cfg,uint32_t id){
 if(cfg)for(uint32_t i=0;i<cfg->count;i++)if(cfg->rules[i].identity==id)return cfg->rules[i].mode!=0;
 return 0;
}
static int sr_wf_parse(SrWfConfig *out,const void *bytes,size_t size){
 if(!out||!bytes||size<16)return 0;
 uint32_t h[4];memcpy(h,bytes,16);
 if(h[0]!=SR_WF_MAGIC||h[1]!=1||h[3]>SR_WF_MAX||size!=16+(size_t)h[3]*32)return 0;
 SrWfConfig next={0};next.revision=h[2];next.count=h[3];
 for(uint32_t i=0;i<h[3];i++){
  SrWfRule *r=&next.rules[i];memcpy(r,(const char *)bytes+16+i*32,32);
  if(!r->identity||r->mode>4||r->stage>31||r->compare>1||r->reserved[0]||r->reserved[1]||r->reserved[2])return 0;
  if(r->mode==1&&(r->threshold<1||r->threshold>65535))return 0;
  if(r->mode==2&&(r->threshold< -45||r->threshold>45))return 0;
  if(r->mode==3&&(r->threshold<0||r->threshold>100))return 0;
  for(uint32_t j=0;j<i;j++)if(next.rules[j].identity==r->identity)return 0;
 }
 *out=next;return 1;
}
static int sr_wf_stage(const SrWfConfig *cfg,uint32_t id,int native,int stages,unsigned defenses,int mp,int mpValid,int hp,int maxhp){
 if(!cfg||stages<1)return native;
 const SrWfRule *r=NULL;for(uint32_t i=0;i<cfg->count;i++)if(cfg->rules[i].identity==id){r=&cfg->rules[i];break;}
 if(!r||!r->mode)return native;
 int cap=stages-1,stage=(int)r->stage;if(stage>cap)stage=cap;
 if(r->mode==1){unsigned n=defenses/(unsigned)r->threshold;return n<(unsigned)stage?(int)n:stage;}
 if(r->mode==4)return stage;
 int pass;
 if(r->mode==2){if(!mpValid||mp< -45||mp>45)return native;pass=r->compare?mp<=r->threshold:mp>=r->threshold;}
 else {if(maxhp<=0||hp<0||hp>maxhp)return native;int64_t a=(int64_t)hp*100,b=(int64_t)maxhp*r->threshold;pass=r->compare?a<=b:a>=b;}
 return pass?stage:0;
}
#ifdef SR_WORKBENCH_FORMS_WINDOWS
#include <windows.h>
#include <wchar.h>
static SrWfConfig g_workbenchForms;
static void sr_wf_poll(HMODULE module){
 static DWORD at;static FILETIME stamp;static DWORD previousSize=0;DWORD now=GetTickCount();if((DWORD)(now-at)<500)return;at=now;
 wchar_t path[32768];if(!GetModuleFileNameW(module,path,32768))return;wchar_t *slash=wcsrchr(path,L'\\');if(!slash)return;lstrcpyW(slash+1,L"workbench_forms.bin");
 HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);if(f==INVALID_HANDLE_VALUE)return;
 DWORD size=GetFileSize(f,NULL),got=0;FILETIME writeTime;unsigned char bytes[16+SR_WF_MAX*32];
 if(!GetFileTime(f,NULL,NULL,&writeTime)){CloseHandle(f);return;}
 if(size==previousSize&&CompareFileTime(&writeTime,&stamp)==0){CloseHandle(f);return;}
 if(size<=sizeof(bytes)&&ReadFile(f,bytes,size,&got,NULL)&&got==size&&sr_wf_parse(&g_workbenchForms,bytes,size)){
  stamp=writeTime;previousSize=size;
#ifdef SR_WF_LOG
  char line[128];snprintf(line,sizeof(line),"workbench forms loaded revision=%lu rules=%lu",(unsigned long)g_workbenchForms.revision,(unsigned long)g_workbenchForms.count);SR_WF_LOG(line);
#endif
 }
 CloseHandle(f);
}
#endif
#endif
