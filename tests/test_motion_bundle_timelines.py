import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))
from motion_bundle_timelines import _TimelineBuilder, group_clips, import_game_marker, phase_times, ref


class MotionTimelineTests(unittest.TestCase):
    def test_per_coin_order_and_clash_slots(self):
        clips = {'s2_2': 99, 's2': 30, 's2_1': 6, 's11': 55, 'parrying_1': 7, 'parrying': 8, 'duel_win': 25}
        groups = group_clips(clips)
        self.assertEqual(groups[8], ('s2', [30, 6, 99]))
        self.assertEqual(groups[24], ('s11', [55]))
        self.assertEqual(groups[17], ('parrying', [8, 7]))
        self.assertEqual(groups[37], ('duel_win', [25]))

    def test_gap_is_not_silently_bound_to_another_coin(self):
        with self.assertRaises(ValueError):
            group_clips({'s1': 1, 's1_2': 2})

    def test_marker_fraction_and_out_of_range_phase(self):
        self.assertEqual(phase_times({'start': .25, 'end': .75, 'steps': 3}, 2), [.5, 1, 1.5])
        self.assertEqual(phase_times({'start': 2, 'end': 2, 'steps': 1}, 1), [1])

    def test_zero_step_guard_does_not_require_move_or_damage(self):
        from motion_bundle_timelines import required_markers
        phase = {'type': 'ToTargetWide', 'steps': 0}
        groups = {3: ('guard', [42])}
        config = {'guard': {'coins': [{'phases': [phase]}]}}
        self.assertEqual(required_markers(groups, config), {'end', 'handoff'})
        phase['steps'] = 1
        self.assertIn('move', required_markers(groups, config))

    def test_stock_director_with_no_scene_bindings_uses_its_own_character_receiver(self):
        prefab = SimpleNamespace(
            app={'motionList': [{'timelineAssets': [ref(5)]}], '_anim': ref(6),
                 '_playableDirector': ref(0), 'm_GameObject': ref(9)},
            objects={}, director={'m_SceneBindings': [], 'm_GameObject': ref(9)},
            root=9, director_id=7, app_id=8,
        )
        self.assertEqual(_TimelineBuilder(prefab).receivers, {'body': ref(6), 'view': ref(8), 'skill': ref(8)})
        prefab.app['_playableDirector'] = ref(99)
        with self.assertRaisesRegex(ValueError, '无法唯一确认'):
            _TimelineBuilder(prefab)

    def test_end_marker_requires_same_game_script_archive_and_file_schema(self):
        expected = SimpleNamespace(path='archive:/cab/scripts', guid=bytes(16), type=0)
        wrong = SimpleNamespace(path='archive:/cab/other', guid=bytes(16), type=0)
        shared = {'header': SimpleNamespace(version=22, endian='<'), 'unity_version': '0.0.0',
                  '_m_target_platform': 19, '_enable_type_tree': True}
        donor_type = SimpleNamespace(local_serialized_file_index=1, local_identifier_in_file=99)
        donor = SimpleNamespace(**shared, externals=[expected], script_types=[donor_type])
        target = SimpleNamespace(**shared, externals=[wrong], script_types=[], types=[])
        prefab = SimpleNamespace(file=target, objects={})
        serialized = SimpleNamespace(class_id=114, script_type_index=0, is_stripped_type=False, type_dependencies=())
        marker = {'m_GameObject': ref(0), 'm_Enabled': 1, 'm_Time': 1.0,
                  'm_Name': 'Character Appearance Marker_End Cheaker(Clone)',
                  'm_Script': {'m_FileID': 1, 'm_PathID': 99}}
        source = SimpleNamespace(assets_file=donor, serialized_type=serialized, read_typetree=lambda: marker.copy())
        self.assertFalse(import_game_marker(prefab, source, 11, 'end'))
        self.assertFalse(target.types)
        target.externals.append(expected)
        save = lambda obj, tree: setattr(obj, 'tree', tree)
        with patch('private_server_art._save', side_effect=save):
            self.assertTrue(import_game_marker(prefab, source, 11, 'end'))
        self.assertEqual(prefab.objects[11].tree['m_Script'], {'m_FileID': 2, 'm_PathID': 99})
        self.assertEqual(target.script_types[0].local_serialized_file_index, 2)
        self.assertIs(prefab.objects[11].assets_file, target)
