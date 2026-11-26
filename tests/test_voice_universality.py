"""Regression coverage for imported appearance/voice association."""
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

WORKBENCH = Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'
sys.path[:0] = [str(WORKBENCH), str(WORKBENCH / 'core')]
import _module_paths  # noqa: F401
import bank_evidence
import bank_mod
import voice_binding


def chunk(tag, data):
    return tag + struct.pack('<I', len(data)) + data + b'\0' * (len(data) % 2)


def bank(samples, events=True):
    names = bytearray(len(samples) * 4)
    headers = bytearray()
    data = bytearray()
    for i, (name, frames, content) in enumerate(samples):
        struct.pack_into('<I', names, 4 * i, len(names))
        names.extend(name.encode('ascii') + b'\0')
        headers.extend(struct.pack('<Q', (frames << 34) | (i << 7) | (7 << 1)))
        data.extend(bytes([content]) * 32)
    head = struct.pack('<4s6I', b'FSB5', 1, len(samples), len(headers), len(names), len(data), 2)
    snd = head.ljust(60, b'\0') + headers + names + data
    proj = chunk(b'LIST', b'PROJ' + chunk(b'LIST', b'EVTS' + (b'EVNT' if events else b'')))
    return chunk(b'RIFF', b'FEV ' + proj + chunk(b'SND ', snd))


class VoiceUniversalityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mos-voice-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.skins = self.root / 'Assets/ImportedSkins'
        self.skins.mkdir(parents=True)
        self.library = self.root / 'Assets/ImportedVoices'
        self.library.mkdir(parents=True)
        self.catalog = self.root / 'Assets/runtime/all_sinners_pools.json'
        self.catalog.parent.mkdir(parents=True)
        self.entries = []
        self.catalog.write_text('{}', encoding='utf8')

    def skin(self, letter, owner, name):
        look = 'WBImp_' + letter * 24
        self.entries.append(dict(identity_id='story_' + look, appearance_name=look,
                                 name=name, import_source=name))
        lines = ['WBMOD1', f'SD_Personality/{owner}_actor.prefab',
                 f'Assets/{owner}_actor.prefab', 'a' * 64 + '.bundle',
                 f'{owner}_actor', '0' * 128, '0' * 128]
        (self.skins / (look + '.cfg')).write_text('\n'.join(lines) + '\n', encoding='ascii')
        self.catalog.write_text(json.dumps({'101': {'entries': self.entries}}), encoding='utf8')
        return look

    def voice(self, targets, included=(), name='shared'):
        revision = 'f' * 64
        folder = self.library / revision
        folder.mkdir()
        (folder / 'custom.bank').write_bytes(b'fixture')
        (folder / 'voice.json').write_text(json.dumps(dict(
            name=name, source=name, revision=revision, targets=targets,
            banks=['custom.bank'], playable_banks=['custom.bank'], included_looks=included)), encoding='utf8')
        return revision

    def test_explicit_same_owner_models_both_bind(self):
        a = self.skin('a', '10109', 'A')
        b = self.skin('b', '10109', 'B')
        self.voice(['10109'], [a, b])
        self.assertEqual(set(voice_binding.reconcile(self.root)), {a, b})

    def test_explicit_single_target_can_override_model_layout(self):
        a = self.skin('a', '10109', 'A')
        self.voice(['10916'], [a])
        self.assertIn(a, voice_binding.reconcile(self.root))
        self.assertIn('\t10916\t', (self.library / 'bindings.tsv').read_text())

    def test_matching_sibling_prevents_unrelated_override(self):
        a = self.skin('a', '10916', 'A')
        b = self.skin('b', '10109', 'B')
        self.voice(['10916'], [a, b])
        self.assertEqual(set(voice_binding.reconcile(self.root)), {a})

    def test_different_unmatched_layouts_are_not_assigned_a_single_voice(self):
        a = self.skin('a', '10109', 'A')
        b = self.skin('b', '10209', 'B')
        self.voice(['10916'], [a, b])
        self.assertEqual(voice_binding.reconcile(self.root), {})

    def test_ambiguous_unrelated_models_remain_unbound(self):
        self.skin('a', '10109', 'A')
        self.skin('b', '10109', 'B')
        self.voice(['10109'])
        self.assertEqual(voice_binding.reconcile(self.root), {})

    def test_package_voice_owner_and_bank_select_only_the_declared_bank(self):
        look = self.skin('a', '10109', 'A')
        other = self.skin('b', '10916', 'B')
        self.entries[0]['imported_voice'] = {'owner': '10916', 'bank': 'Custom.bank'}
        self.catalog.write_text(json.dumps({'101': {'entries': self.entries}}), encoding='utf8')
        rev = self.voice(['10916','10213'], [look])
        directory = self.library / rev
        (directory/'second.bank').write_bytes(b'another playable bank')
        meta = json.loads((directory/'voice.json').read_bytes())
        meta['banks'].append('second.bank'); meta['playable_banks'].append('second.bank')
        (directory/'voice.json').write_text(json.dumps(meta), encoding='utf8')
        self.assertEqual(set(voice_binding.reconcile(self.root)), {look})
        self.assertEqual((self.library/'bindings.tsv').read_text().splitlines(), [f'{look}\t10916\t{rev}\tcustom.bank'])
        for declaration in ({'owner':'10916','bank':'absent.bank'}, {'owner':'10303','bank':'custom.bank'}):
            self.entries[0]['imported_voice'] = declaration
            self.catalog.write_text(json.dumps({'101': {'entries': self.entries}}), encoding='utf8')
            self.assertEqual(voice_binding.reconcile(self.root), {})

    def test_explicit_voice_requires_same_package_and_valid_bank_name(self):
        look = self.skin('a', '10109', 'A')
        self.entries[0]['imported_voice'] = {'owner': '10109', 'bank': 'custom.bank'}
        self.catalog.write_text(json.dumps({'101': {'entries': self.entries}}), encoding='utf8')
        self.voice(['10109'], [], name='unrelated')
        self.assertNotIn(look, voice_binding.reconcile(self.root))
        for bank_name in ('../custom.bank','master.bank','a'*245+'.bank'):
            with self.assertRaises(ValueError):
                voice_binding.validate_voice_policy({'owner':'10109','bank':bank_name})

    def test_old_unresolved_playable_bank_is_reprobed_once_per_evidence(self):
        look = self.skin('a', '10109', 'A')
        self.voice([], [look])
        class Evidence:
            key = 'one'
            calls = 0
            def target_probe_key(self, folder, banks): return self.key
            def probe_targets(self, folder, banks):
                self.calls += 1
                return {'10109'} if self.key == 'two' else set()
        evidence = Evidence()
        self.assertIn(look, voice_binding.reconcile_locked(self.root, evidence))
        self.assertIn(look, voice_binding.reconcile_locked(self.root, evidence))
        self.assertEqual(evidence.calls, 1)
        evidence.key = 'two'
        self.assertIn(look, voice_binding.reconcile_locked(self.root, evidence))
        self.assertEqual(evidence.calls, 2)

    def test_same_duration_changed_sample_identifies_owner(self):
        game = self.root / 'Desktop'
        mod = self.root / 'mod'
        game.mkdir(); mod.mkdir()
        name = 'Voice_Default_S7_4.assets.bank'
        samples = [('battle_s1_10916_1', 32000, 1), ('battle_s1_10109_1', 32000, 2)]
        (game / name).write_bytes(bank(samples))
        (mod / name).write_bytes(bank([(samples[0][0], 32000, 9), samples[1]]))
        with patch.dict(os.environ, {'LIMBUS_GAME_DIR': str(game)}):
            self.assertEqual(bank_evidence.probe_targets(mod, [name]), {'10916'})

    def test_broad_reencoding_does_not_assign_every_owner(self):
        game = self.root / 'Desktop'; mod = self.root / 'mod'
        game.mkdir(); mod.mkdir()
        name = 'Voice_Default_S7_4.assets.bank'
        samples = [('battle_s1_10916_1', 32000, 1), ('battle_s1_10109_1', 32000, 2)]
        (game / name).write_bytes(bank(samples))
        (mod / name).write_bytes(bank([(samples[0][0], 48000, 9), (samples[1][0], 32000, 8)]))
        with patch.dict(os.environ, {'LIMBUS_GAME_DIR': str(game)}):
            self.assertEqual(bank_evidence.probe_targets(mod, [name]), {'10916'})

    def test_reimport_restores_missing_and_corrupt_files(self):
        archive = self.root / 'voice.zip'
        original = bank([('battle_s1_10916_1', 32000, 7)])
        with ZipFile(archive, 'w') as z:
            z.writestr('custom.bank', original)
        record = bank_mod.import_banks(archive, self.root)
        target = self.library / record['revision'] / 'custom.bank'
        for damaged in (None, b'broken'):
            if damaged is None: target.unlink()
            else: target.write_bytes(damaged)
            again = bank_mod.import_banks(archive, self.root)
            self.assertEqual(again['status'], 'updated')
            self.assertEqual(target.read_bytes(), original)

    def test_runtime_notification_changes_after_import(self):
        voice_binding.signal_runtime(self.root)
        revision = self.library / 'runtime-revision'
        first = revision.read_bytes()
        voice_binding.signal_runtime(self.root)
        self.assertNotEqual(first, revision.read_bytes())


if __name__ == '__main__':
    unittest.main()
