/* Keep the native FMOD track, binding, hit times and mixer. Only its private
   graph gets the replacement appearance's weapon events. */
#include "link_authored_timing.h"
#include "link_coin_frames.h"
typedef struct {double start;void *clip,*asset;int index;} LinkSoundCue;
typedef struct {LinkSoundCue cues[96];int count,budget;double start,end;} LinkSoundBank;
static void (*link_begin_sound_plan)(WedgeProbeCtx*);
static int (*link_queue_sound_track)(int,const LinkSoundCue*,int,const LinkSoundBank*);
static void (*link_cancel_sound_track)(int);

static int link_weapon_track(const char *name){
 const char *base="FMOD Custom Track";
 size_t n=strlen(base);
 if(!strcmp(name,"효과음 · 검 털기"))return 1;
 if(strncmp(name,base,n))return 0;
 const char *p=name+n;
 if(!strncmp(p," (",2)){
  p+=2;if(*p<'0'||*p>'9')return 0;
  while(*p>='0'&&*p<='9')p++;
  if(*p++!=')')return 0;
 }
 return !*p||!strcmp(p," · 3코인")||!strcmp(p," · 4코인");
}
static int link_sound_order(const void *left,const void *right){
 const LinkSoundCue *a=left,*b=right;
 return a->start<b->start?-1:a->start>b->start?1:a->index-b->index;
}
static int link_track_muted(void *track){
 void *f=find_field_obj(track,"m_Muted");
 return f&&*(uint8_t*)((char*)track+((size_t (*)(void*))api[API_FIELD_OFFSET])(f));
}
static void link_scan_sound(LinkSoundBank *bank,void *list,const char *animation,int depth){
 int n=list_count(list);
 if(depth>12||n<=0||n>512)return;
 for(int i=0;i<n&&bank->budget>0;i++){
  void *track=list_item(list,i);bank->budget--;
  if(!track||link_track_muted(track))continue;
  const char *name=wedge_name(track);
  if(!strncmp(name,"UnitID_",7)||(name[0]>='1'&&name[0]<='9'&&!name[1]))continue;
  int weapon=link_weapon_track(name),body=link_standard_track(name)||link_instance(track,"AnimationTrack");
  void *clips=rfield(track,"m_Clips");int count=list_count(clips);
  for(int j=0;(weapon||body)&&count<=256&&j<count;j++){
   void *clip=list_item(clips,j),*asset=rfield(clip,"m_Asset");
   double t=link_number(clip,"get_start",0);if(!isfinite(t)||t<0)continue;
   if(weapon&&link_instance(asset,"FMODEventPlayable")&&bank->count<96){
    int k=bank->count++;bank->cues[k]=(LinkSoundCue){t,clip,asset,k};
   }else if(body&&link_instance(asset,"AnimationPlayableAsset")){
    void *anim=rfield(asset,"m_Clip");
    if(anim&&!strcmp(wedge_name(anim),animation)){
     double end=t+link_number(clip,"get_duration",0);
     if(isfinite(end)&&end>t){bank->start=fmin(bank->start,t);bank->end=fmax(bank->end,end);}
    }
   }
  }
  link_scan_sound(bank,rfield(track,"m_Children"),animation,depth+1);
 }
}
static int link_read_sound(LinkSoundBank *bank,void *timeline,const char *animation){
 bank->start=HUGE_VAL;bank->end=0;bank->count=0;bank->budget=480;
 link_scan_sound(bank,rfield(timeline,"m_Tracks"),animation,0);
 if(!isfinite(bank->start)||bank->budget<=0)return 0;
 int n=0;
 for(int i=0;i<bank->count;i++){
  LinkSoundCue cue=bank->cues[i];
  if(cue.start+.08>=bank->start&&cue.start<=bank->end+.08)bank->cues[n++]=cue;
 }
 bank->count=n;qsort(bank->cues,n,sizeof(*bank->cues),link_sound_order);return n;
}
static int link_donor_sound(LinkSoundBank *bank,Skin *skin,LinkBody *base,const char *clip){
 if(link_read_sound(bank,base->timeline,clip))return 1;
 const char *look=link_loaded_look(skin);
 void *motions=rfield(skin->app,"motionList");int count=list_count(motions);
 for(int i=0;i<count&&count<=1024;i++){
  void *motion=list_item(motions,i);int d=-1,n=timeline_count(motion,&d);
  if(!((d>=7&&d<=16)||(d>=24&&d<=34)))continue;
  void *parts=rfield(motion,"timelineAssets");
  for(int j=0;j<n&&n<=64;j++){
   if(!link_donor_body_clip(look,d,j,clip))continue;
   void *t=list_item(parts,j);
   if(t&&t!=base->timeline&&link_read_sound(bank,t,clip))return 1;
  }
 }
 return 0;
}
/* The original S10 second and third coins put several actors' weapon
   events on shared tracks. Their serialized display names retain ownership. */
