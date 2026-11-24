import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

WB=Path(__file__).resolve().parents[1]/'MirrorOfSkin/Workbench'
sys.path.insert(0,str(WB));import _module_paths
import auto_artwork,chapter_cards,name_translations,resource_scan,scan_chapters


class Image:
    def save(self,path,format):Path(path).write_bytes(b'PNG')
class Sprite:
    def read(self):return type('Read',(),{'image':Image()})()
KEY='Assets/Resources_moved/Sprite/Chapter/hells-chicken.png'
class Unity:
    @staticmethod
    def load(path):return type('Bundle',(),{'container':{KEY:Sprite()},'cabs':{}})()


class ChapterRecovery(unittest.TestCase):
    def test_duplicate_same_key_is_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'Assets/runtime').mkdir(parents=True)
            (root/'Assets/runtime/all_sinners_pools.json').write_text('{}')
            result=auto_artwork.extract(root,root,Unity,index={'bundle':{'art_keys':[KEY,KEY],'fingerprint':'a'}},portraits=False)
            self.assertEqual(result['chapter_extracted'],['hells-chicken.png'])
            self.assertEqual(result['errors'],[])
            cards=chapter_cards.load(root)
            self.assertEqual(cards['interlude_3_5']['title'],'地狱鸡')
            self.assertTrue(cards['interlude_3_5']['image_url'])

    def test_chapter_scan_runs_even_when_portraits_are_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'data';cache=Path(tmp)/'cache';(root/'Assets/runtime').mkdir(parents=True);(root/'Workbench/data').mkdir(parents=True);cache.mkdir()
            (root/'Assets/runtime/all_sinners_pools.json').write_text('{}')
            (root/'Workbench/data/chapter_cards.json').write_text(json.dumps({'interlude_3_5':{'chapter':'间章I','title':'地狱鸡','image':'hells-chicken.png'}}),encoding='utf8')
            (cache/'__data').write_bytes(b'fixture')
            with patch.object(resource_scan,'emit'):result=resource_scan.scan(root,cache,Unity)
            self.assertEqual(result['count'],1)
            self.assertEqual(chapter_cards.load(root)['interlude_3_5']['title'],'地狱鸡')
            self.assertTrue(chapter_cards.load(root)['interlude_3_5']['image_url'])

    def test_barber_corrects_old_chinese_misidentification(self):
        self.assertEqual(name_translations.name('story_8372_Barber_NicoleAppearance','神父',{}),'理发师·妮可莉娜')
        self.assertEqual(name_translations.name('other','神父',{}),'神父')

    def test_shared_chapter_image_uses_hashed_extracted_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'Workbench/data';folder=root/'Workbench/chapter_art';data.mkdir(parents=True);folder.mkdir()
            (data/'chapter_cards.json').write_text(json.dumps({'walpurgis_3':{'chapter':'第3次','title':'瓦尔普吉斯之夜','image':'stage-node-id_910603.png'}}),encoding='utf8')
            (folder/'discovered-assets.json').write_text(json.dumps({'stage-node-id_910603.png':{'file':'a'*24+'.png'}}),encoding='utf8')
            (folder/('a'*24+'.png')).write_bytes(b'PNG')
            result=chapter_cards.load(root)['walpurgis_3']
            self.assertEqual(result['title'],'瓦尔普吉斯之夜');self.assertTrue(result['image_url'])

if __name__=='__main__':unittest.main()
