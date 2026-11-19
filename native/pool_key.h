#ifndef SR_POOL_KEY_H
#define SR_POOL_KEY_H

/* A single appearance may exist in multiple rules for the same sinner. */
static int sr_pool_same_key(const PoolRow *a, const PoolRow *b) {
 return a->sinner == b->sinner &&
        !strcmp(a->base_identity, b->base_identity) &&
        !strcmp(a->identity, b->identity)
#ifdef SR_POOL_HAS_GROUP_KEY
        && a->kind==b->kind && !strcmp(a->group_id,b->group_id)
#endif
        ;
}
#ifdef SR_POOL_HAS_GROUP_KEY
/* A new per-personality group can reuse a previously catalogued appearance,
   including when this sinner has never had a scoped row. The independent
   director file can arrive on its own poll, so group evaluation stays there. */
static int sr_pool_catalog_binding(const PoolRow *known,const PoolRow *row){
 if(strcmp(known->identity,row->identity)||known->story!=row->story||
    strcmp(known->asset_key,row->asset_key)||strcmp(known->appearance_name,row->appearance_name)||
    known->excluded!=row->excluded)return 0;
 if(!strcmp(known->base_identity,row->base_identity))return 1;
 if(known->base_identity[0]||!row->base_identity[0])return 0;
 if(row->kind==0&&row->weight==0)return 1;
 if(row->kind!=1||known->kind!=0||!row->group_id[0]||strlen(row->base_identity)!=5)return 0;
 int identity=0;
 for(int i=0;i<5;i++){
  char digit=row->base_identity[i];if(digit<'0'||digit>'9')return 0;
  identity=identity*10+digit-'0';
 }
 return (unsigned)(identity/100)==row->sinner;
}
#endif
static int sr_pool_find_key(const PoolRow *rows, uint32_t count, const PoolRow *key) {
 for (uint32_t i = 0; i < count; ++i)
  if (sr_pool_same_key(&rows[i], key)) return (int)i;
 return -1;
}
#endif
