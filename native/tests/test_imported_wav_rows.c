#include <windows.h>
#include <assert.h>
#include "imported_wav_rows.h"

int main(void){
 ImportedWavRow row;
 char combined[]="11116\tbattle_s2_11116_1_1-01\t0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef.wav\tcustom caption";
 assert(imported_wav_row(combined,&row));
 assert(imported_wav_rank(&row,10101,"battle_s2_10101_1_1-01",0)>0);
 assert(imported_wav_rank(&row,10101,"battle_s2_10101_1_1-02",0)==0);
 assert(imported_wav_rank(&row,10102,"battle_s2_10101_1_1-01",0)==0);
 assert(imported_wav_rank(&row,11116,"battle_s2_11116_1_1-01",0)>0);
 char textOnly[]="11116\tbattle_s2_11116\t\tcustom caption";
 assert(imported_wav_row(textOnly,&row));
 assert(imported_wav_rank(&row,10101,"battle_s2_10101_1",1)>0);
 assert(imported_wav_rank(&row,10101,"battle_s2_10101_1",0)==0);
 assert(imported_wav_rank(&row,10101,"battle_s20_10101_1",1)==0);
 char escape[]="11116\tbattle_s2_11116\t../sample.wav\t";
 assert(!imported_wav_row(escape,&row));
 char unrelated[]="11116\tstage_11116\t\tcustom caption";
 assert(!imported_wav_row(unrelated,&row));
 char wrongOwner[]="11116\tbattle_s2_10101_1\t\tcustom caption";
 assert(!imported_wav_row(wrongOwner,&row));
 char misleadingOwner[]="11116\tbattle_s2_10101_1_11116\t\tcustom caption";
 assert(!imported_wav_row(misleadingOwner,&row));
 const char prefix[]="11116\tbattle_s2_11116\t\t";
 char longCaption[sizeof(prefix)+4096];
 memcpy(longCaption,prefix,sizeof(prefix)-1);
 memset(longCaption+sizeof(prefix)-1,'x',4095);
 longCaption[sizeof(prefix)+4094]=0;
 assert(imported_wav_row(longCaption,&row)&&strlen(row.caption)==4095);
 memcpy(longCaption,prefix,sizeof(prefix)-1);
 longCaption[sizeof(prefix)+4094]='x';
 longCaption[sizeof(prefix)+4095]=0;
 assert(!imported_wav_row(longCaption,&row));
 return 0;
}
