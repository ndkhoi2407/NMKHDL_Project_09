"""Milestone 2 extension over the unchanged Milestone 1 corpus and metrics API."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import csv
import json
import os
import time

# Existing code is imported, NOT copied/changed.
from src.crawler import (MemorySampler, directory_size, paper_dir, read_json,
                         utc_now, write_json)
from .bibliography import ReferenceStore, collect_references
from .latex import Gathered, Node, count_nodes, gather, parse_hierarchy


class Milestone1CorpusReader:
    """Adapter to Milestone 1's existing on-disk contract and helper functions."""

    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)

    def publication(self, arxiv_id: str) -> tuple[Path, dict]:
        folder = paper_dir(self.data_root, arxiv_id)
        return folder, read_json(folder / 'paper.json', {})

    def source_status(self, folder: Path, version: int) -> dict:
        return read_json(folder / f'v{version}' / 'source_status.json', {})


class Milestone2MemorySampler(MemorySampler):
    """Inheritance from the original Milestone 1 MemorySampler; no monkey-patching."""

    def finish(self):
        stats = super().finish()
        stats['metric_origin'] = 'milestone1.MemorySampler'
        return stats


@dataclass
class PublicationResult:
    elements: list[dict]
    hierarchy: list[dict]
    bibtex: list[dict]
    versions: list[dict]
    metrics: dict


