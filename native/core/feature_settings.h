#ifndef SR_FEATURE_SETTINGS_H
#define SR_FEATURE_SETTINGS_H
#include <stdint.h>
#include <windows.h>

/* Runtime feature switches published by the Workbench from MOS_data/设置.json.
   The file is deliberately tiny so the native side never parses user JSON. */
#define SR_UI_SETTINGS_MAGIC UINT32_C(0x49555253) /* "SRUI" */
#define SR_UI_SETTINGS_VERSION 1u
enum {
 SR_UI_MASTER = 1u << 0, /* all cosmetic UI overrides */
 SR_UI_SKILL_NAME = 1u << 1,
 SR_UI_SKILL_ICON = 1u << 2,
 SR_UI_PORTRAIT = 1u << 3,
 SR_UI_BUFF = 1u << 4,
 SR_UI_ALL = SR_UI_MASTER | SR_UI_SKILL_NAME | SR_UI_SKILL_ICON | SR_UI_PORTRAIT | SR_UI_BUFF
};
typedef struct {uint32_t magic,version,flags;} SrUiSettingsHeader;

static uint32_t sr_ui_flags;
static int sr_ui_loaded;

static int sr_ui_on(uint32_t bit){
 return sr_ui_loaded&&(sr_ui_flags&bit)!=0;
}

static void sr_ui_settings_apply(uint32_t flags,const char *source){
 flags&=SR_UI_ALL;
 if(sr_ui_loaded&&flags==sr_ui_flags)return;
 sr_ui_flags=flags;sr_ui_loaded=1;
 char line[160];
 snprintf(line,sizeof(line),"feature settings %s cosmetic_ui=0x%02x master=%d name=%d icon=%d portrait=%d buff=%d",
          source,(unsigned)flags,sr_ui_on(SR_UI_MASTER),sr_ui_on(SR_UI_SKILL_NAME),
          sr_ui_on(SR_UI_SKILL_ICON),sr_ui_on(SR_UI_PORTRAIT),sr_ui_on(SR_UI_BUFF)!=0);
 bootlog(line);
}

static void poll_feature_settings(void){
 static DWORD last;
 DWORD now=GetTickCount();
 if(last&&(DWORD)(now-last)<500)return;
 last=now;
 wchar_t path[32768];
 sr_data_path(g_self,path,32768,L"native_ui.bin");
 if(!path[0])return;
 HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                         NULL,OPEN_EXISTING,0,NULL);
 if(file==INVALID_HANDLE_VALUE){
  DWORD error=GetLastError();
  if(error==ERROR_FILE_NOT_FOUND||error==ERROR_PATH_NOT_FOUND)
   sr_ui_settings_apply(0,"missing: cosmetic UI overrides disabled");
  return;
 }
 SrUiSettingsHeader header;
 DWORD got=0;
 int ok=ReadFile(file,&header,sizeof(header),&got,NULL)&&got==sizeof(header)&&
        header.magic==SR_UI_SETTINGS_MAGIC&&header.version==SR_UI_SETTINGS_VERSION;
 CloseHandle(file);
 if(ok)sr_ui_settings_apply(header.flags,"file");
}
#endif