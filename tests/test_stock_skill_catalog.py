import importlib.util
from pathlib import Path
import unittest


path = Path(__file__).resolve().parents[1] / 'native/tools/build_cosmetic_skill_catalog.py'
spec = importlib.util.spec_from_file_location('stock_skill_catalog', path)
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class SharedStockAppearance(unittest.TestCase):
    def members(self, change=None):
        base = {'id': 101, 'skillTier': 1, 'skillData': [
            {'defType': 'ATTACK', 'skillMotion': 'S1', 'gaksungLevel': 1},
            {'iconID': 91, 'gaksungLevel': 3}]}
        alias = {'id': 201, 'textID': 101, 'skillTier': 1, 'skillData': [
            {'defType': 'ATTACK', 'skillMotion': 'S1', 'iconID': 101, 'gaksungLevel': 1},
            {'iconID': 91, 'gaksungLevel': 3}]}
        rows = [base, alias]
        variants = [{'appearance': 'Shared', 'attributeList': [{'skillId': i, 'number': 1}]}
                    for i in (101, 201)]
        if change:
            change(alias, rows, variants)
        table = catalog.generate({'/static-data/skill/a': {'list': rows},
                                  '/static-data/enemy/a': {'list': variants}}, {}, {})
        return table.split('sr_ui_member_ids[] = {\n')[1].split('};')[0].strip()

    def test_explicit_shared_display(self):
        self.assertEqual(self.members(), '101,')

    def test_shared_exact_id_survives_an_ambiguous_alias(self):
        def add_base_to_variant(alias, rows, variants):
            variants[1]['attributeList'].append({'skillId': 101, 'number': 1})
        self.assertEqual(self.members(add_base_to_variant), '101,')

    def test_incomplete_or_ambiguous_evidence(self):
        for change in (
            lambda a, r, v: a.pop('textID'),
            lambda a, r, v: a.update(nameID=99),
            lambda a, r, v: a['skillData'][1].update(iconID=92),
            lambda a, r, v: a['skillData'][1].update(gaksungLevel=4),
            lambda a, r, v: a['skillData'][0].update(skillMotion='S2'),
            lambda a, r, v: a['skillData'][0].update(defType='GUARD'),
            lambda a, r, v: a.update(skillTier=2),
            lambda a, r, v: v[1]['attributeList'][0].update(number=0),
            lambda a, r, v: v.append({'appearance': 'Shared'}),
            lambda a, r, v: (r.append(dict(a, id=202)), v[1]['attributeList'].append(
                {'skillId': 202, 'number': 1})),
        ):
            with self.subTest(change=change):
                self.assertEqual(self.members(change), '')
