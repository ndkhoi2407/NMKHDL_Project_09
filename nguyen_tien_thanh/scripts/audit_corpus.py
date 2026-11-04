"""Read-only corpus inspection; writes only a small audit export, never parses papers."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, default=ROOT / 'audit_data/corpus_audit.json')
    args = ap.parse_args()
    data = ROOT / 'data'
    discovery = load(data / 'discovery.json')['papers']
    downloads = load(data / 'download_status.json')
    spec = importlib.util.spec_from_file_location('arxiv_parser', ROOT / 'src/parse.py')
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    extensions, errors, probes = Counter(), [], []
    metadata, refs = Counter(), Counter()
    metadata_discrepancies = []
    refs.update({k: 0 for k in ['arxiv_rows', 'non_arxiv_rows', 'unclassified_rows', 'legacy_keyed_arxiv_rows']})
    command_files = Counter()
    sampled_tex = 0
    for paper_number, paper in enumerate(discovery, 1):
        folder = data / paper['folder']
        mp, rp = folder / 'metadata.json', folder / 'references.json'
        if mp.exists():
            m = load(mp)
            metadata['files'] += 1
            metadata['title_authors_submission_present'] += bool(m.get('title') and m.get('authors') and m.get('submission_date'))
            metadata['revision_date_count_matches_versions'] += len(m.get('revised_dates', [])) == len(paper['versions'])
            metadata['venue_present'] += bool(m.get('venue'))
            if len(m.get('revised_dates', [])) != len(paper['versions']):
                metadata_discrepancies.append({'paper': paper['id'], 'discovered_versions': len(paper['versions']),
                                               'revision_dates_in_metadata': len(m.get('revised_dates', []))})
        if rp.exists():
            r = load(rp)
            refs['files'] += 1
            refs['empty_files'] += not bool(r)
            refs['rows'] += len(r)
            for key, reference in r.items():
                # Legacy exports use the dictionary key as the arXiv ID and
                # omit the current code's arxiv_id field. Absence alone must
                # not misclassify all legacy records as non-arXiv references.
                legacy_arxiv = bool(re.fullmatch(r'\d{4}[.-]\d{4,5}(?:v\d+)?|[A-Za-z][A-Za-z0-9.-]*/\d{7}(?:v\d+)?', key))
                if reference.get('arxiv_id') or legacy_arxiv:
                    refs['arxiv_rows'] += 1
                    refs['legacy_keyed_arxiv_rows'] += legacy_arxiv and not reference.get('arxiv_id')
                elif 'arxiv_id' in reference or key.startswith(('s2-', 'ref-')):
                    refs['non_arxiv_rows'] += 1
                else:
                    refs['unclassified_rows'] += 1
        for version in paper['versions']:
            key = paper['id'] + version
            info = downloads.get(key, {})
            vdir = folder / version
            if info.get('status') == 'error':
                errors.append({'version': key, 'http': info.get('http'), 'note': info.get('note'),
                               'source_directory_exists': vdir.exists()})
            # os.walk uses scandir metadata and avoids stat() for each file.
            # Extension inventory is complete; command-presence inspection is
            # explicitly a bounded sample, not historical integrity proof.
            for directory, _, filenames in os.walk(vdir):
                for filename in filenames:
                    f = Path(directory) / filename
                    extensions[f.suffix.lower() or '(no extension)'] += 1
                    if f.suffix.lower() == '.tex' and sampled_tex < 25:
                        text = parser.read_text(f)
                        sampled_tex += 1
                        for command in [r'\includegraphics', r'\begin{figure', r'\caption']:
                            command_files[command] += command in text
        if paper['id'] in ('2607.05431', '2607.07654'):
            vdir = folder / 'v1'
            tex = parser.collect_files(vdir, '.tex')
            texts = {k: parser.strip_comments(parser.read_text(p)) for k, p in tex.items()}
            probes.append({'paper': paper['id'], 'recorded_reason': load(folder / 'parsed.json')['versions']['1']['reason'],
                           'current_root_probe': parser.pick_root(texts, tex),
                           'root_with_normalized_line_endings': parser.pick_root(
                               {k: parser.strip_comments(parser.read_text(p).replace('\r\n', '\n').replace('\r', '\n'))
                                for k, p in tex.items()}, tex),
                           'line_endings': {k: {'LF': p.read_bytes().count(b'\n'), 'CR': p.read_bytes().count(b'\r')}
                                            for k, p in tex.items()},
                           'compiler': load(vdir / '00README.json').get('process', {}).get('compiler'),
                           'tex_files': list(tex), 'probe_scope': 'root selection only; no parsing or writes'})
        if paper_number % 500 == 0:
            print(f'Inspected {paper_number}/{len(discovery)} publications', flush=True)
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for name in ['m1_data', 'm2_data'] for p in sorted((ROOT / name).iterdir()) if p.is_file()}
    result = {'scope': 'Local read-only audit; no network, crawling, parsing or corpus writes',
              'source_extensions': dict(extensions.most_common()), 'files_containing_figure_commands': dict(command_files),
              'figure_command_sample': {'tex_files_examined': sampled_tex, 'selection': 'first 25 TeX files encountered in discovery order'},
              'metadata': dict(metadata), 'references': dict(refs), 'download_errors': errors,
              'metadata_version_discrepancies': metadata_discrepancies,
              'root_probes': probes, 'measured_export_sha256': hashes,
              'code_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                              for name in ['src/parse.py', 'src/process_sources.py', 'src/references.py']}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'Saved read-only audit to {args.output}')
    print(json.dumps({'metadata': dict(metadata), 'references': dict(refs),
                      'download_errors': len(errors), 'root_probes': probes}, indent=2))

if __name__ == '__main__':
    main()
