#include <assert.h>
#include "sinners_native.c"
int main(void){
 ImportedConfig policy={0};
 assert(imported_attack_group_allowed(&policy,7));
 policy.roles[32]=2;
 assert(!imported_attack_group_allowed(&policy,32));
 policy.groupCount=3;policy.groups[0]=7;policy.groups[1]=8;policy.groups[2]=24;
 assert(imported_attack_group_allowed(&policy,7));
 assert(imported_attack_group_allowed(&policy,24));
 assert(!imported_attack_group_allowed(&policy,9));
 assert(!imported_attack_group_allowed(&policy,32));
 assert(!imported_attack_group_allowed(&policy,-1));
 return 0;
}