class Milestone2Parser(Milestone1CorpusReader):
    """Inherits the original corpus's storage contract via Milestone1CorpusReader.

    The crawling and report repositories are never written by this class.
    """

    def __init__(self, data_root: Path, parsed_root: Path):
        super().__init__(data_root)
        self.parsed_root = Path(parsed_root)

    def parse_publication(self, arxiv_id: str) -> PublicationResult:
        folder, paper = self.publication(arxiv_id)
        if not paper:
            raise FileNotFoundError(f'Milestone 1 paper.json missing: {folder}')
        if paper.get('status') != 'found':
            return PublicationResult([], [], [], [], {'status': paper.get('status', 'pending'),
                                                       'versions_expected': 0})
        count = int(paper.get('latest_version') or 0)
        if count < 1:
            raise ValueError(f'Invalid Milestone 1 version count: {arxiv_id}')
        bundles: dict[int, Gathered] = {}
        sources: dict[int, Path] = {}
        source_states: dict[int, str] = {}
        refs = ReferenceStore()
        versions: list[dict] = []
        for version in range(1, count + 1):
            status = self.source_status(folder, version)
            state = status.get('status', 'pending')
            source_states[version] = state
            path = folder / f'v{version}' / 'source'
            sources[version] = path
            if state == 'ok':
                data = gather(path)
                bundles[version] = data
                if data.root:
                    refs.add(version, collect_references(path, data.source))
            elif state not in ('no_latex', 'no_source'):
                raise ValueError(f'{arxiv_id}v{version}: Milestone 1 source not verified ({state})')

        elements: list[dict] = []
        edges: list[dict] = []
        lookup: dict[tuple[str, str], str] = {}
        scoped_ids: dict[tuple, str] = {}
        counts = Counter()
        version_records = []
        before_content = 0
        counter = Counter()
        unique_edges: set[tuple[int, str, str]] = set()
        key_prefix = arxiv_id.replace('.', '-').replace('/', '_')

        def register(kind: str, content: str, unique: bool = False) -> str:
            nonlocal before_content
            before_content += 1
            identity = (kind, content)
            if not unique and identity in lookup:
                return lookup[identity]
            counter[kind] += 1
            ident = f'{key_prefix}#{kind[:3]}{counter[kind]}'
            elements.append({'element_id': ident, 'arxiv_id': arxiv_id,
                             'kind': kind, 'content': content})
            if not unique:
                lookup[identity] = ident
            return ident

        def visit(node: Node, version: int, parent_id: str | None, *, is_root: bool = False, lineage: tuple[str, ...] = ()) -> str:
            content = f'Version {version} root' if is_root else node.content
            # Every version root and positional list/item is structurally distinct.
            unique = is_root or node.kind in ('item', 'list')
            candidate = None if unique else lookup.get((node.kind, content))

            if candidate is not None and candidate in lineage:
                # Prevent an element from becoming its own ancestor.
                # Preserve ordinary cross-version deduplication.
                scoped_key = (node.kind, content, lineage[1:])
                eid = scoped_ids.get(scoped_key)

                if eid is None or eid in lineage:
                    eid = register(node.kind, content, unique=True)
                    elements[-1]['structural_exception'] = 'ancestor_identity_collision'
                    scoped_ids[scoped_key] = eid
            else:
                eid = register(node.kind, content, unique=unique)
            if parent_id is not None:
                identity = (version, eid, parent_id)
                if identity not in unique_edges:
                    unique_edges.add(identity)
                    edges.append({'arxiv_id': arxiv_id, 'version': version,
                                  'element_id': eid, 'parent_id': parent_id})
            for child in node.children:
                visit(child, version, eid, lineage=(*lineage, eid))
            return eid

        for version in range(1, count + 1):
            state = source_states[version]
            data = bundles.get(version)
            common = {'arxiv_id': arxiv_id, 'version': version,
                      'source_status': state, 'root_file': data.root if data else None,
                      'files_used': data.files if data else [],
                      'warnings': data.warnings if data else []}
            if state in ('no_latex', 'no_source'):
                common.update(parse_status='empty', root_id=None, node_count=0)
                version_records.append(common)
                counts['versions_empty'] += 1
                continue
            if data is None or not data.root:
                common.update(parse_status='no_root', root_id=None, node_count=0)
                version_records.append(common)
                counts['versions_no_root'] += 1
                continue
            tree = parse_hierarchy(data.source, refs.aliases.get(version, {}))
            node_counts = count_nodes(tree)
            root_id = visit(tree, version, None, is_root=True)
            common.update(parse_status='ok', root_id=root_id,
                          node_count=sum(node_counts.values()), node_kinds=dict(node_counts))
            version_records.append(common)
            counts['versions_parsed'] += 1
            counts['files_compiled'] += len(data.files)

        metrics = {'status': 'ok', 'versions_expected': count, 'counts': dict(counts),
                   'content_before_dedup': before_content,
                   'content_after_dedup': len(elements),
                   'references_before_dedup': refs.before,
                   'references_after_dedup': len(refs.records),
                   'hierarchy_edges': len(edges)}
        for v in version_records:
            v['canonical_citation_keys'] = refs.aliases.get(v['version'], {})
        return PublicationResult(elements, edges,
                                 [{'arxiv_id': arxiv_id, **x} for x in refs.records],
                                 version_records, metrics)

    def _result_folder(self, arxiv_id: str) -> Path:
        return paper_dir(self.parsed_root, arxiv_id)

    def store(self, arxiv_id: str, result: PublicationResult) -> None:
        folder = self._result_folder(arxiv_id)
        folder.mkdir(parents=True, exist_ok=True)
        for name in ('elements', 'hierarchy', 'bibtex', 'versions'):
            path = folder / f'{name}.jsonl'
            temp = folder / f'.{name}.partial'
            with temp.open('w', encoding='utf-8') as fh:
                for obj in getattr(result, name):
                    fh.write(json.dumps(obj, ensure_ascii=False) + '\n')
            os.replace(temp, path)
        write_json(folder / 'metrics.json', result.metrics)
        # Last write is the commit marker so interrupted processes are retryable.
        write_json(folder / 'checkpoint.json', {'status': 'complete', 'at': utc_now(),
                                                 'schema_version': 1})

    def cached(self, arxiv_id: str) -> dict | None:
        folder = self._result_folder(arxiv_id)
        checkpoint = read_json(folder / 'checkpoint.json', {})
        if checkpoint.get('schema_version') != 1 or checkpoint.get('status') != 'complete':
            return None
        if not all((folder / f'{name}.jsonl').is_file()
                   for name in ('elements', 'hierarchy', 'bibtex', 'versions')):
            return None
        return read_json(folder / 'metrics.json', {})


def export_tables(parser: Milestone2Parser, ids: list[str]) -> None:
    table_dir = parser.parsed_root.parent / 'tables'
    table_dir.mkdir(parents=True, exist_ok=True)
    for name in ('elements', 'hierarchy', 'bibtex', 'versions'):
        temp = table_dir / f'.{name}.partial'
        with temp.open('wb') as output:
            for ident in ids:
                if parser.cached(ident) is None:
                    continue
                path = parser._result_folder(ident) / f'{name}.jsonl'
                with path.open('rb') as reader:
                    while chunk := reader.read(1 << 20):
                        output.write(chunk)
        os.replace(temp, table_dir / f'{name}.jsonl')


