/* Replay the production chapter selector and its ChangeMotion call with the
   native receiver, coin callback and arguments recorded at the boundary. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include "playback_policy.h"
#include "chapter_nine_playback.h"
#include "chapter_forms.h"
typedef struct {const SrChapterActor *chapterActor;const char *look;void *app;int motionCounts[128];signed char chapterRole[128];} Skin;
typedef struct {int nativeValid,nativeStage,viewerActive,chapterSignal,chapterPhase;const char *stageSource;void *observedModel,*chapterModel;const char *baseName;void *nativeAppearance,*baseApp,*observedAction,*observedViewer,*view;} Unit;
typedef struct {void *app;int sourceDetail,sourceIndex,segmentDetail;} ProjectionContext;
typedef struct {int v;} FxPlaybackPlan;
static ProjectionContext g_projection;
static void *g_chapterPlaybackApp,*orig_changeMotion;
static int g_chapterPlaybackDetail;
static FxPlaybackPlan *g_fxCapture;static uint64_t g_fxCaptureOwner;
static Unit u;static Skin skin;
static int model,logToken,viewer,view,baseObj,donor,method,cb,skillId,lastOrder,orderCalls;
static int calls,seenDetail,seenIndex,begins,closed;static void *receiver;
static void *ui_class(void *o){return o;}
static void *find_method(void *k,const char *n,int argc){return strcmp(n,"GetID")?NULL:&method;}
enum {API_FIELD_TYPE,API_TYPE_NAME,API_FREE,API_FIELD_VALUE};
static void *api[4];
static void *ui_unbox(void *o){return o;}
static void *find_field_obj(void *obj,const char *name){return NULL;}
static int team_returns(void *m,const char *name){return m==&method&&!strcmp(name,"System.Int32");}
static int call_int(void *m,void *obj,void **args){return skillId;}
static void *rfield(void *o,const char *n){
 if(o==&view&&!strcmp(n,"_currentActionLog"))return &logToken;
 if(o==&viewer&&!strcmp(n,"_actor"))return &view;
 if(o==&viewer&&!strcmp(n,"_currentSkillModel"))return &model;
 return NULL;
}
static const char *motion_identity(Skin *s){static char buf[1024];snprintf(buf,sizeof(buf),"story_%s",s->look);return buf;}
static int native_order_index(Unit *u,void *a,int coin,int count,int *out){
 orderCalls++;if(a!=&logToken)return 0;*out=lastOrder;return 1;
}
static int is_skill_detail(int d){return (d>=7&&d<=16)||(d>=24&&d<=34);}
static void fx_plan_close_app(void *app,uint64_t n){closed++;}
static void playback_begin(void *app){begins++;}
static void bootlog(const char *msg){}
static int simulateRepeat=0,scopeUsed=0,refIndex=-1;
static int counterpart_visual_part(Unit *unit,Skin *skin,int d,int k,int coin,int withinGroup,int *detail,int *part){
 assert(withinGroup==1||withinGroup==2);
 scopeUsed=withinGroup;
 if(simulateRepeat&&withinGroup==1){refIndex=*part;*part=(*part+1)%skin->motionCounts[*detail];return 1;}
 return 0;
}
#include "chapter_nine_runtime.inc"
static void record(void *app,int detail,uint8_t a1,int part,uint8_t a3,void *callback,uint8_t a5,void *mi){
 assert(a1==1&&a3==2&&a5==3&&callback==&cb&&mi==&method);
 assert(!g_fxCapture&&!g_fxCaptureOwner);
 if(simulateRepeat&&scopeUsed==1){
  assert(g_projection.app==app&&g_projection.sourceDetail==detail&&g_projection.sourceIndex==refIndex);
 }else assert(!g_projection.app);
 if(app==&donor)assert(g_chapterPlaybackApp==app&&g_chapterPlaybackDetail==detail);
 calls++;seenDetail=detail;seenIndex=part;receiver=app;
}
static void set_pair(const char *src,const char *look){
 memset(&skin,0,sizeof(skin));skin.look=look;skin.app=&donor;skin.chapterActor=sr_chapter_actor(src,look);assert(skin.chapterActor);
 u=(Unit){.viewerActive=1,.baseName=src,.baseApp=&baseObj,.observedAction=&logToken,.observedViewer=&viewer,.view=&view};
}
static void play(int d,int k,int id,int coin,int last){
 g_projection.app=&baseObj;g_chapterPlaybackApp=&baseObj;g_chapterPlaybackDetail=71;g_fxCapture=(void*)&baseObj;g_fxCaptureOwner=44;
 chapter_forward(&u,&skin,d,k,id,&logToken,coin,last,1,2,&cb,3,&method);
 assert(g_projection.app==&baseObj&&g_chapterPlaybackApp==&baseObj&&g_chapterPlaybackDetail==71&&g_fxCapture==(void*)&baseObj&&g_fxCaptureOwner==44);
 assert(calls==begins&&calls==closed);
}
int main(void){
 orig_changeMotion=(void*)record;
 unsigned looks=0;
 for(unsigned i=0;i<sizeof(sr_chapter_actors)/sizeof(*sr_chapter_actors);i++){
  const SrChapterActor *a=&sr_chapter_actors[i];
  for(int j=0;j<4&&a->look[j];j++){looks++;assert(sr_chapter_actor(a->base,a->look[j])==a);
   if(a->alternate)assert(sr_chapter_actor(a->alternate,a->look[j])==a);}
 }
 assert(looks==19&&!sr_chapter_actor("10916_OtherAppearance","1314_Thumb_FatherAppearance"));
 for(unsigned i=0;i<sizeof(sr_chapter_clips)/sizeof(*sr_chapter_clips);i++){
  const SrChapterClip *c=&sr_chapter_clips[i];
  assert(sr_chapter_exact_part(c->source,c->target,c->sourceDetail,c->sourceIndex,c->targetDetail,c->expectedCount)==c->targetIndex);
  assert(sr_chapter_exact_part(c->source,c->target,c->sourceDetail,c->sourceIndex,c->targetDetail,c->expectedCount+1)<0);
 }
 for(unsigned i=0;i<sizeof(ch9BySkill)/sizeof(*ch9BySkill);i++){
  const Ch9SkillMapping *m=&ch9BySkill[i];char id[12];snprintf(id,sizeof(id),"%d",m->id/100);
  set_pair(id,m->look);skin.motionCounts[m->target]=4;
  int known=0;assert(chapter_group(&u,&skin,m->source,m->id,&known)==m->target&&known==2);
 }
 set_pair("10916","1314_Thumb_FatherAppearance");skin.motionCounts[12]=4;skillId=1091603;
 assert(chapter_skill_id(&u,&logToken)==skillId&&!chapter_skill_id(&u,&view));
 skillId=1071601;assert(!chapter_skill_id(&u,&logToken));
 for(int i=0;i<4;i++){play(9,i,1091603,i,i==3);assert(seenDetail==12&&seenIndex==i&&receiver==&donor);}
 assert(!orderCalls);
 set_pair("10814","1328_MiddleFinger_discipleAppearance");skin.motionCounts[8]=5;lastOrder=4;
 play(7,1,1081401,1,1);assert(seenDetail==8&&seenIndex==4&&orderCalls==1&&scopeUsed==2);
 simulateRepeat=1;
 play(7,1,1081401,1,0);assert(seenDetail==8&&seenIndex==0&&scopeUsed==1&&refIndex==4);
 simulateRepeat=0;
 set_pair("10115","1347_Index_fatherAppearance");skin.motionCounts[7]=3;skin.motionCounts[9]=3;
 play(9,0,1011505,0,0);assert(seenDetail==7);
 play(9,0,0,0,0);assert(seenDetail==9);
 play(32,1,0,0,0);assert(seenDetail==32&&seenIndex==1);
 set_pair("11115","1327_MiddleFinger_fatherAppearance");play(15,0,0,0,0);assert(receiver==&baseObj&&seenDetail==15);
 set_pair("11115","1327_MiddleFinger_father_Phase4Appearance");play(15,0,0,0,0);assert(receiver==&donor&&seenDetail==37);
 set_pair("10314_Donquixote_Index_Disciple_AwakenAppearance","1325_Index_discipleAppearance");
 play(20,0,0,0,0);assert(receiver==&donor&&seenDetail==20);play(21,0,0,0,0);assert(receiver==&baseObj&&seenDetail==21);
 skin.chapterRole[2]=-1;play(2,0,0,0,0);assert(receiver==&baseObj&&seenDetail==2);
 skin.chapterRole[2]=1;play(2,0,0,0,0);assert(receiver==&donor&&seenDetail==2);
 set_pair("11015","1318_Pinky_DiscipleAppearance");skin.motionCounts[9]=2;
 play(9,0,1101503,0,1);assert(receiver==&baseObj&&seenDetail==9);
 puts("Chapter playback: 19 donor looks, skill mappings, clip evidence, native ordering, original flags/callbacks, duel and transform guards passed.");
}
