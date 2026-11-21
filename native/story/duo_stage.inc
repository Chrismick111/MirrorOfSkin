/* The enemy remains on its native battle root. Only the appearance pivots of
   linked participants are placed on opposing sides of its visual anchor. */
typedef struct {
 void *pivot,*view,*app,*parent;
 uintptr_t root;
 TrioVec original,applied,scale,appliedScale;
 int wrote,scaled,side;
 float gap,width,entry;TrioVec nativeStart,enemyStart;
 int cueStart,cueCount,nativeMoving,captureNativeStart;
} DuoStageMember;
static struct {
 DuoStageMember members[8];unsigned count;
 void *target,*anchor,*pos,*local,*setPos,*setLocal,*localScale,*setScale,*dir,*transformPoint;
 uintptr_t targetRoot,anchorRoot,enemyRendererRoot;
 void *enemyRenderer;
 int active,left,right,hasDirection,attempts;
 float enemyCenterOffsetX;
 double nextAttempt;
} duoStage;
#include "wedge_move_cues.h"
/* Evaluate interrupted tweens from the exact pose at the following marker. */
static TrioVec wedge_lerp_pose(TrioVec from,TrioVec to,double u,int ease){
 float a=(float)fmin(1.,fmax(0.,u)),q=1-a;
 if(ease==6||ease==0)a=1-q*q;
 if(ease==12)a=1-q*q*q*q;
 return (TrioVec){from.x+(to.x-from.x)*a,from.y+(to.y-from.y)*a,from.z+(to.z-from.z)*a};
}
static TrioVec wedge_move_pose(DuoStageMember *m,double t){
 TrioVec from={m->entry,0,0},to=from;double start=0,duration=0;int ease=1;
 for(int i=0;i<m->cueCount;i++){
  const WedgeMoveCue *c=&wedgeMoveCues[m->cueStart+i];if(c->t>t)break;
  from=wedge_lerp_pose(from,to,duration>0?(c->t-start)/duration:1,ease);
  to=c->relative?(TrioVec){from.x-c->x,from.y+c->y,from.z+c->z}:(TrioVec){fabsf(c->x),c->y,c->z};
  start=c->t;duration=c->duration;ease=c->ease;
 }
 return wedge_lerp_pose(from,to,duration>0?(t-start)/duration:1,ease);
}

