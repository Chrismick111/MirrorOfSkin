import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))

import skin_import
import skin_assets


MANIFEST = 'mirrorofskin-migration.json'
SOURCE = {'hero.bundle': b'base test asset', 'spear.bundle': b'donor test asset'}


def recipe():
    def asset(member, prefab):
        return {'member': member, 'sha256': hashlib.sha256(SOURCE[member]).hexdigest(), 'prefab': prefab}
    base = asset('hero.bundle', 'Hero')
    base['bind_groups'] = [7]
    donor = asset('spear.bundle', 'HeroSpear')
    donor.update(groups=[7, 8], detail=24, segments=16)
    return {'schema': 1, 'id': 'test.hero', 'name': 'Test Hero', 'base': base, 'donors': [donor],
            'dependency': 'SD_Enemy/Hero.prefab', 'verified_attack_details': [7, 24]}


class BundleMigrationTest(unittest.TestCase):
    def archive(self, value, members=SOURCE):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr(MANIFEST, json.dumps(value) if isinstance(value, dict) else value)
            for name, body in members.items():
                archive.writestr('custom_appearance/' + name, body)
        buffer.seek(0)
        return buffer

    def test_foreign_recipe_checks_members_before_opening_unity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'foreign.zip'
            path.write_bytes(self.archive(recipe(), {**SOURCE, 'spear.bundle': b'changed'}).getvalue())
            unity = SimpleNamespace(config=SimpleNamespace(FALLBACK_UNITY_VERSION='test'))
            with self.assertRaisesRegex(ValueError, 'SHA-256.*spear.bundle'):
                list(skin_assets.build_assets(path, Path(tmp), unity))

    def test_recipe_resolves_foreign_members_in_declared_order(self):
        from bundle_migration import archive_members, read_recipe
        with zipfile.ZipFile(self.archive(recipe(), dict(reversed(list(SOURCE.items()))))) as archive:
            data = read_recipe(archive)
            self.assertEqual([member.filename for member in archive_members(archive, data)],
                             ['custom_appearance/hero.bundle', 'custom_appearance/spear.bundle'])

    def test_rejects_duplicate_keys_unsafe_names_and_unbounded_groups(self):
        from bundle_migration import read_recipe
        bad = ['{"schema":1,"schema":1}']
        value = recipe()
        value['base']['member'] = '../hero.bundle'
        bad.append(value)
        value = recipe()
        value['donors'][0]['detail'] = 7
        bad.append(value)
        value = recipe()
        value['donors'][0]['segments'] = 1000
        bad.append(value)
        for data in bad:
            with self.subTest(data=data), zipfile.ZipFile(self.archive(data)) as archive, self.assertRaises(ValueError):
                read_recipe(archive)

    def test_rejects_duplicate_members_and_traversal(self):
        from bundle_migration import archive_members, read_recipe
        for name in ('HERO.bundle', '../other.bundle'):
            with self.subTest(name=name), zipfile.ZipFile(self.archive(recipe(), {**SOURCE, name: b'x'})) as archive:
                with self.assertRaises(ValueError):
                    archive_members(archive, read_recipe(archive))

    def test_builtin_recipe_preserves_model_identity_and_group_order(self):
        from bundle_migration import builtin_recipe
        data = builtin_recipe()
        self.assertEqual(data['base']['root'], 'BRolandBaseAppearance')
        self.assertEqual(data['base']['address'], 'Roland/BRolandBase.prefab')
        self.assertEqual([(row['detail'], row['groups']) for row in data['donors']],
                         [(24, [7, 8, 9, 15, 16]), (25, [7, 8, 9, 10, 11, 12])])

    def test_foreign_model_checks_unpacked_size_before_unitypy(self):
        import struct
        from bundle_migration import validated_unpacked_size
        table = bytes(16) + struct.pack('>iIIH', 1, 2**31, 16, 3)
        header = b'UnityFS\0' + struct.pack('>I', 8) + b'5.x.x\x006000.3.0f1\0'
        header_size = (len(header) + 20 + 15) & ~15
        bundle_size = header_size + len(table) + 16
        header += struct.pack('>QIII', bundle_size, len(table), len(table), 64)
        content = header.ljust(header_size, b'\0') + table + bytes(16)
        with self.assertRaisesRegex(ValueError, '解包.*上限'):
            validated_unpacked_size(content)
