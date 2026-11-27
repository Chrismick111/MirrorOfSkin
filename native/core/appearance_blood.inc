/* CharacterAppearanceBlood owns the persistent hit staining on a battle
   model. Use its visual control for both the original and borrowed models. */
typedef struct AppearanceBlood {
 struct AppearanceBlood *next;
 void *appearance,*view,*blood;
 uintptr_t appearanceRoot,bloodRoot;
 uint8_t original,pooled,allow;
 char identity[64];
} AppearanceBlood;

static AppearanceBlood *appearance_blood;
static void *m_getAppearanceBlood,*m_setDisableBlood;
static size_t blood_flag_offset,blood_native_offset,blood_view_offset;
static char blood_allowed[SR_ROW_MAX][64];
static size_t blood_allowed_count;

static int compare_blood_identity(const void *a,const void *b){return strcmp(a,b);}

static int replace_appearance_blood_config(const char *bytes,size_t length){
 static char next[SR_ROW_MAX][64];
 size_t count=0,at=0;
 if(length>=3&&!memcmp(bytes,"\xef\xbb\xbf",3))at=3;
 while(at<length){
  size_t start=at;
  while(at<length&&bytes[at]!='\n')at++;
  size_t n=at-start;
  if(at<length)at++;
  if(n&&bytes[start+n-1]=='\r')n--;
  if(!n)continue;
  if(n>=sizeof(next[0])||count==SR_ROW_MAX||memchr(bytes+start,0,n))return -1;
  memset(next[count],0,sizeof(next[0]));
  memcpy(next[count],bytes+start,n);
  if(!sr_pool_v5_id(next[count]))return -1;
  count++;
 }
 qsort(next,count,sizeof(next[0]),compare_blood_identity);
 if(count==blood_allowed_count&&!memcmp(next,blood_allowed,count*sizeof(next[0])))return 0;
 memcpy(blood_allowed,next,count*sizeof(next[0]));
 blood_allowed_count=count;
 return 1;
}

static int poll_appearance_blood_config(void){
 if(!m_setDisableBlood)return 0;
 static DWORD last;
 static BY_HANDLE_FILE_INFORMATION previous;
 static int havePrevious;
 DWORD now=GetTickCount();
 if(last&&(DWORD)(now-last)<500)return 0;
 last=now;
 wchar_t path[32768];
 sr_data_path(g_self,path,32768,L"appearance-blood-visibility.txt");
 if(!path[0])return 0;
 HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);
 if(file==INVALID_HANDLE_VALUE){
  DWORD error=GetLastError();
  if(error!=ERROR_FILE_NOT_FOUND&&error!=ERROR_PATH_NOT_FOUND)return 0;
  havePrevious=0;
  return replace_appearance_blood_config("",0)==1;
 }
 static char bytes[3+SR_ROW_MAX*65];
 BY_HANDLE_FILE_INFORMATION info;
 DWORD got=0;
 int changed=0;
 if(GetFileInformationByHandle(file,&info)&&!info.nFileSizeHigh&&info.nFileSizeLow<=sizeof(bytes)&&
    (!havePrevious||info.nFileSizeLow!=previous.nFileSizeLow||
     info.nFileIndexHigh!=previous.nFileIndexHigh||info.nFileIndexLow!=previous.nFileIndexLow||
     info.dwVolumeSerialNumber!=previous.dwVolumeSerialNumber||
     CompareFileTime(&info.ftLastWriteTime,&previous.ftLastWriteTime)!=0)&&
    ReadFile(file,bytes,info.nFileSizeLow,&got,NULL)&&got==info.nFileSizeLow){
  int result=replace_appearance_blood_config(bytes,got);
  if(result>=0){previous=info;havePrevious=1;changed=result;}
 }
 CloseHandle(file);
 return changed;
}

static void native_blood_identity(void *app,char id[64]){
 char raw[128];
 id[0]=0;
 if(!identity_text(app,raw,sizeof(raw))||strstr(raw,"_SRN_"))return;
 for(uint32_t k=0;k<g_rowCount;k++){
  const PoolRow *row=&g_rows[k];
  if(!strcmp(row->identity,raw)||!strcmp(row->appearance_name,raw)){
   lstrcpynA(id,row->identity,64);
   return;
  }
 }
 if(strspn(raw,"0123456789")==5&&(!raw[5]||raw[5]=='_')&&
    strncmp(raw,"101",3)>=0&&strncmp(raw,"112",3)<=0){
  memcpy(id,raw,5);id[5]=0;
 }else if(sr_pool_v5_id(raw)){
  if(!strncmp(raw,"story_",6))lstrcpynA(id,raw,64);
  else if(strlen(raw)<58)snprintf(id,64,"story_%s",raw);
 }
}

