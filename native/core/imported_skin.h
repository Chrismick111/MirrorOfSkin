#ifndef SR_IMPORTED_SKIN_H
#define SR_IMPORTED_SKIN_H
#include <string.h>
#include <wchar.h>
typedef struct {
 char dependency[512], asset[1024], layout[256], hash[65], timingKey[96];
 unsigned char roles[128], animator[128];
} ImportedConfig;

static int import_hex(char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}
static int import_letter(char c){return (c>='A'&&c<='Z')||(c>='a'&&c<='z');}
static int import_ident(char c){return import_letter(c)||(c>='0'&&c<='9')||c=='_';}
static int imported_look(const char *s){
 if(!s||strlen(s)!=30||strncmp(s,"WBImp_",6))return 0;
 for(int i=6;i<30;i++)if(!import_hex(s[i]))return 0;
 return 1;
}
static int import_prefab_key(const char *s,int asset){
 size_t n=strlen(s);
 if(n<=7||strcmp(s+n-7,".prefab"))return 0;
 if(asset){if(_strnicmp(s,"Assets/",7))return 0;}
 else if(strncmp(s,"SD_Personality/",15)&&strncmp(s,"SD_Enemy/",9))return 0;
 const char *start=s;
 for(const char *p=s;;p++){
  if(!*p||*p=='/'){
   size_t len=p-start;
   if(!len||(len==1&&*start=='.')||(len==2&&!strncmp(start,"..",2)))return 0;
   if(!*p)break;
   start=p+1;
  }else if(!import_ident(*p)&&*p!='.'&&*p!='-'&&!(asset&&*p==' '))return 0;
 }
 return 1;
}
/* Buffer has a writable terminator at length. Seven LF-delimited ASCII fields. */
static int imported_config_parse(char *buffer,size_t length,ImportedConfig *out){
 if(memchr(buffer,0,length))return 0;
 buffer[length]=0;
 char *lines[7],*next=buffer;
 for(int i=0;i<7;i++){
  lines[i]=next;
  char *lf=strchr(next,'\n');
  if(!lf){if(i!=6)return 0;break;}
  *lf=0;next=lf+1;
  if(i==6&&*next)return 0;
 }
 char *dep=lines[1],*asset=lines[2],*file=lines[3],*layout=lines[4];
 if(strcmp(lines[0],"WBMOD1")||strlen(dep)>=sizeof(out->dependency)||!import_prefab_key(dep,0)||
    strlen(asset)>=sizeof(out->asset)||!import_prefab_key(asset,1)||strlen(file)!=71||
    strcmp(file+64,".bundle")||!*layout||strlen(layout)>=sizeof(out->layout)||
    strlen(lines[5])!=128||strlen(lines[6])!=128)return 0;
 for(int i=0;i<64;i++)if(!import_hex(file[i]))return 0;
 for(const char *p=layout;*p;p++)if(!import_ident(*p))return 0;
 for(int i=0;i<128;i++){
  char role=lines[5][i],anim=lines[6][i];
  if(role<'0'||role>'7'||anim<'0'||anim>'1'||(anim=='1'&&role!='7'))return 0;
  out->roles[i]=role-'0';out->animator[i]=anim-'0';
 }
 strcpy(out->dependency,dep);strcpy(out->asset,asset);strcpy(out->layout,layout);
 memcpy(out->hash,file,64);out->hash[64]=0;
 return 1;
}
static int addon_file_path(wchar_t *path,size_t cap,const wchar_t *relative){
 const wchar_t *dirs[]={L"Assets\\ImportedSkins",L"Assets\\ImportedVoices",L"Assets\\CarraBases"};
 for(size_t i=0;i<sizeof(dirs)/sizeof(*dirs);i++){
  size_t len=wcslen(dirs[i]);
  if(!wcsncmp(relative,dirs[i],len)&&(relative[len]==0||relative[len]==L'\\')){
   sr_data_path(g_self,path,cap,relative);
   return path[0]!=0;
  }
 }
 DWORD n=GetModuleFileNameW(g_self,path,(DWORD)cap);
 wchar_t *tail=n&&n<cap?wcsrchr(path,L'\\'):NULL;
 if(!tail||wcslen(relative)>=cap-(tail+1-path))return 0;
 wcscpy(tail+1,relative);return 1;
}
#endif
