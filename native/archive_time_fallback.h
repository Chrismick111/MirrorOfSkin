#pragma pack(push,1)
typedef struct {int32_t detail,index,count;double value;char name[128];} ArchiveTimeEntry;
typedef struct {uint32_t magic;char look[96];uint32_t count;} ArchiveTimeHeader;
#pragma pack(pop)
static int archive_fill_missing(TimeRecord *r,void *app){
 if(!r||!app)return 0;
 uint64_t hash=1469598103934665603ull;for(const unsigned char *c=(const unsigned char *)r->look;*c;c++){hash^=*c;hash*=1099511628211ull;} wchar_t dir[32768],path[32768];GetModuleFileNameW(g_self,dir,32768);wchar_t *slash=wcsrchr(dir,L'\\');if(!slash)return 0;slash[1]=0;_snwprintf(path,32768,L"%lsarchive-times-candidate\\%016llx.bin",dir,(unsigned long long)hash);
 HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);if(f==INVALID_HANDLE_VALUE)return 0;
 DWORD got=0;ArchiveTimeHeader h;int added=0;
 if(!ReadFile(f,&h,sizeof(h),&got,NULL)||got!=sizeof(h)||h.magic!=0x31585441||!memchr(h.look,0,96)||strcmp(h.look,r->look)||h.count>4096){CloseHandle(f);return 0;}
 void *list=rfield(app,"motionList");int n=list?list_count(list):0;
 for(uint32_t i=0;i<h.count;i++){
  ArchiveTimeEntry e;if(!ReadFile(f,&e,sizeof(e),&got,NULL)||got!=sizeof(e))break;
  if(e.detail<0||e.detail>=128||e.index<0||e.index>=32||e.count<=e.index||e.count>32||!memchr(e.name,0,128)||!isfinite(e.value)||e.value<=0||e.value>600||r->seconds[e.detail][e.index]>0)continue;
  void *motion=NULL;int found=0;
  for(int j=0;j<n;j++){void *m=list_item(list,j);int d=-1,c=timeline_count(m,&d);if(d==e.detail){motion=m;found++;if(c!=e.count)motion=NULL;}}
  if(found!=1||!motion)continue;
  void *arr=rfield(motion,"timelineAssets"),*tl=arr?list_item(arr,e.index):NULL;void *getter=tl?find_method(ui_class(tl),"get_name",0):NULL;int ok=0;void *name=getter?call_obj(getter,tl,NULL,&ok):NULL;char text[128];
  if(ok&&string_ascii(name,text,128)&&!strcmp(text,e.name)){r->seconds[e.detail][e.index]=e.value;added++;}
 }
 CloseHandle(f);if(added){char msg[160];snprintf(msg,sizeof(msg),"archive time fallback look=%.95s segments=%d",r->look,added);bootlog(msg);}
 return added;
}

