"""User portraits stored separately from distributed portraits and manifests."""
import base64, binascii, hashlib, os, pathlib, struct, zlib
MAX_BYTES=1024*1024
def folder_for(root):
 base=pathlib.Path(root).resolve();folder=base/'Workbench'/'user_portraits'
 if not folder.resolve().is_relative_to(base):raise ValueError('头像目录无效')
 return folder

def filename(identity):
 if not isinstance(identity,str) or not identity or len(identity)>128:raise ValueError('无效人格')
 return hashlib.sha256(identity.encode('utf8')).hexdigest()+'.png'

def path_for(root, identity):
 return folder_for(root)/filename(identity)
def validate_png(blob, *, max_bytes=MAX_BYTES, max_dimension=384):
 if len(blob)>max_bytes or not blob.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError(f'图片格式无效或超过 {max_bytes // (1024*1024)} MiB')
 pos=8;first=True;idat=False;ended=False;encoded=[];raw_size=0
 while pos<len(blob):
  if pos+12>len(blob):raise ValueError('PNG 数据不完整')
  size=struct.unpack_from('>I',blob,pos)[0];end=pos+12+size
  if end>len(blob):raise ValueError('PNG 数据不完整')
  kind=blob[pos+4:pos+8];data=blob[pos+8:pos+8+size]
  if zlib.crc32(kind+data)&0xffffffff!=struct.unpack_from('>I',blob,pos+8+size)[0]:raise ValueError('PNG 校验失败')
  if first:
   if kind!=b'IHDR' or size!=13:raise ValueError('PNG 头无效')
   width,height=struct.unpack_from('>II',data)
   if not 0<width<=max_dimension or not 0<height<=max_dimension:raise ValueError('图片尺寸无效')
   depth,colour,compression,filter_type,interlace=struct.unpack_from('5B',data,8)
   if depth!=8 or colour not in (2,6) or compression or filter_type or interlace:raise ValueError('PNG 格式不受支持')
   raw_size=(1+width*(4 if colour==6 else 3))*height
   first=False
  if kind==b'IDAT':idat=True;encoded.append(data)
  if kind==b'IEND':
   if size or end!=len(blob):raise ValueError('PNG 结尾无效')
   ended=True;break
  pos=end
 if not idat or not ended:raise ValueError('PNG 内容不完整')
 try:
  decoder=zlib.decompressobj();pixels=decoder.decompress(b''.join(encoded),raw_size+1)
  if len(pixels)!=raw_size or not decoder.eof or decoder.unused_data:raise ValueError('PNG 内容无效')
 except zlib.error as exc:raise ValueError('PNG 内容无效') from exc
def save(root,identity,encoded):
 try:blob=base64.b64decode(encoded,validate=True)
 except (binascii.Error,ValueError,TypeError) as exc:raise ValueError('图片编码无效') from exc
 validate_png(blob);dst=path_for(root,identity);dst.parent.mkdir(parents=True,exist_ok=True)
 temp=dst.with_name(dst.name+'.tmp');temp.write_bytes(blob);os.replace(temp,dst)
def get(root,identity):
 p=path_for(root,identity)
 if not p.is_file():return None
 blob=p.read_bytes();validate_png(blob);return blob
def reset(root,identity):path_for(root,identity).unlink(missing_ok=True)
