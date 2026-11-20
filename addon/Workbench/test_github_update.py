import hashlib, io, json, pathlib, tempfile, unittest, zipfile, subprocess, sys, threading, time
import github_update as u
import package_release

def catalog(identity='10101',weight=1):return json.dumps({str(i):{'name':str(i),'entries':([{'identity_id':identity,'weight':weight}] if i==101 else [])} for i in range(101,113)}).encode()
def bundle(extra=None):
 files={'scr.py':b'DLL_NAME="SinnersNative-v64.dll"', 'SinnersNative-v64.dll':b'MZdata', 'addon_info.json':b'{"version":"0.64.0"}'}
 if extra:files.update(extra)
 manifest={'schema':1,'game_files':{'GameAssembly.dll':'a'*64},'version':'0.64.0','dll':'SinnersNative-v64.dll','package_files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}}
 files['compatibility.json']=json.dumps(manifest).encode()
 files[u.CATALOG]=catalog()
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w') as z:
  for name,data in files.items():z.writestr(name,data)
 return b.getvalue()

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent);self.root=pathlib.Path(self.tmp.name)/'addon';self.root.mkdir()
  (self.root/'addon_info.json').write_text('{"version":"0.63.0"}')
  (self.root/'Assets/runtime').mkdir(parents=True);(self.root/u.CATALOG).write_bytes(catalog(weight=7))
  (self.root/'随机设置.json').write_text('unchanged',encoding='utf8')
  self.original_fetch=u._fetch;self.original_running=u._running;u._running=lambda:False
 def tearDown(self):u._fetch=self.original_fetch;u._running=self.original_running;self.tmp.cleanup()
 def setbundle(self,b):
  data={'tag_name':'v0.64.0','assets':[{'name':u.ASSET,'state':'uploaded','digest':'sha256:'+hashlib.sha256(b).hexdigest(),'browser_download_url':'https://github.com/'+u.REPO+'/releases/download/v0.64.0/'+u.ASSET}]}
  u._fetch=lambda url,limit:json.dumps(data).encode() if url==u.API else b
 def test_success(self):
  self.setbundle(bundle());self.assertTrue(u.check(self.root)['available']);self.assertTrue(u.install(self.root)['installed']);self.assertEqual((self.root/'随机设置.json').read_text(encoding='utf8'),'unchanged');self.assertEqual((self.root/'scr.py').read_bytes(),b'DLL_NAME="SinnersNative-v64.dll"');self.assertEqual(json.loads((self.root/u.CATALOG).read_text(encoding='utf8'))['101']['entries'][0]['weight'],7)
 def test_protected_and_traversal(self):
  for key in ('随机设置.json','../outside'):
   self.setbundle(bundle({key:b'bad'}))
   with self.assertRaises(u.UpdateError):u.install(self.root)
 def test_running(self):
  u._running=lambda:True
  with self.assertRaises(u.UpdateError):u.install(self.root)
 def test_bad_digest(self):
  b=bundle();self.setbundle(b);fetch=u._fetch;u._fetch=lambda url,limit:fetch(url,limit) if url==u.API else b+b'x'
  with self.assertRaises(u.UpdateError):u.install(self.root)
 def test_catalog_merge(self):
  old=json.loads(catalog(weight=8));old['101']['entries'].append({'identity_id':'local','weight':3,'enabled':False});new=json.loads(catalog());new['101']['entries'][0]['name']='new';new['101']['entries'].append({'identity_id':'new','weight':2})
  x=json.loads(u.merge_catalog(json.dumps(old).encode(),json.dumps(new).encode()));self.assertEqual([(e['identity_id'],e['weight']) for e in x['101']['entries']],[('10101',8),('new',2),('local',3)])
  new['101']['entries'].append(new['101']['entries'][0])
  with self.assertRaises(u.UpdateError):u.merge_catalog(json.dumps(old).encode(),json.dumps(new).encode())
 def test_rollback(self):
  self.setbundle(bundle());(self.root/'scr.py').write_text('old');old=u.os.replace
  def fail(src,dst):
   if str(dst).endswith('addon_info.json'):raise OSError('failure')
   return old(src,dst)
  u.os.replace=fail
  try:
   with self.assertRaises(OSError):u.install(self.root)
   self.assertEqual((self.root/'scr.py').read_text(),'old')
  finally:u.os.replace=old
 def test_missing_release_message(self):
  def fail(url,limit):raise u.UpdateError('仓库尚未发布可安装版本')
  u._fetch=fail
  with self.assertRaisesRegex(u.UpdateError,'仓库尚未发布'):u.check(self.root)
 def test_cross_process_lock(self):
  self.setbundle(bundle())
  workbench_dir=pathlib.Path(__file__).resolve().parent
  worker="""import sys
sys.path.insert(0, sys.argv[1])
from file_lock import FileLock
with FileLock(sys.argv[2]):
    print('ready', flush=True)
    sys.stdin.readline()
"""
  child=subprocess.Popen(
      [sys.executable,'-u','-c',worker,str(workbench_dir),str(self.root/'github-update.lock')],
      cwd=workbench_dir,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
  try:
   self.assertEqual(child.stdout.readline().strip(),'ready');done=threading.Event();errors=[]
   def run():
    try:u.install(self.root)
    except Exception as e:errors.append(e)
    finally:done.set()
   t=threading.Thread(target=run);t.start();time.sleep(.2);self.assertFalse(done.is_set());child.stdin.write('\n');child.stdin.flush();t.join(10)
   self.assertTrue(done.is_set());self.assertFalse(errors)
  finally:
   if child.poll() is None:child.stdin.write('\n');child.stdin.flush()
   child.communicate(timeout=5)
 def test_package_release(self):
  b=bundle();z=zipfile.ZipFile(io.BytesIO(b));files={n:z.read(n) for n in z.namelist()}
  for name,data in files.items():
   p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
  original=(self.root/u.CATALOG).read_bytes();out=pathlib.Path(self.tmp.name)/u.ASSET
  package_release.package(self.root,out)
  self.assertEqual((self.root/u.CATALOG).read_bytes(),original)
  with zipfile.ZipFile(out) as z:self.assertNotIn('随机设置.json',z.namelist())
if __name__=='__main__':unittest.main()
