import io,json,pathlib,sys,unittest,zipfile
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]/'MirrorOfSkin'/'Workbench'
sys.path.insert(0,str(ROOT))
import generic_skin_policy as policy
import skin_assets
import skin_import
import skin_motions

class GenericSkinPolicyTest(unittest.TestCase):
    def test_numbered_private_clashes_require_a_matching_slot_and_action_name(self):
        for slot, name, expected in (
                (17, 'KnightParry9', 4), (37, 'HeroDuelWin2', 2),
                (38, 'HeroClashLose12', 3), (36, 'KnightParryReady2', 1),
                (17, 'HeroAttackParry1', 0), (37, 'KnightTargetDuelWin2', 0),
                (37, 'HeroDuelLose1', 0), (19, 'KnightParry9', 0),
                (17, 'NotAParrySound2', 0), (8, 'KnightParry1', 0)):
            with self.subTest(slot=slot, name=name):
                self.assertEqual(skin_motions._role(name, slot), expected)

    def manifest(self, value):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('mos-skin.json',value)
        b.seek(0);return b

    def test_non_roland_policy_produces_versioned_runtime_config(self):
        address='Assets/Test/Hero.prefab'
        cfg={'attack_groups':{'mode':'random_per_coin','groups':[7,10,24], 'preserve_native_layout':True}}
        with zipfile.ZipFile(self.manifest(json.dumps({'schema':1,'appearances':{address:cfg}}))) as z:
            self.assertEqual(policy.read_manifest(z)[address.lower()],cfg)
        record={'dependency':'SD_Enemy/Test.prefab','asset':address,'layout':'AnotherHero',
                'actions':{'runtime_roles':{'3':7},'runtime_animator':[3]},
                'entry':{'verified_attack_details':[7,10,24]},'policy':cfg}
        lines=skin_import.config(record,'a'*64).decode().splitlines()
        self.assertEqual(lines[0],'WBMOD2');self.assertEqual(lines[-1],'R|1|7,10,24')

    def test_invalid_unverified_and_duplicate_groups_rejected(self):
        for groups in ([7,7],[7,17],[7,24],[True],[]):
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                policy.encode_policy({'attack_groups':{'mode':'random_per_coin','groups':groups,'preserve_native_layout':True}},[7])

    def make_record(self, cfg):
        return {'dependency': 'SD_Enemy/Test.prefab', 'asset': 'Assets/Test/Hero.prefab',
                'layout': 'AnotherHero', 'policy': cfg,
                'entry': {'verified_attack_details': [7, 8]},
                'actions': {'runtime_roles': {'2': 7, '17': 4}, 'runtime_animator': [2],
                            'declarable_timeline_roles': {'3': 7, '36': 1, '37': 2}}}

    def test_role_and_animator_policy_uses_existing_config_without_attack_groups(self):
        record = self.make_record({'clash': {'ready': 36, 'win': [37]},
                                   'defense': {'evade': 2, 'guard': 3}, 'animator': [2]})
        lines = skin_import.config(record, 'a'*64).decode().splitlines()
        self.assertEqual(lines[0], 'WBMOD1')
        self.assertEqual(len(lines), 7)
        self.assertEqual([lines[5][slot] for slot in (2, 3, 17, 36, 37)], ['7', '7', '4', '1', '2'])
        self.assertEqual([lines[6][slot] for slot in (2, 3)], ['1', '0'])
        self.assertEqual(record['actions']['runtime_roles'], {'2': 7, '17': 4})

    def test_roles_reject_attack_missing_conflicting_or_invalid_evidence(self):
        for cfg in ({'clash': {'win': 7}}, {'clash': {'win': 38}}, {'clash': {'win': 17}},
                    {'clash': {'win': 37, 'lose': 37}}, {'clash': {'win': [37, 37]}},
                    {'clash': {'win': True}}, {'defense': {'evade': 3}},
                    {'animator': [3]}, {'animator': [2, 2]}, {'other': []}):
            with self.subTest(cfg=cfg), self.assertRaises(ValueError):
                skin_import.config(self.make_record(cfg), 'a'*64)

    def test_plugin_version_range_is_optional_and_inclusive(self):
        record = self.make_record({'plugin_version': {'min': '1.3.5', 'max': '1.10.0'}})
        for version in ('1.3.5', '1.3.9', '1.10.0'):
            with self.subTest(version=version):
                self.assertTrue(skin_import.config(record, 'a'*64, plugin_version=version).startswith(b'WBMOD1\n'))
        for version in ('1.3.4', '1.10.1', ''):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, '版本'):
                skin_import.config(record, 'a'*64, plugin_version=version)

    def test_voice_only_policy_preserves_wbmod1(self):
        record = self.make_record({'voice': {'owner': '12345', 'bank': 'Hero.bank'}})
        self.assertTrue(skin_import.config(record, 'a'*64).startswith(b'WBMOD1\n'))
        record['policy']['voice']['bank'] = 'Master.bank'
        with self.assertRaisesRegex(ValueError, 'FMOD'):
            skin_import.config(record, 'a'*64)

    def test_duplicate_declared_prefab_fails_across_two_bundles(self):
        address = 'Assets/Test/Hero.prefab'
        unity = SimpleNamespace(config=SimpleNamespace(FALLBACK_UNITY_VERSION='6000.3.0f1'))

        def load(body):
            name = body.decode('ascii') if body.startswith(b'WBImp_') else 'Hero'
            return SimpleNamespace(assets=[SimpleNamespace(objects={1: SimpleNamespace(peek_name=lambda: name)})])

        unity.load = load
        actions = self.make_record({})['actions']
        with TemporaryDirectory() as folder:
            archive = pathlib.Path(folder) / 'two.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr(policy.MANIFEST, json.dumps({'schema': 1, 'appearances': {address: {
                    'dependency': 'SD_Enemy/Hero.prefab'}}}))
                bundle.writestr('custom_appearance/A.bundle', b'A')
                bundle.writestr('custom_appearance/B.bundle', b'B')
            with patch.object(skin_assets, '_catalog_keys', return_value={'SD_Enemy/Hero.prefab'}), \
                    patch.object(skin_assets, '_roots', return_value=[(address, 1, 2)]), \
                    patch.object(skin_assets, '_convert', side_effect=lambda env, sha, look, *args: (look.encode(), 'Hero')), \
                    patch('skin_motions.analyze_motion', return_value=({'verified_attack_details': []}, b'', actions)):
                with self.assertRaisesRegex(ValueError, '多个匹配项'):
                    list(skin_assets.build_assets(archive, pathlib.Path(folder)/'converted', unity))

    def test_declarations_need_owned_visual_timelines_without_damage(self):
        def ptr(path):
            return {'m_FileID': 0, 'm_PathID': path}

        objects = {}

        def put(path, tree, kind='MonoBehaviour'):
            objects[path] = SimpleNamespace(type=SimpleNamespace(name=kind), read_typetree=lambda: tree)

        def track(clip_path, markers=()):
            return {'m_Clips': [{'m_Start': 0, 'm_Duration': 1, 'm_Asset': ptr(90)}],
                    'm_InfiniteClip': ptr(clip_path), 'm_Markers': {'m_Objects': [ptr(p) for p in markers]}}

        put(1, {'m_Component': [{'component': ptr(2)}]}, 'GameObject')
        put(2, {'motionList': [{'_motiondetail': slot, 'timelineAssets': [ptr(slot)]}
                               for slot in (3, 36, 37, 38)]})
        for slot, name in ((3, 'Custom Block'), (36, 'Custom Pose'), (37, 'Custom Audio'), (38, 'Duel_Lose')):
            put(slot, {'m_Name': name, 'm_Tracks': [ptr(slot+40)]})
        put(43, track(91))
        put(76, track(91))
        put(77, track(0))
        put(78, track(91, [92]))
        put(90, {})
        put(91, {}, 'AnimationClip')
        put(92, {'m_Time': 0.25, 'ratios': [], 'sturnInfo': {}})
        root = objects[1]
        root.assets_file = SimpleNamespace(objects=objects)
        with patch('skin_motions.boss_importer.build_entry', return_value=({}, b'')):
            entry, _, actions = skin_motions.analyze_motion(None, root, 'Hero', 'Assets/Test/Hero.prefab', 'Hero',
                                                            declared_roles=True)
        self.assertEqual(actions['declarable_timeline_roles'], {'3': 7, '36': 1})
        applied = policy.apply_action_policy({'defense': {'guard': 3}, 'clash': {'ready': 36}}, actions,
                                             entry['verified_attack_details'])
        self.assertEqual(applied['runtime_roles'], {'3': 7, '36': 1})
        self.assertEqual([item['detail'] for item in applied['unclassified']], [37, 38])

    def test_unknown_and_duplicate_manifest_keys_rejected(self):
        for text in ('{"schema":1,"schema":1,"appearances":{}}',
                     '{"schema":true,"appearances":{}}',
                     '{"schema":1,"appearances":{"Assets/../bad.prefab":{}}}'):
            with zipfile.ZipFile(self.manifest(text)) as z:
                with self.assertRaises(ValueError):policy.read_manifest(z)

if __name__=='__main__':unittest.main()
