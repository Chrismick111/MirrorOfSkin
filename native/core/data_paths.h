#ifndef SR_DATA_PATHS_H
#define SR_DATA_PATHS_H
#include <windows.h>
#include <stdio.h>
/* User data and generated caches live in the launcher-owned MOS_data folder.
   The module directory remains a fallback for old installations. */
static void sr_data_path(HMODULE module,wchar_t *out,size_t cap,const wchar_t *name){
 wchar_t base[32768];DWORD n=GetEnvironmentVariableW(L"APPDATA",base,32768);
 if(out&&cap&&n>0&&n<32768){
  int len=_snwprintf(out,cap,L"%ls\\FaustLauncher\\MOS_data\\%ls",base,name);
  if(len>0&&(size_t)len<cap)return;
 }
 if(out&&cap&&module&&GetModuleFileNameW(module,out,(DWORD)cap)){
  wchar_t *slash=wcsrchr(out,L'\\');
  if(slash&&(size_t)(slash+1-out)+wcslen(name)+1<=cap)lstrcpyW(slash+1,name);
  else out[0]=0;
 }else if(out&&cap)out[0]=0;
}
#endif
