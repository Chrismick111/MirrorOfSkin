/* All paths refer to artwork shipped alongside this test build. */
typedef struct {
    const char *look, *dependency, *asset;
    const wchar_t *file;
    void *bundle, *prefab;
    uintptr_t bundleRoot, prefabRoot;
    const ImportedConfig *config;
} RolandForm;

static RolandForm rolandForms[] = {
    {"BRolandBaseAppearance","SD_Enemy/1348_Index_father_Phase2Appearance.prefab",
     "Assets/Resources_moved/Prefab/SD/SEASON7/P3/BRolandBase.prefab",L"BRoland.bundle"}
};
static void *rolandImage, *rolandOpen, *rolandAsset, *rolandUnload, *rolandGoType;

static RolandForm *roland_form(const char *look){
    for(size_t i=0;i<sizeof(rolandForms)/sizeof(*rolandForms);i++)
        if(!strcmp(look,rolandForms[i].look))return &rolandForms[i];
    return NULL;
}

typedef struct ImportedForm {
    struct ImportedForm *next;
    ImportedConfig config;
    RolandForm art;
    char look[31];
    wchar_t file[72];
} ImportedForm;
static ImportedForm *importedForms;

static RolandForm *local_art_form(const char *look){
    if(!imported_look(look))return roland_form(look);
    for(ImportedForm *i=importedForms;i;i=i->next)
        if(!strcmp(look,i->look))return &i->art;
    wchar_t relative[128],path[32768];
    swprintf(relative,128,L"Assets\\ImportedSkins\\%hs.cfg",look);
    if(!addon_file_path(path,32768,relative))return NULL;
    HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);
    if(f==INVALID_HANDLE_VALUE)return NULL;
    char bytes[4096];DWORD n=0;
    int ok=ReadFile(f,bytes,sizeof(bytes),&n,NULL)&&n<sizeof(bytes);
    CloseHandle(f);
    ImportedForm *i=ok?calloc(1,sizeof(*i)):NULL;
    if(!i||!imported_config_parse(bytes,n,&i->config)){free(i);return NULL;}
    strcpy(i->look,look);
    snprintf(i->config.timingKey,sizeof(i->config.timingKey),"%s-%s",look,i->config.hash);
    swprintf(i->file,72,L"%hs.bundle",i->config.hash);
    i->art=(RolandForm){i->look,i->config.dependency,i->config.asset,i->file,NULL,NULL,0,0,&i->config};
    i->next=importedForms;importedForms=i;
    return &i->art;
}
static void *roland_path(RolandForm *form){
    wchar_t relative[128],path[32768];
    swprintf(relative,128,L"Assets\\%ls\\%ls",form->config?L"ImportedSkins":L"Roland",form->file);
    if(!addon_file_path(path,32768,relative))return NULL;
    int bytes=WideCharToMultiByte(CP_UTF8,0,path,-1,NULL,0,NULL,NULL);
    char *utf=bytes?malloc(bytes):NULL;
    void *value=NULL;
    if(utf&&WideCharToMultiByte(CP_UTF8,0,path,-1,utf,bytes,NULL,NULL))value=make_string(utf);
    free(utf);
    return value;
}

static void roland_unload(void *bundle){
    uint8_t destroyLoadedObjects=0;
    void *args[]={&destroyLoadedObjects};
    if(rfield(bundle,"m_CachedPtr"))call_exc(rolandUnload,bundle,args);
}

static void roland_discard(RolandForm *form){
    int shared=0;
    for(ImportedForm *i=importedForms;i;i=i->next)
        if(&i->art!=form&&form->bundle==i->art.bundle)shared=1;
    if(!shared)roland_unload(form->bundle);
    ui_unroot(form->prefabRoot);ui_unroot(form->bundleRoot);
    form->prefab=form->bundle=NULL;
    form->prefabRoot=form->bundleRoot=0;
}

static void roland_release_if_unused(const char *look){
    RolandForm *form=local_art_form(look);
    if(!form||!form->bundle)return;
    for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used){
        for(int k=0;k<SR_SKIN_MAX;k++){
            Skin *s=&g_units[i].skins[k];
            if(s->used&&!strcmp(look,s->look))return;
        }
    }
    roland_discard(form);
}

