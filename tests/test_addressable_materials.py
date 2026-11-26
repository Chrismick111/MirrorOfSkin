from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))
from addressable_materials import material_closure, verified_replacements, _stock_witnesses
from orphan_voice_tracks import verified_orphans


def asset(name, tree):
    return SimpleNamespace(type=SimpleNamespace(name=name), read_typetree=lambda: tree)


class AddressableMaterialsTest(unittest.TestCase):
    def test_same_material_id_elsewhere_cannot_override_conflicting_slot(self):
        import _module_paths
        cab = 'CAB-' + 'd' * 32
        renderer = asset('ParticleSystemRenderer', {})
        renderer.path_id, renderer.peek_name = 55, lambda: 'Effect'
        def slots(*ids):
            return {'m_Materials': [{'m_FileID': 1, 'm_PathID': p} for p in ids]}
        original = SimpleNamespace(assets=[object()])
        current = SimpleNamespace(assets=[SimpleNamespace(externals=[SimpleNamespace(path=f'archive:/{cab}/{cab}')])])
        roots = [(f'assets/{name}.prefab', i, 0) for i, name in enumerate(('alpha', 'beta'), 1)]
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory/'game.bundle').write_bytes(b'stock')
            index = {'entries': {'game.bundle': {'prefabs': {i: name for name, i, _ in roots}}}}
            unity = SimpleNamespace(load=lambda _: current)
            for old_ids, new_ids, valid in [((11, 99), (11, 99), True),
                                            ((11, 99), (11, 100), False),
                                            ((11, 99), (11,), False)]:
                def reachable(file, root):
                    return [(renderer, slots(*(old_ids if file is original.assets[0] else new_ids)))]
                with self.subTest(slots=new_ids), patch('skin_assets._roots', return_value=roots), \
                        patch('addressable_materials._reachable', side_effect=reachable):
                    result = _stock_witnesses(original, directory, index, {1: {99}}, unity)
                    self.assertEqual(result, {1: cab.lower()} if valid else {})

    def test_donor_requires_multiple_independent_matching_prefabs(self):
        rows = {(1, 'current'): {('one', 11), ('two', 11)}}
        self.assertEqual(verified_replacements(rows), {1: 'current'})
        self.assertEqual(verified_replacements({(1, 'current'): {('one', 11), ('one', 12)}}), {})
        rows[1, 'other'] = {('three', 11)}
        self.assertEqual(verified_replacements(rows), {})

    def test_material_closure_includes_local_shader_and_texture(self):
        objects = {
            5: asset('Material', {'m_Shader': {'m_FileID': 0, 'm_PathID': 6}}),
            6: asset('Shader', {'texture': {'m_FileID': 0, 'm_PathID': 7}}),
            7: asset('Texture2D', {}),
        }
        self.assertEqual(material_closure(SimpleNamespace(objects=objects), {5}), {5, 6, 7})

    def test_closure_rejects_missing_or_unverified_external_resources(self):
        for file_id in (0, 1):
            with self.subTest(file_id=file_id):
                objects = {5: asset('Material', {'m_Shader': {'m_FileID': file_id, 'm_PathID': 6}})}
                with self.assertRaisesRegex(ValueError, '6'):
                    material_closure(SimpleNamespace(objects=objects), {5})

    def test_only_exact_dangling_stock_voice_track_is_certified(self):
        def ref(pid):
            return {'m_FileID': 0, 'm_PathID': pid}

        timeline = {'m_Name': 'Attack', 'm_Tracks': [ref(6), ref(7)]}
        stock = {
            5: asset('MonoBehaviour', timeline),
            6: asset('MonoBehaviour', {'m_Name': 'FMOD Custom Track_Voice', 'm_Parent': ref(5),
                                      'm_Clips': [{'m_Asset': ref(8)}]}),
            7: asset('MonoBehaviour', {'m_Name': 'Effect Track', 'm_Parent': ref(5),
                                      'm_Clips': [{'m_Asset': ref(9)}]}),
        }
        self.assertEqual(verified_orphans(timeline, 5, {6, 7}, stock), {6})
        reordered = dict(timeline, m_Tracks=[ref(7), ref(6)])
        self.assertEqual(verified_orphans(reordered, 5, {6}, stock), set())
