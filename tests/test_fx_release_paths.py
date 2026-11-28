import hashlib, json, os, pathlib, shutil, sys, tempfile, unittest
from unittest import mock

WORKBENCH = pathlib.Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'
sys.path.insert(0, str(WORKBENCH))
import _module_paths
import fx_handoff

class FxCompatibilityTests(unittest.TestCase):
    def test_handoff_real_runner_for_each_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            addon, data, game = base/'addon', base/'user', base/'game'
            fx = addon/'Workbench'/'fx'
            fx.mkdir(parents=True); data.mkdir(); game.mkdir()
            shutil.copy(WORKBENCH/'_module_paths.py', addon/'Workbench')
            for name in ('fx_prepare_runner.py', 'fx_activation.py'):
                shutil.copy(WORKBENCH/'fx'/name, fx/name)
            modules = {
                'effect_schemes': "def get(root,name):\n return {'effects':[{'appearance':'fixture'}]}\n",
                'effect_timelines': "def lookup(*a,**k): return {}\ndef _read_live(*a,**k): pass\ndef state(*a): return {'status':'done'}\n",
                'prepare_plan': "def prepare(compiled,cache,assembly,expected,state):\n assert expected == __import__('hashlib').sha256(assembly.read_bytes()).hexdigest()\n return expected.encode()\n",
                'resource_catalog': "def resolve_roots(game_dir): return {'resource_root':game_dir}\n",
                'effect_plan': "def preview_workbench(plan,state): return plan\n",
                'scan_units': '',
            }
            for name, content in modules.items(): (fx/(name+'.py')).write_text(content,encoding='utf8')
            shutil.copy(WORKBENCH.parent/'release_compatibility.py', addon)
            names = ('GameAssembly.dll', 'UnityPlayer.dll', 'LimbusCompany_Data/il2cpp_data/Metadata/global-metadata.dat')
            builds = {build: {name: hashlib.sha256((build+name).encode()).hexdigest() for name in names} for build in ('old','new')}
            (addon/'compatibility.json').write_text(json.dumps({'game_files':builds['old'],'additional_game_builds':{'new':builds['new']}}),encoding='utf8')
            (data/'compatibility.json').write_text('{}',encoding='utf8')
            (data/'fx_active.json').write_text(json.dumps({'enabled':True,'name':'fixture'}),encoding='utf8')
            for build in ('old','new'):
                for name in names:
                    path=game/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(build+name,encoding='utf8')
                logs=[]
                with mock.patch.object(fx_handoff.mos_data,'data_dir',return_value=data), mock.patch.object(fx_handoff.mos_data,'path',side_effect=lambda root,name:data/name):
                    self.assertTrue(fx_handoff.prepare(addon,game,logs.append,python_exe=sys.executable), logs)
                self.assertEqual((data/'fx-active.bin').read_bytes(),builds[build]['GameAssembly.dll'].encode())

