#include "imported_bundle_path.h"

typedef struct {
    char look[64];
    ImportedConfig config;
    wchar_t file[256];
    wchar_t *loadedPath;
    int bundled;
    void *bundle, *prefab;
    uintptr_t bundleRoot, prefabRoot;
} LocalArtForm;

static void *localBundleImage, *localBundleOpen, *localBundleAsset, *localBundleUnload, *localBundleGoType;
typedef struct LocalArtEntry {
    struct LocalArtEntry *next;
    LocalArtForm art;
} LocalArtEntry;
static LocalArtEntry *localArtEntries;

static LocalArtForm *cached_art_form(const char *look){
    for(LocalArtEntry *i=localArtEntries;i;i=i->next)
        if(!strcmp(look,i->art.look))return &i->art;
    return NULL;
}
static LocalArtForm *local_art_form(const char *look){
    LocalArtForm *known=cached_art_form(look);if(known)return known;
    if(!skin_policy_name(look,sizeof(known->look)))return NULL;
    int bundled=!imported_look(look);
    wchar_t relative[128],path[32768];
    swprintf(relative,128,L"Assets\\%ls\\%hs.cfg",bundled?L"SkinPolicies":L"ImportedSkins",look);
    if(!addon_file_path(path,32768,relative))return NULL;
    HANDLE f=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);
    if(f==INVALID_HANDLE_VALUE)return NULL;
    char bytes[6144];DWORD n=0;
    int ok=ReadFile(f,bytes,sizeof(bytes)-1,&n,NULL)&&n<sizeof(bytes)-1;
    CloseHandle(f);
    LocalArtEntry *i=ok?calloc(1,sizeof(*i)):NULL;
    if(!i)return NULL;
    ImportedConfig *config=&i->art.config;
    ok=bundled?bundled_skin_config_parse(bytes,n,config):imported_config_parse(bytes,n,config);
    if(!ok){free(i);bootlog("Local artwork: invalid appearance policy");return NULL;}
    strcpy(i->art.look,look);i->art.bundled=bundled;
    if(bundled){
        const char *name=strrchr(config->bundlePath,'/');
        swprintf(i->art.file,256,L"%hs",name?name+1:config->bundlePath);
    }else{
        snprintf(config->timingKey,sizeof(config->timingKey),"%s-%s",look,config->hash);
        swprintf(i->art.file,256,L"%hs.bundle",config->hash);
    }
    i->next=localArtEntries;localArtEntries=i;
    return &i->art;
}
static void *local_bundle_key(const wchar_t *path){
    int bytes=WideCharToMultiByte(CP_UTF8,0,path,-1,NULL,0,NULL,NULL);
    char *utf=bytes?malloc(bytes):NULL;
    void *value=NULL;
    if(utf&&WideCharToMultiByte(CP_UTF8,0,path,-1,utf,bytes,NULL,NULL))value=make_string(utf);
    free(utf);
    return value;
}

static void unload_local_bundle(void *bundle){
    uint8_t destroyLoadedObjects=0;
    void *args[]={&destroyLoadedObjects};
    if(rfield(bundle,"m_CachedPtr"))call_exc(localBundleUnload,bundle,args);
}

static void discard_local_art(LocalArtForm *form){
    int shared=0;
    for(LocalArtEntry *i=localArtEntries;i;i=i->next)
        if(&i->art!=form&&form->bundle==i->art.bundle)shared=1;
    if(!shared)unload_local_bundle(form->bundle);
    ui_unroot(form->prefabRoot);ui_unroot(form->bundleRoot);
    free(form->loadedPath);form->loadedPath=NULL;
    form->prefab=form->bundle=NULL;
    form->prefabRoot=form->bundleRoot=0;
}

static void release_unused_local_art(const char *look){
    LocalArtForm *form=cached_art_form(look);
    if(!form||!form->bundle)return;
    for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used){
        for(int k=0;k<SR_SKIN_MAX;k++){
            Skin *s=&g_units[i].skins[k];
            if(s->used&&!strcmp(look,s->look))return;
        }
    }
    discard_local_art(form);
}

