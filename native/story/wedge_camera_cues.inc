/* Scan the same rooted native TimelineAsset whose graph is about to play.
   A shot can span a coin boundary. Keep camera ownership with the director
   during both its authored clips and the intervals between them. */
#include "wedge_stock_shots.h"
static int wedge_camera_cues(const char *assetName){
 int count=0;
 for(int i=0;i<g_wedgeTrackMap.count;i++){
  const WedgeTrack *row=&g_wedgeTrackMap.rows[i];
  if(strncmp(row->name,"On Battle Cam ",14)&&strcmp(row->name,"CamActor"))continue;
  void *muted=find_method(ui_class(row->ptr),"get_mutedInHierarchy",0);
  if(muted&&call_bool(muted,row->ptr,NULL)==1)continue;
  int n=list_count(rfield(row->ptr,"m_Clips"));
  if(n>0&&n<=4096)count+=n;
 }
 if(count>0)return count;
 for(unsigned i=0;i<sizeof(wedgeStockShots)/sizeof(*wedgeStockShots);i++){
  if(!strcmp(wedgeStockShots[i].name,assetName))return wedgeStockShots[i].count;
 }
 return 0;
}

/* Camera playables are driven by CharacterAppearance. CamActor under
   DoNotAdj is a recorded AnimationTrack for a camera rig, not a unit. */
static int wedge_rebind_camera_owners(void *lead,void *director,void *setter){
 int changed=0;
 for(int i=0;i<g_wedgeTrackMap.count;i++){
  const WedgeTrack *row=&g_wedgeTrackMap.rows[i];
  if(!row->root||!row->owner||
     (strncmp(row->name,"On Battle Cam Zoom Track",24)&&strncmp(row->name,"On Battle Cam Rotate Track",26)))continue;
  void *receiver=wedge_presentation_owner(lead,row->owner);
  if(!receiver||receiver==lead)continue;
  void *a[]={row->ptr},*exc=NULL;
  if(ui_invoke(director_binding_method,director,a,&exc)!=lead||exc)continue;
  void *replace[]={row->ptr,receiver};
  ui_invoke(setter,director,replace,&exc);
  if(!exc&&ui_invoke(director_binding_method,director,a,&exc)==receiver&&!exc)changed++;
 }
 if(changed){char line[90];snprintf(line,sizeof(line),"wedge authored camera owners rebound=%d",changed);bootlog(line);}
 return changed;
}
