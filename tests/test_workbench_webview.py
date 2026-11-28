"""Guard the WebView2 window fallback used when pywebview is unavailable."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'MirrorOfSkin' / 'Workbench' / 'ui' / 'open_workbench.ps1'


class WorkbenchWebviewTest(unittest.TestCase):
    def test_window_uses_a_writable_webview2_data_folder(self):
        text = SCRIPT.read_text(encoding='utf-8')
        # WebView2 defaults its user data folder next to powershell.exe under
        # System32, which is not writable and fails with E_ACCESSDENIED.
        self.assertIn("Join-Path $dataRoot 'Workbench\\webview2'", text)
        self.assertIn('CoreWebView2Environment]::CreateAsync($null,$webData,$null)', text)
        self.assertIn('EnsureCoreWebView2Async($wvEnv)', text)

    def test_new_window_event_is_registered_on_core_webview2(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertNotIn('$web.add_NewWindowRequested', text)
        self.assertIn('$web.CoreWebView2.add_NewWindowRequested', text)

    def test_manifest_hash_matches_launcher_script(self):
        manifest = json.loads(
            (ROOT / 'MirrorOfSkin' / 'compatibility.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(
            manifest['package_files']['Workbench/ui/open_workbench.ps1'],
            hashlib.sha256(SCRIPT.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()