"""Optional declarative animation policy supplied by an appearance package."""
import json
import re

MANIFEST = 'mos-skin.json'
_RULES = {'attack_groups', 'dependency', 'native_layout', 'clash', 'defense', 'animator',
          'plugin_version', 'voice'}
_CLASH_ROLES = {'ready': 1, 'win': 2, 'lose': 3, 'neutral': 4, 'special': 5, 'linked': 6}
_DEFENSE_SLOTS = {'evade': 2, 'guard': 3, 'damaged': 4}

def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('外观配置含重复字段：'+key)
        result[key] = value
    return result

def read_manifest(z):
    matches = [i for i in z.infolist() if not i.is_dir() and i.filename.replace('\\','/').casefold() == MANIFEST]
    if len(matches)>1: raise ValueError('外观包包含重复的 mos-skin.json')
    if not matches: return {}
    if matches[0].file_size>65536: raise ValueError('外观配置文件过大')
    data=json.loads(z.read(matches[0]).decode('utf-8-sig'),object_pairs_hook=_unique_pairs)
    if not isinstance(data,dict) or set(data)!={'schema','appearances'} or type(data['schema']) is not int or data['schema'] != 1 or not isinstance(data['appearances'],dict):
        raise ValueError('外观配置格式不受支持')
    result={}
    for address, policy in data['appearances'].items():
        if not isinstance(address,str) or not address.lower().startswith('assets/') or not address.lower().endswith('.prefab') or '\\' in address or any(p in ('','.','..') for p in address.split('/')):
            raise ValueError('外观配置的预制体地址无效')
        key=address.casefold()
        if key in result: raise ValueError('外观配置的预制体地址重复')
        if not isinstance(policy,dict): raise ValueError('外观配置格式无效')
        result[key]=policy
    return result

def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,8})(?:\.(?:0|[1-9][0-9]{0,8})){2}', value):
        raise ValueError('外观配置需要三段数字的插件版本')
    return tuple(map(int, value.split('.')))


def _validate_version(bounds, plugin_version):
    if not isinstance(bounds, dict) or not bounds or bounds.keys() - {'min', 'max'}:
        raise ValueError('外观配置的插件版本范围无效')
    limits = {key: _version(value) for key, value in bounds.items()}
    if 'min' in limits and 'max' in limits and limits['min'] > limits['max']:
        raise ValueError('外观配置的插件版本范围无效')
    if plugin_version is None:
        raise ValueError('无法读取当前插件版本')
    current = _version(plugin_version)
    if current < limits.get('min', current) or current > limits.get('max', current):
        raise ValueError(f'插件版本 {plugin_version} 超出此外观包支持的范围')


def encode_policy(policy, verified, *, plugin_version=None):
    if not isinstance(policy,dict) or set(policy)-_RULES: raise ValueError('外观动作配置无效')
    if 'dependency' in policy and (not isinstance(policy['dependency'],str) or not re.fullmatch(r'(?:SD_Personality|SD_Enemy)/[A-Za-z0-9_./-]+\.prefab',policy['dependency']) or any(p in ('','.','..') for p in policy['dependency'].split('/'))):
        raise ValueError('外观依赖地址无效')
    if 'native_layout' in policy and (not isinstance(policy['native_layout'],str) or not re.fullmatch(r'[A-Za-z0-9_]{1,255}',policy['native_layout'])):
        raise ValueError('外观本体动作布局无效')
    if 'plugin_version' in policy:
        _validate_version(policy['plugin_version'], plugin_version)
    if 'voice' in policy:
        from voice_binding import validate_voice_policy
        validate_voice_policy(policy['voice'])
    if 'attack_groups' not in policy:
        return None
    config=policy['attack_groups']
    if not isinstance(config,dict) or set(config)!={'mode','groups','preserve_native_layout'} or config['mode']!='random_per_coin':
        raise ValueError('外观动作选组方式无效')
    groups=config['groups']; preserve=config['preserve_native_layout']
    if type(preserve) is not bool or not isinstance(groups,list) or not groups or len(groups)>21:
        raise ValueError('外观动作选组参数无效')
    if any(type(g) is not int or not (7<=g<=16 or 24<=g<=34) for g in groups) or len(set(groups))!=len(groups):
        raise ValueError('外观动作组编号无效')
    if not set(groups).issubset(set(verified)):
        raise ValueError('外观配置引用了缺少完整攻击动作的动作组')
    return 'R|'+str(int(preserve))+'|'+','.join(map(str,groups))


def apply_action_policy(policy, actions, verified_attacks):
    """Overlay declarative roles using only evidence from the selected prefab."""
    declared = {}
    clash = policy.get('clash', {})
    if not isinstance(clash, dict) or clash.keys() - _CLASH_ROLES.keys():
        raise ValueError('外观拼点动作配置无效')
    for name, value in clash.items():
        slots = value if isinstance(value, list) else [value]
        if not slots or any(type(slot) is not int or not 1 <= slot < 128 for slot in slots):
            raise ValueError('外观拼点动作槽位无效')
        for slot in slots:
            if slot in declared:
                raise ValueError('外观配置重复声明动作槽位')
            declared[slot] = _CLASH_ROLES[name]

    defense = policy.get('defense', {})
    if (not isinstance(defense, dict) or defense.keys() - _DEFENSE_SLOTS.keys()
            or any(type(slot) is not int or slot != _DEFENSE_SLOTS[name] for name, slot in defense.items())):
        raise ValueError('外观守备动作槽位无效')
    for slot in defense.values():
        if slot in declared:
            raise ValueError('外观配置重复声明动作槽位')
        declared[slot] = 7

    animator = policy.get('animator', [])
    if (not isinstance(animator, list) or any(type(slot) is not int for slot in animator)
            or len(set(animator)) != len(animator) or not set(animator).issubset(actions['runtime_animator'])):
        raise ValueError('外观配置指定的槽位缺少可播放的 Animator 状态')

    roles = actions['runtime_roles'].copy()
    evidence = actions.get('declarable_timeline_roles', {})
    resolved = {**actions, 'runtime_roles': roles}
    new_slots = set()
    for slot, role in declared.items():
        key = str(slot)
        if slot in verified_attacks or roles.get(key, evidence.get(key)) != role:
            raise ValueError(f'外观动作槽位 {slot} 缺少与声明一致的动作证据')
        if key not in roles:
            category = 'defense' if role == 7 else 'clash'
            resolved[category] = [*resolved.get(category, []),
                                  dict(detail=slot, role=role, evidence='timeline')]
            new_slots.add(slot)
            roles[key] = role
    if new_slots:
        resolved['unclassified'] = [item for item in actions.get('unclassified', [])
                                    if item['detail'] not in new_slots]
    return resolved
