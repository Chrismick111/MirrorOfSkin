#ifndef SR_CAMERA_POLICY_H
#define SR_CAMERA_POLICY_H
/* A viewer spans every coin in a skill. Its existence is not a camera lock. */
static int sr_coin_switch_ready(int viewer_active,int camera_owned,int timeline_busy){
 (void)viewer_active;
 return !camera_owned&&!timeline_busy;
}
static int sr_idle_restore_ready(int viewer,int at_base,int base_busy,int donor_busy,int repeated,int *quiet_frames){
 if(viewer||!at_base||base_busy||donor_busy){*quiet_frames=0;return 0;}
 if(repeated)return 0;
 if(*quiet_frames<3)++*quiet_frames;
 return *quiet_frames>=3;
}
#endif
