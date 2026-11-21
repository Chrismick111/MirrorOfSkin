"""Multi-stage appearance groups and deterministic rule preview."""
import math
import rulesets
import group_entries
import merged_appearances

import stage_files
from stage_files import FILE, binary, snapshot
METRICS = {'health': (0, 100), 'sanity': (-45, 45), 'defense': (0, 65535)}
CONDITION_METRICS = dict(METRICS, native=(0, 1), chapter_phase=(0, 3))
# Mirrors native_src/internal_form_policy.h; these are skins on one prefab,
# not separate entries in the appearance catalog.
INTERNAL_FORMS = {
 'story_1327_MiddleFinger_fatherAppearance':['封印剑一','封印剑二','封印剑三'],
 'story_1328_MiddleFinger_discipleAppearance':['热丝关闭','热丝开启'],
 'story_1318_Pinky_DiscipleAppearance':['剑气关闭','剑气开启'],
 'story_1314_Thumb_FatherAppearance':['预知眼开启','预知眼关闭'],
 '11115':['weapon1','weapon2','weapon3','weapon4'],
 '10605':['1_helmet_off','2_helmet_on'], '10515':['off','on'],
 '10412':['head_off','head_on'], '10506':['off','on'],
 '10703':['head','helmet'], '11113':['hat_on','hat_off'],
 '11114':['off','on'], '10914':['off','on'], '10513':['nomal','blood'],
 '10514':['rifle','shotgun'], '10814':['off','on'], '10715':['off','on'],
 '10615':['off','on'], '10911':['1','2','3'], '11111':['lv1','lv2','lv3'],
 '11210':['1','2','3'], '10410':['1st','2nd','3rd'],
 '10312':['常态','另一形态'], '10913':['常态','另一形态'],
}

def director_forms(entry, native_forms=None):
 identity = str(entry.get('identity_id', ''))
 if identity in INTERNAL_FORMS: return INTERNAL_FORMS[identity][:]
 native = (native_forms or {}).get('identities', {}).get(identity, {}).get('forms') or []
 forms = native or entry.get('forms') or []
 return list(forms[:4]) or ['基础形态']
TEMPLATES = [
 ('donglang', '否定一切的东朗', ['story_8049_DongLang_1pAppearance', 'story_8049_DongLang_2pAppearance', 'story_8049_DongLang_3pAppearance']),
 ('vergilius', '维吉里乌斯', ['story_400012_VergiliusAppearance', 'story_400012_Vergilius_EgoAppearance']),
 ('realdon', '堂吉诃德', ['story_8390_RealDon_1pAppearance', 'story_8410_RealDon_2pAppearance']),
]

