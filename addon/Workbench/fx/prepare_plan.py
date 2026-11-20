"""Prepare verified binary data in memory; never deploy or modify game files."""
import effect_plan
import fx_plan_binary

def prepare(plan,cache_root,game_assembly,expected_game_sha256,live_state):
 if plan.get('status')!='offline-draft-not-applied': raise ValueError('unexpected plan status')
 if plan.get('version')!=4: raise ValueError('unsupported plan version')
 effect_plan.verify_before_handoff(plan,live_state,cache_root)
 current=fx_plan_binary.sha256_file(game_assembly)
 if not isinstance(expected_game_sha256,str) or current!=expected_game_sha256.lower():
  raise ValueError('game version changed')
 return fx_plan_binary.encode(plan['operations'],current)