def run(data_root: Path, ids: list[str], *, parsed_root: Path | None = None,
        force: bool = False, make_tables: bool = True, report_root: Path | None = None) -> dict:
    root = Path(data_root)
    output = Path(parsed_root) if parsed_root else root / 'milestone2'
    # Reject path layouts that could overwrite Milestone 1 records.
    if output.resolve() == root.resolve() or output.resolve() == (root / 'records').resolve():
        raise ValueError('Milestone 2 output must be separate from Milestone 1 data or records')
    parser = Milestone2Parser(root, output / 'records_data')
    timer = time.perf_counter()
    monitor = Milestone2MemorySampler()
    monitor.start()
    stats = Counter()
    records: list[dict] = []
    try:
        for index, arxiv_id in enumerate(ids, 1):
            start = time.perf_counter()
            cached = None if force else parser.cached(arxiv_id)
            if cached is not None:
                metric = cached
                status = 'cached'
                stats['cached'] += 1
            else:
                try:
                    result = parser.parse_publication(arxiv_id)
                    parser.store(arxiv_id, result)
                    metric = result.metrics
                    status = result.metrics['status']
                except Exception as exc:
                    metric = {'status': 'error', 'error': f'{type(exc).__name__}: {exc}'}
                    status = 'error'
                    stats['errors'] += 1
            stats['processed'] += int(status not in ('error',))
            stats['fresh_parsed'] += int(status == 'ok' and cached is None)
                      # Safely extract metric counts
            counts = metric.get("counts")

            if not isinstance(counts, dict):
                counts = {}

            stats["versions_expected"] += int(
                metric.get("versions_expected", 0) or 0
            )

            stats["versions_parsed"] += int(
                counts.get("versions_parsed", 0) or 0
            )

            stats["versions_empty"] += int(
                counts.get("versions_empty", 0) or 0
            )

            stats["versions_no_root"] += int(
                counts.get("versions_no_root", 0) or 0
            )

            for field in (
                "content_before_dedup",
                "content_after_dedup",
                "references_before_dedup",
                "references_after_dedup",
                "hierarchy_edges",
            ):
                stats[field] += int(metric.get(field, 0) or 0)
            row = {'arxiv_id': arxiv_id, 'status': status,
                   'seconds': round(time.perf_counter() - start, 4), **metric}
            records.append(row)
            if index % 100 == 0 or index == len(ids):
                print(f'MILE2 | {index}/{len(ids)} | errors={stats["errors"]} '
                      f'| versions_parsed={stats["versions_parsed"]}', flush=True)
        if make_tables:
            export_tables(parser, ids)
        mem = monitor.finish()
        elapsed = time.perf_counter() - timer
        summary = {'generated_at': utc_now(), 'assigned_count_this_run': len(ids),
                   'assigned_start': ids[0] if ids else None,
                   'assigned_end': ids[-1] if ids else None,
                   'metrics': dict(stats), 'wall_seconds': round(elapsed, 3),
                   'avg_seconds_per_publication': round(elapsed / len(ids), 4) if ids else 0,
                   **mem, 'output_disk_bytes': directory_size(output),
                   'table_exported': make_tables,
                   'benchmark_caveat': ('This invocation reuses per-paper checkpoints; timings must not be mistaken for a cold parsing benchmark.'
                       if stats['cached'] else 'Fresh processing within this invocation; benchmarking requires Colab CPU-only.'),
                   'note': 'Subset runs describe only the selected IDs, not the full 5000-paper corpus.'}
        write_json(output / 'summary.json', summary)
        statuspath = output / 'status.csv'
        statuspath.parent.mkdir(parents=True, exist_ok=True)
        with statuspath.open('w', encoding='utf-8', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=['arxiv_id', 'status', 'seconds',
                'versions_expected', 'versions_parsed', 'versions_empty', 'versions_no_root',
                'content_before_dedup', 'content_after_dedup',
                'references_before_dedup', 'references_after_dedup', 'error'])
            writer.writeheader()
            for r in records:
                writer.writerow({k: (r.get('counts', {}).get(k, 0) if k.startswith('versions_') and k != 'versions_expected' else r.get(k, ''))
                                 for k in writer.fieldnames})
        if report_root:
            dst = Path(report_root) / 'report_data'
            dst.mkdir(parents=True, exist_ok=True)
            write_json(dst / 'milestone2_summary.json', summary)
            (dst / 'milestone2_status.csv').write_bytes(statuspath.read_bytes())
        return summary
    finally:
        # Ensure the sampling thread stops even on keyboard interruption.
        monitor.finish()
