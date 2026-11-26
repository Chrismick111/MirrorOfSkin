import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))
from types import SimpleNamespace

from motion_bundle_model import (_empty_animator_clip, animator_replacement, find_body_tracks, animator_body_role,
                                 primary_idle_clip_roles, select_stock_override_tracks, set_idle_loop)


class Object:
    def __init__(self, path_id, kind, tree):
        self.path_id = path_id
        self.type = SimpleNamespace(name=kind)
        self.tree = tree

    def read_typetree(self):
        return self.tree


def ref(path_id):
    return {'m_FileID': 0, 'm_PathID': path_id}


class BodyTracksTests(unittest.TestCase):
    def test_default_uses_looping_idle_unless_idle_is_a_separate_state(self):
        self.assertEqual(animator_body_role('default', {'default'}), 'idle')
        self.assertEqual(animator_body_role('default', {'default', 'idle'}), 'default')
        self.assertEqual(animator_body_role('idle', {'default', 'idle'}), 'idle')
        tree = {'m_MuscleClip': {'m_LoopTime': False, 'm_StopTime': 9.016}}
        set_idle_loop(tree)
        self.assertTrue(tree['m_MuscleClip']['m_LoopTime'])
        self.assertEqual(tree['m_MuscleClip']['m_StopTime'], 9.016)

    def test_only_dedicated_primary_idle_states_claim_placeholder_clips(self):
        def state(name, index):
            tree = {'m_NodeArray': [{'data': {'m_ClipID': index}}]}
            return {'data': {'m_NameID': name, 'm_BlendTreeConstantArray': [{'data': tree}]}}

        primary = {'m_DefaultState': 0, 'm_StateConstantArray': [state(1, 0), state(2, 1)]}
        auxiliary = {'m_DefaultState': 0, 'm_StateConstantArray': [state(2, 2)]}
        controller = {'m_TOS': [(1, 'Default'), (2, 'Idle'), (3, 'Attack')],
                      'm_AnimationClips': [ref(10), ref(20), ref(30)],
                      'm_Controller': {
                          'm_LayerArray': [{'data': {'m_StateMachineIndex': 0}}, {'data': {'m_StateMachineIndex': 1}}],
                          'm_StateMachineArray': [{'data': primary}, {'data': auxiliary}],
                      }}
        self.assertEqual(primary_idle_clip_roles(controller), {10: 'default', 20: 'idle'})
        auxiliary['m_StateConstantArray'].append(state(3, 1))
        self.assertEqual(primary_idle_clip_roles(controller), {10: 'default'})

    def test_default_idle_fallback_loops_but_other_fallback_poses_do_not(self):
        roles = {'default', 'idle'}
        self.assertEqual(animator_replacement('default', roles, {'idle'}), ('idle', True))
        self.assertEqual(animator_replacement('default', roles, {'default', 'idle'}), ('default', False))
        self.assertEqual(animator_replacement('guard', roles, {'idle'}), ('idle', False))

    def test_clip_with_only_an_event_is_not_an_empty_placeholder(self):
        muscle = {'m_StreamedClip': {'curveCount': 0}, 'm_DenseClip': {'m_CurveCount': 0},
                  'm_ConstantClip': {'data': []}}
        tree = {'m_ClipBindingConstant': {'genericBindings': [], 'pptrCurveMapping': []},
                'm_MuscleClip': {'m_Clip': {'data': muscle}}, 'm_Events': []}
        self.assertTrue(_empty_animator_clip(tree))
        tree['m_Events'] = [{'functionName': 'notify'}]
        self.assertFalse(_empty_animator_clip(tree))

    def test_selects_only_unmuted_root_sprite_track(self):
        binding = {'path': 0, 'typeID': 212, 'isPPtrCurve': 1}
        clip = Object(3, 'AnimationClip', {'m_ClipBindingConstant': {
            'genericBindings': [binding], 'pptrCurveMapping': [ref(4)]}})
        track = Object(2, 'MonoBehaviour', {'m_InfiniteClip': ref(3), 'm_Muted': False})
        timeline = Object(1, 'MonoBehaviour', {'m_Tracks': [ref(2)]})
        sprite = Object(4, 'Sprite', {})
        env = SimpleNamespace(assets=[SimpleNamespace(objects={o.path_id: o for o in (timeline, track, clip, sprite)})],
                              container={'assets/s1.playable': timeline})
        tracks = find_body_tracks(env)
        self.assertEqual(tracks['s1'].clip.path_id, 3)
        self.assertEqual(tracks['s1'].sprite_ids, [4])

        # Every segment of a supported defense or clash must reach the timeline writer.
        from motion_bundle_timelines import group_clips
        roles = ['guard', 'guard_1', 'duel_ready', 'duel_win', 'duel_win_1', 'duel_lose']
        env.container = {'alt/' + role + '.playable': timeline for role in roles + ['camera_shake']}
        tracks = find_body_tracks(env)
        self.assertEqual(set(tracks), set(roles))
        groups = group_clips({role: body.clip.path_id for role, body in tracks.items()})
        self.assertEqual({detail: len(parts) for detail, (_, parts) in groups.items()},
                         {3: 2, 36: 1, 37: 2, 38: 1})

    def test_rejects_multiple_body_tracks(self):
        binding = {'path': 0, 'typeID': 212, 'isPPtrCurve': 1}
        clip = Object(3, 'AnimationClip', {'m_ClipBindingConstant': {'genericBindings': [binding], 'pptrCurveMapping': [ref(4)]}})
        tracks = [Object(i, 'MonoBehaviour', {'m_InfiniteClip': ref(3)}) for i in (2, 5)]
        timeline = Object(1, 'MonoBehaviour', {'m_Tracks': [ref(2), ref(5)]})
        sprite = Object(4, 'Sprite', {})
        env = SimpleNamespace(assets=[SimpleNamespace(objects={o.path_id: o for o in [timeline, clip, sprite, *tracks]})], container={'assets/s1.playable': timeline})
        with self.assertRaises(ValueError):
            find_body_tracks(env)

    def test_explicitly_blank_guard_and_missing_sprite_are_distinct(self):
        binding = {'path': 0, 'typeID': 212, 'isPPtrCurve': 1}
        clip = Object(3, 'AnimationClip', {'m_ClipBindingConstant': {
            'genericBindings': [binding], 'pptrCurveMapping': [ref(0)]}})
        track = Object(2, 'MonoBehaviour', {'m_InfiniteClip': ref(3)})
        timeline = Object(1, 'MonoBehaviour', {'m_Tracks': [ref(2)]})
        env = SimpleNamespace(assets=[SimpleNamespace(objects={o.path_id: o for o in (timeline, track, clip)})],
                              container={'assets/guard.playable': timeline})
        blank = set()
        self.assertEqual(find_body_tracks(env, empty_tracks=blank), {})
        self.assertEqual(blank, {'guard'})
        clip.tree['m_ClipBindingConstant']['pptrCurveMapping'] = [ref(99)]
        with self.assertRaisesRegex(ValueError, '精灵引用无法解析'):
            find_body_tracks(env)

    def test_stock_override_needs_authored_skill_timing_and_keeps_contiguous_visuals(self):
        tracks = {name: name for name in ('idle', 's1', 's1_1', 's2', 'damaged', 'damaged_2',
                                          'parrying', 'parrying_1')}
        self.assertEqual(set(select_stock_override_tracks(tracks, {'s1': {}})),
                         {'idle', 's1', 's1_1', 'damaged', 'parrying', 'parrying_1'})
        with self.assertRaisesRegex(ValueError, 's3'):
            select_stock_override_tracks(tracks, {'s3': {}})


if __name__ == '__main__':
    unittest.main()


