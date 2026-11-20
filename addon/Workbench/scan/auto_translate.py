"""Best-effort English-to-Chinese labels for newly discovered appearance names.

Local translations always take priority. Network results are provisional and
cached, never overwrite user-supplied or locally translated names.
"""
import json, pathlib, re, time, urllib.parse, urllib.request

ENDPOINT='https://translate.googleapis.com/translate_a/single'

def label_text(name):
    text=re.sub(r'^(?:story_)?\d+[A-Za-z]?_', '',str(name or ''))
    text=re.sub(r'Appearance$', '',text,flags=re.I)
    text=re.sub(r'(?<=[a-z])(?=[A-Z])',' ',text).replace('_',' ')
    text=re.sub(r'\s+',' ',text).strip()
    return text[:200]

def _read(path):
    try:
        v=json.loads(path.read_text(encoding='utf-8-sig'))
        return v if isinstance(v,dict) else {}
    except (OSError,ValueError): return {}

def translate(text,timeout=3):
    q=urllib.parse.urlencode({'client':'gtx','sl':'en','tl':'zh-CN','dt':'t','q':text})
    req=urllib.request.Request(ENDPOINT+'?'+q,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        raw=response.read(128*1024)
    data=json.loads(raw.decode('utf8'))
    if not isinstance(data,list) or not data or not isinstance(data[0],list):raise ValueError('invalid translation response')
    result=''.join(str(item[0]) for item in data[0] if isinstance(item,list) and item and isinstance(item[0],str)).strip()
    if not result or not re.search(r'[\u3400-\u9fff]',result):raise ValueError('no Chinese translation returned')
    return result[:300]

def fill(pools,cache_path,max_items=60,budget_seconds=20,timeout=3,fetch=translate,clock=time.monotonic):
    """Return stats; callers persist pools under their normal lock.

    Failed items are not cached, and can retry on a future weekly run.
    """
    cache_path=pathlib.Path(cache_path);cache=_read(cache_path);start=clock();attempted=changed=failed=0;updated=False
    for pool in pools.values():
        for entry in pool.get('entries',[]):
            if entry.get('discovery_source')!='local_cache':continue
            current=str(entry.get('name') or '')
            if re.search(r'[\u3400-\u9fff]',current):continue
            text=label_text(entry.get('appearance_name') or current)
            if not text:continue
            value=cache.get(text)
            if not isinstance(value,str) or not re.search(r'[\u3400-\u9fff]',value):
                if attempted>=max_items or clock()-start>=budget_seconds:continue
                attempted+=1
                try:value=fetch(text,timeout=timeout)
                except Exception:failed+=1;continue
                if not isinstance(value,str) or not re.search(r'[\u3400-\u9fff]',value):failed+=1;continue
                cache[text]=value;updated=True
            entry['name']=value;entry['translation_status']='自动暂译';entry['translation_source_text']=text;changed+=1
    if updated:
        cache_path.parent.mkdir(parents=True,exist_ok=True)
        tmp=cache_path.with_name(cache_path.name+'.tmp')
        tmp.write_text(json.dumps(cache,ensure_ascii=False,indent=2)+'\n',encoding='utf8');tmp.replace(cache_path)
    return {'attempted':attempted,'translated':changed,'failed':failed}
