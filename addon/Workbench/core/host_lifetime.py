"""Track launcher processes by kernel handles; standalone sessions remain manual."""
import ctypes, os, threading, time

class Lifetime:
 def __init__(self):
  self.lock=threading.Lock();self.hosts={};self.standalone=False;self.closing=False
  if os.name=='nt':
   self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
   self.kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];self.kernel.OpenProcess.restype=ctypes.c_void_p
   self.kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong];self.kernel.WaitForSingleObject.restype=ctypes.c_ulong
   self.kernel.CloseHandle.argtypes=[ctypes.c_void_p]
 def register(self,pid):
  with self.lock:
   if self.closing:raise ValueError('工作台正在退出，请重新打开')
   if pid is None:self.standalone=True;return
   if not isinstance(pid,int) or pid<=0 or os.name!='nt':raise ValueError('无法验证启动器进程')
   if pid in self.hosts:return
   handle=self.kernel.OpenProcess(0x100000,False,pid)
   if not handle:raise ValueError('启动器进程已退出或无法验证')
   if self.kernel.WaitForSingleObject(handle,0)!=258:
    self.kernel.CloseHandle(handle);raise ValueError('启动器进程已退出')
   self.hosts[pid]=handle
 def release(self,pid):
  with self.lock:
   handle=self.hosts.pop(pid,None)
   if handle:self.kernel.CloseHandle(handle)
 def begin_shutdown(self):
  with self.lock:self.closing=True
 def watch(self,server):
  def run():
   while True:
    time.sleep(1)
    with self.lock:
     for pid,handle in list(self.hosts.items()):
      if self.kernel.WaitForSingleObject(handle,0)==0:self.kernel.CloseHandle(handle);del self.hosts[pid]
     stop=not self.standalone and not self.hosts
     if stop:self.closing=True
    if stop:server.shutdown();return
  threading.Thread(target=run,daemon=True).start()
 def close(self):
  with self.lock:
   for handle in self.hosts.values():self.kernel.CloseHandle(handle)
   self.hosts.clear()
