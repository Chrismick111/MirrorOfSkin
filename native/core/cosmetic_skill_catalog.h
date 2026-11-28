#ifndef SR_COSMETIC_SKILL_CATALOG_H
#define SR_COSMETIC_SKILL_CATALOG_H
#include <stdlib.h>
#include <string.h>

typedef struct { int id,defense,motion,tier,conditional,label; } SrUiSkill;
typedef struct { const char *key; int start,count,portrait; } SrUiOwner;
typedef struct { const char *identity,*file; } SrUiPortraitFile;
#include "cosmetic_skill_catalog_data.inc"

static int sr_ui_compare_skill(const void *key,const void *entry){
 int id=*(const int *)key, other=((const SrUiSkill *)entry)->id;
 return (id>other)-(id<other);
}
static const SrUiSkill *sr_ui_skill(int id){
 return bsearch(&id,sr_ui_skills,sizeof(sr_ui_skills)/sizeof(*sr_ui_skills),
                sizeof(*sr_ui_skills),sr_ui_compare_skill);
}
static int sr_ui_compare_owner(const void *key,const void *entry){
 return strcmp(key,((const SrUiOwner *)entry)->key);
}
/* An imported prefab address can be normalized to lowercase by Unity.
   Resolve it once when loading that appearance's display data. */
static const char *sr_ui_appearance_key(const char *key){
 if(!key||!*key)return NULL;
 const size_t count=sizeof(sr_ui_owners)/sizeof(*sr_ui_owners);
 const SrUiOwner *exact=bsearch(key,sr_ui_owners,count,sizeof(*sr_ui_owners),sr_ui_compare_owner);
 if(exact)return exact->key;
 const char *match=NULL;
 for(size_t i=0;i<count;i++){
  if(_stricmp(key,sr_ui_owners[i].key))continue;
  if(match)return NULL;
  match=sr_ui_owners[i].key;
 }
 return match;
}
static const SrUiOwner *sr_ui_owner(const char *identity,const char *look){
 const char *key=look&&*look?look:identity;
 if(!key)return NULL;
 if(!strncmp(key,"story_",6))key+=6;
 const SrUiOwner *owner=bsearch(key,sr_ui_owners,sizeof(sr_ui_owners)/sizeof(*sr_ui_owners),
                                sizeof(*sr_ui_owners),sr_ui_compare_owner);
 if(!owner&&identity&&strspn(identity,"0123456789")==5&&identity[5]==0)
  owner=bsearch(identity,sr_ui_owners,sizeof(sr_ui_owners)/sizeof(*sr_ui_owners),
                sizeof(*sr_ui_owners),sr_ui_compare_owner);
 return owner;
}
static int sr_cosmetic_stock_portrait(const char *identity,const char *look){
 const SrUiOwner *owner=sr_ui_owner(identity,look);
 return owner?owner->portrait:0;
}
static int sr_ui_compare_portrait(const void *key,const void *entry){
 return strcmp(key,((const SrUiPortraitFile *)entry)->identity);
}
static const char *sr_cosmetic_cached_portrait(const char *identity){
 if(!identity)return NULL;
 const SrUiPortraitFile *row=bsearch(identity,sr_ui_portrait_files,
    sizeof(sr_ui_portrait_files)/sizeof(*sr_ui_portrait_files),sizeof(*sr_ui_portrait_files),sr_ui_compare_portrait);
 return row?row->file:NULL;
}
static int sr_cosmetic_source_conditional(int skill_id){
 const SrUiSkill *s=sr_ui_skill(skill_id);
 return s?s->conditional:-1;
}
static int sr_cosmetic_stock_skill(const char *identity,const char *look,int source_id,
                                   int tier,int defense,int conditional){
 const SrUiOwner *owner=sr_ui_owner(identity,look);
 const SrUiSkill *source=sr_ui_skill(source_id);
 if(!owner||!source||defense!=(source->defense!=0))return 0;
 int best=0,match=0;
 for(int i=0;i<owner->count;i++){
  int id=sr_ui_member_ids[owner->start+i];
  if(id==source_id)return id;
  const SrUiSkill *candidate=sr_ui_skill(id);
  if(!candidate||(candidate->defense!=0)!=defense)continue;
  int score=0;
  if(source->label&&source->label==candidate->label&&source->defense==candidate->defense&&
     source->conditional>=0&&source->conditional==candidate->conditional&&
     !(conditional>0&&candidate->conditional==0))
   score=4;
  else if(conditional!=0||source->conditional!=0||candidate->conditional!=0)continue;
  else if(defense)score=source->defense==candidate->defense?3:1;
  else if(source->motion&&source->motion==candidate->motion){
   score=candidate->tier==tier?3:2;
  }
  if(score>best){best=score;match=id;}
  else if(score==best)match=0;
 }
 return match;
}

static int sr_cosmetic_stock_display_skill(const char *identity,const char *look,int source_id,
                                           int tier,int defense,int conditional){
 const SrUiSkill *source=sr_ui_skill(source_id);
 if(!source||defense!=(source->defense!=0)||
    (conditional>=0&&source->conditional>=0&&source->conditional!=conditional))return 0;
 if(!defense&&!tier)tier=source->tier;
 int existing=sr_cosmetic_stock_skill(identity,look,source_id,tier,defense,conditional);
 if(existing==source_id)return existing;
 const SrUiSkill *matched=sr_ui_skill(existing);
 if(matched&&matched->defense==source->defense&&(defense||conditional!=0||matched->tier==tier||
    (source->label&&source->label==matched->label)))return existing;
 const SrUiOwner *owner=sr_ui_owner(identity,look);
 if(!owner||conditional<0||(!defense&&(tier<1||tier>3)))return 0;
 int match=0;
 for(int i=0;i<owner->count;i++){
  const SrUiSkill *candidate=sr_ui_skill(sr_ui_member_ids[owner->start+i]);
  if(!candidate||candidate->defense!=source->defense||candidate->conditional!=conditional||
     (!defense&&candidate->tier!=tier))continue;
  if(match)return 0;
  match=candidate->id;
 }
 return match;
}
#endif
