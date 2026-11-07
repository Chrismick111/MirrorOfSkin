/* Read the actual native coin log when a known Boolean accessor exists.
   Unknown metadata stays unknown; color is never inferred from damage. */
static const char *diagnostic_coin_type(Unit *u){
 if(!u||!u->observedViewer)return "unknown";
 void *get=find_method(ui_class(u->observedViewer),"CurrentCoinLog",0);int ok=0;
 void *log=get?call_obj(get,u->observedViewer,NULL,&ok):NULL;if(!ok||!log)return "unknown";
 const char *names[]={"get_IsUnbreakable","IsUnbreakable","get_IsUnbreakCoin","IsUnbreakCoin"};
 for(int i=0;i<4;i++){
  void *m=find_method(ui_class(log),names[i],0);if(!m)continue;
  void *type=((void *(*)(void *))api[API_RETURN_TYPE])(m);
  char *name=type?((char *(*)(void *))api[API_TYPE_NAME])(type):NULL;
  int isBool=name&&!strcmp(name,"System.Boolean");if(name)((void (*)(void *))api[API_FREE])(name);
  if(isBool){int value=call_bool(m,log,NULL);return value<0?"unknown":value?"unbreakable":"normal";}
 }
 return "unknown";
}
