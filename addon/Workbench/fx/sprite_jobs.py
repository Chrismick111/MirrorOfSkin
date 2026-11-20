"""Single cooperative background sprite scan; status never exposes mutable internals."""
import threading
import sprite_gallery

_lock=threading.Lock()
_job={'status':'idle'}
_cancel=None
class Cancelled(Exception): pass

def state():
 with _lock:return dict(_job)

def start(appearance,roots):
 global _cancel
 if not isinstance(appearance,str) or not appearance:raise ValueError('请选择外观')
 with _lock:
  if _job.get('status')=='running':
   if _job.get('appearance')==appearance:return dict(_job)
   raise ValueError('已有素材读取任务，请先等待或取消')
  _cancel=threading.Event();event=_cancel
  _job.clear();_job.update(status='running',appearance=appearance,stage='准备读取',done=0,total=0)
 def progress(stage,done,total):
  if event.is_set():raise Cancelled()
  with _lock:_job.update(stage='建立资源索引' if stage=='index' else '读取素材与缩略图',done=done,total=total)
 def run():
  try:
   result=sprite_gallery.inventory(appearance,roots,progress=progress)
   if event.is_set():raise Cancelled()
   with _lock:_job.update(status='done',result=result,stage='读取完成')
  except Cancelled:
   with _lock:_job.update(status='cancelled',stage='已取消')
  except Exception as exc:
   with _lock:_job.update(status='error',message=str(exc),stage='读取失败')
 threading.Thread(target=run,daemon=True).start()
 return state()

def cancel():
 with _lock:
  if _job.get('status')=='running' and _cancel:_cancel.set();_job['stage']='正在取消，等待当前资源包读取结束'
  return dict(_job)
