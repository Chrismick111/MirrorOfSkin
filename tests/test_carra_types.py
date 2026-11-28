import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))
import _module_paths
from carra_import import _recover_types, _read_layout, _script_key
from UnityPy.helpers.UnityVersion import UnityVersion


def asset(*libraries):
    return NS(externals=[NS(path=name, guid=b'guid', type=0) for name in libraries],
              types=[], objects={}, script_types=[], header=NS(version=22), reader=NS(endian='<'),
              unity_version='6000.3.0f1', version=UnityVersion.from_str('6000.3.0f1'),
              _m_target_platform=19, _enable_type_tree=True)


def donor(library):
    file = asset('other', library)
    file.script_types.append(NS(local_serialized_file_index=2, local_identifier_in_file=410))
    file.types.append(NS(class_id=114, node='author-script', is_stripped_type=False,
                         type_dependencies=(), script_type_index=0))
    return file


def body(pid=410):
    return bytes(16) + struct.pack('<iq', 1, pid) + bytes(4)


class CarraTypeTests(unittest.TestCase):
    def layouts(self, decode):
        def read(node, data, target, *, complete=True):
            if not complete:
                return _read_layout(node, data, target, complete=False)
            return decode(node, data, target)
        return patch('carra_import._read_layout', side_effect=read)

    def test_second_layout_of_same_script_can_match(self):
        target = asset('scripts')
        first, second = donor('scripts'), donor('scripts')
        first.types[0].node = 'older-layout'
        def read(node, *args, **kwargs):
            if node == 'older-layout':
                raise ValueError('wrong size')
            return {'m_Script': {'m_FileID': 1, 'm_PathID': 410}}
        with self.layouts(read):
            actual = _recover_types(target, {504: [(123, body())]}, [first, second])
        self.assertEqual(actual, {504: 0})
        self.assertEqual(target.types[0].node, 'author-script')

    def test_sparse_type_and_external_indices_remap_without_padding(self):
        target = asset('scripts')
        native = donor('scripts')
        tree = {'m_Script': {'m_FileID': 1, 'm_PathID': 410}}
        decode = Mock(return_value=tree)
        with self.layouts(decode):
            result = _recover_types(target, {87: [(2, body()), (3, body())]}, [donor('wrong'), native])
        self.assertEqual(result, {87: 0})
        self.assertEqual(len(target.types), 1)
        self.assertEqual(target.script_types[0].local_serialized_file_index, 1)
        self.assertEqual(native.script_types[0].local_serialized_file_index, 2)
        self.assertEqual(decode.call_count, 2)

    def test_mixed_scripts_and_missing_libraries_do_not_guess(self):
        with self.assertRaisesRegex(ValueError, '一致的脚本引用'):
            _recover_types(asset('scripts'), {84: [(1, body()), (2, body(411))]}, [])
        with self.assertRaisesRegex(ValueError, '缺少匹配'):
            _recover_types(asset('scripts'), {84: [(1, body())]}, [donor('wrong')])

    def test_incompatible_object_never_installs_a_type(self):
        target = asset('scripts')
        with self.layouts(Mock(side_effect=ValueError('wrong size'))):
            with self.assertRaisesRegex(ValueError, '对象 77'):
                _recover_types(target, {84: [(77, body())]}, [donor('scripts')])
        self.assertEqual(target.types, [])
        self.assertEqual(target.script_types, [])

    def test_no_partial_registration_when_later_script_is_missing(self):
        target = asset('scripts')
        slots = {107: [(12, body())], 932: [(15, body(420))]}
        tree = {'m_Script': {'m_FileID': 1, 'm_PathID': 410}}
        with self.layouts(Mock(return_value=tree)):
            with self.assertRaisesRegex(ValueError, '932'):
                _recover_types(target, slots, [donor('scripts')])
        self.assertEqual((target.types, target.script_types), ([], []))

    def test_two_author_slots_can_reuse_one_definition(self):
        target = asset('scripts')
        tree = {'m_Script': {'m_FileID': 1, 'm_PathID': 410}}
        with self.layouts(Mock(return_value=tree)):
            result = _recover_types(target, {107: [(12, body())], 932: [(15, body())]}, [donor('scripts')])
        self.assertEqual(result, {107: 0, 932: 0})
        self.assertEqual(len(target.types), 1)

    def test_local_script_numbers_are_scoped_to_the_file(self):
        first, second = asset(), asset()
        first.objects = {35: NS(class_id=115), 36: NS(class_id=1)}
        second.objects = {35: NS(class_id=115)}
        self.assertNotEqual(_script_key(first, 0, 35), _script_key(second, 0, 35))
        self.assertIsNone(_script_key(first, 0, 36))
        self.assertIsNone(_script_key(first, 0, 37))
