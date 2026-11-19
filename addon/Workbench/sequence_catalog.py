"""Find decodable candidate clips without assuming bundle-wide ownership."""
from sprite_sequence import decode_single_sprite_sequence,decode_sprite_layers

def collect_sequences(objects,wanted,bundle,thumbnail,progress=None,limit=200):
    sprites={(o.assets_file.name,o.path_id):o for o in objects if o.type.name=='Sprite'}
    groups=[];stats={'matched':0,'unavailable':0,'truncated':False}
    for i,obj in enumerate(objects):
        if progress and i%50==0:progress()
        if obj.type.name!='AnimationClip':continue
        try:
            name=obj.read().m_Name
        except Exception:continue
        if name not in wanted:continue
        stats['matched']+=1
        try:
            tree=obj.read_typetree()
            try:layers=[{'frames':decode_single_sprite_sequence(tree),'path':None}]
            except ValueError:layers=decode_sprite_layers(tree)
            new=[]
            for layer_number,layer in enumerate(layers,1):
                result=[]
                for frame in layer['frames']:
                    if frame['path_id']==0:
                        result.append({'name':'空白','blank':True,'start':frame['start'],'duration':frame['duration'],'thumbnail':None});continue
                    if frame['file_id']!=0:raise ValueError('external sprite')
                    sprite=sprites.get((obj.assets_file.name,frame['path_id']))
                    if sprite is None:raise ValueError('sprite unavailable')
                    image=thumbnail(sprite)
                    result.append({'name':sprite.read().m_Name,'sprite_key':'%s:%s'%(sprite.assets_file.name,sprite.path_id),
                                   'path_id':str(sprite.path_id),'cab':sprite.assets_file.name,'bundle':bundle,
                                   'start':frame['start'],'duration':frame['duration'],'thumbnail':image})
                new.append({'name':name,'bundle':bundle,'path_id':str(obj.path_id),'cab':obj.assets_file.name,
                            'layer':layer_number,'layer_count':len(layers),'layer_path':layer['path'],
                            'frames':result,'duration':sum(x['duration'] for x in result)})
            room=max(0,limit-len(groups))
            groups.extend(new[:room])
            if len(new)>room:stats['truncated']=True
        except Exception:
            stats['unavailable']+=1
        if len(groups)>=limit:
            stats['truncated']=True;break
    return groups,stats
