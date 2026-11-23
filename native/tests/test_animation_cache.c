#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "sinners_native.c"
static void save_fixture(const char *name,double duration){
 TimeRecord r={0};r.magic=0x31435441;strcpy(r.look,name);r.seconds[9][0]=duration;
 uint64_t h=1469598103934665603ull;for(const unsigned char *c=(const unsigned char *)name;*c;c++){h^=*c;h*=1099511628211ull;}
 wchar_t dir[32768],file[32768];GetModuleFileNameW(NULL,dir,32768);wchar_t *end=wcsrchr(dir,92);assert(end);end[1]=0;lstrcatW(dir,L"animation-times-f0caf8bf");CreateDirectoryW(dir,NULL);
 _snwprintf(file,32768,L"%ls/%016llx.bin",dir,(unsigned long long)h);
 HANDLE f=CreateFileW(file,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);assert(f!=INVALID_HANDLE_VALUE);DWORD n;assert(WriteFile(f,&r,sizeof(r),&n,NULL)&&n==sizeof(r));CloseHandle(f);
}
int main(void){
 g_self=GetModuleHandleW(NULL);api=NULL;
 save_fixture("test-source",1);save_fixture("test-donor",2);
 TimeRecord *a=time_record(NULL,"test-source");assert(a&&a->seconds[9][0]==1);
 assert(time_record(NULL,"test-source")==a&&g_timeCount==1);
 TimeRecord *b=time_record(NULL,"test-donor");assert(b&&g_timeCount==2);
 static Unit u;static Skin skin;strcpy(u.baseName,"test-source");strcpy(skin.look,"test-donor");
 assert(cached_time_ratio(&u,&skin,9,9,0,0)==2);
 a->seconds[9][0]=4;assert(cached_time_ratio(&u,&skin,9,9,0,0)==0.5);
 assert(cached_time_ratio(&u,&skin,9,9,32,0)==0);
 assert(time_record(NULL,NULL)==NULL);
 HeapFree(GetProcessHeap(),0,a);HeapFree(GetProcessHeap(),0,b);g_timeCount=0;
 a=time_record(NULL,"test-source");assert(a&&a->seconds[9][0]==1);
 ImportedConfig oldConfig={0},newConfig={0};
 strcpy(oldConfig.timingKey,"WBImp_same_look-old");
 strcpy(newConfig.timingKey,"WBImp_same_look-new");
 save_fixture(oldConfig.timingKey,3);save_fixture(newConfig.timingKey,5);
 skin.imported=&oldConfig;assert(cached_time_ratio(&u,&skin,9,9,0,0)==3);
 skin.imported=&newConfig;assert(cached_time_ratio(&u,&skin,9,9,0,0)==5);
 skin.imported=&oldConfig;assert(cached_time_ratio(&u,&skin,9,9,0,0)==3);
 puts("PASS same imported look retains per-bundle cached timing across revisions");
 puts("PASS persisted cache read without any IL2CPP API, memory reuse, fresh-session reuse, acceleration, deceleration and index bounds");return 0;
}

