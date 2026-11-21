"""Acceptance run for three appearances against the local game resources.

Output goes to stdout as one JSON document plus a short human table. Nothing is
written outside --out, so it is safe to run on a copied workbench directory.

    python run_acceptance.py --out DIR [--identity 10101 ...]
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import _module_paths

import effect_timelines
import resource_catalog


def describe(identity, roots):
    lookup = effect_timelines.lookup(identity, roots)
    row = {'requested': identity, 'status': lookup['status'],
           'appearance': lookup.get('appearance'), 'resolved_by': lookup.get('resolved_by'),
           'reason': lookup.get('reason'), 'notice': lookup.get('notice'),
           'records': len(lookup.get('records') or [])}
    index, how = resource_catalog.load_index(roots['index_dir'], roots['resource_root'], auto_build=False)
    table = resource_catalog.appearance_table(index)
    row['bundle'] = table.get(lookup.get('appearance') or '') if lookup.get('appearance') else None
    row['index_source'] = how
    if lookup['status'] == 'ok':
        samples = []
        for record in (lookup.get('records') or [])[:6]:
            samples.append({'detail': record.get('detail'), 'index': record.get('index'),
                            'name': record.get('name'), 'path_id': record.get('path_id'),
                            'bundle_path': record.get('bundle'), 'status': record.get('status'),
                            'tracks': len(record.get('tracks') or [])})
        row['sample_records'] = samples
        details = sorted({r.get('detail') for r in (lookup.get('records') or []) if r.get('detail') is not None})
        row['details'] = details
        row['motions'] = sum(1 for d in details)
    return row, lookup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='')
    parser.add_argument('--identity', action='append', default=[])
    parser.add_argument('--live', action='store_true', help='also read bundles for one appearance')
    args = parser.parse_args()
    roots = resource_catalog.resolve_roots()
    identities = args.identity or ['10101', 'story_1079', '400001_JiashichunAppearance']
    rows = []
    for identity in identities:
        row, _ = describe(identity, roots)
        rows.append(row)
    unknown = effect_timelines.unknown_report(roots)
    document = {'roots': {k: str(roots.get(k)) for k in
                          ('game_dir', 'resource_root', 'index_dir', 'timeline_dir')},
                'rows': rows, 'audited_unknown': unknown}
    if args.live:
        for identity in identities[:1]:
            live = effect_timelines.start(identity)
            document.setdefault('live', {})[identity] = live
    print(json.dumps(document, ensure_ascii=False, indent=1))
    if args.out:
        path = pathlib.Path(args.out)
        path.mkdir(parents=True, exist_ok=True)
        (path / 'acceptance.json').write_text(json.dumps(document, ensure_ascii=False, indent=1),
                                              encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
