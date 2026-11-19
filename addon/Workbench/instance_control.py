"""One workbench server per addon directory, with OS-released ownership."""
import json, os, pathlib, re, time, urllib.request

class Instance:
 def __init__(self, root):
  self.root=pathlib.Path(root);self.root.mkdir(parents=True,exist_ok=True)
  self.lock=open(self.root/'workbench-instance.lock','a+b');self.owner=False
  self.state=self.root/'workbench-instance.json'
 def acquire(self):
  try:
   self.lock.seek(0)
   if os.name=='nt':
    import msvcrt;msvcrt.locking(self.lock.fileno(),msvcrt.LK_NBLCK,1)
   else:
    import fcntl;fcntl.flock(self.lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
   self.owner=True
  except OSError:self.owner=False
  return self.owner
 def publish(self,url):
  temp=self.state.with_suffix('.json.tmp');temp.write_text(json.dumps({'url':url,'pid':os.getpid()}),encoding='utf8');os.replace(temp,self.state)
 def existing(self):
  for _ in range(100):
   try:
    url=json.loads(self.state.read_text(encoding='utf8'))['url']
    if not re.fullmatch(r'http://127\.0\.0\.1:\d{1,5}/[A-Za-z0-9_-]+/',url):raise ValueError('invalid URL')
    with urllib.request.urlopen(url+'api/instance-ping',timeout=.3) as response:
     if json.load(response).get('workbench') is True:return url
   except Exception:time.sleep(.05)
  raise RuntimeError('现有工作台暂不可连接，请稍后重试')
 def attach(self,url,pid):
  token=url.rstrip('/').rsplit('/',1)[-1]
  data=json.dumps({'host_pid':pid}).encode('utf8')
  request=urllib.request.Request(url+'api/instance-attach',data,{'Content-Type':'application/json','X-Workbench':token})
  with urllib.request.urlopen(request,timeout=3) as response:
   if not json.load(response).get('attached'):raise RuntimeError('无法连接现有工作台')
 def close(self):
  if self.owner:
   try:self.state.unlink(missing_ok=True)
   except OSError:pass
  self.lock.close()