static void *roland_prefab(RolandForm *form){
    if(form->bundle){
        if(rfield(form->bundle,"m_CachedPtr")&&rfield(form->prefab,"m_CachedPtr"))return form->prefab;
        bootlog("Local artwork: cached Unity art expired; reopening local bundle");
        roland_discard(form);
    }
    if(!rolandOpen||!rolandAsset||!rolandUnload||!rolandGoType){
        bootlog("Local artwork: Unity AssetBundle API unavailable");return NULL;
    }
    void *bundle=NULL;int shared=0,ok=1;
    for(ImportedForm *i=importedForms;form->config&&i;i=i->next)
        if(&i->art!=form&&!strcmp(i->config.hash,form->config->hash)&&rfield(i->art.bundle,"m_CachedPtr")){
            bundle=i->art.bundle;shared=1;break;
        }
    if(!bundle){
        void *path=roland_path(form);if(!path)return NULL;
        uintptr_t pathRoot=ui_root(path);
        void *openArgs[]={path};
        bundle=call_obj(rolandOpen,NULL,openArgs,&ok);
        ui_unroot(pathRoot);
        if(!bundle){bootlog("Local artwork: could not open bundle");return NULL;}
    }
    uintptr_t bundleRoot=ui_root(bundle);
    void *key=make_string(form->asset);uintptr_t keyRoot=ui_root(key);
    void *args[]={key,rolandGoType};
    void *prefab=call_obj(rolandAsset,bundle,args,&ok);
    ui_unroot(keyRoot);
    if(!rfield(prefab,"m_CachedPtr")){
        if(!shared)roland_unload(bundle);
        ui_unroot(bundleRoot);
        bootlog("Local artwork: prefab missing from bundle");return NULL;
    }
    form->prefab=prefab;form->prefabRoot=ui_root(prefab);
    form->bundle=bundle;form->bundleRoot=bundleRoot;
    return prefab;
}

static void roland_clear(void){
    while(importedForms){
        ImportedForm *item=importedForms;
        roland_discard(&item->art);
        importedForms=item->next;free(item);
    }
    for(size_t i=0;i<sizeof(rolandForms)/sizeof(*rolandForms);i++)roland_discard(&rolandForms[i]);
}

/* Yi Sang's delivered S1..S9 group and part are the Oracle Device's weapon choice.
   Other identities draw independently once per coin, even across repeated queries. */
static int roland_armory(Skin *skin){
    return skin && !strcmp(skin->look,"BRolandBaseAppearance");
}
/* One equal-weight draw per group. Its fractional position selects one of
   that group's authored attack segments, so even a one-coin skill can use
   the later gun and greatsword clips. Cache both decisions until the next action. */
static int roland_draw(Skin *skin,int coin,double draw){
    static const int groups[]={7,8,9,10,11,12,13,14,15,24,25};
    int available[sizeof(groups)/sizeof(*groups)],n=0;
    for(size_t i=0;i<sizeof(groups)/sizeof(*groups);i++)
        if(skin->motionCounts[groups[i]]>0)available[n++]=groups[i];
    if(!n)return 0;
    double pos=draw*n;
    int slot=(int)pos;
    if(slot>=n)slot=n-1;
    int group=available[slot],count=skin->motionCounts[group];
    int part=(int)((pos-slot)*count);
    skin->weaponGroups[coin]=(unsigned char)group;
    skin->weaponParts[coin]=(unsigned char)(part<count?part:count-1);
    return group;
}
static int roland_weapon(Unit *u,Skin *s,void *action,int coin,int source,int fallback){
    if(!roland_armory(s))return fallback;
    if(sr_pair_base(u->baseName,"10115_YiSang_Index_FatherAppearance")){
        if(source>=7 && source<=16 && s->motionCounts[source]>0)return source;
        return fallback;
    }
    if(!action||coin<0||coin>=SR_VARIETY_COINS)return fallback;
    if(s->weaponAction!=action || s->weaponViewer!=u->observedViewer){
        memset(s->weaponGroups,0,sizeof(s->weaponGroups));
        s->weaponAction=action;
        s->weaponViewer=u->observedViewer;
    }
    if(!s->weaponGroups[coin]){
        double draw;
        if(!random_double(&draw)||!roland_draw(s,coin,draw))return fallback;
    }
    return s->weaponGroups[coin];
}