static int blood_object_alive(void *obj){
 return obj&&*(void **)((char *)obj+blood_native_offset)!=NULL;
}

static void *blood_owner(void *appearance){
 return *(void **)((char *)appearance+blood_view_offset);
}

static uint8_t blood_disabled(void *blood){
 return *(uint8_t *)((char *)blood+blood_flag_offset)!=0;
}

static void set_appearance_blood_disabled(void *blood,uint8_t value){
 void *args[]={&value};
 static int reportedSuccess,reportedFailure;
 if(call_exc(m_setDisableBlood,blood,args)){
  if(value&&!reportedSuccess){reportedSuccess=1;bootlog("character blood: battle appearance suppression applied");}
 }else if(!reportedFailure){
  reportedFailure=1;
  bootlog("character blood: SetDisableBlood invocation failed");
 }
}

static void release_appearance_blood(AppearanceBlood *entry){
 if(blood_object_alive(entry->blood)&&blood_disabled(entry->blood)!=entry->original)
  set_appearance_blood_disabled(entry->blood,entry->original);
 ui_unroot(entry->bloodRoot);
 entry->bloodRoot=0;
 entry->blood=NULL;
}

static void update_appearance_blood(AppearanceBlood *entry,int refresh){
 if(refresh)entry->allow=bsearch(entry->identity,blood_allowed,blood_allowed_count,
                               sizeof(blood_allowed[0]),compare_blood_identity)!=NULL;
 if(entry->allow){
  if(entry->blood)release_appearance_blood(entry);
  return;
 }
 if(refresh){
  void *exception=NULL;
  void *blood=ui_invoke(m_getAppearanceBlood,entry->appearance,NULL,&exception);
  if(!exception&&blood!=entry->blood){
   release_appearance_blood(entry);
   if(blood_object_alive(blood)){
    entry->bloodRoot=ui_root(blood);
    if(entry->bloodRoot){entry->blood=blood;entry->original=blood_disabled(blood);}
   }
  }
 }
 if(blood_object_alive(entry->blood)&&!blood_disabled(entry->blood))
  set_appearance_blood_disabled(entry->blood,1);
}

static void observe_appearance_blood(void *appearance,void *view,const char *identity){
 if(!m_setDisableBlood||!blood_object_alive(appearance)||!blood_object_alive(view)||
    blood_owner(appearance)!=view)return;
 for(AppearanceBlood *entry=appearance_blood;entry;entry=entry->next){
  if(entry->appearance==appearance){
   if(entry->view!=view){
    release_appearance_blood(entry);
    entry->view=view;
    entry->pooled=0;
   }
   if(identity){lstrcpynA(entry->identity,identity,sizeof(entry->identity));entry->pooled=1;}
   else if(!entry->pooled)native_blood_identity(appearance,entry->identity);
   update_appearance_blood(entry,1);
   return;
  }
 }
 AppearanceBlood *entry=HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,sizeof(*entry));
 if(!entry)return;
 entry->appearanceRoot=ui_root(appearance);
 if(!entry->appearanceRoot){HeapFree(GetProcessHeap(),0,entry);return;}
 entry->appearance=appearance;
 entry->view=view;
 if(identity){lstrcpynA(entry->identity,identity,sizeof(entry->identity));entry->pooled=1;}
 else native_blood_identity(appearance,entry->identity);
 entry->next=appearance_blood;
 appearance_blood=entry;
 update_appearance_blood(entry,1);
}

static void sync_appearance_blood(int enabled,int refresh){
 for(AppearanceBlood **link=&appearance_blood;*link;){
  AppearanceBlood *entry=*link;
  if(enabled&&blood_object_alive(entry->appearance)&&blood_owner(entry->appearance)==entry->view&&
     blood_object_alive(entry->view)){
   update_appearance_blood(entry,refresh);
   link=&entry->next;
  }else{
   *link=entry->next;
   release_appearance_blood(entry);
   ui_unroot(entry->appearanceRoot);
   HeapFree(GetProcessHeap(),0,entry);
  }
 }
}
