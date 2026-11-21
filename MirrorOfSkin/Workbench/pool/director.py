import struct,time,zlib
import json,hashlib,os,math
MODES={'independent':0,'round':1,'sequence':2}
ACTIONS=('attack','clash','defense')
def validate(config,known):
 if config.get('schema')!=1 or not isinstance(config.get('characters',{}),dict) or not isinstance(config.get('forms',{}),dict):raise ValueError('演出规则格式不支持')
 for target,rules in config.get('characters',{}).items():
  if target not in {str(i) for i in range(101,113)}:raise ValueError('无效角色')
  for action,rule in rules.items():
   if action not in ACTIONS or rule.get('mode') not in MODES:raise ValueError('无效抽取模式')
   seq=rule.get('sequence',[])
   if seq:raise ValueError('顺序模式采用人格池成员顺序，请在池中上下移动成员；不支持独立sequence列表')
   
 for identity,rule in config.get('forms',{}).items():
  if not str(identity).isdigit() or int(identity)>2147483647 or identity not in known or rule.get('mode') not in ('native','defense','sanity','health','fixed'):raise ValueError('无效形态规则')
  threshold=rule.get('threshold',1);stage=rule.get('stage',1);compare=rule.get('compare',0)
  if type(threshold)!=int or type(stage)!=int or type(compare)!=int or not 0<=stage<=31 or compare not in (0,1):raise ValueError('形态阈值或阶段无效')
  limits={'native':(-45,65535),'defense':(1,65535),'sanity':(-45,45),'health':(0,100),'fixed':(-45,65535)}
  lo,hi=limits[rule['mode']]
  if not lo<=threshold<=hi:raise ValueError('形态阈值超出范围')
 if len(config.get('forms',{}))>256:raise ValueError('最多256项形态规则')
def binaries(config):
 rows=[]
 for target,rules in config.get('characters',{}).items():rows.append(struct.pack('<4I',int(target),*[MODES[rules.get(a,{}).get('mode','independent')] for a in ACTIONS]))
 modes={'native':0,'defense':1,'sanity':2,'health':3,'fixed':4}
 forms=[struct.pack('<IIiIIIII',int(identity),modes[r['mode']],r.get('threshold',1),r.get('stage',1),r.get('compare',0),0,0,0) for identity,r in config.get('forms',{}).items()]
 return {'workbench_rules.bin':struct.pack('<4I',0x31525753,1,len(rows),16)+b''.join(rows),'workbench_forms.bin':struct.pack('<4I',0x31464657,1,zlib.crc32(b''.join(forms))&0xffffffff,len(forms))+b''.join(forms)}
def snapshot(root):
 p=root/'演出编排.json';raw=p.read_bytes() if p.exists() else b''
 return {'revision':hashlib.sha256(raw).hexdigest(),'config':json.loads(raw.decode('utf-8-sig')) if raw else {'schema':1,'characters':{},'forms':{}}}
def save(root,config,revision,known):
 validate(config,known)
 blobs=binaries(config)
 blobs['演出编排.json']=json.dumps(config,ensure_ascii=False,allow_nan=False,indent=2).encode('utf8')
 if snapshot(root)['revision']!=revision:raise ValueError('演出规则已在其他窗口修改，请刷新后重试')
 originals={name:(root/name).read_bytes() if (root/name).exists() else None for name in blobs}
 if originals['演出编排.json'] is not None:(root/'演出编排.workbench.bak').write_bytes(originals['演出编排.json'])
 written=[]
 try:
  for name,blob in blobs.items():
   tmp=root/(name+'.tmp');tmp.write_bytes(blob);os.replace(tmp,root/name);written.append(name)
 except Exception:
  for name in reversed(written):
   if originals[name] is None:(root/name).unlink(missing_ok=True)
   else:
    tmp=root/(name+'.rollback');tmp.write_bytes(originals[name]);os.replace(tmp,root/name)
  raise
 return snapshot(root)
