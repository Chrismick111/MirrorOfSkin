#include <assert.h>
#include "sinners_native.c"

int main(void){
    wchar_t name[100];
    swprintf(name,100,L"Local\\MOS-config-test-%lu",GetCurrentProcessId());
    HANDLE owner=CreateFileMappingW(INVALID_HANDLE_VALUE,NULL,PAGE_READWRITE,0,sizeof(Config),name);
    assert(owner && GetLastError()!=ERROR_ALREADY_EXISTS);
    Config *first=MapViewOfFile(owner,FILE_MAP_ALL_ACCESS,0,0,sizeof(Config));
    assert(first);
    first->magic=0x3152534e;first->version=SR_PROTOCOL_VERSION;first->bytes=sizeof(Config);
    first->reserved[0]=5;
    Config *reader=open_config_section(name);
    assert(reader && reader->reserved[0]==5);
    UnmapViewOfFile(first);CloseHandle(owner);
    for(unsigned i=6;i<=7;i++){
        HANDLE next=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,name);
        assert(next);
        Config *writer=MapViewOfFile(next,FILE_MAP_ALL_ACCESS,0,0,sizeof(Config));
        assert(writer && writer->reserved[0]==i-1);
        writer->reserved[0]=i;
        assert(reader->reserved[0]==i);
        UnmapViewOfFile(writer);CloseHandle(next);
    }
    close_config_section();
    assert(!OpenFileMappingW(FILE_MAP_READ,FALSE,name));
    puts("PASS config section survives consecutive host reloads and receives revisions 6 and 7");
    return 0;
}
