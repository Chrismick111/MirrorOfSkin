/* Visual-only staging for the three authored Oscar coin sections. The game keeps
   its battle transforms. Only the two visible appearance pivots are offset. */
typedef struct {float x,y,z;} TrioVec;
typedef struct {TrioVec center,extent;} TrioBounds;
typedef struct {
 void *pivot,*parent; uintptr_t pivotRoot,parentRoot;
 TrioVec original,applied,initialRoot;
 float spacing;int owner,role,wrote,retired,placed;
} TrioStageMember;
static struct {
 int part;void *lead,*position,*local,*write,*restore;uintptr_t leadRoot;
 TrioStageMember members[2];int count;
} trioStage;

static int trio_vec(void *method,void *target,TrioVec *v){
 int ok=0;void *box=target&&method?call_obj(method,target,NULL,&ok):NULL;
 const TrioVec *value=ok&&box?(const TrioVec *)ui_unbox(box):NULL;
 if(!value||!isfinite(value->x)||!isfinite(value->y)||!isfinite(value->z))return 0;
 *v=*value;return 1;
}
static int trio_same(TrioVec a,TrioVec b){
 return fabsf(a.x-b.x)+fabsf(a.y-b.y)+fabsf(a.z-b.z)<.003f;
}
static void trio_release_offset(TrioStageMember *m){
 TrioVec local;
 if(m->wrote&&trio_vec(trioStage.local,m->pivot,&local)&&trio_same(local,m->applied)){
  void *args[]={&m->original};call_exc(trioStage.restore,m->pivot,args);
 }
 m->wrote=0;
}
static void trio_stage_end(void){
 for(int i=0;i<trioStage.count;i++){
  TrioStageMember *m=&trioStage.members[i];trio_release_offset(m);
  if(m->placed){
   char line[140];snprintf(line,sizeof(line),"trio stage part=%d owner=%d placed=%d nativeTookOver=%d",trioStage.part,m->role,m->placed,m->retired);bootlog(line);
  }
  ui_unroot(m->parentRoot);ui_unroot(m->pivotRoot);
 }
 ui_unroot(trioStage.leadRoot);memset(&trioStage,0,sizeof(trioStage));
}
static float trio_half_width(LinkVisualOwner *o){
 int ok=0;void *get=o->renderer?find_method(ui_class(o->renderer),"get_bounds",0):NULL;
 void *b=get?call_obj(get,o->renderer,NULL,&ok):NULL;
 TrioBounds *bounds=ok&&b?(TrioBounds*)ui_unbox(b):NULL;
 return bounds&&isfinite(bounds->extent.x)&&bounds->extent.x>0?bounds->extent.x:1;
}
static void trio_stage_begin(LinkVisualScene *s,void *asset){
 if(s->ensembleSize!=3||!asset)return;
 const char *n=wedge_name(asset);
 if(!n)return;
 int part=!strcmp(n,"11116_S5_Link_01")?1:!strcmp(n,"11116_S5_Link_02")?2:!strcmp(n,"11116_S5_Link_03")?3:0;
 if(!part)return;
 int lead=-1;
 for(unsigned i=0;i<s->ownerCount;i++)if(s->owners[i].id==11116)lead=(int)i;
 if(lead<0)return;
 void *tr=body_get(s->owners[lead].go,"get_transform");if(!tr)return;
 void *tc=ui_class(tr);
 trioStage.position=find_method(tc,"get_position",0);trioStage.local=find_method(tc,"get_localPosition",0);
 trioStage.write=find_method(tc,"set_position",1);trioStage.restore=find_method(tc,"set_localPosition",1);
 if(!trioStage.write||!trioStage.restore||!trioStage.position||!trioStage.local)return;
 trioStage.leadRoot=ui_root(tr);if(!trioStage.leadRoot)return;
 trioStage.lead=tr;trioStage.part=part;
 float leadWidth=trio_half_width(&s->owners[lead]);
 for(unsigned i=0;i<s->ownerCount&&trioStage.count<2;i++){
  LinkVisualOwner *o=&s->owners[i];
  if((o->id!=10316&&o->id!=11017)||!o->renderer)continue;
  void *parent=body_get(o->go,"get_transform");if(!parent)continue;
  void *path=make_string("[Transform,Fixed]ScaleAndPositionPivot");uintptr_t nameRoot=ui_root(path);
  const char *types[]={"System.String"};void *find=method_by_types_one(ui_class(parent),"Find",types,1);
  int ok=0;void *args[]={path};void *pivot=nameRoot&&find?call_obj(find,parent,args,&ok):NULL;
  uintptr_t root=ok&&pivot?ui_root(pivot):0;ui_unroot(nameRoot);
  if(!root)continue;
  TrioStageMember m={0};m.pivot=pivot;m.pivotRoot=root;m.parent=parent;m.parentRoot=ui_root(parent);
  if(!m.parentRoot||!trio_vec(trioStage.position,parent,&m.initialRoot)){ui_unroot(root);ui_unroot(m.parentRoot);continue;}
  m.owner=(int)i;m.role=o->id;m.spacing=fmaxf(1.3f,leadWidth+trio_half_width(o)+.2f);
  trioStage.members[trioStage.count++]=m;
 }
}
static float trio_progress(int part,int role,double t){
 /* From the original follower MoveTracks. Don enters on coin 1, Sinclair on
    coin 2. Coin 3 includes a one-unit relative step for Sinclair. */
 if(role==10316)return part>1?1.f:(float)fmin(1.,fmax(0.,(t-.2833333333)/.066));
 return part>2?1.f:part<2?0.f:(float)fmin(1.,fmax(0.,(t-.15)/.066));
}
static void trio_stage_tick(LinkVisualScene *s,double t){
 if(!trioStage.part)return;
 TrioVec lead;if(!trio_vec(trioStage.position,trioStage.lead,&lead))return;
 for(int i=0;i<trioStage.count;i++){
  TrioStageMember *m=&trioStage.members[i];LinkVisualOwner *o=&s->owners[m->owner];
  Unit *u=unit_for_app(o->app);TrioVec root,local;
  if(m->retired)continue;
  if(!u||rfield(u->view,"_curAppearance")!=o->app||!trio_vec(trioStage.position,m->parent,&root)||!trio_vec(trioStage.local,m->pivot,&local)){
   trio_release_offset(m);m->retired=1;continue;
  }
  /* A successful native dash closes the staging gap. Leave its travel and
     final placement intact; a depth-only sorting jump is not a dash. */
  float gap=fabsf(root.x-lead.x);
  if(fabsf(root.x-m->initialRoot.x)>.25f&&gap<=1.6f*m->spacing){
   trio_release_offset(m);m->retired=1;continue;
  }
  if(!m->wrote||!trio_same(local,m->applied))m->original=local;
  if(!m->wrote&&gap>=.65f*m->spacing&&gap<=1.4f*m->spacing&&fabsf(root.z-lead.z)<1.5f)continue;
  float progress=trio_progress(trioStage.part,m->role,t);
  float side=m->role==10316?-1.f:1.f;
  float step=trioStage.part==3&&m->role==11017?(float)fmin(1.,fmax(0.,(t-.0166666667)/.066)):0;
  TrioVec desired={lead.x+side*(m->spacing+(1-progress)*1.6f)+side*step,lead.y,lead.z+side*.25f};
  TrioVec actual;
  if(m->wrote&&trio_vec(trioStage.position,m->pivot,&actual)&&trio_same(actual,desired))continue;
  void *args[]={&desired};
  if(call_exc(trioStage.write,m->pivot,args)&&trio_vec(trioStage.local,m->pivot,&m->applied)){m->wrote=1;m->placed++;}
 }
}
