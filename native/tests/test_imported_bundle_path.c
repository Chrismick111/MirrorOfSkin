#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include <windows.h>

#include "data_paths.h"
static HMODULE g_self;
#include "imported_skin.h"
#include "imported_bundle_path.h"

static const wchar_t filename[]=L"BRoland.bundle";
static const wchar_t collection[]=L"\u5916\u6765\u5916\u89c2";
static const wchar_t package[]=L"\u6d4b\u8bd5 \u5305-2";
static const char *look="BRolandBaseAppearance";

static void save(const wchar_t *path,const char *stream,DWORD size){
 HANDLE file=CreateFileW(path,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
 DWORD count=0;
 assert(file!=INVALID_HANDLE_VALUE&&WriteFile(file,stream,size,&count,NULL)&&count==size);
 CloseHandle(file);
}

static DWORD encode(const wchar_t *input,char *bytes){
 int count=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,input,-1,bytes,512,NULL,NULL);
 assert(count>0);
 return (DWORD)count-1;
}

int main(void){
 wchar_t relative[512],line[512],out[MAX_PATH];
 char bytes[512];
 swprintf(line,512,L"%ls/%ls/%ls",collection,package,filename);
 assert(imported_bundle_relative(bytes,encode(line,bytes),filename,relative,512));
 assert(wcsstr(relative,package)&&!wcschr(relative,L'/'));
 swprintf(line,512,L"%ls/%ls/%ls\r\n",collection,package,filename);
 assert(imported_bundle_relative(bytes,encode(line,bytes),filename,relative,512));
 swprintf(line,512,L"%ls/%ls/%ls\nother",collection,package,filename);
 assert(!imported_bundle_relative(bytes,encode(line,bytes),filename,relative,512));
 swprintf(line,512,L"%ls/../%ls",collection,filename);
 assert(!imported_bundle_relative(bytes,encode(line,bytes),filename,relative,512));
 swprintf(line,512,L"%ls/a\\b/%ls",collection,filename);
 assert(!imported_bundle_relative(bytes,encode(line,bytes),filename,relative,512));
 swprintf(line,512,L"%ls/%ls/other.bundle",collection,package);
 assert(!imported_bundle_relative(bytes,encode(line,bytes),filename,relative,512));
 assert(!imported_bundle_relative("\xC0\xAF",2,filename,relative,512));

 wchar_t profile[MAX_PATH],temp[MAX_PATH],saved[32768];
 assert(GetEnvironmentVariableW(L"APPDATA",saved,32768)<32768);
 assert(GetTempPathW(MAX_PATH,temp)>0);
 swprintf(profile,MAX_PATH,L"%lsMOS-path-%lu-%llu",temp,GetCurrentProcessId(),GetTickCount64());
 assert(CreateDirectoryW(profile,NULL)&&SetEnvironmentVariableW(L"APPDATA",profile));
 wchar_t dirs[4][MAX_PATH];
 swprintf(dirs[0],MAX_PATH,L"%ls\\FaustLauncher",profile);
 swprintf(dirs[1],MAX_PATH,L"%ls\\MOS_data",dirs[0]);
 swprintf(dirs[2],MAX_PATH,L"%ls\\Assets",dirs[1]);
 swprintf(dirs[3],MAX_PATH,L"%ls\\ImportedSkins",dirs[2]);
 for(int i=0;i<4;i++)assert(CreateDirectoryW(dirs[i],NULL));
 assert(imported_bundle_path(look,filename,"Roland/BRoland.bundle",out,MAX_PATH)&&wcsstr(out,L"Assets\\Roland\\BRoland.bundle"));
 assert(imported_bundle_path(look,filename,NULL,out,MAX_PATH)&&wcsstr(out,L"MOS_data\\Assets\\ImportedSkins"));
 wchar_t loc[MAX_PATH],top[MAX_PATH],folder[MAX_PATH],bundle[MAX_PATH];
 swprintf(loc,MAX_PATH,L"%ls\\%hs.loc",dirs[3],look);
 swprintf(line,512,L"%ls/%ls/%ls",collection,package,filename);
 save(loc,bytes,encode(line,bytes));
 assert(!imported_bundle_path(look,filename,"Roland/BRoland.bundle",out,MAX_PATH)); /* Managed package was deleted. */

 assert(addon_file_path(top,MAX_PATH,collection)&&CreateDirectoryW(top,NULL));
 swprintf(folder,MAX_PATH,L"%ls\\%ls",top,package);
 assert(CreateDirectoryW(folder,NULL));
 swprintf(bundle,MAX_PATH,L"%ls\\%ls",folder,filename);
 save(bundle,"bundle",6);
 assert(imported_bundle_path(look,filename,"Roland/BRoland.bundle",out,MAX_PATH)&&!wcscmp(out,bundle));
 assert(imported_bundle_path(look,filename,NULL,out,MAX_PATH)&&!wcscmp(out,bundle));

 assert(DeleteFileW(bundle)&&RemoveDirectoryW(folder)&&RemoveDirectoryW(top));
 assert(!imported_bundle_path(look,filename,NULL,out,MAX_PATH));
 assert(DeleteFileW(loc));
 for(int i=3;i>=0;i--)assert(RemoveDirectoryW(dirs[i]));
 assert(RemoveDirectoryW(profile)&&SetEnvironmentVariableW(L"APPDATA",saved[0]?saved:NULL));
 puts("PASS legacy and managed Unicode bundle lookup, invalid locator and deleted package");
}
