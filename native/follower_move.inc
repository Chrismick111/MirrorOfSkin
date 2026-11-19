/* Movement notifications from the serialized CharacterAppearanceTimelineTrack.
   Compare actual MonoScript classes: display names have editor suffixes and
   a movement-only track can contain a marker named "Skill Give Timing...". */
static void *move_game_class(const char *name){
 return ((void *(*)(void *,const char *,const char *))api[API_CLASS])(g_game,"",name);
}

static int move_track_has_owner_markers(void *track){
 if(ui_class(track)!=move_game_class("CharacterAppearanceTimelineTrack"))return 0;
 void *countMethod=find_method(ui_class(track),"GetMarkerCount",0);
 void *itemMethod=find_method(ui_class(track),"GetMarker",1);
 if(!countMethod||!itemMethod||!team_returns(countMethod,"System.Int32")||
    !team_returns(itemMethod,"UnityEngine.Timeline.IMarker"))return 0;
 int ok=0;
 void *countBox=call_obj(countMethod,track,NULL,&ok);
 const int *value=ok&&countBox?(const int *)ui_unbox(countBox):NULL;
 if(!value||*value<=0||*value>128)return 0;
 int count=*value,hasMove=0;
 void *direction=move_game_class("SkillGiveTiming_SetDirection");
 void *relative=move_game_class("SkillGiveTiming_TweenMove_RelativeV2");
 void *toTarget=move_game_class("SkillGiveTiming_TweenMove_ToTarget_Wide");
 /* Linked unit movement tracks can also carry authored shake notifications.
    They retain their original schedule and run exactly once on the declared
    UnitID receiver. Camera framing has separate playable tracks. */
 void *shake=move_game_class("CharacterAppearanceMarker_CameraShaker_Detail");
 for(int i=0;i<count;i++){
  void *args[]={&i};
  void *marker=call_obj(itemMethod,track,args,&ok);
  void *klass=ok&&marker?ui_class(marker):NULL;
  if(!klass)return 0;
  if(klass==relative||klass==toTarget)hasMove=1;
  else if(klass!=direction&&klass!=shake)return 0;
 }
 return hasMove;
}

static int wedge_rebind_movement(void *actor,void *director,void *setter){
 int changed=0;
 for(int i=0;i<g_wedgeTrackMap.count;i++){
  const WedgeTrack *track=&g_wedgeTrackMap.rows[i];
  if(!track->root||!track->owner||strcmp(track->name,"MoveTrack"))continue;
  void *owner=wedge_presentation_owner(actor,track->owner);
  if(!owner||owner==actor||!move_track_has_owner_markers(track->ptr))continue;
  void *args[]={track->ptr};
  void *exc=NULL;
  void *old=ui_invoke(director_binding_method,director,args,&exc);
  if(exc||old!=actor)continue;
  void *replacement[]={track->ptr,owner};
  ui_invoke(setter,director,replacement,&exc);
  void *actual=exc?NULL:ui_invoke(director_binding_method,director,args,&exc);
  int accepted=!exc&&actual==owner;
  changed+=accepted;
  char line[240];
  snprintf(line,sizeof(line),"wedge follower movement owner=%d path=%s old=%p target=%p accepted=%d",
           track->owner,track->path,old,owner,accepted);
  bootlog(line);
 }
 return changed;
}