static int link_shared_sound_owner(void *clip){
 char name[128];void *label=rfield(clip,"m_DisplayName");
 if(!label||!string_ascii(label,name,sizeof(name)))return 0;
 if(!strncmp(name,"pamelisinc_",11))return 11017;
 if(!strncmp(name,"pameladon_",10))return 10316;
 if(!strncmp(name,"yunafaust_",10))return 10216;
 return 0;
}
static int link_sound_swap(LinkAttackEdit *edit,const WedgeTrack *row,int owner,const LinkSoundBank *bank){
 void *track=row->ptr;
 LinkSwap s={.track=track,.list=rfield(track,"m_Clips"),.cache=rfield(track,"m_ClipsCache")};
 int n=list_count(s.list);
 if(n<1||n>96||edit->swapCount>=32||!find_field_obj(track,"m_ClipsCache"))return 0;
 LinkSoundCue scheduled[96];int slots=0;
 for(int i=0;i<n;i++){
  void *clip=list_item(s.list,i),*asset=rfield(clip,"m_Asset");
  double t=link_number(clip,"get_start",0);
  if(link_instance(asset,"FMODEventPlayable")&&isfinite(t)&&(row->owner||link_shared_sound_owner(clip)==owner))
   scheduled[slots++]=(LinkSoundCue){t,clip,asset,i};
 }
 if(!slots)return 0;
 qsort(scheduled,slots,sizeof(*scheduled),link_sound_order);
 s.listRoot=ui_root(s.list);s.cacheRoot=ui_root(s.cache);
 if(!s.listRoot||(s.cache&&!s.cacheRoot)||!link_private_list(&s,n)){link_release_swap(&s);return 0;}
 int manual=link_queue_sound_track&&link_queue_sound_track(owner,scheduled,slots,bank);
 if(manual){
  void *remove=find_method(ui_class(s.privateList),"RemoveAt",1);
  unsigned char drop[96]={0};
  for(int i=0;i<slots;i++)drop[scheduled[i].index]=1;
  for(int index=n-1;index>=0;index--)if(drop[index]){
   void *args[]={&index};
   if(!remove||!call_exc(remove,s.privateList,args)){
    link_cancel_sound_track(slots);link_release_swap(&s);return 0;
   }
  }
 }
 for(int i=0;!manual&&i<slots;i++){
  int k=slots>1?(int)lround((double)i*(bank->count-1)/(slots-1)):0;
  LinkBody sound={.asset=bank->cues[k].asset};uintptr_t root=0;
  double in=link_number(bank->cues[k].clip,"get_clipIn",0),scale=link_number(bank->cues[k].clip,"get_timeScale",0);
  void *copy=isfinite(in)&&in>=0&&isfinite(scale)&&scale>0?link_clone_clip(scheduled[i].clip,&sound,in,scale,&root):NULL;
  void *args[]={&scheduled[i].index,copy};
  int ok=copy&&call_exc(find_method(ui_class(s.privateList),"set_Item",2),s.privateList,args);
  ui_unroot(root);if(!ok){link_release_swap(&s);return 0;}
 }
 void *sorted=find_field_obj(track,"m_CacheSorted");
 if(sorted){s.sorted=(uint8_t*)track+((size_t (*)(void*))api[API_FIELD_OFFSET])(sorted);s.oldSorted=*s.sorted;}
 if(!set_ref(track,"m_Clips",s.privateList)){if(manual)link_cancel_sound_track(slots);link_release_swap(&s);return 0;}
 if(!set_ref(track,"m_ClipsCache",NULL)){set_ref(track,"m_Clips",s.list);if(manual)link_cancel_sound_track(slots);link_release_swap(&s);return 0;}
 if(s.sorted)*s.sorted=0;
 edit->swaps[edit->swapCount++]=s;return slots;
}
static int link_audio_group(int owner){
 int group=0;double earliest=HUGE_VAL;
 for(int i=0;i<g_wedgeTrackMap.count;i++){
  const WedgeTrack *r=&g_wedgeTrackMap.rows[i];
  if(r->owner!=owner||!link_standard_track(r->name)||link_track_muted(r->ptr))continue;
  void *clips=rfield(r->ptr,"m_Clips");int n=list_count(clips);
  for(int j=0;j<n&&n<=256;j++){
   void *c=list_item(clips,j),*a=rfield(c,"m_Asset"),*anim=rfield(a,"m_Clip");
   if(!anim)continue;
   int skill=link_skill_group(wedge_name(anim));double start=link_number(c,"get_start",0);
   if(skill>0&&start<earliest){earliest=start;group=skill;}
  }
 }
 return group;
}
static int link_has_sound_slot(int owner){
 for(int i=0;i<g_wedgeTrackMap.count;i++){
  const WedgeTrack *row=&g_wedgeTrackMap.rows[i];
  if((row->owner&&row->owner!=owner)||!link_weapon_track(row->name)||link_track_muted(row->ptr))continue;
  void *clips=rfield(row->ptr,"m_Clips");int n=list_count(clips);
  for(int j=0;j<n&&n<=96;j++){
   void *clip=list_item(clips,j);
   if((row->owner||link_shared_sound_owner(clip)==owner)&&link_instance(rfield(clip,"m_Asset"),"FMODEventPlayable"))return 1;
  }
 }
 return 0;
}
static void link_prepare_audio(LinkAttackEdit *edit,WedgeProbeCtx *ctx){
 if(link_begin_sound_plan)link_begin_sound_plan(ctx);
 int seen[8],count=0;
 for(int i=0;i<g_wedgeTrackMap.count&&count<8;i++){
  const WedgeTrack *row=&g_wedgeTrackMap.rows[i];int id=row->owner;
  if(!id)continue;
  int j=0;while(j<count&&seen[j]!=id)j++;if(j<count)continue;seen[count++]=id;
  void *app=wedge_presentation_owner(ctx->target,id);Unit *unit=app?unit_for_app(app):NULL;
  Skin *skin=unit?skin_for_app(unit,app):NULL;
  if(!skin||skin->row<0||(unsigned)skin->row>=g_rowCount||(g_rows[skin->row].excluded&SR_STATIC_APPEARANCE_FLAG))continue;
  if(!link_has_sound_slot(id))continue;
  int group=link_audio_group(id);if(!group)group=ctx->visualCoin>=0?ctx->visualCoin+1:1;
  LinkBody *body=link_get_coin_body(edit,skin,group,ctx->scene,ctx->visualCoin);if(!body||!body->timeline)continue;
  const LinkBeatRow *beats=link_authored_row(ctx->scene,id);
  const char *look=link_loaded_look(skin);
  LinkSwing swing=link_coin_donor_swing(look,body->name,body->in,link_active_span(body),beats?beats->count:0,ctx->visualCoin);
  const char *clip=swing.count?swing.clip:body->name;LinkSoundBank bank;
  if(!link_donor_sound(&bank,skin,body,clip))continue;
  int cues=0;
  for(int k=0;k<g_wedgeTrackMap.count;k++){
   const WedgeTrack *r=&g_wedgeTrackMap.rows[k];
   if((!r->owner||r->owner==id)&&link_weapon_track(r->name)&&!link_track_muted(r->ptr))cues+=link_sound_swap(edit,r,id,&bank);
  }
  if(cues){char line[256];snprintf(line,sizeof(line),"link donor audio scene=%.60s owner=%d clip=%.70s donorEvents=%d scheduled=%d",ctx->scene,id,clip,bank.count,cues);bootlog(line);}
 }
}
