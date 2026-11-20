/* A visual-only donor has no authored attack. Move only its own cloned
   appearance. Its hidden timing receiver continues to deliver native callbacks. */
typedef struct { float x,y,z; } VisiblePosition;
typedef struct {
 void *app,*transform,*read,*write;
 VisiblePosition rest,applied;
 uintptr_t root;
 DWORD start;
 int wrote;
} VisibleAttack;
static VisibleAttack visibleAttacks[SR_UNIT_MAX];
static int visible_position(VisibleAttack *attack,VisiblePosition *value){
 void *box=call_obj(attack->read,attack->transform,NULL,NULL);
 VisiblePosition *position=box?ui_unbox(box):NULL;
 if(!position||!isfinite(position->x)||!isfinite(position->y)||!isfinite(position->z))return 0;
 *value=*position;return 1;
}
static void visible_attack_end(Unit *u){
 VisibleAttack *attack=&visibleAttacks[u-g_units];
 if(!attack->root)return;
 VisiblePosition now;
 if(attack->wrote&&visible_position(attack,&now)&&!memcmp(&now,&attack->applied,sizeof now)){
  void *args[]={&attack->rest};call_exc(attack->write,attack->transform,args);
 }
 ui_unroot(attack->root);memset(attack,0,sizeof(*attack));
}
static VisiblePosition visible_attack_pose(VisiblePosition rest,DWORD elapsed){
 /* Short lift, strike and settle, in donor-local units. */
 float phase=(float)elapsed/420.f;
 float lift=phase<0.28f?phase/0.28f:phase<0.55f?(0.55f-phase)/0.27f:0;
 float strike=phase<0.28f?0:phase<0.55f?(phase-0.28f)/0.27f:phase<1?(1-phase)/0.45f:0;
 rest.y+=lift*.19f;rest.x+=strike*.46f-lift*.12f;return rest;
}
static void visible_attack_tick(Unit *u,DWORD now){
 VisibleAttack *attack=&visibleAttacks[u-g_units];
 if(!attack->root)return;
 DWORD elapsed=now-attack->start;
 if(!enabled_now()||cleanup_pending||u->dead||elapsed>=420||!held_appearance(u)||held_appearance(u)->app!=attack->app){
  visible_attack_end(u);return;
 }
 VisiblePosition current;
 if(!visible_position(attack,&current)){visible_attack_end(u);return;}
 /* If an authored control changed the transform, preserve its new position. */
 if(attack->wrote&&memcmp(&current,&attack->applied,sizeof current))attack->rest=current;
 VisiblePosition pose=visible_attack_pose(attack->rest,elapsed);
 void *args[]={&pose};if(call_exc(attack->write,attack->transform,args)){attack->applied=pose;attack->wrote=1;}
}
static void visible_attack_begin(Unit *u,Skin *skin,int detail,int coin){
 visible_attack_end(u);
 VisibleAttack *attack=&visibleAttacks[u-g_units];
 void *transform=call_obj(m_getTransform,skin->go,NULL,NULL);
 if(!transform)return;
 attack->read=find_method(ui_class(transform),"get_localPosition",0);
 attack->write=find_method(ui_class(transform),"set_localPosition",1);
 attack->transform=transform;
 if(!attack->write||!attack->read||!visible_position(attack,&attack->rest))return;
 attack->root=ui_root(transform);if(!attack->root)return;
 attack->app=skin->app;attack->start=GetTickCount()-16;visible_attack_tick(u,GetTickCount());
 char line[200];snprintf(line,sizeof line,"visible donor movement look=%.63s source=%d coin=%d applied=%d",skin->look,detail,coin,attack->wrote);bootlog(line);
}

/* Observe the primary body sprite before playback. A running director with
   no primary sprite renderer may be an animated multi-part or skeletal body. */
typedef struct {
 void *app,*renderer,*getSprite,*firstSprite;
 uintptr_t spriteRoot;
 DWORD start;
 int detail,coin;
} VisibleWatch;
static VisibleWatch visibleWatches[SR_UNIT_MAX];
static void visible_watch_clear(Unit *u){
 VisibleWatch *watch=&visibleWatches[u-g_units];
 ui_unroot(watch->spriteRoot);memset(watch,0,sizeof(*watch));
}
static void visible_watch_begin(Unit *u,Skin *skin,int detail,int coin){
 visible_watch_clear(u);visible_attack_end(u);
 VisibleWatch *watch=&visibleWatches[u-g_units];
 watch->app=skin->app;watch->detail=detail;watch->coin=coin;watch->start=GetTickCount();
 watch->renderer=rfield(skin->app,"sprenderer_charactermotion");
 if(watch->renderer)watch->getSprite=find_method(ui_class(watch->renderer),"get_sprite",0);
 if(watch->getSprite){
  watch->firstSprite=call_obj(watch->getSprite,watch->renderer,NULL,NULL);
  watch->spriteRoot=ui_root(watch->firstSprite);
 }
}
static void visible_watch_tick(Unit *u,DWORD now){
 VisibleWatch *watch=&visibleWatches[u-g_units];Skin *skin=held_appearance(u);
 if(!enabled_now()||cleanup_pending||u->dead||!skin||skin->app!=watch->app){
  visible_watch_clear(u);return;
 }
 if(watch->getSprite&&call_obj(watch->getSprite,watch->renderer,NULL,NULL)!=watch->firstSprite){
  visible_watch_clear(u);return;
 }
 /* A live director can hold the primary sprite while animating a weapon,
    a second body or a transform. Leave the authored motion untouched. */
 if(director_playing(skin->app)||presentation_busy(skin->app)||
    (u->endedApp==skin->app&&u->endedGeneration==u->playbackGeneration)){
  visible_watch_clear(u);return;
 }
 if(now-watch->start<180)return;
 visible_attack_begin(u,skin,watch->detail,watch->coin);
 visible_watch_clear(u);
}
