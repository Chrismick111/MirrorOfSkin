#ifndef SR_IMPORTED_BUNDLE_PATH_H
#define SR_IMPORTED_BUNDLE_PATH_H

/* A locator is one relative UTF-8 path. The directory may use Unicode, but
   the name of the payload must match the bundle named by the appearance. */
static int imported_bundle_relative(const char *bytes,DWORD n,const wchar_t *file,
                                    wchar_t *relative,size_t cap){
 static const wchar_t top[]=L"\u5916\u6765\u5916\u89c2/";
 if(!n||n>=512)return 0;
 if(bytes[n-1]=='\n'){
  --n;
  if(n&&bytes[n-1]=='\r')--n;
 }
 if(!n||memchr(bytes,0,n))return 0;
 wchar_t wide[512];
 int length=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,bytes,(int)n,wide,511);
 if(length<=0)return 0;
 wide[length]=0;
 const size_t prefix=(sizeof(top)/sizeof(*top))-1;
 if((size_t)length<=prefix||wcsncmp(wide,top,prefix))return 0;
 wchar_t *name=wide+prefix,*slash=wcschr(name,L'/');
 if(!slash||slash==name||slash-name>124||slash[-1]==L'.'||slash[-1]==L' '||
    wcscmp(slash+1,file)||(size_t)length>=cap)return 0;
 for(wchar_t *p=name;p<slash;p++)
  if(*p<0x20||wcschr(L"\\:*?\"<>|",*p))return 0;
 wide[prefix-1]=L'\\';
 *slash=L'\\';
 wcscpy(relative,wide);
 return 1;
}

static int regular_bundle_dir(const wchar_t *path){
 DWORD attrs=GetFileAttributesW(path);
 return attrs!=INVALID_FILE_ATTRIBUTES&&(attrs&FILE_ATTRIBUTE_DIRECTORY)&&
        !(attrs&FILE_ATTRIBUTE_REPARSE_POINT);
}

static int managed_bundle_file(wchar_t *path){
 wchar_t *last=wcsrchr(path,L'\\');
 if(!last)return 0;
 DWORD attrs=GetFileAttributesW(path);
 if(attrs==INVALID_FILE_ATTRIBUTES||attrs&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))return 0;
 *last=0;
 wchar_t *parent=wcsrchr(path,L'\\');
 int ok=parent&&regular_bundle_dir(path);
 if(ok){
  *parent=0;
  ok=regular_bundle_dir(path);
  *parent=L'\\';
 }
 *last=L'\\';
 return ok;
}

static int imported_bundle_path_mode(const char *look,const wchar_t *file,const char *assetPath,
                                     wchar_t *out,size_t cap,int allowFallback){
 wchar_t relative[512];
 swprintf(relative,512,L"Assets\\ImportedSkins\\%hs.loc",look);
 if(!addon_file_path(out,cap,relative))return 0;
 HANDLE locator=CreateFileW(out,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,NULL,
                           OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(locator==INVALID_HANDLE_VALUE){
  DWORD err=GetLastError();
  if(!allowFallback||(err!=ERROR_FILE_NOT_FOUND&&err!=ERROR_PATH_NOT_FOUND))return 0;
  if(assetPath){
   swprintf(relative,512,L"Assets\\%hs",assetPath);
   for(wchar_t *p=relative;*p;p++)if(*p==L'/')*p=L'\\';
  }else swprintf(relative,512,L"Assets\\ImportedSkins\\%ls",file);
  return addon_file_path(out,cap,relative);
 }
 char bytes[512];
 DWORD n=0;
 BY_HANDLE_FILE_INFORMATION info;
 int ok=GetFileInformationByHandle(locator,&info)&&
        !(info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))&&
        ReadFile(locator,bytes,sizeof(bytes),&n,NULL);
 CloseHandle(locator);
 return ok&&imported_bundle_relative(bytes,n,file,relative,512)&&
        addon_file_path(out,cap,relative)&&managed_bundle_file(out);
}

static int imported_bundle_path(const char *look,const wchar_t *file,const char *assetPath,
                                wchar_t *out,size_t cap){
 return imported_bundle_path_mode(look,file,assetPath,out,cap,1);
}

#endif
