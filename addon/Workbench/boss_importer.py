import copy,json,math,re,struct,pathlib
MAGIC=b'SST1'
def _finite(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
def build_entry(candidate,metadata,asset_key,target='101',display_name=None):
 """Build from verified appearance + real MotionMetadataList, never guessed timing."""
 appearance=candidate.get('appearance_name',candidate.get('appearance'))
 if not isinstance(appearance,str) or not re.fullmatch(r'[A-Za-z0-9_]+',appearance):raise ValueError('Unsupported appearance identifier')
 if not isinstance(asset_key,str) or not asset_key.endswith('.prefab') or len(asset_key.encode('ascii'))>=128:raise ValueError('Verified Addressables prefab key required')
 if str(target) not in {str(i) for i in range(101,113)}:raise ValueError('Invalid target sinner')
 if metadata.get('AppearanceName')!=appearance:raise ValueError('Metadata appearance mismatch')
 actual={};contracts=[];names={}
 for motion in candidate.get('motions',[]):
  detail=motion['detail']
  if detail in actual:raise ValueError('Duplicate appearance motion')
  actual[detail]=motion.get('timelines',[])
 seen=set()
 for motion in metadata.get('motionList',[]):
  detail=motion['motionDetail'];items=motion.get('motionTimelineDatas',[])
  if type(detail)!=int or not 0<=detail<128 or detail in seen:raise ValueError('Invalid metadata motion')
  seen.add(detail);timelines=actual.get(detail,[])
  if not items or len(items)!=len(timelines):raise ValueError('Timeline count mismatch')
  names[str(detail)]=[]
  for i,(item,timeline) in enumerate(zip(items,timelines)):
   name=timeline.get('name')
   if timeline.get('null') or not name or not name.isascii() or len(name.encode('ascii'))>=128:raise ValueError('Unresolved timeline contract')
   if item.get('motionIndex')!=i:raise ValueError('Metadata index mismatch')
   if not _finite(item.get('duration')) or not 0<item['duration']<=600:raise ValueError('Real duration required')
   if not _finite(item.get('endMarkerTime')) or item['endMarkerTime']< -1:raise ValueError('Real end marker required')
   for field in ('hitMarkerTime','giveDamageDelay'):
    if not _finite(item.get(field)):raise ValueError('Real timing metadata required: '+field)
   contracts.append(struct.pack('<iii128s',detail,i,len(items),name.encode('ascii')));names[str(detail)].append(name)
 if not any(d in seen for d in range(7,17)) and not any(d in seen for d in range(24,35)):raise ValueError('No verified attack motions')
 if not 0<len(contracts)<=512:raise ValueError('Contract limit exceeded')
 identity='story_'+appearance
 if len(identity.encode('ascii'))>=64 or len(appearance.encode('ascii'))>=64:raise ValueError('Native identifier field limit exceeded')
 raw=json.dumps(metadata,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode('ascii')
 if len(raw)>1048576:raise ValueError('Metadata too large')
 entry={'sinner':str(target),'identity_id':identity,'appearance_name':appearance,'asset_key':asset_key,'name':display_name or appearance,'weight':0,'story_metadata':copy.deepcopy(metadata),'story_timeline_names':names,'excluded_actions':[]}
 # Keep selection off by default; users choose bosses explicitly in custom pools.
 return entry,struct.pack('<4sIII',MAGIC,1,len(contracts),len(raw))+b''.join(contracts)+raw

def export_candidate(candidate,metadata,asset_key,out,**kwargs):
 entry,blob=build_entry(candidate,metadata,asset_key,**kwargs);out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
 (out/(entry['identity_id']+'.bin')).write_bytes(blob)
 (out/(entry['identity_id']+'.json')).write_text(json.dumps(entry,ensure_ascii=False,indent=2),encoding='utf8');return entry
