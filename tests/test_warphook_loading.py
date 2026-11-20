import ast
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


HOST = Path(__file__).resolve().parents[1] / 'addon' / 'scr.py'


class WarpHookLoadingTests(unittest.TestCase):
    def setUp(self):
        self.source = HOST.read_text('utf-8-sig')
        tree = ast.parse(self.source)
        body = [node for node in tree.body
                if getattr(node, 'name', None) in ('inject', 'WarpHookLoadError')]
        self.api = Mock()
        self.modules = Mock(return_value={'sinnersnative-v64.dll': object()})
        self.scope = {'DLL_NAME': 'SinnersNative-v64.dll', 'ROOT': HOST.parent,
                      'modules': self.modules, 'log': Mock()}
        exec(compile(ast.Module(body=body, type_ignores=[]), str(HOST), 'exec'), self.scope)
        self.host = patch.dict(sys.modules, {'warphook': self.api})
        self.host.start()
        self.addCleanup(self.host.stop)

    def test_failure_87_stops_at_host(self):
        self.api.inject_dll.return_value = False, 'winerror=87'
        with self.assertRaisesRegex(RuntimeError, 'winerror=87'):
            self.scope['inject'](123, {})
        self.api.inject_dll.assert_called_once()
        self.modules.assert_not_called()

    def test_existing_module_skips_loading(self):
        self.scope['inject'](123, self.modules.return_value)
        self.api.inject_dll.assert_not_called()

    def test_success_checks_fixed_addon_module(self):
        self.api.inject_dll.return_value = True, ''
        self.scope['inject'](123, {})
        self.api.inject_dll.assert_called_once_with(123, str(HOST.parent / 'SinnersNative-v64.dll'))
        self.modules.assert_called_once_with(123)

    def test_no_private_loader_or_debug_privilege(self):
        for symbol in ('WriteProcessMemory', 'CreateRemoteThread', 'SeDebugPrivilege', 'VirtualAllocEx'):
            with self.subTest(symbol=symbol):
                self.assertFalse(symbol in self.source)


if __name__ == '__main__':
    unittest.main()