static void *duo_type(void *klass){
 return klass?((void *(*)(void *))api[API_TYPE_OBJECT])(((void *(*)(void *))api[API_CLASS_TYPE])(klass)):NULL;
}
static int duo_enemy(void *lead,void *other){
 if(!lead||!other||lead==other)return 0;
 void *getter=find_method(c_view,"get_unitModel",0);
 int ok=0;
 void *a=getter?call_obj(getter,lead,NULL,&ok):NULL;
 void *b=ok?call_obj(getter,other,NULL,&ok):NULL;
 const char *types[]={"BattleUnitModel"};
 void *model=((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"","BattleUnitModel");
 void *ally=model?method_by_types_one(model,"IsAlly",types,1):NULL;
 void *args[]={b};
 return ok&&a&&b&&ally&&call_bool(ally,a,args)==0;
}
static void *duo_direct_target(void *source,void *lead){
 const char *getters[]={"get_MainTargetView","get_MainTarget","GetMainTargetView","get_TargetUnitView","get_TargetView","get_Target"};
 for(unsigned i=0;source&&i<sizeof(getters)/sizeof(*getters);i++){
  void *k=ui_class(source),*m=find_method(k,getters[i],0);
  if(!m||!team_returns(m,"BattleUnitView")||!team_instance_method(k,m))continue;
  int ok=0;void *v=call_obj(m,source,NULL,&ok);
  if(ok&&duo_enemy(lead,v))return v;
 }
 const char *fields[]={"_mainTarget","_target","_mainTargetView","_targetView","_defender","_opponent","<MainTarget>k__BackingField","<Target>k__BackingField"};
 for(unsigned i=0;source&&i<sizeof(fields)/sizeof(*fields);i++){
  void *f=find_field_obj(source,fields[i]);if(!f)continue;
  void *t=((void *(*)(void *))api[API_FIELD_TYPE])(f);
  char *n=t?((char *(*)(void *))api[API_TYPE_NAME])(t):NULL;
  int match=n&&!strcmp(n,"BattleUnitView");if(n)((void (*)(void *))api[API_FREE])(n);
  void *v=match?rfield(source,fields[i]):NULL;
  if(v&&duo_enemy(lead,v))return v;
 }
 return NULL;
}
static void *duo_find_enemy(LinkVisualScene *s,void *lead){
 void *bget=find_method(c_view,"get_BehaviourActionViewer",0);
 int ok=0;void *beh=bget?call_obj(bget,lead,NULL,&ok):NULL;
 void *v=duo_direct_target(s->action,lead);
 if(!v)v=duo_direct_target(s->viewer,lead);
 if(!v)v=duo_direct_target(beh,lead);
 if(v)return v;
 void *targetFlag=find_method(c_view,"get_isBehaviourTarget",0);
 void *type=duo_type(c_view);void *args[]={type};
 void *all=m_findAll&&type&&targetFlag?call_obj(m_findAll,NULL,args,&ok):NULL;
 uintptr_t root=ok?ui_root(all):0;if(!root)return NULL;
 uintptr_t n=*(uintptr_t *)((char *)all+24);int best=0;
 void *chosen=NULL;
 for(uintptr_t i=0;i<n&&n<=4096;i++){
  v=((void **)((char *)all+32))[i];
  if(!v||v==lead||call_bool(targetFlag,v,NULL)!=1||!duo_enemy(lead,v))continue;
  int score=1;
  if(s->action&&rfield(v,"_currentActionLog")==s->action)score=2;
  if(beh&&bget&&call_obj(bget,v,NULL,&ok)==beh&&ok)score=3;
  if(s->viewer&&m_getViewer&&call_obj(m_getViewer,v,NULL,&ok)==s->viewer&&ok)score=4;
  if(score>best){best=score;chosen=v;}else if(score==best)chosen=NULL;
 }
 ui_unroot(root);return chosen;
}
static void duo_directions(void){
 void *t=duo_type(((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"","DIRECTION"));
 int ok=0;void *nm=t?find_method(ui_class(t),"GetEnumNames",0):NULL,*vm=t?find_method(ui_class(t),"GetEnumValues",0):NULL;
 void *names=nm?call_obj(nm,t,NULL,&ok):NULL;uintptr_t nr=ui_root(names);
 void *values=vm?call_obj(vm,t,NULL,&ok):NULL;uintptr_t vr=ui_root(values);
 int mask=0;
 if(nr&&vr&&ok){
  uintptr_t n=*(uintptr_t *)((char *)names+24);
  if(n==*(uintptr_t *)((char *)values+24)&&n<128)for(uintptr_t i=0;i<n;i++){
   char name[96];if(!string_ascii(((void **)((char *)names+32))[i],name,sizeof(name)))continue;
   int v=((int *)((char *)values+32))[i];
   if(!lstrcmpiA(name,"Left")){duoStage.left=v;mask|=1;}
   if(!lstrcmpiA(name,"Right")){duoStage.right=v;mask|=2;}
  }
 }
 duoStage.hasDirection=mask==3;ui_unroot(vr);ui_unroot(nr);
}
static void duo_restore_member(DuoStageMember *m){
 TrioVec now;
 if(m->wrote&&trio_vec(duoStage.local,m->pivot,&now)&&trio_same(now,m->applied)){
  void *args[]={&m->original};call_exc(duoStage.setLocal,m->pivot,args);
 }
 if(m->scaled&&trio_vec(duoStage.localScale,m->pivot,&now)&&trio_same(now,m->appliedScale)){
  void *args[]={&m->scale};call_exc(duoStage.setScale,m->pivot,args);
 }
 m->wrote=m->scaled=0;
}
static void duo_stage_end(void){
 for(unsigned i=0;i<duoStage.count;i++){duo_restore_member(&duoStage.members[i]);ui_unroot(duoStage.members[i].root);}
 ui_unroot(duoStage.targetRoot);ui_unroot(duoStage.anchorRoot);ui_unroot(duoStage.enemyRendererRoot);memset(&duoStage,0,sizeof(duoStage));
}
static int duo_stage_center(float xyz[3]){
 TrioVec c;if(!duoStage.active||!trio_vec(duoStage.pos,duoStage.anchor,&c))return 0;
 xyz[0]=c.x+duoStage.enemyCenterOffsetX;xyz[1]=c.y;xyz[2]=c.z;return 1;
}
static int duo_stage_camera_bounds(unsigned i,float center[3],float extents[3]){
 if(!duoStage.active||i>=duoStage.count)return 0;
 TrioVec p;DuoStageMember *m=&duoStage.members[i];
 if(!trio_vec(duoStage.pos,m->pivot,&p))return 0;
 float width=fmaxf(.5f,m->width);
 center[0]=p.x;center[1]=p.y+width;center[2]=p.z;
 extents[0]=width;extents[1]=width;extents[2]=.1f;return 1;
}
static void *duo_child(void *tr,const char *path){
 const char *types[]={"System.String"};
 void *find=tr?method_by_types_one(ui_class(tr),"Find",types,1):NULL;
 void *name=make_string(path);uintptr_t root=ui_root(name);
 void *args[]={name};int ok=0;void *p=find&&root?call_obj(find,tr,args,&ok):NULL;ui_unroot(root);return ok?p:NULL;
}
static void duo_stage_begin(LinkVisualScene *s){
 if(s->ensembleSize<2||s->ownerCount<2||s->ownerCount>8||!s->viewer)return;
 Unit *lead=unit_for_app(s->app);
 if(!lead||!lead->view)return;
 void *target=duo_find_enemy(s,lead->view);if(!target)return;
 duoStage.targetRoot=ui_root(target);duoStage.target=target;
 void *enemyApp=rfield(target,"_curAppearance");
 void *anchor=enemyApp?body_get(enemyApp,"get_transform"):NULL;
 if(!anchor)anchor=body_get(target,"get_SkinPivot");
 duoStage.anchorRoot=ui_root(anchor);duoStage.anchor=anchor;
 if(!duoStage.targetRoot||!duoStage.anchorRoot){duo_stage_end();return;}
 void *tc=ui_class(anchor);
 duoStage.pos=find_method(tc,"get_position",0);duoStage.local=find_method(tc,"get_localPosition",0);
 const char *vector[]={"UnityEngine.Vector3"};
 duoStage.transformPoint=method_by_types_one(tc,"TransformPoint",vector,1);
 duoStage.setPos=find_method(tc,"set_position",1);duoStage.setLocal=find_method(tc,"set_localPosition",1);
 duoStage.localScale=find_method(tc,"get_localScale",0);duoStage.setScale=find_method(tc,"set_localScale",1);
 duoStage.dir=find_method(c_view,"get_UnitDirection",0);duo_directions();
 if(!duoStage.pos||!duoStage.local||!duoStage.setPos||!duoStage.setLocal){duo_stage_end();return;}
 float enemyWidth=1;
 void *body=duo_child(anchor,"[Transform,Fixed]ScaleAndPositionPivot/[Transform]PivotForAnim/[SpRenderer]");
 if(body){
  void *type=duo_type(unity_class_anywhere("UnityEngine","SpriteRenderer"));LinkVisualOwner enemy={0};
  if(type)follower_component_one(body,type,&enemy.renderer);
  if(enemy.renderer){
   duoStage.enemyRendererRoot=ui_root(enemy.renderer);
   if(duoStage.enemyRendererRoot)duoStage.enemyRenderer=enemy.renderer;
   enemyWidth=trio_half_width(&enemy);
   void *get=find_method(ui_class(enemy.renderer),"get_bounds",0);int ok=0;
   void *box=get?call_obj(get,enemy.renderer,NULL,&ok):NULL;
   TrioBounds *b=ok&&box?(TrioBounds*)ui_unbox(box):NULL;TrioVec ground;
   if(b&&isfinite(b->center.x)&&trio_vec(duoStage.pos,anchor,&ground))
    duoStage.enemyCenterOffsetX=b->center.x-ground.x;
  }
 }
 /* Multipart enemies may not use the standard body transform path. Choose
    their largest enabled body part for close-up focus only. */
 if(!duoStage.enemyRenderer&&enemyApp){
  void *parts=body_get(enemyApp,"get_Sprenderer_charactermotion_Parts");uintptr_t pr=ui_root(parts);
  int count=pr?list_count(parts):0;float area=0;
  for(int i=0;i<count&&count<=128;i++){
   void *part=list_item(parts,i);if(!part)continue;
   void *get=find_method(ui_class(part),"get_enabled",0);
   if(!get||call_bool(get,part,NULL)!=1)continue;
   int ok=0;void *box=call_obj(find_method(ui_class(part),"get_bounds",0),part,NULL,&ok);
   TrioBounds *b=ok&&box?(TrioBounds*)ui_unbox(box):NULL;float size=b?b->extent.x*b->extent.y:0;
   if(isfinite(size)&&size>area){area=size;duoStage.enemyRenderer=part;}
  }
  duoStage.enemyRendererRoot=ui_root(duoStage.enemyRenderer);
  if(!duoStage.enemyRendererRoot)duoStage.enemyRenderer=NULL;
  ui_unroot(pr);
 }
 /* Keep the same inner pair when Oscar and the other members join. */
 const int lineup[]={10316,11017,11116,11216,10216};
 int ranks[8];duoStage.count=s->ownerCount;
 float center[3];TrioVec ground;
 if(!trio_vec(duoStage.pos,anchor,&ground)){duo_stage_end();return;}
 center[0]=ground.x+duoStage.enemyCenterOffsetX;center[1]=ground.y;center[2]=ground.z;
 for(unsigned i=0;i<s->ownerCount;i++){
  LinkVisualOwner *o=&s->owners[i];Unit *u=unit_for_app(o->app);
  DuoStageMember *m=&duoStage.members[i];m->parent=body_get(o->go,"get_transform");
  m->pivot=duo_child(m->parent,"[Transform,Fixed]ScaleAndPositionPivot");m->root=ui_root(m->pivot);
  if(!m->root||!u||!u->view||!trio_vec(duoStage.pos,m->pivot,&m->nativeStart)){duo_stage_end();return;}
  m->captureNativeStart=trioStage.part!=0;
  m->enemyStart=(TrioVec){center[0],center[1],center[2]};
  ranks[i]=5+(int)i;
  for(int j=0;j<5;j++)if(lineup[j]==o->id)ranks[i]=j;
  if(s->ensembleSize==2&&s->ownerCount==2)ranks[i]=o->id<s->owners[1-i].id?0:1;
  m->app=o->app;m->view=u->view;m->side=ranks[i]%2?1:-1;
  m->width=trio_half_width(o);
  /* S6 and S10 have dedicated FollowPositions. Their oppositeActor flags
     differ for Faust and Gregor; their initial distances also differ. */
  int s6=!strncmp(s->coinAsset,"11116_S6_Link_",14),s10=!strncmp(s->coinAsset,"11116_S10_Link_",15);
  if(s6||s10){
   m->side=(o->id==10316||(s6&&o->id==10216)||(s10&&o->id==11216))?1:-1;
   m->entry=o->id==10316||o->id==11017?7.5f:(s6&&o->id==11216?12.f:6.f);
  }
  for(unsigned j=0;j<sizeof(wedgeMoveCues)/sizeof(*wedgeMoveCues);j++){
   if(wedgeMoveCues[j].owner!=o->id||strcmp(wedgeMoveCues[j].asset,s->coinAsset))continue;
   if(!m->cueCount)m->cueStart=(int)j;m->cueCount++;
  }
 }
 for(unsigned i=0;i<s->ownerCount;i++){
  DuoStageMember *m=&duoStage.members[i];m->gap=fmaxf(1.6f,enemyWidth+m->width+.1f);
  for(unsigned j=0;j<s->ownerCount;j++)if(ranks[j]<ranks[i]&&duoStage.members[j].side==m->side)
   m->gap+=2.f*duoStage.members[j].width+.2f;
  m->entry=fmaxf(m->entry,m->gap+(m->cueCount?m->width:0));
 }
 if(trioStage.part)trio_stage_end();
 duoStage.active=1;char msg[160];snprintf(msg,sizeof(msg),"duo stage target=%p ensemble=%d members=%u directions=%d",target,s->ensembleSize,s->ownerCount,duoStage.hasDirection);bootlog(msg);
}
static void duo_stage_tick(LinkVisualScene *s,double t){
 if(s->ensembleSize<2)return;
 if(!duoStage.active){
  if(t<duoStage.nextAttempt)return;
  duo_stage_begin(s);duoStage.nextAttempt=t+.25;
 }
 float center[3];if(!duo_stage_center(center))return;
 for(unsigned i=0;i<duoStage.count;i++){
  DuoStageMember *m=&duoStage.members[i];TrioVec world,local;
  if(rfield(m->view,"_curAppearance")!=m->app){duo_restore_member(m);continue;}
  if(!trio_vec(duoStage.local,m->pivot,&local)||!trio_vec(duoStage.pos,m->pivot,&world))continue;
  /* The validation read preceded release of the trio's display offset. */
  if(m->captureNativeStart){m->nativeStart=world;m->captureNativeStart=0;}
  if(!m->wrote||!trio_same(local,m->applied))m->original=local;
  /* The victim supplies horizontal aim. Its hit reaction may lift the
     entire appearance; each attacker's feet belong to their own stage. */
  TrioVec dst={center[0]+m->side*m->gap,m->nativeStart.y,m->enemyStart.z-.05f};
  /* Recover the authored world position without undoing our display offset.
     Parent transforms carry the MoveTrack, the pivot carries local animation. */
  if(m->parent&&duoStage.transformPoint){
   void *args[]={&m->original};int ok=0;
   void *box=call_obj(duoStage.transformPoint,m->parent,args,&ok);
   TrioVec *v=ok&&box?(TrioVec*)ui_unbox(box):NULL;
   if(v&&isfinite(v->x)&&isfinite(v->y)&&isfinite(v->z)){
    float start=fabsf(m->nativeStart.x-m->enemyStart.x);
    float travel=fabsf(v->x-m->enemyStart.x)-start;
    if(fabsf(v->x-m->nativeStart.x)+fabsf(v->y-m->nativeStart.y)>.04f)m->nativeMoving=1;
    TrioVec p=wedge_move_pose(m,t);
    if(m->nativeMoving){
     p.x=m->entry+travel;
     float ownRise=v->y-m->nativeStart.y,victimRise=center[1]-m->enemyStart.y;
     if(fabsf(victimRise)<.01f||fabsf(ownRise-victimRise)>.01f)p.y=ownRise;
     p.z=v->z-m->nativeStart.z;
    }
    dst.x=center[0]+m->side*fmaxf(m->gap,p.x);dst.y+=p.y;dst.z+=p.z;
   }
  }
  if(!trio_same(world,dst)){
   void *args[]={&dst};if(call_exc(duoStage.setPos,m->pivot,args)&&trio_vec(duoStage.local,m->pivot,&m->applied))m->wrote=1;
  }
  TrioVec sc;if(!duoStage.hasDirection||!duoStage.dir||!duoStage.setScale||!trio_vec(duoStage.localScale,m->pivot,&sc))continue;
  int native=call_int(duoStage.dir,m->view,NULL);
  if(native!=duoStage.left&&native!=duoStage.right)continue;
  if(!m->scaled||!trio_same(sc,m->appliedScale))m->scale=sc;
  TrioVec facing=m->scale;if(native!=(m->side<0?duoStage.right:duoStage.left))facing.x=-facing.x;
  if(!trio_same(facing,sc)){
   void *args[]={&facing};if(call_exc(duoStage.setScale,m->pivot,args)){m->appliedScale=facing;m->scaled=1;}
  }
 }
}
