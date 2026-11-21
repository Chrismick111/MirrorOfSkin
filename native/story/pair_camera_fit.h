#ifndef PAIR_CAMERA_FIT_H
#define PAIR_CAMERA_FIT_H
#include <math.h>
#include <float.h>
typedef struct {float x,y,z;} PcPoint;
typedef struct {int ortho;float cx,cy,kx,ky,nearPlane;} PcLens;
typedef struct {float x,y,back,scale;} PcAdjustment;
static int pc_intersect(const PcPoint *p,int n,PcLens l,float back,float scale,PcAdjustment *out){
 float xl=-FLT_MAX,xh=FLT_MAX,yl=-FLT_MAX,yh=FLT_MAX;
 for(int i=0;i<n;i++){
  float z=p[i].z+back;if(!isfinite(z)||z<l.nearPlane)return 0;
  float d=l.ortho?scale:z;
  xl=fmaxf(xl,p[i].x-(.90f-l.cx)*d/l.kx);
  xh=fminf(xh,p[i].x-(.10f-l.cx)*d/l.kx);
  yl=fmaxf(yl,p[i].y-(.90f-l.cy)*d/l.ky);
  yh=fminf(yh,p[i].y-(.10f-l.cy)*d/l.ky);
 }
 if(xl>xh||yl>yh)return 0;
 *out=(PcAdjustment){fmaxf(xl,fminf(xh,0)),fmaxf(yl,fminf(yh,0)),back,scale};return 1;
}
/* Prefer a pan to a zoom. Solve for the smallest common dolly distance (or
   orthographic size) for which every projected body corner fits. */
static int pc_fit(const PcPoint *p,int n,PcLens l,PcAdjustment *out){
 if(n<1||n>72||!(l.kx>0&&l.ky>0&&l.nearPlane>0)||!isfinite(l.cx)||!isfinite(l.cy))return 0;
 float back=0,hi=1,lo=0;
 for(int i=0;i<n;i++){
  if(!isfinite(p[i].x)||!isfinite(p[i].y)||!isfinite(p[i].z))return 0;
  if(p[i].z<l.nearPlane)back=fmaxf(back,l.nearPlane-p[i].z+.001f);
 }
 if(pc_intersect(p,n,l,back,1,out))return 1;
 int found=0;
 for(int i=0;i<24;i++,hi*=2){
  if(pc_intersect(p,n,l,back+(l.ortho?0:hi),1+(l.ortho?hi:0),out)){found=1;break;}
 }
 if(!found)return 0;
 for(int i=0;i<20;i++){
  float mid=(lo+hi)*.5f;
  if(pc_intersect(p,n,l,back+(l.ortho?0:mid),1+(l.ortho?mid:0),out))hi=mid;else lo=mid;
 }
 return pc_intersect(p,n,l,back+(l.ortho?0:hi),1+(l.ortho?hi:0),out);
}
#endif
