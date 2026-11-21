#define SR_VOICE_SIZE(a) (sizeof(a) / sizeof((a)[0]))
static unsigned sr_voice_catalog_owner(const char *appearance){
    if(!appearance || !*appearance) return 0;
    size_t lo=0,hi=SR_VOICE_SIZE(sr_voice_aliases);
    while(lo<hi){
        size_t mid=lo+(hi-lo)/2;
        int cmp=strcmp(appearance,sr_voice_aliases[mid].appearance);
        if(cmp==0) return sr_voice_aliases[mid].owner;
        if(cmp<0) hi=mid; else lo=mid+1;
    }
    return 0;
}
static int sr_voice_label_index(const char *key){
    if(!key || !*key) return -1;
    size_t lo=0,hi=SR_VOICE_SIZE(sr_voice_labels);
    while(lo<hi){
        size_t mid=lo+(hi-lo)/2;
        int cmp=strcmp(key,sr_voice_labels[mid].key);
        if(cmp==0) return (int)mid;
        if(cmp<0) hi=mid; else lo=mid+1;
    }
    return -1;
}
static size_t sr_voice_member_lower_bound(unsigned owner,unsigned index){
    size_t lo=0,hi=SR_VOICE_SIZE(sr_voice_members);
    while(lo<hi){
        size_t mid=lo+(hi-lo)/2;
        if(sr_voice_members[mid].owner<owner ||
           (sr_voice_members[mid].owner==owner && sr_voice_members[mid].label<index)) lo=mid+1;
        else hi=mid;
    }
    return lo;
}
static int sr_voice_member_index(unsigned owner,const char *key){
    int index=sr_voice_label_index(key);
    if(!owner || index<0) return -1;
    size_t i=sr_voice_member_lower_bound(owner,(unsigned)index);
    return i<SR_VOICE_SIZE(sr_voice_members) && sr_voice_members[i].owner==owner &&
           sr_voice_members[i].label==(unsigned)index ? index : -1;
}
static const char *sr_voice_catalog_bubble(const char *literalKey){
    int i=sr_voice_label_index(literalKey);
    return i>=0 && sr_voice_labels[i].bubble ? sr_voice_labels[i].text : NULL;
}
static const char *sr_voice_catalog_text(unsigned owner,const char *literalKey){
    int i=sr_voice_member_index(owner,literalKey);
    return i<0 ? NULL : sr_voice_labels[i].text;
}
static int sr_voice_catalog_audio(unsigned owner,const char *literalKey){
    int i=sr_voice_member_index(owner,literalKey);
    return i>=0 && sr_voice_labels[i].audio;
}
static int sr_voice_numbered_suffix(const char *s){
    if(!s || !*s) return 0;
    for(;*s;s++) if(*s<'0' || *s>'9') return 0;
    return 1;
}
static int sr_voice_catalog_has_event(unsigned owner,const char *event){
    if(!owner || !event || !*event) return 0;
    int index=sr_voice_member_index(owner,event);
    if(index>=0 && (sr_voice_labels[index].audio || sr_voice_labels[index].text)) return 1;
    char prefix[128];
    int len=snprintf(prefix,sizeof(prefix),"%s_%u_",event,owner);
    if(len<0 || (size_t)len>=sizeof(prefix)) return 0;
    for(size_t i=sr_voice_member_lower_bound(owner,0);i<SR_VOICE_SIZE(sr_voice_members) && sr_voice_members[i].owner==owner;i++){
        unsigned label=sr_voice_members[i].label;
        const char *key=sr_voice_labels[label].key;
        if(!strncmp(key,prefix,(size_t)len) && sr_voice_numbered_suffix(key+len) &&
            (sr_voice_labels[label].audio || sr_voice_labels[label].text)) return 1;
    }
    return 0;
}
static const char *sr_voice_catalog_event_key(unsigned source,unsigned donor,const char *key){
    int i=sr_voice_member_index(donor,key);
    if(i>=0) return sr_voice_labels[i].key;
    if(!source || !donor || !key || !*key) return NULL;
    for(size_t n=0;n<SR_VOICE_SIZE(sr_voice_common_events);n++){
        char prefix[96],replacement[128];
        int size=snprintf(prefix,sizeof(prefix),"%s_%u_",sr_voice_common_events[n],source);
        if(size<0 || (size_t)size>=sizeof(prefix) || strncmp(key,prefix,(size_t)size)) continue;
        const char *suffix=key+size;
        if(!sr_voice_numbered_suffix(suffix)) return NULL;
        size=snprintf(replacement,sizeof(replacement),"%s_%u_%s",sr_voice_common_events[n],donor,suffix);
        if(size<0 || (size_t)size>=sizeof(replacement)) return NULL;
        i=sr_voice_member_index(donor,replacement);
        return i>=0 ? sr_voice_labels[i].key : NULL;
    }
    return NULL;
}
static const char *sr_voice_catalog_only_event(unsigned owner,const char *event){
    if(!owner || !event) return NULL;
    for(size_t n=0;n<SR_VOICE_SIZE(sr_voice_common_events);n++){
        if(strcmp(event,sr_voice_common_events[n])) continue;
        char prefix[96];
        int len=snprintf(prefix,sizeof(prefix),"%s_%u_",event,owner);
        if(len<0 || (size_t)len>=sizeof(prefix)) return NULL;
        const char *found=NULL;
        for(size_t j=sr_voice_member_lower_bound(owner,0);j<SR_VOICE_SIZE(sr_voice_members) && sr_voice_members[j].owner==owner;j++){
            unsigned i=sr_voice_members[j].label;
            const char *key=sr_voice_labels[i].key;
            if(strncmp(key,prefix,(size_t)len) || !sr_voice_numbered_suffix(key+len)) continue;
            if(found || sr_voice_labels[i].audio || !sr_voice_labels[i].text) return NULL;
            found=key;
        }
        return found;
    }
    return NULL;
}
#undef SR_VOICE_SIZE
