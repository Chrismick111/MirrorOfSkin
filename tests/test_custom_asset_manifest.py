import json
from io import BytesIO
from pathlib import Path, PurePosixPath
import sys
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))


def model(bundle='__data', address='Assets/Models/Fox.prefab', resource='Fox'):
    return dict(label='SD_Personality', resourceId=resource, bundle=bundle, assetPath=address)


def package(rows, files=()):
    body = BytesIO()
    with ZipFile(body, 'w') as archive:
        archive.writestr('Pack/custom_bundles/asset_manifest.json', json.dumps({'overrides': rows}))
        for name in files:
            archive.writestr(name, b'UnityFS\0fixture')
    return ZipFile(body)


class CustomAssetManifestTest(unittest.TestCase):
    def test_only_explicit_battle_bindings_resolve_in_manifest_folder(self):
        from custom_asset_manifest import read_bindings

        rows = [model('MyModel'), model('MyModel', resource='FoxAlias'),
                dict(model('portraits'), label='Sprite_Personality', assetType='Sprite'),
                dict(model('enemy'), label='SD_Enemy', assetType='GameObject')]
        with package(rows, ('Pack/custom_bundles/mymodel', 'Pack/custom_bundles/enemy',
                            'Other/custom_bundles/mymodel')) as archive:
            bindings = read_bindings(archive)
        self.assertEqual([str(path) for _, path, _ in bindings],
                         ['Pack/custom_bundles/mymodel', 'Pack/custom_bundles/enemy'])
        self.assertEqual([item.resource_id for item in bindings[0][2]], ['Fox', 'FoxAlias'])

    def test_wrong_bundle_traversal_and_conflicting_resource_fail(self):
        from custom_asset_manifest import read_bindings

        for rows, files in (([model('missing')], ('Other/custom_bundles/missing',)),
                            ([model('../missing')], ('Pack/missing',)),
                            ([model(), model(address='Assets/Wolf.prefab')], ('Pack/custom_bundles/__data',)),
                            ([model('bad.dll')], ('Pack/custom_bundles/bad.dll',))):
            with self.subTest(rows=rows), package(rows, files) as archive:
                with self.assertRaises(ValueError):
                    read_bindings(archive)

    def test_only_exact_asset_paths_are_selected(self):
        from custom_asset_manifest import resolve_prefabs, read_bindings

        with package([model()], ('Pack/custom_bundles/__data',)) as archive:
            _, path, bindings = read_bindings(archive)[0]
        other = ('Assets/Other/Fox.prefab', 1, 3)
        target = ('assets/models/fox.prefab', 2, 3)
        self.assertEqual(resolve_prefabs(path, bindings, [other, target]), [(bindings, target)])
        with self.assertRaises(ValueError):
            resolve_prefabs(path, bindings, [other])

    def test_normalization_only_keeps_manifest_and_listed_models(self):
        from mod_archive import _supported_member

        p = PurePosixPath('Pack/custom_bundles')
        self.assertTrue(_supported_member(p / 'asset_manifest.json'))
        for name in ('look', '__data', 'undeclared.bundle', 'loader.dll', 'extra.json'):
            self.assertFalse(_supported_member(p / name))
        for name in ('custom_banks/sound.bank', 'patch.carra2', 'Voice_Test_10101.json', 'mos-skin.json',
                     'custom_appearance/legacy.bundle', 'custom_limbus_data/personality/author.json'):
            self.assertTrue(_supported_member(p / name))
