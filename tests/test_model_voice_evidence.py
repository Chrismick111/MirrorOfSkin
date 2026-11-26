import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))
import _module_paths
import skin_motions


def ref(pid, file_id=0):
    return {'m_FileID': file_id, 'm_PathID': pid}


def event(guid=1, path=''):
    return {'m_Name': 'FMODEventPlayable(Clone)', 'eventName': path,
            'EventReference': {'Guid': {'Data1': guid, 'Data2': 0, 'Data3': 0, 'Data4': 0}}}


def track(name, *assets, **fields):
    return dict(m_Name=name, m_Clips=[dict(m_Start=0, m_Duration=0.2, m_Asset=ref(item))
                                     for item in assets], **fields)


class ModelVoiceEvidenceTest(unittest.TestCase):
    def inspect(self, trees, tracks):
        trees = {1: {'m_Tracks': tracks}, **trees}
        app = {'motionList': [{'_motiondetail': 7, 'timelineAssets': [ref(1), ref(1)]}]}
        return skin_motions._model_voice_evidence(app, trees.get)

    def test_counts_real_voice_playables_once_across_shared_timelines(self):
        trees = {2: track('Group', m_Children=[ref(3)]),
                 3: track('FMOD Custom Track_Voice (1)', 4, 5, 6, 7),
                 4: event(-2), 5: event(0), 6: event(1, 'event:/SFX/weapons/hit'),
                 7: event(0, 'event:/Voice/Hero/Attack')}
        self.assertEqual(self.inspect(trees, [ref(2)]), {'state': 'found', 'count': 2})

    def test_empty_track_sfx_and_unreferenced_character_are_not_voice(self):
        trees = {2: track('FMOD Custom Track_Voice'), 3: track('FMOD Custom Track', 4),
                 4: event(), 5: track('FMOD Custom Track_Voice', 4, m_Parent=ref(1))}
        self.assertEqual(self.inspect(trees, [ref(2), ref(3)]), {'state': 'none', 'count': 0})

    def test_identifies_renamed_native_voice_track_by_script(self):
        trees = {2: track('Renamed', 4, m_Script=ref(3)), 3: {'m_ClassName': 'FMODCustomTrack_Voice'},
                 4: event()}
        self.assertEqual(self.inspect(trees, [ref(2)]), {'state': 'found', 'count': 1})

    def test_shared_stock_event_is_inherited_and_distinct_event_is_authored(self):
        app = {'motionList': [{'timelineAssets': [ref(1)]}]}
        trees = {1: {'m_Tracks': [ref(2)]}, 2: track('FMOD Custom Track_Voice', 3), 3: event(21)}
        baseline = lambda: frozenset({('guid', (21, 0, 0, 0))})
        self.assertEqual(skin_motions._model_voice_evidence(app, trees.get, stock_voice=baseline),
                         {'state': 'inherited', 'count': 1})
        trees.update({2: track('FMOD Custom Track_Voice', 3, 4), 4: event(22)})
        self.assertEqual(skin_motions._model_voice_evidence(app, trees.get, stock_voice=baseline),
                         {'state': 'found', 'count': 1})
        self.assertEqual(skin_motions._model_voice_evidence(app, trees.get, stock_only=True),
                         {'state': 'inherited', 'count': 2})

    def test_unavailable_stock_comparison_preserves_voice_without_attributing_it(self):
        app = {'motionList': [{'timelineAssets': [ref(1)]}]}
        trees = {1: {'m_Tracks': [ref(2)]}, 2: track('FMOD Custom Track_Voice', 3), 3: event()}
        self.assertEqual(skin_motions._model_voice_evidence(app, trees.get, stock_voice=lambda: None),
                         {'state': 'found_unattributed', 'count': 1})
        self.assertEqual(skin_motions._model_voice_evidence(app, trees.get, stock_voice=frozenset),
                         {'state': 'found', 'count': 1})
        self.assertEqual(skin_motions._model_voice_evidence(app, trees.get), {'state': 'found', 'count': 1})

    def test_nonlocal_and_missing_references_leave_result_unknown(self):
        trees = {2: track('FMOD Custom Track_Voice', 4)}
        self.assertEqual(self.inspect(trees, [ref(2)]), {'state': 'unknown', 'count': 0})
        self.assertEqual(self.inspect(trees, [ref(2, 1)]), {'state': 'unknown', 'count': 0})

    def test_ignores_muted_group_and_accepts_explicit_voice_marker(self):
        trees = {2: track('Group', m_Muted=1, m_Children=[ref(3)]),
                 3: track('FMOD Custom Track_Voice', 4), 4: event(),
                 5: track('Marker Track', m_Markers={'m_Objects': [ref(6)]}),
                 6: {**event(0, 'event:/Voice/Hero/Attack'), 'm_Time': 0.0}}
        self.assertEqual(self.inspect(trees, [ref(2), ref(5)]), {'state': 'found', 'count': 1})
