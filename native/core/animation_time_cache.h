/* Immutable timeline durations, keyed by appearance; pinned game build only. */
#define TC_COINS 32
#define TC_MAX 4096
typedef struct {uint32_t magic;char look[96];double seconds[128][TC_COINS];} TimeRecord;
static TimeRecord *g_timeRecords[TC_MAX];static unsigned char g_archiveFilled[TC_MAX];static int g_timeCount;
#include "archive_time_fallback.h"
/* Fill absent timings from the currently loaded appearance, retaining cached native values. */
static int time_scan_missing(TimeRecord *r,void *app){
 if(!r||!app)return 0;
 void *list=rfield(app,"motionList");int count=list?list_count(list):0,added=0;
 if(count<0||count>1024)return 0;
 for(int i=0;i<count;i++){
  void *motion=list_item(list,i);int detail=-1,n=timeline_count(motion,&detail);
  if(detail<0||detail>=128||n<0||n>TC_COINS)continue;
  void *assets=rfield(motion,"timelineAssets");
  for(int j=0;j<n;j++){
   if(r->seconds[detail][j]>0)continue;
   void *tl=list_item(assets,j),*m=tl?find_method(ui_class(tl),"get_duration",0):NULL;int ok=0;
   void *box=m?call_obj(m,tl,NULL,&ok):NULL;double value=ok&&box?*(double *)ui_unbox(box):0;
   if(isfinite(value)&&value>0&&value<=600){r->seconds[detail][j]=value;added++;}
  }
 }
 return added;
}
static TimeRecord *time_record(void *app,const char *look){
 if(!look)return NULL;
 for(int i=0;i<g_timeCount;i++)if(!strcmp(g_timeRecords[i]->look,look)){if(app&&!g_archiveFilled[i]){time_scan_missing(g_timeRecords[i],app);archive_fill_missing(g_timeRecords[i],app);g_archiveFilled[i]=1;}return g_timeRecords[i];}
 if(!look||strlen(look)>=96||g_timeCount==TC_MAX)return NULL;
 TimeRecord *r=HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,sizeof(*r));if(!r)return NULL;
 uint64_t hash=1469598103934665603ull;for(const unsigned char *c=(const unsigned char *)look;*c;c++){hash^=*c;hash*=1099511628211ull;}
 wchar_t dir[32768],path[32768],temp[32768];GetModuleFileNameW(g_self,dir,32768);wchar_t *slash=wcsrchr(dir,L'\\');if(!slash){HeapFree(GetProcessHeap(),0,r);return NULL;}slash[1]=0;
 lstrcatW(dir,L"animation-times-f0caf8bf");CreateDirectoryW(dir,NULL);
 _snwprintf(path,32768,L"%ls\\%016llx.bin",dir,(unsigned long long)hash);
 HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);DWORD got=0;
 if(f!=INVALID_HANDLE_VALUE){int ok=GetFileSize(f,NULL)==sizeof(*r)&&ReadFile(f,r,sizeof(*r),&got,NULL)&&got==sizeof(*r);CloseHandle(f);
  if(ok&&r->magic==0x31435441&&!memcmp(r->look,look,strlen(look)+1)){
   int valid=1;for(int d=0;d<128;d++)for(int c=0;c<TC_COINS;c++)if(!isfinite(r->seconds[d][c])||r->seconds[d][c]<0||r->seconds[d][c]>600)valid=0;
   if(valid){time_scan_missing(r,app);archive_fill_missing(r,app);g_archiveFilled[g_timeCount]=app!=NULL;g_timeRecords[g_timeCount++]=r;bootlog("animation cache hit; timeline scan skipped");return r;}
  }
 }
 if(!app){HeapFree(GetProcessHeap(),0,r);return NULL;}
 memset(r,0,sizeof(*r));r->magic=0x31435441;lstrcpynA(r->look,look,96);
 void *list=rfield(app,"motionList");int count=list_count(list),valid=0;
 if(count>=0&&count<=1024)for(int i=0;i<count;i++){
  void *motion=list_item(list,i);int detail=-1,n=timeline_count(motion,&detail);
  if(detail<0||detail>=128||n<0||n>TC_COINS)continue;
  void *assets=rfield(motion,"timelineAssets");
  for(int j=0;j<n;j++){void *tl=list_item(assets,j);if(!tl)continue;
   void *m=find_method(ui_class(tl),"get_duration",0);int ok=1;void *box=m?call_obj(m,tl,NULL,&ok):NULL;
   double value=ok&&box?*(double *)ui_unbox(box):0;
   if(isfinite(value)&&value>0&&value<=600){r->seconds[detail][j]=value;valid++;}
  }
 }
 if(!valid){int supplemented=archive_fill_missing(r,app);if(!supplemented){HeapFree(GetProcessHeap(),0,r);return NULL;}g_archiveFilled[g_timeCount]=1;g_timeRecords[g_timeCount++]=r;bootlog("animation cache supplied by validated archive references");return r;}
 _snwprintf(temp,32768,L"%ls.tmp",path);f=CreateFileW(temp,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
 if(f!=INVALID_HANDLE_VALUE){DWORD written;int ok=WriteFile(f,r,sizeof(*r),&written,NULL)&&written==sizeof(*r);CloseHandle(f);if(ok)MoveFileExW(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);}
 archive_fill_missing(r,app);g_archiveFilled[g_timeCount]=1;g_timeRecords[g_timeCount++]=r;char line[160];snprintf(line,sizeof(line),"animation cache scanned look=%.95s timelines=%d",look,valid);bootlog(line);return r;
}
static double cached_time_ratio(Unit *u,Skin *skin,int detail,int mapped,int source,int donor){
 if(!u||!skin||detail<0||detail>=128||mapped<0||mapped>=128||source<0||source>=TC_COINS||donor<0||donor>=TC_COINS)return 0;
 TimeRecord *a=time_record(u->baseApp,u->baseName),*b=time_record(skin->app,skin->look);
 double src=a?a->seconds[detail][source]:0,dst=b?b->seconds[mapped][donor]:0;
 return src>0&&dst>0?dst/src:0;
}