static void *load_local_prefab(LocalArtForm *form){
    if(form->bundle){
        if(rfield(form->bundle,"m_CachedPtr")&&rfield(form->prefab,"m_CachedPtr"))return form->prefab;
        bootlog("Local artwork: cached Unity art expired; reopening local bundle");
        discard_local_art(form);
    }
    if(!localBundleOpen||!localBundleAsset||!localBundleUnload||!localBundleGoType){
        bootlog("Local artwork: Unity AssetBundle API unavailable");return NULL;
    }
    void *bundle=NULL;int shared=0,ok=1;
    wchar_t path[32768];
    int havePath=imported_bundle_path(form->look,form->file,form->bundled?form->config.bundlePath:NULL,path,32768);
    for(LocalArtEntry *i=localArtEntries;i;i=i->next){
        LocalArtForm *other=&i->art;
        if(other==form||!rfield(other->bundle,"m_CachedPtr"))continue;
        int sameHash=!form->bundled&&!other->bundled&&!strcmp(other->config.hash,form->config.hash);
        int samePath=havePath&&other->loadedPath&&!_wcsicmp(path,other->loadedPath);
        if(sameHash||samePath){bundle=other->bundle;shared=1;break;}
    }
    if(!bundle){
        if(!havePath){bootlog("Local artwork: managed bundle path is invalid or missing");return NULL;}
        void *key=local_bundle_key(path);if(!key)return NULL;
        uintptr_t pathRoot=ui_root(key);
        void *openArgs[]={key};
        bundle=call_obj(localBundleOpen,NULL,openArgs,&ok);
        ui_unroot(pathRoot);
        if(!bundle){bootlog("Local artwork: could not open bundle");return NULL;}
    }
    uintptr_t bundleRoot=ui_root(bundle);
    void *key=make_string(form->config.asset);uintptr_t keyRoot=ui_root(key);
    void *args[]={key,localBundleGoType};
    void *prefab=call_obj(localBundleAsset,bundle,args,&ok);
    ui_unroot(keyRoot);
    if(!rfield(prefab,"m_CachedPtr")){
        if(!shared)unload_local_bundle(bundle);
        ui_unroot(bundleRoot);
        bootlog("Local artwork: prefab missing from bundle");return NULL;
    }
    form->prefab=prefab;form->prefabRoot=ui_root(prefab);
    form->bundle=bundle;form->bundleRoot=bundleRoot;
    if(havePath)form->loadedPath=_wcsdup(path);
    return prefab;
}

static void clear_local_art(void){
    while(localArtEntries){
        LocalArtEntry *item=localArtEntries;
        discard_local_art(&item->art);
        localArtEntries=item->next;free(item);
    }
}

static int skin_has_coin_groups(Skin *skin){
    const ImportedConfig *config=skin_local_policy(skin);
    return config&&config->groupCount&&!config->routeCount;
}
static int group_source_passthrough(Unit *u,Skin *s){
    const ImportedConfig *config=skin_local_policy(s);
    if(!u||!config)return 0;
    if(s->imported)return config->groupPassthrough&&sr_pair_base(u->baseName,config->layout);
    const char *source=config->groupSource;
    if(!*source)return 0;
    if(!strcmp(u->baseName,source))return 1;
    return strspn(u->baseName,"0123456789")==5&&u->baseName[5]==0&&source[5]=='_'&&
           !strncmp(u->baseName,source,5);
}
/* One equal-weight draw per group. Its fractional position selects one of
   that group's authored attack segments, so even a one-coin skill can use
   the later gun and greatsword clips. Cache both decisions until the next action. */
static int draw_coin_group(Skin *skin,int coin,double draw){
    const ImportedConfig *config=skin_local_policy(skin);
    if(!config)return 0;
    int available[128],n=0;
    for(int i=0;i<config->groupCount;i++){
        int d=config->groups[i];if(d<SR_MOTION_CACHE&&skin->motionCounts[d]>0)available[n++]=d;
    }
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
static int group_for_coin(Unit *u,Skin *s,void *action,int coin,int source,int fallback){
    if(!skin_has_coin_groups(s))return fallback;
    if(group_source_passthrough(u,s)){
        if(source>=0 && source<SR_MOTION_CACHE && s->motionCounts[source]>0)return source;
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
        if(!random_double(&draw)||!draw_coin_group(s,coin,draw))return fallback;
    }
    return s->weaponGroups[coin];
}
