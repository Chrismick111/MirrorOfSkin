from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))


class IndependentAppearance(unittest.TestCase):
    def test_runtime_trigger_matches_declared_character_and_excludes_alternate_layouts(self):
        from skin_assets import _independent_trigger

        keys = {'SD_Personality/10401_Ryoshu_BaseAppearance.prefab',
                'SD_Personality/10401_Ryoshu_Base_CP9Appearance.prefab',
                'SD_Personality/10201_Faust_BaseAppearance.prefab'}
        self.assertEqual(_independent_trigger(4, keys), 'SD_Personality/10401_Ryoshu_BaseAppearance.prefab')
        with self.assertRaises(ValueError):
            _independent_trigger(3, keys)

    def test_loader_custom_alias_can_enter_independent_conversion(self):
        from skin_assets import _loader_dependency

        custom = SimpleNamespace(resource_id='Authored', label='SD_Personality')
        keys = {'SD_Personality/10401_Ryoshu_BaseAppearance.prefab'}
        self.assertIsNone(_loader_dependency([custom], 'Authored', 'Assets/Authored.prefab', keys, required=False))
        with self.assertRaises(ValueError):
            _loader_dependency([custom], 'Authored', 'Assets/Authored.prefab', keys)

    def test_material_identity_ignores_pointer_ids_but_preserves_properties(self):
        from standalone_materials import _stock_material_identity, material_identity

        def material(shader, texture, opacity):
            return {'m_Name': 'Particles', 'm_Shader': {'m_FileID': 1, 'm_PathID': shader},
                    'm_SavedProperties': {'m_TexEnvs': [('_MainTex', {'m_Texture': {'m_FileID': 0, 'm_PathID': texture}})],
                                          'm_Floats': [('_Opacity', opacity)]}}

        identity = material_identity(material(1, 2, 0.5))
        self.assertEqual(identity, material_identity(material(3, 4, 0.5)))
        self.assertNotEqual(identity, material_identity(material(1, 0, 0.5)))
        self.assertNotEqual(identity, material_identity(material(1, 2, 0.8)))
        inherited = material(1, 2, 0.5)
        inherited['m_Parent'] = {'m_FileID': 1, 'm_PathID': 18}
        self.assertIsNone(_stock_material_identity(inherited))

    def test_shader_archive_retains_player_schema_and_uses_model_mount(self):
        from standalone_materials import StandaloneMaterials

        serialized = SimpleNamespace(class_id=48, old_type_hash=b'type', is_stripped_type=False,
                                     script_type_index=-1, type_dependencies=None)
        donor = SimpleNamespace(name='resources.assets', unity_version='6000.3.12f1',
                                header=SimpleNamespace(version=22, endian='<'),
                                _m_target_platform=19, _enable_type_tree=False, objects={})
        source = SimpleNamespace(assets_file=donor, path_id=1418, serialized_type=serialized)
        resolver = StandaloneMaterials.__new__(StandaloneMaterials)
        resolver.externals = []
        resolver.shaders = {5: (b'bytes', source)}
        resolver.shader_objects = {}
        resolver.shader_ids = {}
        resolver.preload_refs = {}
        resolver.mounts = {}
        external = SimpleNamespace(path='archive:/CAB-original/CAB-original', temp_empty='', guid=b'1'*16, type=0)
        model = SimpleNamespace(flags=4, externals=[external], parent=object())

        ref = resolver.shader_pointer(5, {'m_FileID': 1, 'm_PathID': 19})
        shaders = resolver.shader_file(model, 'CAB-model', 'CAB-shaders')
        self.assertEqual(ref, {'m_FileID': 1, 'm_PathID': 1418})
        self.assertEqual(resolver.preload_refs, {(1, 19): (1, 1418)})
        self.assertEqual(resolver.externals[0].path, 'archive:/CAB-model/CAB-shaders')
        self.assertEqual(external.path, 'archive:/CAB-original/CAB-original')
        self.assertEqual((shaders.unity_version, shaders.flags), ('6000.3.12f1', 4))
        self.assertFalse(shaders._enable_type_tree)
        self.assertEqual(shaders.types, [serialized])
        self.assertIs(shaders.objects[1418].assets_file, shaders)
