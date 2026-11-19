/* Included after the native list helpers; all calls run on the render pump. */
typedef struct {SrAutoForm value;SrInternalForm internal;} AutoRuntime;
static AutoRuntime autoForms[SR_AUTO_MAX];
static unsigned autoCount;
static int autoByRow[SR_ROW_MAX];
static SrAutoForm autoRead[SR_AUTO_MAX];
static void auto_path(wchar_t *path,const wchar_t *file){
 GetModuleFileNameW(g_self,path,32768);wchar_t *p=wcsrchr(path,L'\\');if(p)lstrcpyW(p+1,file);else path[0]=0;
}
static int auto_existing_row(const SrAutoForm *p){
 for(uint32_t i=0;i<g_rowCount;i++){
  if(strcmp(g_rows[i].identity,p->identity))continue;
  if(p->kind==1&&strncmp(g_rows[i].appearance_name,p->names[0],64))continue;
  return (int)i;
 }
 return -1;
}
static AutoRuntime *auto_for_row(int row){
 return row>=0&&(uint32_t)row<g_rowCount&&autoByRow[row]>0?&autoForms[autoByRow[row]-1]:NULL;
}
static int auto_assign(int row,const SrAutoForm *p){
 if(row<0||(uint32_t)row>=g_rowCount||sr_form_index(g_rows[row].identity)>=0||sr_internal_policy(g_rows[row].identity)||!strcmp(g_rows[row].identity,"10312")||!strcmp(g_rows[row].identity,"10913"))return 0;
 if(!(g_rows[row].excluded&SR_AUTO_FLAG))return 0;
 AutoRuntime *a=auto_for_row(row);
 if(!a){if(autoCount==SR_AUTO_MAX)return 0;a=&autoForms[autoCount];autoByRow[row]=(int)++autoCount;}
 a->value=*p;a->internal.id=a->value.identity;a->internal.count=p->count;
 for(unsigned i=0;i<4;i++)a->internal.skins[i]=a->value.names[i];
 return 1;
}
static int auto_form_valid(const SrAutoForm *p){
 if(!memchr(p->identity,0,64)||p->count<2||p->count>4||(p->kind!=1&&p->kind!=2))return 0;
 int row=auto_existing_row(p);if(row<0)return 0;
 for(unsigned i=0;i<p->count;i++){
  if(!memchr(p->names[i],0,64)||!sr_auto_name(p->names[i]))return 0;
  for(unsigned j=0;j<i;j++)if(!strcmp(p->names[i],p->names[j]))return 0;
  if(p->kind==1){
   char asset[128];snprintf(asset,sizeof(asset),"SD_Personality/%s.prefab",p->names[i]);
   if(!memchr(p->assets[i],0,128)||strcmp(p->assets[i],asset)||strncmp(p->names[i],p->identity,5))return 0;
  }
 }
 if(p->kind==1&&strcmp(p->names[0],g_rows[row].appearance_name))return 0;
 if(p->kind==2){char out[4][64];char names[4][64];memcpy(names,p->names,sizeof(names));
  if(sr_auto_skins(names,p->count,out)!=(int)p->count||memcmp(out,p->names,p->count*64))return 0;}
 return 1;
}
static void auto_bind_policy(const SrAutoForm *policy){
 int source=auto_existing_row(policy);
 if(source<0)return;
 int binding=0;
 for(uint32_t row=0;row<g_rowCount;row++){
  if(!(g_rows[row].excluded&SR_AUTO_FLAG)||strcmp(g_rows[row].identity,policy->identity)||
     strcmp(g_rows[row].asset_key,g_rows[source].asset_key))continue;
  if(binding)autoByRow[row]=binding;
  else if(auto_assign((int)row,policy))binding=autoByRow[row];
 }
}
static void auto_forms_load(void){
 wchar_t path[32768];auto_path(path,L"auto_forms.bin");
 HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);
 if(f==INVALID_HANDLE_VALUE)return;
 DWORD got=0;uint32_t h[4];int ok=ReadFile(f,h,16,&got,NULL)&&got==16&&h[0]==0x31464153&&h[1]==1&&h[2]<=SR_AUTO_MAX&&h[3]==sizeof(SrAutoForm);
 if(ok)ok=ReadFile(f,autoRead,h[2]*(DWORD)sizeof(SrAutoForm),&got,NULL)&&got==h[2]*sizeof(SrAutoForm);
 CloseHandle(f);if(!ok){bootlog("automatic forms snapshot rejected");return;}
 for(unsigned i=0;i<h[2];i++)if(!auto_form_valid(&autoRead[i])){bootlog("automatic form entry rejected; retaining previous policy");return;}
 for(unsigned i=0;i<h[2];i++)auto_bind_policy(&autoRead[i]);
}
static int auto_desired(Unit *u,int row){
 AutoRuntime *a=auto_for_row(row);
 if(!a||a->value.kind!=1)return 0;
 unsigned n=u->formState.evades,cap=a->value.count-1;return (int)(n<cap?n:cap);
}
static const SrInternalForm *auto_internal(int row){
 AutoRuntime *a=auto_for_row(row);return a&&a->value.kind==2?&a->internal:NULL;
}
static void auto_publish_internal(Skin *skin,const SrAutoForm *p){
 wchar_t path[32768];auto_path(path,L"auto_internal_forms.jsonl");
 HANDLE f=CreateFileW(path,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_ALWAYS,0,NULL);if(f==INVALID_HANDLE_VALUE)return;
 char line[768];int len=snprintf(line,sizeof(line),"{\"protocol\":%u,\"pid\":%lu,\"nonce\":%lu,\"id\":\"%s\",\"appearance\":\"%s\",\"names\":[",SR_PROTOCOL_VERSION,(unsigned long)GetCurrentProcessId(),(unsigned long)(g_cfg?g_cfg->reserved[2]:0),p->identity,g_rows[skin->row].appearance_name);
 for(unsigned i=0;i<p->count;i++)len+=snprintf(line+len,sizeof(line)-len,"%s\"%s\"",i?",":"",p->names[i]);
 len+=snprintf(line+len,sizeof(line)-len,"]}\r\n");DWORD done;WriteFile(f,line,len,&done,NULL);CloseHandle(f);
}
static int auto_skin_count(void *list){
 int n=list_count(list);if(n>=0)return n;
 void *field=find_field_obj(list,"Count");
 void *box=field?((void *(*)(void *,void *))api[API_FIELD_VALUE])(field,list):NULL;
 if(!box||strcmp(((const char *(*)(void *))api[API_CLASS_NAME])(ui_class(box)),"Int32"))return -1;
 return *(int *)ui_unbox(box);
}
static void *auto_skin_item(void *list,int index){
 void *array=rfield(list,"Items");
 if(array){
  const char *types[]={"System.Int32"};void *m=pick_method(ui_class(array),"GetValue",types,1);
  void *args[]={&index};int ok=0;return m?call_obj(m,array,args,&ok):NULL;
 }
 return list_item(list,index);
}
static void auto_detect_skin(Skin *skin){
 PoolRow *row=&g_rows[skin->row];
 if(!(row->excluded&SR_AUTO_FLAG)||sr_form_index(row->identity)>=0||sr_internal_policy(row->identity)||!strcmp(row->identity,"10312")||!strcmp(row->identity,"10913"))return;
 AutoRuntime *existing=auto_for_row(skin->row);if(existing&&existing->value.kind==1)return;
 void *spines=rfield(skin->app,"_spineSkins");int n=list_count(spines);
 for(int i=0;i<n&&i<32;i++){
  void *spine=list_item(spines,i),*anim=spine?rfield(spine,"_spine_Animation"):NULL;int ok=0;
  void *m=anim?find_method(ui_class(anim),"get_Skeleton",0):NULL;
  void *skeleton=m?call_obj(m,anim,NULL,&ok):NULL;if(!ok||!skeleton)continue;
  m=find_method(ui_class(skeleton),"get_Data",0);void *data=m?call_obj(m,skeleton,NULL,&ok):NULL;if(!ok||!data)continue;
  m=find_method(ui_class(data),"get_Skins",0);void *skins=m?call_obj(m,data,NULL,&ok):NULL;if(!ok||!skins)continue;
  int count=auto_skin_count(skins);if(count<2||count>16)continue;
  char names[16][64]={0};int valid=1;
  for(int j=0;j<count;j++){
   void *item=auto_skin_item(skins,j);m=item?find_method(ui_class(item),"get_Name",0):NULL;
   void *text=m?call_obj(m,item,NULL,&ok):NULL;
   if(!ok||!string_ascii(text,names[j],64)){valid=0;break;}
  }
  if(!valid)continue;
  SrAutoForm p={0};strcpy(p.identity,row->identity);p.kind=2;
  p.count=sr_auto_skins(names,count,p.names);if(p.count<2)continue;
  int changed=!existing||memcmp(&existing->value,&p,sizeof(p));
  if(auto_assign(skin->row,&p)&&changed){auto_publish_internal(skin,&p);bootlog("new identity internal form stages validated and cached");}
  return;
 }
 /* A cached skin policy from an older asset is not blindly reused. */
 if(existing&&existing->value.kind==2){skin->internalFailed=15;bootlog("automatic internal form not confirmed on this instance");}
}

