"""Run preparation, human-label validation, weak labels, ML and publication output.

CLI entry point: python -m src.milestone3.cli <prepare|train|inspect> ...
Does not modify any existing Milestone 1/2 file.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import random

from .matching import FEATURE_NAMES, candidates, make_features, mrr_at_5, weak_match

LABEL_COLUMNS = ['arxiv_id', 'citation_key', 'label_status', 'groundtruth_arxiv_id',
                 'citation_title', 'suggested_1', 'suggested_2', 'suggested_3',
                 'suggested_4', 'suggested_5', 'heuristic_score']


def load_jsonl(path: Path, chosen: set[str] | None = None) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    with path.open(encoding='utf-8') as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            p = row['arxiv_id']
            if chosen is None or p in chosen:
                grouped[p].append(row)
    return dict(grouped)


def write_csv(path: Path, records: list[dict], columns: list[str] = LABEL_COLUMNS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, columns, extrasaction='ignore')
        w.writeheader()
        w.writerows(records)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def data_paths(root: Path) -> tuple[Path, Path]:
    return root / 'data/milestone2/tables/bibtex.jsonl', root / 'data/tables/references.jsonl'


def prepare(root: Path, output: Path, members: int, manual_per_member: int, seed: int,
            auto_max_bib: int = 150) -> dict:
    """Select manually reviewable publications, weak-label >=10% of remaining papers.

Manual CSV has *unreviewed* entries, never fabricated true labels.
    """
    bibfile, reffile = data_paths(root)
    refs = load_jsonl(reffile)
    count = Counter()
    with bibfile.open(encoding='utf-8') as f:
        for line in f:
            if line.strip():
                count[json.loads(line)['arxiv_id']] += 1
    all_papers = sorted({f'2607.{i:05d}' for i in range(13694, 18694)})
    manual_n = 5 * members
    min_entries = 20
    eligible_manual = [p for p in all_papers if 20 <= count[p] <= 100 and len(refs.get(p, [])) >= 8]
    if len(eligible_manual) < manual_n:
        raise ValueError(f'Only {len(eligible_manual)} manual candidates, required {manual_n}')
    rng = random.Random(seed)
    rng.shuffle(eligible_manual)
    manual = sorted(eligible_manual[:manual_n])
    remaining = set(all_papers) - set(manual)
    required_auto = max(math.ceil(.10 * len(remaining)), 2 * members)
    eligible_auto = [p for p in sorted(remaining)
                     if 1 <= count[p] <= auto_max_bib and 1 <= len(refs.get(p, [])) <= 100]
    if len(eligible_auto) < required_auto:
        raise ValueError(f'Only {len(eligible_auto)} automatic candidates; need {required_auto}')
    rng.shuffle(eligible_auto)
    auto = sorted(eligible_auto[:required_auto])
    selected = set(manual) | set(auto)
    bib = load_jsonl(bibfile, selected)
    output.mkdir(parents=True, exist_ok=True)
    manual_rows = []
    auto_rows = []
    for p in manual:
        for e in bib[p][:manual_per_member]:
            scored = candidates(e, refs.get(p, []))
            best = [r['ref_arxiv_id'] for r, _, _ in scored[:5]]
            row = {'arxiv_id': p, 'citation_key': e['citation_key'], 'label_status': 'unreviewed',
                   'groundtruth_arxiv_id': '', 'citation_title': str(e.get('title') or '')[:500],
                   'heuristic_score': round(scored[0][2], 6) if scored else 0.0}
            row.update({f'suggested_{j}': best[j-1] if j <= len(best) else '' for j in range(1, 6)})
            manual_rows.append(row)
    for i, p in enumerate(auto, 1):
        for e in bib[p]:
            match, score, ranked = weak_match(e, refs.get(p, []))
            row = {'arxiv_id': p, 'citation_key': e['citation_key'],
                   'label_status': 'auto_matched' if match else 'auto_none',
                   'groundtruth_arxiv_id': match or '',
                   'citation_title': str(e.get('title') or '')[:500],
                   'heuristic_score': round(score, 6)}
            row.update({f'suggested_{j}': ranked[j-1] if j <= len(ranked) else '' for j in range(1, 6)})
            auto_rows.append(row)
        if i % 50 == 0:
            print(f'AUTO LABEL {i}/{len(auto)} | rows={len(auto_rows)}', flush=True)
    write_csv(output / 'manual_labels_TEMPLATE.csv', manual_rows)
    write_csv(output / 'automatic_labels.csv', auto_rows)
    info = {'member_count_assumed': members, 'manual_publications_selected': len(manual),
            'manual_entries_pending_review': len(manual_rows), 'manual_publication_ids': manual,
            'automatic_publications_labeled': len(auto), 'automatic_label_entries': len(auto_rows),
            'auto_matches': sum(bool(x['groundtruth_arxiv_id']) for x in auto_rows),
            'auto_none': sum(not x['groundtruth_arxiv_id'] for x in auto_rows),
            'required_auto_publications': required_auto, 'seed': seed,
            'manual_labeling_complete': False, 'training_complete': False,
            'official_test_mrr_at_5': None,
            'limitations': ['Automatic labels are heuristics, not human ground truth.',
                            'Manual labels must be reviewed and verified by group members.',
                            'Train and final dataset export require verified manual labels.']}
    (output/'preparation_summary.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in info.items() if k != 'manual_publication_ids'}, indent=2))
    return info


def validate_manual(manual: list[dict], bib: dict[str,list[dict]], refs: dict[str,list[dict]], members: int) -> None:
    by_paper: dict[str, set[str]] = defaultdict(set)
    per_key = {(p, r['citation_key']) for p, entries in bib.items() for r in entries}
    ref_ids = {p: {r['ref_arxiv_id'] for r in entries} for p, entries in refs.items()}
    for row in manual:
        p, key = row['arxiv_id'], row['citation_key']
        if (p, key) not in per_key:
            raise ValueError(f'Manual label not in Mile2 bibtex: {p}/{key}')
        if key in by_paper[p]:
            raise ValueError(f'Duplicate manual annotation: {p}/{key}')
        by_paper[p].add(key)
        status = row['label_status'].strip().lower()
        truth = row['groundtruth_arxiv_id'].strip()
        if status not in ('matched','none'):
            raise ValueError(f'Unreviewed/invalid manual label {p}/{key}: {status!r}')
        if status == 'matched' and truth not in ref_ids.get(p, set()):
            raise ValueError(f'Ground truth {truth} is not a crawled arXiv reference of {p}')
        if status == 'none' and truth:
            raise ValueError(f'Label none must have blank groundtruth: {p}/{key}')
    valid_manual = sum(len(keys)>=20 for keys in by_paper.values())
    if valid_manual < 5 * members or len(manual)<100*members:
        raise ValueError(f'Manual labels: {valid_manual} publications >=20 (need {5*members}), '
                         f'{len(manual)} entries (need {100*members})')


def split_groups(manual_papers: list[str], auto_papers: list[str], members: int, seed: int) -> dict[str, str]:
    rng = random.Random(seed)
    manual, auto = sorted(manual_papers), sorted(auto_papers)
    rng.shuffle(manual); rng.shuffle(auto)
    if len(manual) < 5*members or len(auto) < 2*members:
        raise ValueError('Not enough publications for group-level split')
    split = {p:'train' for p in manual+auto}
    for p in manual[:members]+auto[:members]: split[p]='test'
    for p in manual[members:2*members]+auto[members:2*members]: split[p]='valid'
    return split


def train(root: Path, output: Path, members: int, seed: int) -> dict:
    """Train supervised logistic ranker only with explicitly confirmed manual labels.

