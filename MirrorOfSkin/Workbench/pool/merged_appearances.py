"""Explicit multi-phase families for the workbench. No implicit pool migration."""
import copy,hashlib


FAMILIES = [
 ('cromer','克罗默',['story_8029_CromerAppearance','story_8030_Cromer_2pAppearance']),
 ('littlebuffe','小巴菲',['story_400041_LittleBuffeAppearance','story_400041_LittleBuffe_2pAppearance','story_400041_LittleBuffe_3pAppearance']),
 ('warder','看守者',['story_1485_WarderAppearance','story_1486_Warder_2pAppearance','story_1487_Warder_3pAppearance']),
 ('vergilius-400012','维吉里乌斯（剧情）',['story_400012_VergiliusAppearance','story_400012_Vergilius_EgoAppearance']),
 ('vergilius-9999','维吉里乌斯',['story_9999_VergiliusAppearance','story_9999_Vergilius_EgoAppearance']),
 ('index-father','食指父辈·里恩',['story_1347_Index_fatherAppearance','story_1348_Index_father_Phase2Appearance']),
 ('index-disciple-kong','食指子辈·空',['story_1325_Index_Disciple_NormalAppearance','story_1325_Index_discipleAppearance']),
 ('ring-disciple-albina','环指子辈·阿尔比娜',['story_1319_RingFinger_DiscipleAppearance','story_1336_RingFinger_Disciple_CastoffAppearance']),
 ('middle-father','中指父辈',['story_1327_MiddleFinger_fatherAppearance','story_1327_MiddleFinger_father_Phase4Appearance']),
 ('donglang','东朗',['story_8049_DongLang_1pAppearance','story_8049_DongLang_2pAppearance','story_8049_DongLang_3pAppearance']),
 ('realdon','堂吉诃德',['story_8390_RealDon_1pAppearance','story_8410_RealDon_2pAppearance']),
]
NATIVE_FAMILIES = {'index-disciple-kong', 'ring-disciple-albina'}


def family_info(key, name, members):
    group_id = 'merged_' + hashlib.sha256(key.encode()).hexdigest()[:16]
    return dict(id=key, name=name, members=members[:], group_id=group_id,
                group_ids=[group_id + suffix for suffix in ('_s', '_d', '_n')],
                native_supported=key in NATIVE_FAMILIES)


def families(catalog):
    known = {str(entry.get('identity_id', '')) for entry in catalog}
    return [family_info(key, name, members) for key, name, members in FAMILIES
            if all(identity in known for identity in members)]


def make_group(family, mode):
    if mode == 'native' and family['id'] not in NATIVE_FAMILIES:
        raise ValueError('该外观尚未接入对应的本体形态')
    modes = {'sanity45': ('sanity', '_s'), 'defense1': ('defense', '_d'), 'native': ('native', '_n')}
    if mode not in modes:
        raise ValueError('未知形态切换条件')
    metric, suffix = modes[mode]
    members = family['members']
    stages = []
    for index, identity in enumerate(members):
        conditions = []
        if index:
            if metric == 'sanity':
                value = 23 if len(members) == 3 and index == 1 else 45
            else:
                value = index if metric == 'defense' else 1
            conditions.append(dict(metric=metric, op='gte', value=value))
        stages.append(dict(identity_id=identity, form=0, priority=index, match='all', conditions=conditions))
    return dict(id=family['group_id'] + suffix, name=family['name'], enabled=True,
                hold=mode == 'defense1', stages=stages)


def upgrade_legacy_groups(config):
    if not isinstance(config, dict) or config.get('schema') != 1 or not isinstance(config.get('groups'), list):
        return config
    groups = list(config['groups'])
    for key, name, members in FAMILIES:
        if len(members) != 3:
            continue
        new = make_group(family_info(key, name, members), 'sanity45')
        old = copy.deepcopy(new)
        old['stages'][1]['conditions'][0]['value'] = 45
        for index, group in enumerate(groups):
            if group == old:
                groups[index] = new
    return dict(config, groups=groups) if groups != config['groups'] else config
