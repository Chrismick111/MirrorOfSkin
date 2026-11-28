import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCAN = Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench/scan'
sys.path.insert(0, str(SCAN))
import auto_artwork
import resource_scan
sys.path.insert(0,str(SCAN.parent))
import _module_paths,workbench


class ArtworkRecovery(unittest.TestCase):
    def test_archived_idle_key_is_detected(self):
        self.assertEqual(auto_artwork.classify_asset('Assets/Sprites/SkinPreview/SkinPreview-Archived/01/10104_Name_0_idle.png'),('archive_preview','10104'))
        self.assertIsNone(auto_artwork.classify_asset('Assets/Sprites/SkinPreview/SkinPreview-Archived/01/10104_Name_attack.png'))

    def test_nested_event_portrait_key_is_detected(self):
        self.assertEqual(auto_artwork.classify_asset(
            'Assets/Resources_moved/Sprite/Unit/Portrait/Ep7_3_Portrait/8412_portrait.png'),
            ('portrait','8412'))

    def test_same_source_in_multiple_bundles_retries_an_unreadable_copy(self):
        class Image:
            def save(self,path,format):Path(path).write_bytes(b'PNG')
        class Asset:
            def __init__(self,bad):self.bad=bad
            def read(self):
                if self.bad:raise OSError('unreadable copy')
                return type('Read',(),{'image':Image()})()
        key='Assets/Sprites/SkinPreview/SkinPreview-Archived/01/10104_Name_0_idle.png'
        class Unity:
            @staticmethod
            def load(path):return type('Bundle',(),{'container':{key:Asset(str(path).endswith('bad'))}})()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'Assets/runtime').mkdir(parents=True);(root/'Workbench/data').mkdir(parents=True)
            (root/'Assets/runtime/all_sinners_pools.json').write_text(json.dumps({'101':{'entries':[{'identity_id':'10104','appearance_name':'10104_Name'}]}}))
            (root/'Workbench/data/portrait_source_paths.json').write_text(json.dumps({'10104':key}))
            with patch.object(auto_artwork.scan_chapters,'detect',return_value={}):
                result=auto_artwork.extract(root,root,Unity,files=[root/'bad',root/'good'])
            self.assertEqual(result['added'],['10104']);self.assertEqual(result['errors'],[])

    def test_portable_source_disambiguates_archived_alternatives(self):
        class Image:
            def save(self,path,format):Path(path).write_bytes(b'PNG')
        class Asset:
            def read(self):return type('Read',(),{'image':Image()})()
        first='Assets/Sprites/SkinPreview/SkinPreview-Archived/03/10314_Name_176_idle.png'
        second='Assets/Sprites/SkinPreview/SkinPreview-Archived/03/10314_Name_177_idle.png'
        class Unity:
            @staticmethod
            def load(path):return type('Bundle',(),{'container':{first:Asset(),second:Asset()}})()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'Assets/runtime').mkdir(parents=True);(root/'Workbench/data').mkdir(parents=True)
            (root/'Assets/runtime/all_sinners_pools.json').write_text(json.dumps({'101':{'entries':[{'identity_id':'10314','appearance_name':'10314_Name'}]}}))
            (root/'Workbench/data/portrait_source_paths.json').write_text(json.dumps({'10314':second}))
            with patch.object(auto_artwork.scan_chapters,'detect',return_value={}):
                result=auto_artwork.extract(root,root,Unity,files=[root/'bundle'])
            self.assertEqual(result['added'],['10314'])
            actual=json.loads((root/'Workbench/local_portraits/local_portraits.json').read_text())
            self.assertEqual(actual['10314']['source'],second)

    def test_first_use_starts_once_and_respects_low_memory_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);wb=root/'Workbench';wb.mkdir()
            with patch.object(workbench,'_portrait_start',return_value=True) as start:
                self.assertTrue(workbench._first_portrait_start(root));start.assert_called_once()
                (wb/'images_disabled.flag').write_text('1')
                self.assertFalse(workbench._first_portrait_start(root))
                (wb/'images_disabled.flag').unlink();(wb/'first_image_scan.done').write_text('1')
                self.assertFalse(workbench._first_portrait_start(root))

    def test_prefab_sprite_selects_renderer_under_exact_appearance(self):
        class O:
            def __init__(self,pid,kind,data):self.path_id=pid;self.type=type('Type',(),{'name':kind})();self.data=data
            def parse_as_dict(self):return self.data
            def read(self):return type('Read',(),{'image':'correct sprite'})()
        go=lambda pid:{'m_GameObject':{'m_PathID':pid}}
        env=type('Env',(),{'objects':[
            O(1,'GameObject',{'m_Name':'8411_target'}),O(2,'GameObject',{'m_Name':'[SpRenderer]'}),
            O(3,'Transform',{**go(1),'m_Father':{'m_PathID':0}}),
            O(4,'Transform',{**go(2),'m_Father':{'m_PathID':3}}),
            O(5,'SpriteRenderer',{**go(2),'m_Enabled':1,'m_Sprite':{'m_FileID':0,'m_PathID':6}}),
            O(6,'Sprite',{})]})()
        self.assertEqual(auto_artwork.prefab_sprite(env,'8411_target'),'correct sprite')
        self.assertIsNone(auto_artwork.prefab_sprite(env,'wrong_target'))

    def test_external_cab_is_loaded_from_another_cache_bundle(self):
        class Obj:
            def __init__(self, env): self.env=env
            def read(self):
                if not self.env.loaded: raise FileNotFoundError('File cab-1234 not found in cache')
                return type('Read',(),{'image':'image'})()
        class Env:
            def __init__(self,path):
                self.loaded=False;self.cabs={'cab-1234':1} if path=='dependency' else {}
                self.container={'asset':Obj(self)}
            def load_file(self,path): self.loaded=path=='dependency'
        class Unity:
            @staticmethod
            def load(path): return Env(path)
        self.assertEqual(auto_artwork.BundleReader(Unity,['other','dependency']).image('primary','asset'),'image')

    def test_missing_manifest_file_is_candidate(self):
        pools={'101':{'entries':[{'identity_id':'10101','appearance_name':'10101_example'}]}}
        manifest={'10101':{'file':'a'*24+'.png'}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(auto_artwork.candidates(pools, manifest, {}, root=root), {'10101':['10101']})
            folder=root/'Workbench/portraits';folder.mkdir(parents=True)
            (folder/('a'*24+'.png')).write_bytes(b'image')
            self.assertEqual(auto_artwork.candidates(pools, manifest, {}, root=root), {})

    def test_opaque_game_portrait_is_accepted(self):
        class Image:
            def save(self, path, format): Path(path).write_bytes(b'PNG')
        class Asset:
            def read(self): return type('Read', (), {'image':Image()})()
        key='Assets/Resources_moved/Sprite/Unit/Portrait/90004_portrait.png'
        class Unity:
            @staticmethod
            def load(path): return type('Bundle', (), {'container':{key:Asset()}})()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'Assets/runtime').mkdir(parents=True)
            (root/'Assets/runtime/all_sinners_pools.json').write_text(json.dumps({'101':{'entries':[
                {'identity_id':'story_90004','appearance_name':'90004_enemy'}]}}))
            with patch.object(auto_artwork.scan_chapters, 'detect', return_value={}):
                result=auto_artwork.extract(root,root,Unity,files=[root/'bundle'])
            self.assertEqual(result['added'],['story_90004'])
            self.assertTrue(list((root/'Workbench/local_portraits').glob('*.png')))

    def test_manual_resource_scan_discovers_unlisted_portraits(self):
        class Image:
            def save(self, path, format): Path(path).write_bytes(b'PNG')
        class Asset:
            def read(self): return type('Read', (), {'image':Image()})()
        key='Assets/Resources_moved/Sprite/Unit/Portrait/90004_portrait.png'
        class Unity:
            @staticmethod
            def load(path): return type('Bundle', (), {'container':{key:Asset()}})()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'data';cache=Path(tmp)/'cache'
            (root/'Assets/runtime').mkdir(parents=True);cache.mkdir()
            (cache/'__data').write_bytes(b'fixture')
            (root/'Assets/runtime/all_sinners_pools.json').write_text(json.dumps({'101':{'entries':[
                {'identity_id':'story_90004','appearance_name':'90004_enemy'}]}}))
            with patch.object(auto_artwork.scan_chapters,'detect',return_value={}),patch.object(resource_scan,'emit'):
                result=resource_scan.scan(root,cache,Unity)
            self.assertEqual(result['count'],1)

    def test_enemy_table_maps_appearance_to_different_portrait_id(self):
        class Image:
            def save(self, path, format): Path(path).write_bytes(b'PNG')
        class Asset:
            def read(self): return type('Read', (), {'image':Image()})()
        key='Assets/Resources_moved/Sprite/Unit/Portrait/1245_portrait.png'
        class Unity:
            @staticmethod
            def load(path): return type('Bundle', (), {'container':{key:Asset()}})()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'Assets/runtime').mkdir(parents=True)
            (root/'Assets/runtime/all_sinners_pools.json').write_text(json.dumps({'101':{'entries':[
                {'identity_id':'story_8263','appearance_name':'8263_enemy'}]}}))
            with patch.object(auto_artwork.scan_chapters,'detect',return_value={}):
                result=auto_artwork.extract(root,root,Unity,files=[root/'bundle'],aliases={'8263_enemy':['1245']})
            self.assertEqual(result['added'],['story_8263'])

    def test_manual_scan_reads_enemy_portrait_mapping(self):
        class Image:
            def save(self,path,format):Path(path).write_bytes(b'PNG')
        class Sprite:
            def read(self):return type('Read',(),{'image':Image()})()
        class Table:
            def read(self):return type('Read',(),{'m_Script':json.dumps({'list':[{'appearance':'8263_enemy','sdPortrait':'1245'}]})})()
        portrait='Assets/Resources_moved/Sprite/Unit/Portrait/1245_portrait.png'
        table='Assets/Resources_moved/StaticData/static-data/abnormality-unit/test.json'
        class Unity:
            @staticmethod
            def load(path):return type('Bundle',(),{'container':{portrait:Sprite(),table:Table()}})()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'data';cache=Path(tmp)/'cache';(root/'Assets/runtime').mkdir(parents=True);cache.mkdir()
            (cache/'__data').write_bytes(b'fixture')
            (root/'Assets/runtime/all_sinners_pools.json').write_text(json.dumps({'101':{'entries':[{'identity_id':'story_8263','appearance_name':'8263_enemy'}]}}))
            with patch.object(auto_artwork.scan_chapters,'detect',return_value={}),patch.object(resource_scan,'emit'):
                self.assertEqual(resource_scan.scan(root,cache,Unity)['count'],1)


if __name__=='__main__':unittest.main()
