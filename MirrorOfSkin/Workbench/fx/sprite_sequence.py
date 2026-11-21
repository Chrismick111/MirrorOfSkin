"""Experimental SpriteRenderer sequence decoder, not a full animator.

An optional constant Transform position is ignored: returned frames do not
describe composition, transforms, effects, or final appearance on screen.
"""
import math, struct

def decode_sprite_layers(tree):
    """Extract independent Sprite curves from streamed multi-layer clips.

    Other curves, layer visibility and transforms are not composed or rendered.
    Only streamed clips with a contiguous final block of Sprite bindings are
    accepted; dense and constant curves need separate binding-index mapping.
    """
    try:
        binding=tree['m_ClipBindingConstant']['genericBindings'];refs=tree['m_ClipBindingConstant']['pptrCurveMapping']
        muscle=tree['m_MuscleClip'];start=float(muscle['m_StartTime']);stop=float(muscle['m_StopTime'])
        clip=muscle['m_Clip']['data'];stream=clip['m_StreamedClip'];words=stream['data']
        continuous=stream['curveCount'];count=stream['discreteCurveCount']
        if not isinstance(continuous,int) or not isinstance(count,int) or continuous<0 or count<1 or count>64:raise ValueError('unsupported curve count')
        if len(binding)<count or any(x.get('isPPtrCurve') for x in binding[:-count]) or any(x.get('isPPtrCurve')!=1 or x.get('typeID')!=212 for x in binding[-count:]):raise ValueError('ambiguous bindings')
        if clip['m_DenseClip']['m_CurveCount'] or clip['m_ConstantClip']['data']:raise ValueError('unsupported additional curve storage')
        if not math.isfinite(start) or not math.isfinite(stop) or stop<=start:raise ValueError('invalid bounds')
        layers=[{'path':x.get('path'),'frames':[]} for x in binding[-count:]];i=0;ended=False
        while i<len(words):
            if i+2>len(words):raise ValueError('truncated frame')
            t=struct.unpack('<f',struct.pack('<I',words[i]))[0];n=words[i+1];i+=2
            if math.isinf(t) and t>0 and n==0:
                if i!=len(words):raise ValueError('trailing data')
                ended=True;break
            if not isinstance(n,int) or n<0 or i+n*5>len(words):raise ValueError('truncated keys')
            if t < -1e30:t=start
            if not math.isfinite(t) or t<start:raise ValueError('invalid frame time')
            for _ in range(n):
                idx=words[i];value=struct.unpack('<f',struct.pack('<I',words[i+4]))[0];i+=5
                if idx<continuous:continue
                layer=idx-continuous
                if layer>=count or t>=stop or not math.isfinite(value) or value!=int(value) or not 0<=int(value)<len(refs):raise ValueError('invalid sprite key')
                ref=refs[int(value)];frames=layers[layer]['frames'];item={'start':t,'file_id':ref['m_FileID'],'path_id':ref['m_PathID']}
                if frames and t<=frames[-1]['start']:
                    if item==frames[-1]:continue
                    raise ValueError('nonmonotonic sprite keys')
                frames.append(item)
        if not ended:raise ValueError('missing sequence boundary')
        for layer in layers:
            frames=layer['frames']
            if not frames or frames[0]['start']!=start:raise ValueError('missing layer initial sprite')
            for j,frame in enumerate(frames):frame['duration']=(frames[j+1]['start'] if j+1<len(frames) else stop)-frame['start']
        return layers
    except (KeyError,TypeError,IndexError,struct.error,OverflowError) as exc:
        raise ValueError('unsupported or invalid animation data') from exc

def decode_single_sprite_sequence(tree):
    try:
        bindings=tree['m_ClipBindingConstant']['genericBindings']
        refs=tree['m_ClipBindingConstant']['pptrCurveMapping']
        muscle=tree['m_MuscleClip'];start=float(muscle['m_StartTime']);stop=float(muscle['m_StopTime'])
        clip=muscle['m_Clip']['data'];stream=clip['m_StreamedClip'];words=stream['data']
        if not bindings or bindings[0].get('typeID')!=212 or bindings[0].get('isPPtrCurve')!=1:raise ValueError('unsupported bindings')
        constants=clip['m_ConstantClip']['data'];rest=bindings[1:]
        if rest and (len(rest)!=1 or rest[0].get('typeID')!=4 or rest[0].get('attribute')!=1 or rest[0].get('isPPtrCurve')!=0 or len(constants)!=3):raise ValueError('unsupported bindings')
        if stream.get('curveCount')!=0 or stream.get('discreteCurveCount')!=1 or clip['m_DenseClip']['m_CurveCount']!=0 or (not rest and constants):raise ValueError('unsupported curves')
        if not math.isfinite(start) or not math.isfinite(stop) or stop<=start:raise ValueError('invalid bounds')
        frames=[];i=0;ended=False
        while i<len(words):
            if i+2>len(words):raise ValueError('truncated frame')
            t=struct.unpack('<f',struct.pack('<I',words[i]))[0];n=words[i+1];i+=2
            if math.isinf(t) and t>0 and n==0:
                if i!=len(words):raise ValueError('trailing data')
                ended=True;break
            if n!=1 or i+5>len(words):raise ValueError('unsupported frame')
            curve=words[i];v=struct.unpack('<f',struct.pack('<I',words[i+4]))[0];i+=5
            if curve!=0 or not math.isfinite(v) or v!=int(v) or not 0<=int(v)<len(refs):raise ValueError('invalid sprite reference')
            if t < -1e30:t=start
            if not math.isfinite(t) or t<start or t>=stop or (frames and t<=frames[-1]['start']):raise ValueError('invalid frame time')
            ref=refs[int(v)];frames.append({'start':t,'file_id':ref['m_FileID'],'path_id':ref['m_PathID']})
        if not ended or not frames or frames[0]['start']!=start:raise ValueError('missing sequence boundary')
        for i,frame in enumerate(frames):frame['duration']=(frames[i+1]['start'] if i+1<len(frames) else stop)-frame['start']
        return frames
    except (KeyError,TypeError,IndexError,struct.error,OverflowError) as exc:
        raise ValueError('unsupported or invalid animation data') from exc
