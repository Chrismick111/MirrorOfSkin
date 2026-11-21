/* Fit the native battle camera only when the requested appearance bounds leave
   its viewport. The native director still supplies its orientation and shot. */
#include "pair_camera_fit.h"
typedef struct {PcPoint center,extents;} PcBounds;
typedef struct {
 void *main,*view,*projection,*ortho,*nearPlane,*farPlane,*size,*setSize,*transform,*position,*setPosition,*right,*up,*forward,*bounds;
} PcMethods;
static PcMethods pcMethods;
static struct {
 void *camera,*tr;uintptr_t cameraRoot,trRoot;
 PcPoint original,applied;float size,appliedSize;
 PcPoint shown;float shownSize;double lastTime;int following;
 int wrotePosition,wroteSize,requests,corrected,visible,unavailable,measureFailed;
 int nativeFrames,cues,focusFrames;
} pc;
static int pc_value(void *method,void *obj,void *out,size_t bytes){
 int ok=0;void *b=method?call_obj(method,obj,NULL,&ok):NULL;
 void *v=ok&&b?ui_unbox(b):NULL;if(!v)return 0;memcpy(out,v,bytes);return 1;
}
static int pc_set(void *method,void *obj,void *value){
 void *args[]={value};return method&&obj&&call_exc(method,obj,args);
}
static int pc_close(PcPoint a,PcPoint b){
 return fabsf(a.x-b.x)<.0001f&&fabsf(a.y-b.y)<.0001f&&fabsf(a.z-b.z)<.0001f;
}
/* A director pan may replace only one world coordinate. Undo our previous
   contribution independently on the coordinates it left in place. */
static float pc_native_axis(float current,float applied,float original){
 return applied!=original&&fabsf(current-applied)<.0001f?original:current;
}
static void pc_observe_position(PcPoint now){
 if(pc.wrotePosition){
  pc.original=(PcPoint){pc_native_axis(now.x,pc.applied.x,pc.original.x),
                        pc_native_axis(now.y,pc.applied.y,pc.original.y),
                        pc_native_axis(now.z,pc.applied.z,pc.original.z)};
 }else pc.original=now;
 pc.applied=now;pc.wrotePosition=!pc_close(now,pc.original);
}
static void pc_restore(void){
 PcPoint now;float size;
 if(pc.wrotePosition&&pc.tr&&pc_value(pcMethods.position,pc.tr,&now,sizeof(now))){
  pc_observe_position(now);
  if(pc.wrotePosition)pc_set(pcMethods.setPosition,pc.tr,&pc.original);
 }
 if(pc.wroteSize&&pc.camera&&pc_value(pcMethods.size,pc.camera,&size,sizeof(size))&&fabsf(size-pc.appliedSize)<.0001f)
  pc_set(pcMethods.setSize,pc.camera,&pc.size);
 pc.wrotePosition=pc.wroteSize=pc.following=0;
}
static void pc_release(void){
 pc_restore();ui_unroot(pc.cameraRoot);ui_unroot(pc.trRoot);
 pc.camera=pc.tr=NULL;pc.cameraRoot=pc.trRoot=0;
}
static void pair_camera_end(void){
 pc_release();
 if(pc.requests){
  char line[240];snprintf(line,sizeof(line),"link camera frames=%d fit=%d allVisible=%d cameraUnavailable=%d invalidBoundsOrProjection=%d nativeCameraFrames=%d cues=%d contactFocusFrames=%d",
   pc.requests,pc.corrected,pc.visible,pc.unavailable,pc.measureFailed,pc.nativeFrames,pc.cues,pc.focusFrames);bootlog(line);
 }
 memset(&pc,0,sizeof(pc));
}
/* Source times restart at zero for each coin. Continue the filtered pose only
   on a synchronous successor in the same viewer/action. */
