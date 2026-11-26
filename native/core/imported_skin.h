#ifndef SR_IMPORTED_SKIN_H
#define SR_IMPORTED_SKIN_H
#include <limits.h>
#include <string.h>
#include <wchar.h>
#define IMPORTED_ROUTE_LIMIT 128
typedef struct {
 int skill;
 unsigned char tier, coins, slot, priority;
} ImportedAttackRoute;
typedef struct {
 char dependency[512], asset[1024], layout[256], hash[65], timingKey[96];
 unsigned char roles[128], animator[128];
 unsigned char groupCount,groupPassthrough,groups[128];
 char bundlePath[256],groupSource[256];
 unsigned char nativeTiming[128];
 int routeCount;
 ImportedAttackRoute routes[IMPORTED_ROUTE_LIMIT];
} ImportedConfig;

/* Only authored attack slots may feed the ordinary per-coin planner. */
static int imported_attack_group_allowed(const ImportedConfig *c,int detail){
 if(!c||detail<0||detail>=128)return 0;
 if(c->roles[detail])return 0;
 if(!c->groupCount)return 1;
 for(int i=0;i<c->groupCount;i++)if(c->groups[i]==detail)return 1;
 return 0;
}

static int import_hex(char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}
static int import_letter(char c){return (c>='A'&&c<='Z')||(c>='a'&&c<='z');}
static int import_ident(char c){return import_letter(c)||(c>='0'&&c<='9')||c=='_';}
static int imported_look(const char *s){
 if(!s||strlen(s)!=30||strncmp(s,"WBImp_",6))return 0;
 for(int i=6;i<30;i++)if(!import_hex(s[i]))return 0;
 return 1;
}
static int skin_policy_name(const char *s,size_t limit){
 size_t n=strlen(s);
 if(!n||n>=limit)return 0;
 for(const char *p=s;*p;p++)if(!import_ident(*p))return 0;
 return 1;
}
static int import_prefab_key(const char *s,int asset){
 size_t n=strlen(s);
 if(n<=7||strcmp(s+n-7,".prefab"))return 0;
 if(asset){if(_strnicmp(s,"Assets/",7))return 0;}
 else if(strncmp(s,"SD_Personality/",15)&&strncmp(s,"SD_Enemy/",9)&&
         strncmp(s,"SD_Abnormality/",sizeof("SD_Abnormality/")-1))return 0;
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
static int skin_policy_lines(char *buffer,size_t length,char **lines,int count){
 if(memchr(buffer,0,length))return 0;
 buffer[length]=0;
 char *next=buffer;
 for(int i=0;i<count;i++){
  lines[i]=next;
  char *lf=strchr(next,'\n');
  if(!lf){if(i!=count-1)return 0;break;}
  *lf=0;next=lf+1;
  if(i==count-1&&*next)return 0;
 }
 return 1;
}
static int skin_policy_groups(ImportedConfig *out,const char *s,int disjoint){
 if(!*s)return 0;
 while(*s){
  if(*s<'0'||*s>'9')return 0;
  int n=0;
  do{n=n*10+(*s++-'0');if(n>=128)return 0;}while(*s>='0'&&*s<='9');
  if(!((n>=7&&n<=16)||(n>=24&&n<=34))||(disjoint&&out->roles[n]))return 0;
  for(int i=0;i<out->groupCount;i++)if(out->groups[i]==n)return 0;
  out->groups[out->groupCount++]=(unsigned char)n;
  if(!*s)break;
  if(*s++!=','||!*s)return 0;
 }
 return 1;
}
static int skin_policy_number(const char **cursor,int limit,int *out){
 const char *s=*cursor;
 if(*s<'0'||*s>'9')return 0;
 int value=0;
 do{
  int digit=*s++-'0';
  if(value>limit/10||(value==limit/10&&digit>limit%10))return 0;
  value=value*10+digit;
 }while(*s>='0'&&*s<='9');
 *cursor=s;*out=value;
 return 1;
}
static int skin_policy_routes(ImportedConfig *out,const char *s){
 if(strncmp(s,"S|",2))return 0;
 s+=2;
 for(;;){
  int skill,tier,coins,slot,priority;
  if(out->routeCount==IMPORTED_ROUTE_LIMIT||
     !skin_policy_number(&s,INT_MAX,&skill)||*s++!=','||skill<1||
     !skin_policy_number(&s,3,&tier)||*s++!=','||tier<1||
     !skin_policy_number(&s,128,&coins)||*s++!=','||coins<1||
     !skin_policy_number(&s,127,&slot)||*s++!=','||
     !skin_policy_number(&s,255,&priority)||!imported_attack_group_allowed(out,slot))return 0;
  for(int i=0;i<out->routeCount;i++){
   const ImportedAttackRoute *r=&out->routes[i];
   if(r->skill==skill&&r->tier==tier&&r->coins==coins)return 0;
  }
  out->routes[out->routeCount++]=(ImportedAttackRoute){skill,tier,coins,slot,priority};
  if(!*s)return 1;
  if(*s++!=';')return 0;
 }
}
static int imported_route_select(const ImportedConfig *c,const int *count,int skill,int tier,int coins){
 const ImportedAttackRoute *best=NULL;
 int bestExact=0,bestDistance=0;
 for(int i=0;i<c->routeCount;i++){
  const ImportedAttackRoute *r=&c->routes[i];
  if(r->tier!=tier||count[r->slot]<=0)continue;
  int exact=r->skill==skill;
  int distance=coins>0?(r->coins>coins?r->coins-coins:coins-r->coins):0;
  if(!best||exact>bestExact||
     (exact==bestExact&&(distance<bestDistance||
      (distance==bestDistance&&(r->priority<best->priority||
       (r->priority==best->priority&&r->slot<best->slot)))))){
   best=r;bestExact=exact;bestDistance=distance;
  }
 }
 return best?best->slot:-1;
}
/* WBMOD2 adds group policy to WBMOD1. WBMOD3 adds authored per-skill routes. */
static int imported_config_parse(char *buffer,size_t length,ImportedConfig *out){
 char *lines[9]={0};
 int v3=length>=7&&!strncmp(buffer,"WBMOD3\n",7);
 int v2=length>=7&&!strncmp(buffer,"WBMOD2\n",7);
 if(!skin_policy_lines(buffer,length,lines,v3?9:v2?8:7))return 0;
 char *dep=lines[1],*asset=lines[2],*file=lines[3],*layout=lines[4];
 if((strcmp(lines[0],"WBMOD1")&&!v2&&!v3)||strlen(dep)>=sizeof(out->dependency)||!import_prefab_key(dep,0)||
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
 out->groupCount=out->groupPassthrough=0;
 out->routeCount=0;
 if(v2||v3){
  char *s=lines[7];if(!s||strncmp(s,"R|",2)||(s[2]!='0'&&s[2]!='1')||s[3]!='|'||!s[4])return 0;
  out->groupPassthrough=(unsigned char)(s[2]-'0');
  if(!skin_policy_groups(out,s+4,0))return 0;
 }
 if(v3&&!skin_policy_routes(out,lines[8]))return 0;
 strcpy(out->dependency,dep);strcpy(out->asset,asset);strcpy(out->layout,layout);
 memcpy(out->hash,file,64);out->hash[64]=0;
 return 1;
}
static int bundled_skin_bundle_path(const char *path){
 size_t n=strlen(path);
 if(n<=7||strcmp(path+n-7,".bundle"))return 0;
 size_t segment=0;
 for(const char *p=path;p<path+n-7;p++){
  if(*p=='/'){
   if(!segment)return 0;
   segment=0;
  }else{
   if(!import_ident(*p)&&*p!='-')return 0;
   segment++;
  }
 }
 return segment>0;
}
static int bundled_skin_config_parse(char *buffer,size_t length,ImportedConfig *out){
 char *line[10];
 if(!skin_policy_lines(buffer,length,line,10)||strcmp(line[0],"WBSKIN1"))return 0;
 if(strlen(line[1])>=sizeof(out->dependency)||!import_prefab_key(line[1],0)||
    strlen(line[2])>=sizeof(out->asset)||!import_prefab_key(line[2],1)||
    strlen(line[3])>=sizeof(out->bundlePath)||!bundled_skin_bundle_path(line[3])||
    !skin_policy_name(line[4],sizeof(out->layout))||
    (strcmp(line[5],"-")&&!skin_policy_name(line[5],sizeof(out->groupSource)))||
    strlen(line[6])!=128||strlen(line[7])!=128||strlen(line[8])!=128)return 0;
 ImportedConfig parsed={0};
 for(int i=0;i<128;i++){
  char role=line[6][i],anim=line[7][i],timing=line[8][i];
  if(role<'0'||role>'7'||anim<'0'||anim>'1'||(anim=='1'&&role!='7')||
     timing<'0'||timing>'1'||(timing=='1'&&(role<'1'||role>'5')))return 0;
  parsed.roles[i]=role-'0';parsed.animator[i]=anim-'0';parsed.nativeTiming[i]=timing-'0';
 }
 if(strcmp(line[9],"-")&&(strncmp(line[9],"R|",2)||!skin_policy_groups(&parsed,line[9]+2,1)))return 0;
 strcpy(parsed.dependency,line[1]);strcpy(parsed.asset,line[2]);
 strcpy(parsed.bundlePath,line[3]);strcpy(parsed.layout,line[4]);
 if(strcmp(line[5],"-"))strcpy(parsed.groupSource,line[5]);
 *out=parsed;
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
