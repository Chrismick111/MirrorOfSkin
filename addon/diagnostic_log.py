import pathlib,time,threading
LIMIT=8*1024*1024
class DiagnosticLog:
 def __init__(self,root):
  self.root=pathlib.Path(root);self.offsets={};self.target=self.root/'诊断日志.txt'
  with self.target.open('a',encoding='utf-8') as f:
   f.write('\n=== 诊断会话 '+time.strftime('%Y-%m-%d %H:%M:%S')+' ===\n')
   for name in ('addon_info.json','compatibility.json','warmup_status.json'):
    try:
     import json
     obj=json.loads((self.root/name).read_text(encoding='utf-8-sig'))
     if name=='compatibility.json':obj={k:obj.get(k) for k in ('version','dll','protocol')}
     f.write(name+': '+json.dumps(obj,ensure_ascii=False)+'\n')
    except (OSError,ValueError):pass
 def poll(self):
  chunks=[]
  for name in ('native.log','native_runtime.log'):
   p=self.root/name
   if not p.exists():continue
   size=p.stat().st_size;old=self.offsets.get(name,max(0,size-131072))
   if size<old:old=0
   with p.open('rb') as f:f.seek(old);data=f.read(262144);self.offsets[name]=f.tell()
   if data:chunks.append('\n['+time.strftime('%Y-%m-%d %H:%M:%S')+' '+name+']\n'+data.decode('utf-8',errors='replace'))
  if not chunks:return
  if self.target.exists() and self.target.stat().st_size>LIMIT:self.target.replace(self.root/'诊断日志-上一份.txt')
  with self.target.open('a',encoding='utf-8') as f:f.write(''.join(chunks))
 def run(self,stop):
  while not stop.is_set():
   try:self.poll()
   except OSError:pass
   stop.wait(3)
def start(root,stop):
 logger=DiagnosticLog(root);logger.poll()
 threading.Thread(target=logger.run,args=(stop,),name='SinnersDiagnosticLog',daemon=True).start()
 return logger