def candidates(catalog, annotations=None):
 known = {str(e['identity_id']) for e in catalog}
 result = []
 for key, name, identities in TEMPLATES:
  if not all(x in known for x in identities):
   continue
  stages = []
  for i, identity in enumerate(identities):
   stages.append({'identity_id': identity, 'form': 0, 'priority': i, 'match': 'all',
                  'conditions': [] if i == 0 else [{'metric': 'health', 'op': 'lte', 'value': 70 if i == 1 else 30}]})
  result.append({'id': key, 'name': name, 'enabled': True, 'hold': False, 'stages': stages})
 # Only generate internal-form candidates for entries explicitly confirmed by
 # the existing form annotations. Repeated catalog rows are deduplicated.
 seen = set()
 for entry in catalog:
  identity = str(entry.get('identity_id', ''))
  forms = entry.get('director_forms') or director_forms(entry)
  if identity in seen or identity not in (annotations or {}) or not 2 <= len(forms) <= 4: continue
  seen.add(identity)
  stages = []
  for i in range(len(forms)):
   stages.append({'identity_id': identity, 'form': i, 'priority': i, 'match': 'all',
                  'conditions': [] if i == 0 else [{'metric': 'health', 'op': 'lte', 'value': (100 * (len(forms) - i)) // len(forms)}]})
  result.append({'id': 'internal-' + identity, 'name': str(entry.get('name') or identity), 'enabled': True, 'hold': False, 'stages': stages})
 return result

def validate(config, catalog):
 if not isinstance(config, dict) or config.get('schema') != 1 or not isinstance(config.get('groups'), list) or len(config['groups']) > 64:
  raise ValueError('形态组配置格式无效')
 known = {str(e['identity_id']): e for e in catalog}
 ids, active = set(), set()
 for group in config['groups']:
  if not isinstance(group, dict): raise ValueError('形态组格式无效')
  gid, name, enabled, stages = group.get('id'), group.get('name'), group.get('enabled'), group.get('stages')
  if not group_entries.valid_group_id(gid) or gid in ids: raise ValueError('形态组编号无效或重复')
  ids.add(gid)
  if not isinstance(name, str) or not name.strip() or len(name) > 80 or type(enabled) is not bool or type(group.get('hold', False)) is not bool: raise ValueError('形态组名称或状态无效')
  if not isinstance(stages, list) or not 1 <= len(stages) <= 8: raise ValueError('每组需要 1 至 8 个阶段')
  members = set()
  for i, stage in enumerate(stages):
   if not isinstance(stage, dict): raise ValueError('阶段格式无效')
   identity = stage.get('identity_id')
   if not isinstance(identity, str) or identity not in known: raise ValueError('阶段包含未知外观：' + str(identity))
   members.add(identity)
   form = stage.get('form', 0)
   forms = known[identity].get('director_forms') or director_forms(known[identity])
   if type(form) is not int or form < 0 or form >= len(forms): raise ValueError('外观内部形态无效')
   if type(stage.get('priority', i)) is not int or not 0 <= stage.get('priority', i) <= 65535: raise ValueError('阶段优先级无效')
   if stage.get('match', 'all') not in ('all', 'any'): raise ValueError('阶段规则无效')
   try: encoded_identity = identity.encode('ascii')
   except UnicodeEncodeError: raise ValueError('外观资源编号无效')
   if not encoded_identity or len(encoded_identity) >= 64: raise ValueError('外观资源编号过长')
   conditions = stage.get('conditions', [])
   if not isinstance(conditions, list) or len(conditions) > 4 or (i == 0 and conditions) or (i != 0 and not conditions): raise ValueError('默认阶段不应有条件，其他阶段需要 1 至 4 条条件')
   for condition in conditions:
    if not isinstance(condition, dict) or condition.get('metric') not in CONDITION_METRICS or condition.get('op') not in ('lte', 'gte'): raise ValueError('触发条件无效')
    value = condition.get('value'); low, high = CONDITION_METRICS[condition['metric']]
    if type(value) is not int or not low <= value <= high: raise ValueError('触发阈值超出范围')

def preview(group, health, sanity, defense, current_stage=0):
 stages = group['stages']; values = {'health': health, 'sanity': sanity, 'defense': defense}
 if any(c.get('metric')=='chapter_phase' for stage in stages for c in stage.get('conditions',[])):raise ValueError('第九章专属阶段需要战斗中的人格状态，暂不支持离线预演')
 if any(c.get('metric')=='native' for stage in stages for c in stage.get('conditions',[])):raise ValueError('依照本体切换需要战斗中的本体状态，暂不支持离线预演')
 if type(current_stage) is not int or not 0 <= current_stage < len(stages): raise ValueError('当前阶段无效')
 for metric, value in values.items():
  lo, hi = METRICS[metric]
  if type(value) is not int or not lo <= value <= hi: raise ValueError('预演状态超出范围：' + metric)
 matches=[]; details=[]
 for i, stage in enumerate(stages):
  checks=[]
  for c in stage.get('conditions',[]):
   actual=values[c['metric']]; matched=actual <= c['value'] if c['op']=='lte' else actual >= c['value']
   checks.append(dict(c, actual=actual, matched=matched))
  matched=True if i==0 else (all(c['matched'] for c in checks) if stage.get('match','all')=='all' else any(c['matched'] for c in checks))
  priority=stage.get('priority',i)
  if i and matched: matches.append((priority,i))
  details.append({'index':i,'priority':priority,'match':stage.get('match','all'),'matched':matched,'conditions':checks})
 selected=max(matches)[1] if matches else 0
 held=bool(group.get('hold',False) and current_stage>selected)
 index=current_stage if held else selected
 for detail in details:
  i=detail['index']
  detail['status']='保持当前阶段' if held and i==index else ('规则选中' if i==selected else ('优先级较低' if i and detail['matched'] else ('默认阶段' if i==0 else '条件未满足')))
 return {'index':index,'stage':stages[index],'reason':'按只进阶设置保持当前阶段' if held else ('满足触发条件' if index else '未满足其他阶段，使用默认阶段'), 'details':details,'selected_by_rules':selected,'held':held}

def trace(group, steps, current_stage=0):
 if not isinstance(steps,list) or not 1<=len(steps)<=100: raise ValueError('预演轨迹需要 1 至 100 个状态')
 results=[]
 for state in steps:
  if not isinstance(state,dict): raise ValueError('预演状态格式无效')
  prior=current_stage
  result=preview(group,state.get('health'),state.get('sanity'),state.get('defense'),prior)
  current_stage=result['index']
  results.append(dict(result,state={k:state[k] for k in METRICS},from_stage=prior))
 return {'steps':results}

def pool_link_warnings(root, new_config, old_config=None):
 """Warn for actual group references, not legacy static appearance rows."""
 used=set()
 def add(entries):
  for entry in entries or []:
   if isinstance(entry,dict) and entry.get('entry_kind')=='group':used.add(entry.get('group_id'))
 for profile in (rulesets.custom(root).get('characters') or {}).values():
  if isinstance(profile,dict):add(profile.get('entries'))
 global_rules=rulesets._read(rulesets.global_file(root),{})
 for profile in (global_rules.get('pools') or {}).values():
  if isinstance(profile,dict):add(profile.get('entries'))
 folder=root/rulesets.DIR
 if folder.is_dir():
  for path in folder.glob('*.json'):
   item=rulesets._read(path,{})
   if item.get('scope')=='identity':add(item.get('entries'))
 groups={g.get('id'):g for g in new_config.get('groups',[]) if isinstance(g,dict)}
 return ['形态组“%s”仍在规则池中，但已删除或停用；请重新启用或从规则池移除。'%gid for gid in sorted(used) if not groups.get(gid,{}).get('enabled')]

def migrate_legacy_groups(root):
 stage_files.migrate(root, merged_appearances.upgrade_legacy_groups)


def save(root, config, revision, catalog):
 config = merged_appearances.upgrade_legacy_groups(config)
 validate(config, catalog)
 if snapshot(root)['revision'] != revision: raise ValueError('形态组已被其他窗口修改，请刷新后重试')
 return stage_files.publish(root, config)
