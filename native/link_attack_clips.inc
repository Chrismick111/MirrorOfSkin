/* The director builds its graph synchronously inside ChangeMotion. Give the
   graph private TimelineClips with the selected appearance's real playable
   assets. The graph retains the private clips while the shared track returns
   to its authored list and cache immediately after graph construction. */
#include "link_phase.h"
#include "link_donor_body_index.h"
#include "link_body_phase.h"
#include "link_live_body_keys.h"

typedef struct {
 void *asset; double in,scale,span,length; char name[100];void *timeline;int detail,part;
} LinkBody;
typedef struct {
 const char *look; int detail,part,budget,ambiguous,verified; void *track; LinkBody body;
} LinkBodySearch;
typedef struct {
 void *track,*list,*cache,*privateList;
 uintptr_t listRoot,cacheRoot,privateRoot;
 uint8_t *sorted,oldSorted;
} LinkSwap;
typedef struct {
 Skin *skin; int group,coin; LinkBody body; uintptr_t root;
} LinkChoice;
typedef struct {
 LinkSwap swaps[32]; LinkChoice choices[48];
 int swapCount,choiceCount,windows,attacks,owners,privateFailures,projectionFailures;
} LinkAttackEdit;

static int link_instance(void *obj,const char *name){
 if(!obj)return 0;
 for(void *k=ui_class(obj);k;k=ui_parent(k)){
  const char *type=((const char *(*)(void *))api[API_CLASS_NAME])(k);
  if(type&&!strcmp(type,name))return 1;
 }
 return 0;
}
static double link_number(void *obj,const char *property,int single){
 if(!obj)return NAN;
 void *getter=find_method(ui_class(obj),property,0);
 if(!getter||!team_returns(getter,single?"System.Single":"System.Double"))return NAN;
 int ok=0;void *box=call_obj(getter,obj,NULL,&ok);
 void *value=ok?ui_unbox(box):NULL;
 return !value?NAN:single?(double)*(float *)value:*(double *)value;
}
static int link_digits(const char *s){
 if(!s||*s<'1'||*s>'9')return 0;
 int value=0;
 while(*s>='0'&&*s<='9'){if(value>1000)return 0;value=value*10+*s++-'0';}
 if(*s=='_'){s++;if(*s<'0'||*s>'9')return 0;while(*s>='0'&&*s<='9')s++;}
 return *s?0:value;
}
static int link_skill_group(const char *name){
 if(!name)return 0;
 for(const char *s=name;(s=strstr(s,"_S"))!=NULL;s+=2){
  int n=link_digits(s+2);if(n)return n;
  if(!strncmp(s,"_Skill",6)&&(n=link_digits(s+6)))return n;
 }
 return 0;
}
static int link_standard_track(const char *name){
 const char *tail=NULL;
 if(!strncmp(name,"Animation Track",15))tail=name+15;
 else if(!strncmp(name,"AnimationTrack",14))tail=name+14;
 if(!tail)return 0;
 if(!*tail)return 1;
 if(tail[0]!=' '||tail[1]!='('||tail[2]<'0'||tail[2]>'9')return 0;
 tail+=2;while(*tail>='0'&&*tail<='9')tail++;
 return tail[0]==')'&&tail[1]==0;
}
static double link_active_span(const LinkBody *body){
 return fmin(body->span*body->scale,body->length-body->in);
}
static int link_track_muted(void *track);
static uint64_t link_hash_label(uint64_t key,const char *text){
 do{key=(key^(unsigned char)*text)*UINT64_C(1099511628211);}while(*text++);
 return key;
}
static int link_live_body_binding(uint64_t prefix,const char *animation,int detail,int part){
 uint64_t key=link_hash_label(prefix,animation);
 key=(key^(unsigned)detail)*UINT64_C(1099511628211);
 key=(key^(unsigned)part)*UINT64_C(1099511628211);
 size_t lo=0,hi=sizeof(link_live_body_keys)/sizeof(link_live_body_keys[0]);
 while(lo<hi){
  size_t mid=lo+(hi-lo)/2;uint64_t found=link_live_body_keys[mid];
  if(found==key)return 1;
  if(found<key)lo=mid+1;else hi=mid;
 }
 return 0;
}
static void link_find_body(LinkBodySearch *q,void *tracks,int depth){
 int count=list_count(tracks);if(depth>12||count<0||count>256)return;
 for(int i=0;i<count&&q->budget>0;i++){
  void *track=list_item(tracks,i);if(!track||link_track_muted(track))continue;
  q->budget--;const char *name=wedge_name(track);
  /* Do not take another actor's body or inactive alternate form groups. */
  if(!strncmp(name,"UnitID_",7)||(name[0]>='1'&&name[0]<='9'&&!name[1]))continue;
  if(link_instance(track,"AnimationTrack")){
   int standard=link_standard_track(name);
   const char *look=!strncmp(q->look,"story_",6)?q->look+6:q->look;
   uint64_t prefix=link_hash_label(link_hash_label(UINT64_C(14695981039346656037),look),name);
   void *clips=rfield(track,"m_Clips");int n=list_count(clips);
   for(int j=0;j<n&&n<=256;j++){
    void *clip=list_item(clips,j),*asset=rfield(clip,"m_Asset"),*anim=rfield(asset,"m_Clip");
    if(!link_instance(asset,"AnimationPlayableAsset")||!link_instance(anim,"AnimationClip"))continue;
    char animName[100];snprintf(animName,sizeof(animName),"%s",wedge_name(anim));
    int known=link_donor_body_clip(q->look,q->detail,q->part,animName);
    const char *last=strrchr(animName,'_');
    int verified=known>0||(known<0&&link_live_body_binding(prefix,animName,q->detail,q->part));
    if(!known||(!verified&&(!standard||q->verified||(!link_skill_group(animName)&&!(last&&link_digits(last+1))))))continue;
    double span=link_number(clip,"get_duration",0);
    double in=link_number(clip,"get_clipIn",0),scale=link_number(clip,"get_timeScale",0),length=link_number(anim,"get_length",1);
    if(!(span>0&&in>=0&&scale>0&&in<length))continue;
    if(verified&&!q->verified){q->verified=1;q->ambiguous=0;q->track=NULL;q->body=(LinkBody){0};}
    if(!verified&&q->track&&q->track!=track){q->ambiguous=1;continue;}
    LinkBody candidate={asset,in,scale,span,length};
    if(!(link_active_span(&candidate)>link_active_span(&q->body)))continue;
    q->track=track;q->body=candidate;
    snprintf(q->body.name,sizeof(q->body.name),"%s",animName);
   }
  }
  void *children=rfield(track,"m_Children");if(children)link_find_body(q,children,depth+1);
 }
}
/* Keep the longest exposure of each named attack. Several timelines commonly
   point back to the same attack, including very short camera cutaways. */
