#ifndef IMPORTED_WAV_ROWS_H
#define IMPORTED_WAV_ROWS_H
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "voice_owner_field.h"

typedef struct {
 unsigned owner;
 const char *key, *wav, *caption;
} ImportedWavRow;

static int imported_wav_row(char *line, ImportedWavRow *row){
 char *key=strchr(line,'\t');
 if(!key)return 0;
 *key++=0;
 char *wav=strchr(key,'\t');
 if(!wav)return 0;
 *wav++=0;
 char *caption=strchr(wav,'\t');
 if(!caption)return 0;
 *caption++=0;
 size_t digits=strspn(line,"0123456789"), k=strlen(key);
 if(digits<3||digits>8||*line=='0'||line[digits]||k<8||k>=192||strlen(caption)>4095||
    strncmp(key,"battle",6)||strspn(key,"abcdefghijklmnopqrstuvwxyz0123456789_-")!=k||
    strpbrk(caption,"\r\n\t")||(!*wav&&!*caption))return 0;
 if(*wav&&(strspn(wav,"0123456789abcdef")!=64||strcmp(wav+64,".wav")))return 0;
 if(*caption&&!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,caption,-1,NULL,0))return 0;
 unsigned owner=(unsigned)strtoul(line,NULL,10);
 if(!battle_voice_speaker(key,owner))return 0;
 *row=(ImportedWavRow){owner,key,wav,caption};
 return 1;
}

/* Preserve the complete variant suffix, including nested indices and any
   numbered WAV variant explicitly named by the game's event. An unnumbered
   caption can label the whole event, independently of its audio variants. */
static int imported_wav_rank(const ImportedWavRow *row,unsigned source,const char *key,int caption){
 if(!(caption?*row->caption:*row->wav))return 0;
 const char *owner=battle_voice_speaker(row->key,row->owner);
 if(!owner)return 0;
 if(!strcmp(row->key,key))return 4;
 const char *incoming=battle_voice_speaker(key,source);
 if(!incoming)incoming=battle_voice_speaker(key,row->owner);
 if(!incoming||incoming-key!=owner-row->key||strncmp(key,row->key,(size_t)(incoming-key)))return 0;
 const char *rowSuffix=owner+strspn(owner,"0123456789");
 const char *incomingSuffix=incoming+strspn(incoming,"0123456789");
 if(!strcmp(rowSuffix,incomingSuffix))return 3;
 if(caption&&!*rowSuffix&&*incomingSuffix=='_')return 1;
 return 0;
}
#endif
