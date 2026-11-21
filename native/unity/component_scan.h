#ifndef COMPONENT_SCAN_H
#define COMPONENT_SCAN_H
#include <stdint.h>
static int component_entry_matches(uintptr_t base,uintptr_t ptr,uintptr_t rva,int in_game){return in_game&&base&&ptr&&ptr>=base&&ptr-base==rva;}
#endif