static void pair_camera_continue(void){pc.lastTime=0;}
static void pc_init(void){
 void *c=unity_class_anywhere("UnityEngine","Camera"),*tr=unity_class_anywhere("UnityEngine","Transform"),*r=unity_class_anywhere("UnityEngine","Renderer");
 if(!c||!tr||!r)return;
#define PC_GET(field,klass,name) pcMethods.field=find_method(klass,name,0)
 PC_GET(main,c,"get_main");PC_GET(view,c,"get_worldToCameraMatrix");PC_GET(projection,c,"get_projectionMatrix");PC_GET(ortho,c,"get_orthographic");
 PC_GET(nearPlane,c,"get_nearClipPlane");PC_GET(farPlane,c,"get_farClipPlane");PC_GET(size,c,"get_orthographicSize");PC_GET(transform,c,"get_transform");
 PC_GET(position,tr,"get_position");PC_GET(right,tr,"get_right");PC_GET(up,tr,"get_up");PC_GET(forward,tr,"get_forward");PC_GET(bounds,r,"get_bounds");
#undef PC_GET
 pcMethods.setSize=find_method(c,"set_orthographicSize",1);pcMethods.setPosition=find_method(tr,"set_position",1);
}
static PcPoint pc_view(const float *m,PcPoint a){
 /* Unity Matrix4x4 is stored by columns; in camera space forward is -Z. */
 return (PcPoint){m[0]*a.x+m[4]*a.y+m[8]*a.z+m[12],m[1]*a.x+m[5]*a.y+m[9]*a.z+m[13],
                  -(m[2]*a.x+m[6]*a.y+m[10]*a.z+m[14])};
}
static int pc_lens(void *cam,PcLens *l){
 float proj[16];uint8_t ortho=0;
 if(!pc_value(pcMethods.projection,cam,proj,sizeof(proj))||!pc_value(pcMethods.ortho,cam,&ortho,1)||
    !pc_value(pcMethods.nearPlane,cam,&l->nearPlane,sizeof(float)))return 0;
 l->ortho=ortho!=0;l->kx=proj[0]*.5f;l->ky=proj[5]*.5f;
 l->cx=.5f*(1+(ortho?proj[12]:-proj[8]));l->cy=.5f*(1+(ortho?proj[13]:-proj[9]));
 return l->nearPlane>0&&l->kx>0&&l->ky>0&&fabsf(proj[1])+fabsf(proj[4])+fabsf(proj[3])+fabsf(proj[7])<1e-5f&&
   fabsf(proj[11]-(ortho?0:-1))<1e-5f&&fabsf(proj[15]-(ortho?1:0))<1e-5f;
}
static int pc_camera(void){
 if(!pcMethods.main)pc_init();
 int ok=0;void *cam=pcMethods.main?call_obj(pcMethods.main,NULL,NULL,&ok):NULL;
 if(!cam||!ok){pc_release();return 0;}
 if(pc.camera!=cam){
  pc_release();pc.cameraRoot=ui_root(cam);if(!pc.cameraRoot)return 0;
  pc.camera=cam;pc.tr=call_obj(pcMethods.transform,cam,NULL,&ok);pc.trRoot=ok?ui_root(pc.tr):0;
  if(!pc.trRoot){pc_release();return 0;}
 }
 return 1;
}
static int pc_body_bounds(void *renderer,PcBounds *b){
 return renderer&&pc_value(pcMethods.bounds,renderer,b,sizeof(*b))&&
  isfinite(b->center.x)&&isfinite(b->center.y)&&isfinite(b->center.z)&&
  isfinite(b->extents.x)&&isfinite(b->extents.y)&&isfinite(b->extents.z)&&
  b->extents.x>=0&&b->extents.y>=0&&b->extents.z>=0&&b->extents.x+b->extents.y+b->extents.z>.00001f;
}
static int pc_points(LinkVisualScene *s,double t,PcPoint *world){
 int n=0,duo=s->ensembleSize==2;
 for(unsigned i=0;i<s->ownerCount;i++){
  LinkVisualOwner *o=&s->owners[i];
  if(!duo){
   int active=0;
   for(unsigned j=0;j<s->windowCount;j++){
    LinkVisualWindow *w=&s->windows[j];if(w->owner==(int)i&&w->duration>0&&t>=w->start&&t<w->start+w->duration){active=1;break;}
   }
   /* An original-skin follower has no donor window. Its native body keys
      still identify when it joins and leaves a group shot. */
   if(s->cameraCues>0){
    const LinkBeatRow *row=link_authored_row(s->coinAsset,o->id);
    if(row&&row->count>1){
     double first=linkBeatTimes[row->first],last=linkBeatTimes[row->first+row->count-1];
     active=t>=first-1e-6&&t<=last+.12;
    }
   }
   if(!active)continue;
  }
  Unit *u=unit_for_app(o->app);PcBounds b;
  if(!u||rfield(u->view,"_curAppearance")!=o->app)return -1;
  void *display=linkOverlays[i].visible?linkOverlays[i].renderer:NULL;
  if(!pc_body_bounds(display,&b)&&!pc_body_bounds(o->renderer,&b)){
   float c[3],e[3];if(!duo_stage_camera_bounds(i,c,e))return -1;
   b.center=(PcPoint){c[0],c[1],c[2]};b.extents=(PcPoint){e[0],e[1],e[2]};
  }
  for(int k=0;k<8;k++)world[n++]=(PcPoint){b.center.x+(k&1?b.extents.x:-b.extents.x),
     b.center.y+(k&2?b.extents.y:-b.extents.y),b.center.z+(k&4?b.extents.z:-b.extents.z)};
 }
 return n;
}
static int pc_project(void *cam,PcPoint *world,int n,PcPoint *local,PcLens *lens){
 float view[16];if(!pc_value(pcMethods.view,cam,view,sizeof(view))||!pc_lens(cam,lens))return 0;
 for(int i=0;i<n;i++)local[i]=pc_view(view,world[i]);return 1;
}
static int pc_inside(PcPoint *v,int n,PcLens l,float farClip,float margin){
 for(int i=0;i<n;i++){
  if(!isfinite(v[i].z)||v[i].z<l.nearPlane||v[i].z>farClip)return 0;
  float div=l.ortho?1:v[i].z,x=l.cx+l.kx*v[i].x/div,y=l.cy+l.ky*v[i].y/div;
  if(!isfinite(x)||!isfinite(y)||x<margin||x>1-margin||y<margin||y>1-margin)return 0;
 }return 1;
}
static float pc_dot(PcPoint a,PcPoint b){return a.x*b.x+a.y*b.y+a.z*b.z;}
static PcPoint pc_delta(PcPoint a,PcPoint b){return (PcPoint){a.x-b.x,a.y-b.y,a.z-b.z};}
static PcPoint pc_mix(PcPoint a,PcPoint b,float blend){
 return (PcPoint){a.x+(b.x-a.x)*blend,a.y+(b.y-a.y)*blend,a.z+(b.z-a.z)*blend};
}
/* Evaluate a hypothetical pose in memory; no intermediate transform reaches Unity. */
static PcLens pc_reframe(const PcPoint *source,PcPoint *out,int n,PcLens lens,
                        PcPoint delta,PcPoint x,PcPoint y,PcPoint z,float sizeRatio){
 float dx=pc_dot(delta,x),dy=pc_dot(delta,y),dz=pc_dot(delta,z);
 for(int i=0;i<n;i++)out[i]=(PcPoint){source[i].x+dx,source[i].y+dy,source[i].z+dz};
 if(lens.ortho){lens.kx*=sizeRatio;lens.ky*=sizeRatio;}
 return lens;
}
#include "pair_focus_cues.h"
static int pc_contact_cue(LinkVisualScene *s,double t){
 if(s->ensembleSize!=2||s->ownerCount!=2||(!s->owners[0].look[0]&&!s->owners[1].look[0]))return 0;
 for(unsigned i=0;i<sizeof(pcFocusCues)/sizeof(*pcFocusCues);i++){
  if(t>=pcFocusCues[i].start&&t<pcFocusCues[i].end&&!strcmp(pcFocusCues[i].scene,s->coinAsset))return 1;
 }
 return 0;
}
static void pair_camera_tick(LinkVisualScene *s,double t,double frameDelta){
 if(!(frameDelta>0))return;
 int authored=s->cameraCues>0,adapt=0;
 if(authored){
  for(unsigned i=0;i<s->ownerCount;i++)if(s->owners[i].look[0]){adapt=1;break;}
  pc.nativeFrames++;pc.cues=s->cameraCues;
  if(!adapt){pc.requests++;return;}
 }
 if(s->ownerCount<2){pc_restore();return;}
 if(t>s->end)return;
 pc.requests++;
 if(!pc_camera()){pc.unavailable++;return;}
 PcPoint world[72],local[72],trial[72],now,x,y,z;
 PcLens lens;float farClip=0,size=1;
 int n=pc_points(s,t,world);
 if(n<0){pc.measureFailed++;return;}
 int contact=authored&&pc_contact_cue(s,t);
 /* A native shot can lock to one actor. Frame the active attack bodies first,
    then include the victim during a duo lift or a group attack. */
 PcBounds enemy;
 if(n>0&&(contact||(authored&&s->ensembleSize>2))&&duoStage.active&&pc_body_bounds(duoStage.enemyRenderer,&enemy)){
  for(int k=0;k<8;k++)world[n++]=(PcPoint){enemy.center.x+(k&1?enemy.extents.x:-enemy.extents.x),
    enemy.center.y+(k&2?enemy.extents.y:-enemy.extents.y),enemy.center.z+(k&4?enemy.extents.z:-enemy.extents.z)};
 }
 int minimum=authored?8:16;
 if(n<minimum&&!pc.following)return;
 if(!pc_project(pc.camera,world,n,local,&lens)||!pc_value(pcMethods.farPlane,pc.camera,&farClip,sizeof(farClip))||
    !pc_value(pcMethods.position,pc.tr,&now,sizeof(now))||!pc_value(pcMethods.right,pc.tr,&x,sizeof(x))||
    !pc_value(pcMethods.up,pc.tr,&y,sizeof(y))||!pc_value(pcMethods.forward,pc.tr,&z,sizeof(z))||
    (lens.ortho&&(!pc_value(pcMethods.size,pc.camera,&size,sizeof(size))||!(size>0)))){
  pc.measureFailed++;return;
 }
 pc_observe_position(now);
 if(!pc.wroteSize||fabsf(size-pc.appliedSize)>.0001f){pc.size=size;pc.wroteSize=0;}
 PcPoint target=pc.original;float targetSize=pc.size;
 PcLens originalLens=pc_reframe(local,trial,n,lens,pc_delta(now,target),x,y,z,size/targetSize);
 /* Stop following individual sprite silhouettes. Trigger at 2% of the edge,
    leave 10% after a correction, release when the native shot fits comfortably. */
 if(n>=minimum&&!pc_inside(trial,n,originalLens,farClip,pc.following?.10f:.02f)){
  PcAdjustment a;if(!pc_fit(trial,n,originalLens,&a)){pc.measureFailed++;return;}
  for(int i=0;i<n;i++)if(trial[i].z+a.back>=farClip){pc.measureFailed++;return;}
  target.x+=a.x*x.x+a.y*y.x-a.back*z.x;
  target.y+=a.x*x.y+a.y*y.y-a.back*z.y;
  target.z+=a.x*x.z+a.y*y.z-a.back*z.z;
  targetSize*=a.scale;
  if(pc.following&&pc.shownSize>0){
   PcLens held=pc_reframe(local,trial,n,lens,pc_delta(now,pc.shown),x,y,z,size/pc.shownSize);
   if(pc_inside(trial,n,held,farClip,.02f)){target=pc.shown;targetSize=pc.shownSize;}
  }
 }
 if(pc.following){
  float blend=(float)-expm1(-(authored?frameDelta:fmax(0.,t-pc.lastTime))/.085);
  PcPoint smooth=pc_mix(pc.shown,target,blend);
  float smoothSize=pc.shownSize+(targetSize-pc.shownSize)*blend;
  PcLens preview=pc_reframe(local,trial,n,lens,pc_delta(now,smooth),x,y,z,size/smoothSize);
  /* Smooth only while the active fighters remain inside the actual shot. */
  if(!authored||pc_inside(trial,n,preview,farClip,0)){target=smooth;targetSize=smoothSize;}

 }
 pc.lastTime=t;
 int wrote=0;
 if(!pc_close(target,now)){
  if(!pc_set(pcMethods.setPosition,pc.tr,&target)){pc.measureFailed++;return;}
  pc.applied=target;pc.wrotePosition=1;wrote=1;
 }
 if(lens.ortho&&fabsf(targetSize-size)>.0001f){
  if(!pc_set(pcMethods.setSize,pc.camera,&targetSize)){pc.measureFailed++;return;}
  pc.appliedSize=targetSize;pc.wroteSize=1;wrote=1;
 }
 pc.shown=target;pc.shownSize=targetSize;
 pc.following=!pc_close(target,pc.original)||fabsf(targetSize-pc.size)>.0001f;
 if(wrote){pc.corrected++;if(contact)pc.focusFrames++;}
 if((!wrote||pc_project(pc.camera,world,n,local,&lens))&&pc_inside(local,n,lens,farClip,0))pc.visible++;
}
