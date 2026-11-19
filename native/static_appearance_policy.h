#ifndef SR_STATIC_APPEARANCE_POLICY_H
#define SR_STATIC_APPEARANCE_POLICY_H

/* Reserved protocol bit: a visual-only donor has no attack timeline. */
#define SR_STATIC_APPEARANCE_FLAG 0x40000000u

static int sr_static_lookup_detail(unsigned flags, int is_attack, int detail) {
 return (flags & SR_STATIC_APPEARANCE_FLAG) && is_attack ? 0 : detail;
}

/* The timeline receiver and the visible appearance must be considered
   separately. A visual-only donor cannot own attack callbacks. */
typedef struct {
 int show_donor;
 int keep_base_active;
 int hide_base_renderer;
 int forward_attack_to_base;
} SrStaticAppearancePlan;

static SrStaticAppearancePlan sr_static_appearance_plan(unsigned flags, int selected, int attack) {
 int static_selected = selected && !!(flags & SR_STATIC_APPEARANCE_FLAG);
 SrStaticAppearancePlan result = {
  !!selected, static_selected, static_selected, static_selected && !!attack
 };
 return result;
}
#endif