enum { LINK_BODY_VARIANTS=32 };
typedef struct {LinkBody body[LINK_BODY_VARIANTS];int count;} LinkBodyPool;
static const char *link_loaded_look(const Skin *skin){
 return skin->look[0]?skin->look:g_rows[skin->row].appearance_name;
}
static void link_body_add(LinkBodyPool *pool,LinkBody body){
 for(int i=0;i<pool->count;i++)if(!strcmp(pool->body[i].name,body.name)){
  if(link_active_span(&body)>link_active_span(&pool->body[i]))pool->body[i]=body;
  return;
 }
 if(pool->count<LINK_BODY_VARIANTS)pool->body[pool->count++]=body;
}
static void link_choose_body(LinkChoice *choice){
 Skin *skin=choice->skin;const char *look=link_loaded_look(skin);
 void *motions=rfield(skin->app,"motionList");int n=list_count(motions);
 if(n<=0||n>1024)return;
 void *byDetail[SR_MOTION_CACHE]={0};int counts[SR_MOTION_CACHE]={0},available[SR_MOTION_CACHE],total=0;
 for(int i=0;i<n;i++){
  void *motion=list_item(motions,i);int d=-1,count=timeline_count(motion,&d);
  if(!((d>=7&&d<=16)||(d>=24&&d<=34))||count<=0||count>64||byDetail[d])continue;
  byDetail[d]=motion;counts[d]=count;
 }
 for(int d=0;d<SR_MOTION_CACHE;d++)if(byDetail[d])available[total++]=d;
 if(!total)return;
 int first=(choice->group-1)%total;
 LinkBodyPool motionsPool,otherParts;motionsPool.count=otherParts.count=0;
 /* Each coin gets one stable body. Prefer distinct motion groups, then
    distinct complete animations in other parts of those groups. */
 for(int attempt=0;attempt<total;attempt++){
  int d=available[(first+attempt)%total];void *parts=rfield(byDetail[d],"timelineAssets");
  LinkBody best={0};
  for(int p=0;p<counts[d];p++){
   void *timeline=list_item(parts,p);if(!timeline)continue;
   LinkBodySearch q={.look=look,.detail=d,.part=p,.budget=256};
   link_find_body(&q,rfield(timeline,"m_Tracks"),0);
   if(q.budget<=0||q.ambiguous||!q.body.asset)continue;
   if(motionsPool.count&&!link_matching_body_phase(motionsPool.body[0].name,q.body.name))continue;
   q.body.timeline=timeline;q.body.detail=d;q.body.part=p;
   if(link_active_span(&q.body)>link_active_span(&best))best=q.body;
   if(choice->coin>0)link_body_add(&otherParts,q.body);
  }
  if(best.asset&&(!motionsPool.count||link_active_span(&best)>=fmin(.15,link_active_span(&motionsPool.body[0]))))link_body_add(&motionsPool,best);
  if(motionsPool.count>choice->coin)break;
 }
 if(!motionsPool.count)return;
 if(motionsPool.count<=choice->coin)for(int i=0;i<otherParts.count;i++){
  LinkBody b=otherParts.body[i];
  if(link_matching_body_phase(motionsPool.body[0].name,b.name)&&
     link_active_span(&b)>=fmin(.15,link_active_span(&motionsPool.body[0])))link_body_add(&motionsPool,b);
 }
 LinkBody *selected=&motionsPool.body[choice->coin%motionsPool.count];
 choice->root=ui_root(selected->asset);
 if(!choice->root)return;
 choice->body=*selected;
 static LONG reports;
 if(InterlockedIncrement(&reports)<=160){
  char line[260];
  snprintf(line,sizeof(line),"link donor action look=%.70s sourceGroup=%d motion=%d part=%d animation=%.90s active=%.4f+%.4f coinVariant=%d",look,choice->group,selected->detail,selected->part,selected->name,selected->in,link_active_span(selected),choice->coin);
  bootlog(line);
 }
}
static LinkBody *link_get_coin_body(LinkAttackEdit *e,Skin *skin,int group,const char *scene,int coin){
 const char *look=link_loaded_look(skin);
 /* Appearances with exact sprite curves already vary individual swings at
    the authored strike frames. Other appearances use their live motion list. */
 if(coin<0||!scene||link_donor_body_clip(look,0,0,NULL)>=0)coin=0;
 else{
  const char *s=strstr(scene,"_S");
  if(s){
   char *end=NULL;long skill=strtol(s+2,&end,10);
   if(skill>0&&skill<100&&!strncmp(end,"_Link",5))group=(int)skill;
  }
 }
 for(int i=0;i<e->choiceCount;i++)if(e->choices[i].skin==skin&&e->choices[i].group==group&&e->choices[i].coin==coin)return &e->choices[i].body;
 if(e->choiceCount>=48)return NULL;
 LinkChoice *choice=&e->choices[e->choiceCount++];choice->skin=skin;choice->group=group;choice->coin=coin;
 link_choose_body(choice);return &choice->body;
}
static LinkBody *link_get_body(LinkAttackEdit *e,Skin *skin,int group){return link_get_coin_body(e,skin,group,NULL,0);}
static void *link_clone_clip(void *source,const LinkBody *body,double in,double scale,uintptr_t *root){
 void *cloneMethod=find_method(ui_class(source),"MemberwiseClone",0);int ok=0;
 void *clip=cloneMethod?call_obj(cloneMethod,source,NULL,&ok):NULL;
 *root=ok?ui_root(clip):0;if(!*root)return NULL;
 /* Write only into the private copy. TimelineClip setters mark their shared
    parent dirty; these fields have already been validated by typed getters
    and the same limits used by the Timeline setters. */
 void *inField=find_field_obj(clip,"m_ClipIn"),*speedField=find_field_obj(clip,"m_TimeScale");
 if(!inField||!speedField||!set_ref(clip,"m_Asset",body->asset))return NULL;
 memcpy((char *)clip+((size_t (*)(void *))api[API_FIELD_OFFSET])(inField),&in,sizeof(in));
 memcpy((char *)clip+((size_t (*)(void *))api[API_FIELD_OFFSET])(speedField),&scale,sizeof(scale));
 return clip;
}
static void link_release_swap(LinkSwap *s){
 ui_unroot(s->privateRoot);ui_unroot(s->cacheRoot);ui_unroot(s->listRoot);
}
static int link_private_list(LinkSwap *s,int n){
 int zero=0,ok=0;void *args[]={&zero,&n},*k=ui_class(s->list);
 void *range=find_method(k,"GetRange",2);
 s->privateList=range?call_obj(range,s->list,args,&ok):NULL;
 s->privateRoot=ok?ui_root(s->privateList):0;
 if(s->privateRoot)return 1;
 /* Stripped IL2CPP builds can omit GetRange. ToArray is used by TrackAsset
    itself. Never modify a list clone until it has its own backing array. */
 void *clone=find_method(k,"MemberwiseClone",0),*toArray=find_method(k,"ToArray",0);
 if(!clone||!toArray)return 0;
 s->privateList=call_obj(clone,s->list,NULL,&ok);
 s->privateRoot=ok?ui_root(s->privateList):0;
 if(!s->privateRoot)return 0;
 void *items=call_obj(toArray,s->list,NULL,&ok);uintptr_t itemsRoot=ok?ui_root(items):0;
 int separate=itemsRoot&&items!=rfield(s->list,"_items")&&set_ref(s->privateList,"_items",items);
 ui_unroot(itemsRoot);return separate;
}
static void link_edit_track(LinkAttackEdit *e,void *actor,const WedgeTrack *row){
 if(!row->owner||!row->ptr||!link_standard_track(row->name)||!link_instance(row->ptr,"AnimationTrack")||e->swapCount>=32)return;
 void *owner=wedge_presentation_owner(actor,row->owner);Unit *unit=owner?unit_for_app(owner):NULL;
 Skin *skin=unit?skin_for_app(unit,owner):NULL;
 if(!skin||skin->row<0||(uint32_t)skin->row>=g_rowCount||(g_rows[skin->row].excluded&SR_STATIC_APPEARANCE_FLAG))return;
 e->owners++;
 LinkSwap s={.track=row->ptr,.list=rfield(row->ptr,"m_Clips"),.cache=rfield(row->ptr,"m_ClipsCache")};
 int n=list_count(s.list);if(n<=0||n>256)return;
 if(!find_field_obj(row->ptr,"m_ClipsCache")){e->privateFailures++;return;}
 s.listRoot=ui_root(s.list);s.cacheRoot=s.cache?ui_root(s.cache):0;
 if(!s.listRoot||(s.cache&&!s.cacheRoot)){link_release_swap(&s);return;}
 void *sortedField=find_field_obj(row->ptr,"m_CacheSorted");
 if(sortedField){s.sorted=(uint8_t *)row->ptr+((size_t (*)(void *))api[API_FIELD_OFFSET])(sortedField);s.oldSorted=*s.sorted;}
 int changed=0;
 for(int i=0;i<n;i++){
  void *clip=list_item(s.list,i),*asset=rfield(clip,"m_Asset"),*animation=rfield(asset,"m_Clip");
  if(!link_instance(asset,"AnimationPlayableAsset")||!link_instance(animation,"AnimationClip"))continue;
  int group=link_skill_group(wedge_name(animation));if(!group)continue;
  e->attacks++;
  LinkBody *body=link_get_body(e,skin,group);if(!body||!body->asset)continue;
  double in,scale;
  if(!link_project_phase(link_number(clip,"get_clipIn",0),link_number(clip,"get_timeScale",0),link_number(clip,"get_duration",0),link_number(animation,"get_length",1),body->in,body->scale,body->span,body->length,&in,&scale)){e->projectionFailures++;continue;}
  if(!s.privateList&&!link_private_list(&s,n)){e->privateFailures++;break;}
  uintptr_t root=0;void *copy=link_clone_clip(clip,body,in,scale,&root);
  void *args[]={&i,copy};
  if(copy&&call_exc(find_method(ui_class(s.privateList),"set_Item",2),s.privateList,args))changed++;
  else e->privateFailures++;
  ui_unroot(root);
 }
 if(changed&&set_ref(s.track,"m_Clips",s.privateList)){
  set_ref(s.track,"m_ClipsCache",NULL);if(s.sorted)*s.sorted=0;
  e->swaps[e->swapCount++]=s;e->windows+=changed;
 }else link_release_swap(&s);
}
static void link_restore_attacks(LinkAttackEdit *e){
 for(int i=e->swapCount-1;i>=0;i--){
  LinkSwap *s=&e->swaps[i];set_ref(s->track,"m_Clips",s->list);set_ref(s->track,"m_ClipsCache",s->cache);
  if(s->sorted)*s->sorted=s->oldSorted;link_release_swap(s);
 }
 for(int i=0;i<e->choiceCount;i++)ui_unroot(e->choices[i].root);
}
static _Thread_local int link_attack_active;
#include "link_donor_audio.inc"
static void wedge_probe_original(void *ctx){
 WedgeProbeCtx *c=ctx;LinkAttackEdit e={0};
 int use=!link_attack_active&&!c->singleCoin&&c->target==g_wedgeMapApp&&wedge_probe_main_thread();
 /* The trio supplies body frames at render submission. Keep its native
    motion tracks intact rather than playing a second donor pose clock. */
 if(use&&c->detail==11){
  Unit *actor=unit_for_app(c->target);
  if(actor&&!strncmp(actor->baseName,"11116",5)&&(actor->baseName[5]==0||actor->baseName[5]=='_'))use=0;
 }
 int audio=!link_attack_active&&c->singleCoin&&c->scene[0]&&c->target==g_wedgeMapApp&&wedge_probe_main_thread();
 if(use||audio){
  link_attack_active++;
  if(audio)link_prepare_audio(&e,c);
  if(use)for(int i=0;i<g_wedgeTrackMap.count;i++)link_edit_track(&e,c->target,&g_wedgeTrackMap.rows[i]);
 }
 ((void (*)(void *,int,uint8_t,int,uint8_t,void *,uint8_t,void *))orig_changeMotion)(c->target,c->detail,c->a1,c->index,c->a3,c->callback,c->a5,c->mi);
 if(use||audio){
  link_restore_attacks(&e);link_attack_active--;
  static LONG logs;
  if(InterlockedIncrement(&logs)<=100){
   char line[240];snprintf(line,sizeof(line),"link donor clips detail=%d part=%d ownerTracks=%d source=%d applied=%d restoredTracks=%d resolution=%d privateFailures=%d timingSkips=%d",c->detail,c->index,e.owners,e.attacks,e.windows,e.swapCount,e.choiceCount,e.privateFailures,e.projectionFailures);bootlog(line);
  }
 }
}