Weak-labeled data may also contribute to training and auto-only evaluation;
metrics by label origin are disclosed separately.
    """
    preparation_path = output/'preparation_summary.json'
    if not preparation_path.exists():
        raise FileNotFoundError('Run prepare and complete interactive manual review before training.')
    preparation = json.loads(preparation_path.read_text(encoding='utf-8'))
    if preparation.get('manual_labeling_complete') is not True:
        raise ValueError('Complete the human review with verify_manual_mile3.py before training.')

    manual_path = output/'manual_labels_REVIEWED.csv'
    if not manual_path.exists():
        raise FileNotFoundError('Create the authoritative manual_labels_REVIEWED.csv through the manual review workflow first.')
    expected_hash = preparation.get('manual_labels_sha256')
    if not expected_hash or hashlib.sha256(manual_path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError('Reviewed labels differ from the human-confirmed review file; rerun review before training.')

    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    import joblib
    preparation['training_complete'] = False
    preparation['official_test_mrr_at_5'] = None
    preparation_path.write_text(json.dumps(preparation, indent=2) + '\n', encoding='utf-8')

    manual = read_csv(manual_path)
    auto = read_csv(output/'automatic_labels.csv')
    chosen = {x['arxiv_id'] for x in manual+auto}
    bibfile, reffile = data_paths(root)
    bib = load_jsonl(bibfile, chosen)
    refs = load_jsonl(reffile, chosen)
    validate_manual(manual, bib, refs, members)
    # Guard publication membership and missing/incorrect weak annotations.
    assert not ({r['arxiv_id'] for r in manual} & {r['arxiv_id'] for r in auto})
    auto_papers = {r['arxiv_id'] for r in auto}
    expected_auto = max(math.ceil(.10*(5000-len({r['arxiv_id'] for r in manual}))), 2*members)
    if len(auto_papers) < expected_auto:
        raise ValueError(f'Only {len(auto_papers)} automatic papers, need {expected_auto}')
    for row in auto:
        if row['label_status'] not in ('auto_matched','auto_none'):
            raise ValueError('Invalid automatic label')
        value = row['groundtruth_arxiv_id']
        if value and value not in {ref['ref_arxiv_id'] for ref in refs.get(row['arxiv_id'],[])}:
            raise ValueError('Automatic label points to another paper reference pool')
    manual_papers = {r['arxiv_id'] for r in manual}
    split = split_groups(list(manual_papers), list(auto_papers), members, seed)
    origin = {p:('manual' if p in manual_papers else 'automatic') for p in split}
    by_key = {(p, e['citation_key']):e for p,es in bib.items() for e in es}
    data = {'train': [[],[]], 'valid':[[],[]], 'test':[[],[]]}
    # Full candidate matrix is constructed for *every labeled entry*.
    count_rows = Counter()
    for row in manual+auto:
        p, key, truth = row['arxiv_id'], row['citation_key'], row['groundtruth_arxiv_id'].strip()
        e = by_key[p,key]
        dest = split[p]
        for ref in refs.get(p, []):
            feature = make_features(e, ref)
            label = int(bool(truth) and truth == ref['ref_arxiv_id'])
            data[dest][0].append(feature)
            data[dest][1].append(label)
            count_rows[dest] += 1
    X, y = data['train']
    if not X or len(set(y)) < 2:
        raise ValueError('Need both positive and negative TRAIN candidate pairs; inspect manual/auto matches.')
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=350, class_weight='balanced', random_state=seed))
    model.fit(np.asarray(X), np.asarray(y))
    def make_predictions(rows: list[dict]) -> list[dict]:
        predictions = []
        for idx, row in enumerate(rows, 1):
            p,key,truth = row['arxiv_id'],row['citation_key'],row['groundtruth_arxiv_id'].strip()
            reference_list = refs.get(p, [])
            feature = [make_features(by_key[p,key], ref) for ref in reference_list]
            probabilities = model.predict_proba(np.asarray(feature))[:,1] if feature else []
            order = sorted(range(len(reference_list)),key=lambda k:(-probabilities[k],reference_list[k]['ref_arxiv_id']))[:5]
            record = {'arxiv_id':p, 'partition':split[p], 'citation_key':key,
                      'groundtruth_arxiv_id':truth or None}
            record.update({f'cand_{j}':reference_list[order[j-1]]['ref_arxiv_id'] if j<=len(order) else None for j in range(1,6)})
            predictions.append(record)
        return predictions
    predictions = make_predictions(manual+auto)
    results = {}
    for part in ('train','valid','test'):
        for kind in ('manual','automatic'):
            subset = [r for r in predictions if r['partition']==part and origin[r['arxiv_id']]==kind]
            results[f'{part}_{kind}'] = {'publications':len({r['arxiv_id'] for r in subset}),
                                          'entries':len(subset), 'mrr_at_5':mrr_at_5(subset)}
    output.mkdir(exist_ok=True, parents=True)
    with (output/'predictions.jsonl').open('w', encoding='utf-8') as f:
        for r in predictions:
            f.write(json.dumps(r,ensure_ascii=False)+'\n')
    joblib.dump(model, output/'ranking_model.joblib')
    summary = {'status':'trained_with_manual_and_weak_auto_labels', 'team_members':members,
               'manual_publications':len(manual_papers), 'auto_publications':len(auto_papers),
               'manual_entries':len(manual), 'automatic_entries':len(auto), 'prediction_rows':len(predictions),
               'candidate_matrix_rows':dict(count_rows),'feature_names':FEATURE_NAMES,
               'evaluation':results,
               'caveat':'Automatic labels are weak pseudo-ground-truth, not human-verified. Test manual and automatic scores are separate.'}
    (output/'training_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    test_manual = results['test_manual']
    test_automatic = results['test_automatic']
    test_entries = test_manual['entries'] + test_automatic['entries']
    preparation['training_complete'] = True
    preparation['official_test_mrr_at_5'] = (
        (test_manual['mrr_at_5'] * test_manual['entries']
         + test_automatic['mrr_at_5'] * test_automatic['entries']) / test_entries
        if test_entries else None
    )
    preparation_path.write_text(json.dumps(preparation, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary,indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description='Milestone 3 reference matching / human labeling / MRR@5')
    parser.add_argument('action', choices=['prepare','train','inspect'])
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--output', type=Path, default=Path('data/milestone3'))
    parser.add_argument('--members', type=int, default=1, help='Actual group size; REQUIRED before submission')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--manual-entries-per-paper', type=int, default=20)
    args=parser.parse_args()
    if args.members < 1 or args.manual_entries_per_paper < 20:
        parser.error('--members >= 1 and --manual-entries-per-paper >= 20 required')
    if args.action == 'prepare':
        prepare(args.root, args.output, args.members, args.manual_entries_per_paper,args.seed)
    elif args.action == 'train':
        train(args.root, args.output, args.members,args.seed)
    else:
        for name in ('preparation_summary.json','training_summary.json'):
            p=args.output/name
            print(p, p.read_text(encoding='utf-8') if p.exists() else 'NOT CREATED')


if __name__=='__main__':
    main()
