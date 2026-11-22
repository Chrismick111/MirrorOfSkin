/* Faithful shape of the installed Ring Finger prefab: three null bindings for
   the sprite body on clash 17, two missing attack bindings, plus authored and
   target tracks that must survive a second initialization unchanged. */
static Stub bodyTimeline,bodyTrackList,bodyTrack,targetTrack,motionList;
static void *bindings[6];static int bindingPart,bindingDetail,bodyWrites,guardPlays;
static const char *binding_class_name(void *k){return "AnimationTrack";}
static void *binding_field(void *k,const char *s){
 if(!strcmp(s,"motionList"))return (void*)2;
 if(!strcmp(s,"m_Tracks"))return (void*)1;
 return clash_test_field(k,s);
}
static void *binding_method(void *k,const char *s,int n){
 if(!strcmp(s,"GetGenericBinding"))return (void*)105;
 if(!strcmp(s,"SetGenericBinding"))return (void*)106;
 if(!strcmp(s,"get_name"))return (void*)107;
 return clash_test_method(k,s,n);
}
static void *guard_string(const char *s){assert(!strcmp(s,"Guard"));return &stock;}
static void *binding_invoke(void *m,void *o,void **a,void **e){
 static struct {void *header[2];int len;wchar_t name[32];} label;
 static int count;
 *e=NULL;
 switch((uintptr_t)m){
 case 102:return &bindingDetail;
 case 103:count=o==&motionList||o==&bodyTrackList?2:3;return &count;
 case 104:{
  int i=*(int*)a[0];
  if(o==&motionList){bindingDetail=i?7:17;return &clashMotion;}
  if(o==&clashList){bindingPart=(bindingDetail==7?3:0)+i;return &bodyTimeline;}
  assert(o==&bodyTrackList);return i?&targetTrack:&bodyTrack;
 }
 case 105:assert(o==&director&&a[0]==&bodyTrack);return bindings[bindingPart];
 case 106:assert(o==&director&&a[0]==&bodyTrack&&a[1]==&stock);bindings[bindingPart]=a[1];bodyWrites++;return NULL;
 case 107:wcscpy(label.name,o==&bodyTrack?L"Animation Track":L"Target");label.len=(int)wcslen(label.name);return &label;
 case 108:assert(o==&stock&&a[0]==&stock&&*(int*)a[1]==-1&&*(float*)a[2]==0);guardPlays++;return NULL;
 default:return clash_test_invoke(m,o,a,e);
 }
}
static void test_imported_bindings(Skin *skin){
 uintptr_t saved=donor.fields[1];
 donor.fields[1]=(uintptr_t)&motionList;donor.fields[2]=(uintptr_t)&director;
 bodyTimeline.fields[0]=(uintptr_t)&bodyTrackList;
 api[API_FIELD]=binding_field;api[API_METHOD]=binding_method;api[API_CLASS_NAME]=binding_class_name;
 api[API_INVOKE]=binding_invoke;
 bindings[3]=&targetTrack; /* existing binding on attack part zero */
 prepare_imported_body_bindings(skin);prepare_imported_body_bindings(skin);
 assert(bodyWrites==5&&bindings[3]==&targetTrack);
 donor.fields[1]=saved;donor.fields[2]=0;
 api[API_FIELD]=clash_test_field;api[API_METHOD]=clash_test_method;api[API_INVOKE]=clash_test_invoke;
}
/* Exercise imported poses via the normal entries, including nested GetMotion. */
static void test_imported_clash(Unit *u,Skin *skin){
 ImportedConfig config={0};skin->imported=&config;
 strcpy(skin->look,"WBImp_0123456789abcdef01234567");
 strcpy(config.layout,"1348_Index_father_Phase2Appearance");
 strcpy(u->baseName,"10901");
 config.roles[2]=config.roles[3]=7;config.animator[3]=1;
 config.roles[20]=4;config.roles[33]=2;
 memset(skin->clashCount,0,sizeof(skin->clashCount));
 api[API_FIELD]=clash_test_field;api[API_METHOD]=clash_test_method;api[API_INVOKE]=clash_test_invoke;
 m_getMotion=(void*)101;donor.fields[4]=(uintptr_t)&stock;clashMotion.fields[4]=(uintptr_t)&clashList;
 cache_clash_roles(skin);
 assert(!roland_armory(skin)&&skin->chapterRole[3]>0&&skin->chapterRole[2]<0);
 assert(skin->chapterRole[21]<0&&skin->chapterRole[32]<0&&skin->chapterRole[33]>0);
 g_clashOwner=u;g_clashRole=2;int prevCoin=u->coinMotion;u->coinMotion=21;
 assert(clash_request(u,20)==2&&!clash_request(u,21));
 g_clashOwner=NULL;g_clashRole=0;u->coinMotion=prevCoin;
 assert(!clash_request(u,33)); /* The source identity's skill still means attack. */
 assert(get_motion_hook(&source,37,0,NULL)==&donor&&lastDetail==33);
 int before=calls;change_motion_hook(&source,37,0,9,0,(void*)91,0,NULL);
 assert(calls==before+1&&lastReceiver==&donor&&lastDetail==33&&lastPart==1&&lastCallback==(void*)91);
 before=calls;change_motion_hook(&source,3,0,0,0,(void*)92,0,NULL);
 assert(calls==before+1&&lastReceiver==&donor&&lastDetail==3&&lastCallback==(void*)92);
 assert(get_motion_hook(&source,2,0,NULL)==&donor&&lastDetail==20);
 assert(clash_donor_slot(skin,37,2)==33);
 config.roles[37]=2;skin->chapterRole[37]=1;
 assert(clash_donor_slot(skin,17,2)==37); /* Explicit standard slot precedes an alternate. */
 parryPart=0;parryViaPlayback=1;before=calls;
 assert(parry_hook(&source,1,1,0,0,0,17,0,NULL)==17);
 assert(calls==before+1&&lastDetail==37&&lastCallback==(void*)87);
 config.roles[17]=4;skin->chapterRole[17]=1;skin->clashCount[17]=3;
 skin->motionCounts[7]=3;importedAnimatorPlay=(void*)108;test_imported_bindings(skin);
 config.roles[37]=config.roles[33]=0;
 parryViaPlayback=0;parryPart=-1;before=calls;
 assert(parry_hook(&source,1,2.94f,0,1,0,35,0,NULL)==17);
 assert(calls==before+1&&lastReceiver==&donor&&lastDetail==17&&lastPart==0);
 u->staticHidden=1;view.fields[0]=(uintptr_t)&source;api[API_STRING_NEW]=guard_string;api[API_INVOKE]=binding_invoke;
 before=calls;change_motion_hook(&source,3,0,0,0,(void*)94,0,NULL);
 assert(calls==before+1&&guardPlays==1&&lastReceiver==&donor&&lastDetail==3&&lastCallback==(void*)94);
 view.fields[0]=(uintptr_t)&donor;u->staticHidden=0;importedAnimatorPlay=NULL;
 api[API_INVOKE]=clash_test_invoke;config.roles[17]=0;
 config.roles[37]=config.roles[33]=config.roles[20]=0;
 assert(get_motion_hook(&source,37,0,NULL)==&donor&&lastDetail==0);
 skin->imported=NULL;donor.fields[4]=0;m_getMotion=NULL;
 api[API_FIELD]=fake_field;api[API_METHOD]=fake_method;api[API_INVOKE]=fake_invoke;
 puts("PASS imported cosmetic clash: authored win, verified Animator defense, neutral/idle fallback, original callback once");
}

