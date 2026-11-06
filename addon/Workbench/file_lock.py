import contextlib,os,threading,time
class FileLock:
 """Reentrant thread lock plus one-byte OS lock shared by workbench processes."""
 def __init__(self,path):self.path=path;self.thread=threading.RLock();self.local=threading.local()
 def __enter__(self):
  self.thread.acquire();depth=getattr(self.local,'depth',0)
  if depth:self.local.depth=depth+1;return self
  stream=None
  try:
   stream=open(self.path,'a+b')
   # Windows byte-range locks can extend beyond EOF. Writing a seed byte
   # before acquiring the lock races another process already holding it.
   deadline=time.monotonic()+15
   while True:
    try:
     stream.seek(0)
     if os.name=='nt':
      import msvcrt
      msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
     else:
      import fcntl
      fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
     break
    except (OSError,BlockingIOError):
     if time.monotonic()>=deadline:raise TimeoutError('其他工作台正在保存，请稍后重试')
     time.sleep(.025)
   self.local.stream=stream;self.local.depth=1;return self
  except BaseException:
   if stream:stream.close()
   self.thread.release();raise
 def __exit__(self,*args):
  try:
   self.local.depth-=1
   if not self.local.depth:
    stream=self.local.stream
    try:
     stream.seek(0)
     if os.name=='nt':
      import msvcrt
      msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
     else:
      import fcntl
      fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
    finally:stream.close();self.local.stream=None
  finally:self.thread.release()
