import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import _module_paths
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import custom_pools
import workbench


class Tests(unittest.TestCase):
    def test_empty_custom_pool_is_allowed(self):
        pools = {'101': {'entries': [{'identity_id': '10102', 'weight': 1}]}}
        result = custom_pools.apply_custom_pools(
            pools,
            {'schema': 1, 'characters': {'101': {'enabled': True, 'entries': []}}},
        )
        self.assertEqual(result['101']['entries'], [])

    def test_workbench_accepts_empty_pool(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as tmp:
            root = pathlib.Path(tmp) / 'addon'
            (root / 'Workbench').mkdir(parents=True)
            store = workbench.Store(root)
            store.validate('101', {'enabled': True, 'entries': []}, {'10102'})


if __name__ == '__main__':
    unittest.main()
