/* Immutable timeline durations, keyed by appearance; pinned game build only. */
#define TC_COINS 32
#define TC_MAX 512
typedef struct {uint32_t magic;char look[96];double seconds[128][TC_COINS];} TimeRecord;
static TimeRecord *g_timeRecords[TC_MAX];static int g_timeCount;
static TimeRecord *time_record(void *app,const char *look){
 if(!look)return NULL;
 for(int i=0;i<g_timeCount;i++)if(!strcmp(g_timeRecords[i]->look,look))return g_timeRecords[i];
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
   if(valid){g_timeRecords[g_timeCount++]=r;bootlog("animation cache hit; timeline scan skipped");return r;}
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
 if(!valid){HeapFree(GetProcessHeap(),0,r);return NULL;}
 _snwprintf(temp,32768,L"%ls.tmp",path);f=CreateFileW(temp,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
 if(f!=INVALID_HANDLE_VALUE){DWORD written;int ok=WriteFile(f,r,sizeof(*r),&written,NULL)&&written==sizeof(*r);CloseHandle(f);if(ok)MoveFileExW(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);}
 g_timeRecords[g_timeCount++]=r;char line[160];snprintf(line,sizeof(line),"animation cache scanned look=%.95s timelines=%d",look,valid);bootlog(line);return r;
}
static double cached_time_ratio(Unit *u,Skin *skin,int detail,int mapped,int source,int donor){
 if(!u||!skin||detail<0||detail>=128||mapped<0||mapped>=128||source<0||source>=TC_COINS||donor<0||donor>=TC_COINS)return 0;
 TimeRecord *a=time_record(u->baseApp,u->baseName),*b=time_record(skin->app,skin->look);
 double src=a?a->seconds[detail][source]:0,dst=b?b->seconds[mapped][donor]:0;
 return src>0&&dst>0?dst/src:0;
}
