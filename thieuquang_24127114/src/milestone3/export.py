"""Strict flat six-table Parquet exporter for the Milestone 3 HF data contract.

Requires `pip install pyarrow`. No uploading or rewriting of upstream tables.
Optional --min-id/--max-id permit **one student's own assigned ID range**.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

TABLES = {
    'papers': ('data/tables/papers.jsonl', ['arxiv_id', 'title', 'authors', 'submission_date', 'revised_dates', 'venue']),
    'references': ('data/tables/references.jsonl', ['arxiv_id', 'ref_arxiv_id', 'ref_title', 'ref_authors', 'ref_submission_date', 'ref_s2_id']),
    'elements': ('data/milestone2/tables/elements.jsonl', ['element_id', 'arxiv_id', 'kind', 'content']),
    'hierarchy': ('data/milestone2/tables/hierarchy.jsonl', ['arxiv_id', 'version', 'element_id', 'parent_id']),
    'bibtex': ('data/milestone2/tables/bibtex.jsonl', ['arxiv_id', 'citation_key', 'entry_type', 'title', 'authors', 'year', 'doi', 'journal', 'url']),
    'predictions': ('data/milestone3/predictions.jsonl', ['arxiv_id', 'partition', 'citation_key', 'groundtruth_arxiv_id', 'cand_1','cand_2','cand_3','cand_4','cand_5']),
}
LIST_COLUMNS = {'authors', 'revised_dates', 'ref_authors'}
INT_COLUMNS = {'year','version'}
NONNULL = {'papers': ['arxiv_id'], 'references':['arxiv_id','ref_arxiv_id'],
           'elements':['element_id','arxiv_id','kind'], 'hierarchy':['arxiv_id','version','element_id','parent_id'],
           'bibtex':['arxiv_id','citation_key','entry_type'],
           'predictions':['arxiv_id','partition','citation_key']}
DICTIONARY_COLUMNS = {'kind', 'entry_type', 'partition'}


def schema_for(table: str):
    import pyarrow as pa
    fields=[]
    for name in TABLES[table][1]:
        kind = (pa.list_(pa.string()) if name in LIST_COLUMNS else
                pa.int32() if name in INT_COLUMNS else
                pa.dictionary(pa.int32(),pa.string()) if name in DICTIONARY_COLUMNS else pa.string())
        fields.append(pa.field(name,kind,nullable=name not in NONNULL[table]))
    return pa.schema(fields)


def validate_row(table: str, original: dict) -> dict:
    fields = TABLES[table][1]
    missing = set(fields) - original.keys()
    if missing:
        raise ValueError(f'{table}: missing columns {sorted(missing)}')
    row = {}
    for field in fields:
        value=original[field]
        if field in LIST_COLUMNS:
            if value is None: value=[]
            if not isinstance(value,list) or not all(isinstance(x,str) for x in value):
                raise ValueError(f'{table}.{field}: expected flat string list')
        elif field in INT_COLUMNS:
            if value in (None,''): value=None
            elif isinstance(value,bool) or not isinstance(value,int):
                raise ValueError(f'{table}.{field}: expected integer or null')
        elif value is not None and not isinstance(value,str):
            raise ValueError(f'{table}.{field}: expected flat string or null')
        if field in NONNULL[table] and value is None:
            raise ValueError(f'{table}.{field} must be non-null')
        if table == 'predictions' and field == 'partition' and value not in ('train','valid','test'):
            raise ValueError(f'invalid split {value!r}')
        row[field]=value
    return row


def in_range(identifier: str, minimum: str|None, maximum: str|None) -> bool:
    # Fixed-width modern arXiv identifiers are lexicographically sortable.
    if minimum and identifier < minimum: return False
    if maximum and identifier > maximum: return False
    return True


def export(root:Path, output:Path, predictions:Path|None=None,
           minimum:str|None=None, maximum:str|None=None, shard_size:int=25_000,
           validate_only:bool=False) -> dict:
    if bool(minimum) != bool(maximum):
        raise ValueError('Specify both --min-id and --max-id for an individual range')
    if minimum and maximum and minimum > maximum:
        raise ValueError('min-id must not be greater than max-id')
    if shard_size < 1:
        raise ValueError('shard_size must be greater than zero')
    preparation_path=root/'data/milestone3/preparation_summary.json'
    preparation=json.loads(preparation_path.read_text(encoding='utf-8')) if preparation_path.exists() else {}
    manual_reviewed=preparation.get('manual_labeling_complete') is True
    training_complete=preparation.get('training_complete') is True
    if not validate_only and not manual_reviewed:
        raise ValueError('Complete and confirm human review before creating the final dataset export.')
    if not validate_only and not training_complete:
        raise ValueError('Retrain the model after manual review before creating the final dataset export.')
    if not validate_only:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as e:
            raise RuntimeError('Install pyarrow: py -m pip install pyarrow') from e
    output.mkdir(parents=True,exist_ok=True)
    summary={}
    for table,(rel,cols) in TABLES.items():
        path=predictions if table=='predictions' and predictions else root/rel
        if not path.exists():
            if table=='predictions':
                raise FileNotFoundError('Train matching model first: predictions.jsonl does not exist')
            raise FileNotFoundError(path)
        dest=output/'data'/table
        if not validate_only and dest.exists():
            for old_shard in dest.glob('part-*.parquet'):
                old_shard.unlink()
        buffer=[]; total=0; shard=0
        def flush():
            nonlocal shard
            if not buffer or validate_only:return
            dest.mkdir(parents=True,exist_ok=True)
            pq.write_table(pa.Table.from_pylist(buffer,schema=schema_for(table)),
                           dest/f'part-{shard:05d}.parquet',compression='zstd')
            shard+=1
            buffer.clear()
        with path.open(encoding='utf-8') as f:
            for lineno,line in enumerate(f,1):
                if not line.strip():continue
                row=json.loads(line)
                if not in_range(row['arxiv_id'],minimum,maximum):continue
                normalized=validate_row(table,row)
                total+=1
                if not validate_only:
                    buffer.append(normalized)
                    if len(buffer)>=shard_size:flush()
        flush()
        summary[table]={'rows':total,'parquet_shards':shard}
        print(f'{table}: {total:,} rows, {shard} Parquet shards',flush=True)
    if not validate_only:
        card=['---','configs:']
        for table in TABLES:
            card += [f'- config_name: {table}', '  data_files:', '  - split: train',f'    path: data/{table}/*.parquet']
        card += [
            '---',
            '',
            '# Individual arXiv Data Science Pipeline Dataset',
            '',
            'This dataset contains the six flat, sharded Parquet tables produced by an individual '
            'Introduction to Data Science project: crawled paper and reference metadata, parsed '
            'document elements and hierarchy, standardized BibTeX, and reference-matching predictions.',
            '',
            '## Scope and provenance',
            '',
            f'- Assigned arXiv ID range: `{minimum}` through `{maximum}`.',
            '- This is one student’s assigned corpus, not a group-wide aggregate.',
            '- `predictions` contains only publications selected for matching train/validation/test splits; '
            'it does not contain predictions for every paper in the corpus.',
            ('- Manual annotations have been manually checked against the source references.'
             if manual_reviewed else
             '- The manual annotations have not been human-verified; labels, predictions, and metrics are provisional.'),
            ('- The model was trained after manual review.'
             if training_complete else
             '- The model has not been retrained after completed manual review.'),
            '- Automatically generated labels are weak heuristic pseudo-labels, not human ground truth.',
            '- Text and metadata are derived from arXiv source material and Semantic Scholar. '
            'Consult the upstream sources for applicable terms and item-level licensing; no blanket '
            'license is asserted for third-party content.',
            '',
            '## Configurations and row counts',
            '',
            '| Configuration | Rows |',
            '|---|---:|',
        ]
        card.extend(f'| `{table}` | {details["rows"]:,} |' for table, details in summary.items())
        card += [
            '',
            'Each configuration is stored as flat Parquet with an explicit schema. Load one table with:',
            '',
            '```python',
            'from datasets import load_dataset',
            'papers = load_dataset("OWNER/DATASET", "papers", split="train")',
            '```',
            '',
            '## Limitations',
            '',
            'The manually reviewed sample is small. Automatic labels can contain errors, and the reported '
            'matching metrics should not be interpreted as generalization to unseen publications. '
            'The `none` label and candidate coverage depend on the references available in the crawled data.',
        ]
        (output/'README.md').write_text('\n'.join(card)+'\n', encoding='utf-8')
    (output/'export_summary.json').write_text(json.dumps({
        'tables':summary,'student_arxiv_min':minimum,'student_arxiv_max':maximum,
        'mode':'validate_only' if validate_only else 'parquet',
        'manual_labeling_complete':manual_reviewed,'training_complete':training_complete,
        'published_online':False},indent=2),encoding='utf-8')
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--output',type=Path,default=Path('data/milestone3/huggingface_dataset'))
    p.add_argument('--predictions',type=Path)
    p.add_argument('--min-id')
    p.add_argument('--max-id')
    p.add_argument('--shard-size',type=int,default=25_000)
    p.add_argument('--validate-only',action='store_true')
    args=p.parse_args()
    if bool(args.min_id) != bool(args.max_id):p.error('specify both --min-id and --max-id')
    if args.min_id and args.max_id and args.min_id>args.max_id:p.error('min-id > max-id')
    export(args.root,args.output,args.predictions,args.min_id,args.max_id,args.shard_size,args.validate_only)

if __name__=='__main__':main()
