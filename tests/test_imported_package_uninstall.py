"""Package removal uses one catalog/rules transaction and preserves siblings."""
import json
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parent/'MirrorOfSkin/Workbench'))
sys.path.insert(0, str(here))
from delete_imported import delete
from import_packages import LIBRARY_MARKER, MARKER, encode_index, ensure_library, index_path, locator_path, read_index
from imported_package_uninstall import refresh_packages


class PackageDeletion(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)/'data'
        self.addon = Path(folder.name)/'addon'
        self.managed = self.addon/'外来外观'
        self.managed.mkdir(parents=True)
        self.catalog = self.root/'Assets/runtime/all_sinners_pools.json'
        self.assets = self.root/'Assets/ImportedSkins'
        self.assets.mkdir(parents=True)
        self.catalog.parent.mkdir()
        self.lock = lambda _: nullcontext()
        self.library = ensure_library(self.root, self.addon)
        self.packages = []
        self.entries = []

    def add(self, directory, number, looks):
        package_id = '%032x' % number
        path = self.managed/directory
        path.mkdir()
        (path/MARKER).write_text(json.dumps({'id':package_id}))
        model = 'a'*64+'.bundle'
        (path/model).write_bytes(b'art')
        identities = []
        for look in looks:
            exact = 'WBImp_'+('%024x' % look)
            identity = 'story_'+exact
            identities.append(identity)
            self.entries.append(dict(identity_id=identity, appearance_name=exact))
            (self.assets/(exact+'.cfg')).write_text('WBMOD1\na\nb\n'+model+'\nd\ne\nf\n')
            locator_path(self.root, identity).write_text(f'外来外观/{directory}/{model}', encoding='utf8')
        row = dict(directory=directory, source=directory+'.zip', id=package_id, identities=identities)
        self.packages.append(row)
        index_path(self.root).write_bytes(encode_index(dict(schema=1, packages=self.packages, library=self.library)))
        self.catalog.write_text(json.dumps({'101':{'entries':self.entries}}))
        return path, model, identities

    def refresh(self):
        return refresh_packages(self.root, self.addon, lock_factory=self.lock)

    def ids(self):
        return [row['identity_id'] for row in json.loads(self.catalog.read_bytes())['101']['entries']]

    @staticmethod
    def remove(path, model):
        (path/MARKER).unlink()
        (path/model).unlink()
        path.rmdir()

    def test_missing_folder_uninstalls_whole_package_once(self):
        gone, model, first = self.add('删除包', 1, [1,2])
        kept, _, second = self.add('保留包', 2, [3])
        rules = self.root/'自定义人格池.json'
        rules.write_text(json.dumps(dict(entries=self.entries)))
        self.remove(gone, model)
        self.assertEqual(self.refresh(), {'removed':[{'directory':'删除包','identities':first}], 'blocked':[]})
        self.assertEqual(self.ids(), second)
        self.assertEqual([e['identity_id'] for e in json.loads(rules.read_bytes())['entries']], second)
        self.assertTrue((kept/model).is_file())
        self.assertFalse(any(locator_path(self.root, identity).exists() for identity in first))
        self.assertEqual(self.refresh(), {'removed':[], 'blocked':[]})

    def test_stage_protection_blocks_entire_package(self):
        gone, model, identities = self.add('删除包', 1, [1,2])
        (self.root/'演出编排.json').write_text(json.dumps(dict(stages=[dict(identity_id=identities[-1])])))
        self.remove(gone, model)
        self.assertTrue(self.refresh()['blocked'])
        self.assertEqual(self.ids(), identities)

    def test_reimport_prunes_only_unconfigured_stock_siblings_of_proven_package(self):
        from imported_package_uninstall import prune_old_stock
        _, _, group = self.add('服务器包', 1, [1,2,3])
        _, _, unrelated = self.add('旁包', 2, [4])
        (self.root/'自定义人格池.json').write_bytes(encode_index({'entries':[{'identity_id':group[2]}]}))
        kept = prune_old_stock(self.root, self.addon, '服务器包.zip', group[:1],
                              [*group,*unrelated])
        self.assertEqual(kept, [group[2]])
        self.assertEqual(self.ids(), [group[0], group[2], *unrelated])
        self.assertEqual(read_index(self.root)['packages'][0]['identities'], [group[0],group[2]])

    def test_reinstall_can_delete_one_orphan_and_its_rule(self):
        _, _, identities = self.add('待恢复', 1, [1,2])
        self.managed.rename(self.addon/'旧库')
        rules = self.root/'自定义人格池.json'
        rules.write_text(json.dumps(dict(entries=self.entries)))
        delete(self.root, identities[0], addon=self.addon, lock_factory=self.lock)
        self.assertEqual(self.ids(), identities[1:])
        self.assertEqual(read_index(self.root)['packages'][0]['identities'], identities[1:])
        self.assertEqual([r['identity_id'] for r in json.loads(rules.read_bytes())['entries']], identities[1:])
        self.assertFalse(locator_path(self.root, identities[0]).exists())
        delete(self.root, identities[1], addon=self.addon, lock_factory=self.lock)
        self.assertFalse(read_index(self.root)['packages'])

    def test_manual_delete_does_not_touch_another_library_or_reused_folder(self):
        for library_matches in (False, True):
            number = 1 + int(library_matches)
            path, model, identities = self.add(str(number),number,[number])
            (self.managed/LIBRARY_MARKER).write_bytes(encode_index({'id':self.library if library_matches else '9'*32}))
            (path/MARKER).write_bytes(encode_index({'id':'8'*32}))
            delete(self.root, identities[0], addon=self.addon, lock_factory=self.lock)
            self.assertEqual((path/model).read_bytes(), b'art')
            self.assertFalse(locator_path(self.root,identities[0]).exists())

    def test_missing_appearance_in_restored_package_keeps_model_and_group_protection(self):
        path, model, identities = self.add('部分恢复', 1,[1,2])
        index=read_index(self.root)
        index['packages'][0]['missing_identities']=[identities[0]]
        index_path(self.root).write_bytes(encode_index(index))
        group=self.root/'演出编排.json'
        group.write_text(json.dumps({'stages':[{'identity_id':identities[0]}]}))
        with self.assertRaisesRegex(ValueError, '形态组'):
            delete(self.root,identities[0],addon=self.addon,lock_factory=self.lock)
        self.assertEqual(read_index(self.root),index)
        group.unlink()
        delete(self.root,identities[0],addon=self.addon,lock_factory=self.lock)
        self.assertEqual(self.ids(),identities[1:])
        self.assertNotIn('missing_identities',read_index(self.root)['packages'][0])
        self.assertEqual((path/model).read_bytes(),b'art')

    def test_rename_missing_parent_and_empty_directory_do_not_uninstall(self):
        path, model, identities = self.add('原名', 1, [1])
        renamed = path.rename(path.with_name('改名'))
        self.assertFalse(self.refresh()['removed'])
        self.assertIn('外来外观/改名', locator_path(self.root, identities[0]).read_text(encoding='utf8'))
        whole = self.managed.rename(self.managed.with_name('暂不可用'))
        self.managed.mkdir()
        self.assertFalse(self.refresh()['removed'])
        (self.managed/LIBRARY_MARKER).unlink(missing_ok=True)
        self.managed.rmdir()
        whole.rename(self.managed)
        (renamed/MARKER).unlink()
        self.assertFalse(self.refresh()['removed'])
        self.assertEqual(self.ids(), identities)

    def test_workbench_delete_preserves_same_file_until_last_reference(self):
        path, model, identities = self.add('原名', 1, [1,2])
        delete(self.root, identities[0], addon=self.addon, lock_factory=self.lock)
        self.assertTrue((path/model).is_file())
        delete(self.root, identities[1], addon=self.addon, lock_factory=self.lock)
        self.assertFalse((path/model).exists())
        self.assertTrue((path/MARKER).is_file())
        self.assertFalse(self.ids())


if __name__ == '__main__':
    unittest.main()