static const char *artHash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
static void import_fixture(char *cfg,const char *dep,const char *asset){
 char map[129],anim[129];memset(map,'0',128);memset(anim,'0',128);map[128]=anim[128]=0;
 map[3]='7';anim[3]='1';map[37]='2';
 sprintf(cfg,"WBMOD1\n%s\n%s\n%s.bundle\n8389_Theatre_BariAppearance\n%s\n%s\n",dep,asset,artHash,map,anim);
}
static wchar_t profile[MAX_PATH],launcher[MAX_PATH],data[MAX_PATH],assets[MAX_PATH],savedAppData[32768];
static void open_test_profile(void){
 assert(GetEnvironmentVariableW(L"APPDATA",savedAppData,32768)<32768);
 /* Run the real user-data lookup in a private profile. */
 wchar_t temp[MAX_PATH];
 assert(GetTempPathW(MAX_PATH,temp)>0);
 assert(swprintf(profile,MAX_PATH,L"%lsMOS-test-%lu-%llu",temp,GetCurrentProcessId(),GetTickCount64())>0);
 assert(CreateDirectoryW(profile,NULL)&&SetEnvironmentVariableW(L"APPDATA",profile));
 assert(swprintf(launcher,MAX_PATH,L"%ls\\FaustLauncher",profile)>0&&CreateDirectoryW(launcher,NULL));
 assert(swprintf(data,MAX_PATH,L"%ls\\MOS_data",launcher)>0&&CreateDirectoryW(data,NULL));
 assert(swprintf(assets,MAX_PATH,L"%ls\\Assets",data)>0&&CreateDirectoryW(assets,NULL));
}
static void close_test_profile(void){
 wchar_t logfile[32768];sr_data_path(g_self,logfile,32768,L"native_runtime.log");
 if(logHandle!=INVALID_HANDLE_VALUE){
  CloseHandle(logHandle);logHandle=INVALID_HANDLE_VALUE;InitOnceInitialize(&logOnce);
  assert(DeleteFileW(logfile));
 }
 assert(SetEnvironmentVariableW(L"APPDATA",savedAppData[0]?savedAppData:NULL));
 assert(RemoveDirectoryW(assets)&&RemoveDirectoryW(data)&&RemoveDirectoryW(launcher)&&RemoveDirectoryW(profile));
}
static void test_imported_art(void){
 char cfg[2048];ImportedConfig parsed={0};
 const char *dep="SD_Personality/10213_Faust_Shi_EastAppearance.prefab",*asset="assets/test folder/test.prefab";
 import_fixture(cfg,dep,asset);assert(imported_config_parse(cfg,strlen(cfg),&parsed));
 assert(parsed.roles[37]==2&&parsed.animator[3]&&!strcmp(parsed.hash,artHash));
 import_fixture(cfg,"SD_Enemy/../bad.prefab",asset);assert(!imported_config_parse(cfg,strlen(cfg),&parsed));
 import_fixture(cfg,dep,"Assets/x\\y.prefab");assert(!imported_config_parse(cfg,strlen(cfg),&parsed));
 import_fixture(cfg,dep,asset);strcat(cfg,"extra\n");assert(!imported_config_parse(cfg,strlen(cfg),&parsed));
 import_fixture(cfg,dep,asset);cfg[strlen(cfg)-2]='9';assert(!imported_config_parse(cfg,strlen(cfg),&parsed));
 import_fixture(cfg,dep,asset);size_t full=strlen(cfg);cfg[13]=0;assert(!imported_config_parse(cfg,full,&parsed));
 assert(!imported_look("WBImp_0123456789abcdef0123456/"));
 char looks[2][31];wchar_t dir[32768],paths[2][32768],relative[160];
 assert(addon_file_path(dir,32768,L"Assets\\ImportedSkins"));assert(wcsstr(dir,assets)==dir);int createdDir=CreateDirectoryW(dir,NULL);
 import_fixture(cfg,dep,asset);
 for(int j=0;j<2;j++){
  snprintf(looks[j],31,"WBImp_%016llx%08lx",(unsigned long long)GetCurrentProcessId(),(unsigned long)j);
  swprintf(relative,160,L"Assets\\ImportedSkins\\%hs.cfg",looks[j]);
  assert(addon_file_path(paths[j],32768,relative));
  HANDLE f=CreateFileW(paths[j],GENERIC_WRITE,0,NULL,CREATE_NEW,0,NULL);
  assert(f!=INVALID_HANDLE_VALUE);DWORD wrote;
  assert(WriteFile(f,cfg,(DWORD)strlen(cfg),&wrote,NULL)&&wrote==strlen(cfg));CloseHandle(f);
 }
 int oldGen=generation,oldUnloads=unloads;
 assert(build_art(0,looks[0])==1);
 Skin *first=&g_units[0].skins[0];
 assert(first->imported&&!strcmp(first->imported->dependency,dep)&&!roland_armory(first));
 assert(strlen(skin_timing_key(first))==95&&!strcmp(skin_timing_key(first)+31,artHash));
 assert(DeleteFileW(paths[0]));  /* The active entry retains its bundle and timing revision. */
 wchar_t timing[32768];assert(story_metadata_path(first,"story_example",timing,32768));
 swprintf(relative,160,L"Assets\\ImportedSkins\\%hs-%hs.sst",looks[0],artHash);assert(wcsstr(timing,relative));
 assert(build_art(1,looks[0])==1&&build_art(2,looks[1])==1);
 assert(generation==oldGen+1&&g_units[1].skins[0].imported==first->imported);
 unit_release(&g_units[0]);unit_release(&g_units[1]);assert(unloads==oldUnloads);
 unit_release(&g_units[2]);g_frame+=3;collect_retire();
 assert(unloads==oldUnloads+1&&roots==0);
 roland_clear();assert(DeleteFileW(paths[1]));
 assert(!build_art(0,looks[0]));ui_unroot(g_loadRoot);g_loadBox=NULL;g_loadRoot=0;
 if(createdDir)RemoveDirectoryW(dir);
 puts("PASS imported configuration validation, versioned timing, actual build entry and shared bundle ownership across multiple units/prefabs");
}
