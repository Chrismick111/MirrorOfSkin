static int warm_forms(Unit *u,int row){
 if(unit_bad(u,row))return 0;
 int i=sr_form_index(g_rows[row].identity);
 if(i>=0)return (u->unavailableForms&(1u<<i))?1:2;
 AutoRuntime *a=auto_for_row(row);
 if(a&&a->value.kind==1&&!auto_form_failed(u,row))return a->value.count;
 return 1;
}
static int warm_cache_required(Unit *u,int row,int form){
 for(int i=0;i<u->ncand;i++)if(u->cand[i]==row)return form<warm_forms(u,row);
 return 0;
}
static void warm_enqueue(Unit *u){
 if(!g_cfg||g_cfg->mode!=1||!u||u->dead||u->preserveSpecial||!u->ncand)return;
 /* Fair, bounded enqueue work. All variants share the same async loader. */
 int span=u->ncand*4;
 for(int n=0;n<4;n++){
  int token=u->warmCursor++%span;int row=u->cand[token/4],form=token%4;
  if(form<warm_forms(u,row))queue_push_form(u,row,form);
 }
}
static void warm_totals(int *ready,int *total,int *units,int *failed){
 *ready=*total=*units=*failed=0;
 for(int i=0;i<SR_UNIT_MAX;i++){
  Unit *u=&g_units[i];if(!u->used||u->dead||u->preserveSpecial||!u->ncand)continue;
  (*units)++;*failed+=u->nbad+u->nautoFailed;
  for(unsigned bits=u->unavailableForms;bits;bits>>=1)*failed+=(bits&1);
  for(int j=0;j<u->ncand;j++){
   int row=u->cand[j],n=warm_forms(u,row);
   for(int form=0;form<n;form++){(*total)++;if(skin_index_form(u,row,form)>=0)(*ready)++;}
  }
 }
}
static void warm_publish(void){
 if(!g_cfg||g_cfg->mode!=1)return;
 int ready,total,units,failed;warm_totals(&ready,&total,&units,&failed);
 int roster=0;for(int i=0;i<SR_UNIT_MAX;i++)if(g_units[i].used&&!g_units[i].dead)roster++;
 static int previous[5]={-1,-1,-1,-1,-1};int current[]={ready,total,units,failed,roster};
 if(!memcmp(previous,current,sizeof(current)))return;
 wchar_t temp[32768],dest[32768];auto_path(temp,L"warmup_status.json.tmp");auto_path(dest,L"warmup_status.json");
 char text[384];int n=snprintf(text,sizeof(text),"{\"protocol\":%u,\"pid\":%lu,\"ready\":%d,\"total\":%d,\"units\":%d,\"roster\":%d,\"failed\":%d,\"complete\":%s}",SR_PROTOCOL_VERSION,(unsigned long)GetCurrentProcessId(),ready,total,units,roster,failed,units&&total&&ready==total?"true":"false");
 HANDLE f=CreateFileW(temp,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,0,NULL);
 if(f!=INVALID_HANDLE_VALUE){DWORD written;int ok=WriteFile(f,text,n,&written,NULL)&&written==(DWORD)n;CloseHandle(f);
  if(ok&&MoveFileExW(temp,dest,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))memcpy(previous,current,sizeof(current));}
 if(total&&ready<total)say("Preparing full pool: %d/%d appearances; wait before starting actions",ready,total);
}
