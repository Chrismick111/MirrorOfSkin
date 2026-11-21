#include "sinners_native.c"
#include <assert.h>
int main(void){char a[128]="10102_YiSang_7Appearance(Clone)",b[32]="10102",c[64]="10103_bad",d[32]="10102_X ",e[32]="10102_";assert(normalize_source_name("10102",a)&&!strcmp(a,"10102_YiSang_7Appearance"));assert(!normalize_source_name("10102",b));assert(!normalize_source_name("10102",c));assert(normalize_source_name("10102",d)&&!strcmp(d,"10102_X"));assert(!normalize_source_name("10102",e));assert(!normalize_source_name("abcde",a));return 0;}