/* The authoritative identity table is exported once per process (four rows
   per frame, two milliseconds budget). No prefabs are loaded by this scan. */
static void *discoveryList;static uintptr_t discoveryRoot;
static int discoveryIndex,discoveryCount,discoveryWritten,discoveryDone;
static DWORD discoveryNext;static HANDLE discoveryFile=INVALID_HANDLE_VALUE;
static int discovery_returns(void *method,const char *expected){
 if(!method)return 0;void *type=((void *(*)(void *))api[API_RETURN_TYPE])(method);
 char *name=type?((char *(*)(void *))api[API_TYPE_NAME])(type):NULL;
 int good=name&&!strcmp(name,expected);
 if(!good){char line[192];snprintf(line,sizeof(line),"identity discovery return type expected=%.48s actual=%.80s",expected,name?name:"missing");bootlog(line);}
 if(name)((void (*)(void *))api[API_FREE])(name);return good;
}
static void discovery_abort(void){
 if(discoveryFile!=INVALID_HANDLE_VALUE){CloseHandle(discoveryFile);discoveryFile=INVALID_HANDLE_VALUE;}
 ui_unroot(discoveryRoot);discoveryRoot=0;discoveryList=NULL;discoveryIndex=discoveryCount=discoveryWritten=0;
 discoveryNext=GetTickCount()+10000;
}
static void discovery_tick(void){
 if(discoveryDone||!g_cfg||!g_ready||!enabled_now())return;
 DWORD now=GetTickCount();if(!discoveryList){
  if(discoveryNext&&(LONG)(now-discoveryNext)<0)return;discoveryNext=now+10000;
  void *k=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"","StaticDataManager");
  void *m=k?find_method(k,"get_Instance",0):NULL;int ok=0;
  void *manager=m?call_obj(m,NULL,NULL,&ok):NULL;if(!ok||!manager)return;
  m=find_method(ui_class(manager),"get_PersonalityStaticDataList",0);void *db=m?call_obj(m,manager,NULL,&ok):NULL;if(!ok||!db)return;
  m=find_method(ui_class(db),"GetList",0);void *list=m?call_obj(m,db,NULL,&ok):NULL;if(!ok||!list)return;
  int count=list_count(list);if(count<=0||count>SR_ROW_MAX)return;
  discoveryRoot=ui_root(list);if(!discoveryRoot)return;discoveryList=list;discoveryCount=count;
  wchar_t path[32768];auto_path(path,L"identity_catalog.json.tmp");
  discoveryFile=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,0,NULL);
  if(discoveryFile==INVALID_HANDLE_VALUE){discovery_abort();return;}
  char header[160];int len=snprintf(header,sizeof(header),"{\"protocol\":%u,\"pid\":%lu,\"nonce\":%lu,\"rows\":[",SR_PROTOCOL_VERSION,(unsigned long)GetCurrentProcessId(),(unsigned long)g_cfg->reserved[2]);DWORD done;
  if(!WriteFile(discoveryFile,header,len,&done,NULL)||done!=(DWORD)len){discovery_abort();return;}
 }
 for(int batch=0;batch<4&&discoveryIndex<discoveryCount;batch++){
  if(batch&&(DWORD)(GetTickCount()-now)>=2)break;
  void *item=list_item(discoveryList,discoveryIndex++);if(!item)continue;
  void *idMethod=find_method(ui_class(item),"get_ID",0),*charMethod=find_method(ui_class(item),"get_CharacterId",0),*appMethod=find_method(ui_class(item),"get_Appearance",0);
  if(!discovery_returns(idMethod,"System.Int32")||!discovery_returns(charMethod,"System.Int32")||!discovery_returns(appMethod,"System.String")){bootlog("identity discovery signature unavailable; deferred");discovery_abort();return;}
  void *hiddenField=find_field_obj(item,"hidden");if(!hiddenField){bootlog("identity discovery hidden flag unavailable; deferred");discovery_abort();return;}
  void *hidden=((void *(*)(void *,void *))api[API_FIELD_VALUE])(hiddenField,item);
  if(!hidden||strcmp(((const char *(*)(void *))api[API_CLASS_NAME])(ui_class(hidden)),"Boolean")){discovery_abort();return;}
  int hiddenFlag=*(uint8_t *)ui_unbox(hidden);
  int id=call_int(idMethod,item,NULL),character=call_int(charMethod,item,NULL),ok=0;
  void *text=call_obj(appMethod,item,NULL,&ok);char look[64];
  if(!ok||!string_ascii(text,look,64)||!sr_auto_identity(id,character,look,hiddenFlag))continue;
  char line[256];int len=snprintf(line,sizeof(line),"%s{\"id\":%d,\"character\":%d,\"appearance\":\"%s\",\"hidden\":false}",discoveryWritten?",":"",id,character,look);DWORD done;
  if(!WriteFile(discoveryFile,line,len,&done,NULL)||done!=(DWORD)len){discovery_abort();return;}discoveryWritten++;
 }
 if(discoveryIndex==discoveryCount){
  DWORD done;int ok=WriteFile(discoveryFile,"]}",2,&done,NULL)&&done==2;CloseHandle(discoveryFile);discoveryFile=INVALID_HANDLE_VALUE;
  wchar_t from[32768],to[32768];auto_path(from,L"identity_catalog.json.tmp");auto_path(to,L"identity_catalog.json");
  if(ok&&discoveryWritten&&MoveFileExW(from,to,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)){discoveryDone=1;bootlog("authoritative identity snapshot exported; automatic discovery ready");}
  discovery_abort();
 }
}
