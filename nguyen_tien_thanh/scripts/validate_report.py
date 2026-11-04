"""Check report exports without opening or modifying the original corpus."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import report_utils as ru


def audit():
    m1 = json.loads((ROOT / 'm1_data/summary.json').read_text(encoding='utf-8'))
    m2 = json.loads((ROOT / 'm2_data/summary.json').read_text(encoding='utf-8'))
    p1 = ru.pd.read_csv(ROOT / 'm1_data/papers.csv')
    p2 = ru.pd.read_csv(ROOT / 'm2_data/papers.csv')
    d1, d2 = m1['data'], m2['data']
    checks = []
    def check(name, observed, expected):
        checks.append({'Check': name, 'Observed': observed, 'Expected': expected,
                       'Result': 'PASS' if observed == expected else 'FAIL'})
    check('M1 publication count', len(p1), d1['papers_found'])
    check('M1 version count', int(p1.versions.sum()), d1['versions_total'])
    for status, count in d1['versions_by_status'].items():
        check(f'M1 {status} versions', int(p1[f'versions_{status}'].sum()), count)
    check('M1 successful publications', int(p1.scraped_ok.sum()), d1['papers_scraped_successfully'])
    check('M2 publication count', len(p2), d2['papers_total'])
    check('Same publication IDs across milestones', set(p1.id) == set(p2.id), True)
    for col, key in [('versions', 'versions_total'), ('versions_ok', 'versions_ok'),
                     ('versions_empty', 'versions_empty'), ('versions_failed', 'versions_failed'),
                     ('elements_before_dedup', 'elements_before_dedup'),
                     ('elements_after_dedup', 'elements_after_dedup'),
                     ('bib_before_dedup', 'bib_before_dedup'), ('bib_after_dedup', 'bib_after_dedup')]:
        check(f'M2 {col}', int(p2[col].sum()), d2[key])
    tables = json.loads((ROOT / 'm2_data/tables_stats.json').read_text())
    for name, key in [('elements', 'elements_after_dedup'), ('hierarchy', 'hierarchy_rows'), ('bibtex', 'bib_after_dedup')]:
        check(f'{name} table rows', tables[name]['rows'], d2[key])
    kinds = json.loads((ROOT / 'm2_data/kind_counts.json').read_text())
    check('Element kind counts', sum(kinds.values()), d2['elements_after_dedup'])
    samples = ru.pd.read_csv(ROOT / 'm2_data/samples.csv')
    check('M2 memory sample count', len(samples), m2['memory']['samples'])
    failures = json.loads((ROOT / 'm2_data/failures.json').read_text())
    check('Failed-version evidence', len(failures['failed_versions']), d2['versions_failed'])
    return ru.pd.DataFrame(checks)


def inventory():
    return ru.pd.DataFrame([
        {'Input': p.relative_to(ROOT).as_posix(), 'Bytes': p.stat().st_size,
         'SHA256': hashlib.sha256(p.read_bytes()).hexdigest()}
        for folder in ['m1_data', 'm2_data'] for p in sorted((ROOT / folder).iterdir()) if p.is_file()
    ])


if __name__ == '__main__':
    results = audit()
    print(results.to_string(index=False))
    if (results.Result != 'PASS').any():
        raise SystemExit('Report evidence is inconsistent; inspect the failed checks.')
