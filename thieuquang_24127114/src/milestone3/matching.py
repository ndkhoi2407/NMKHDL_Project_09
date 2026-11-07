"""Deterministic candidate features, conservative weak labeling and supervised ranking.

Only citations and arXiv references from the *same publication* are compared.
No external LLM, pretrained model, API service or hidden online lookup is used.
"""
from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
import math
import re
import unicodedata

_STOP = frozenset('a an the of for in on with by from to and or et al some an as at into via using based study studies new'.split())
_ARXIV = re.compile(r'(?<!\d)(?:arxiv\s*:\s*)?(\d{4}\.\d{4,5})(?:v\d+)?(?!\d)', re.I)
_OLD = re.compile(r'(?:hep-th|hep-ph|astro-ph|cond-mat|math|quant-ph|cs)/\d{7}', re.I)
_DOI = re.compile(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+', re.I)
_TOK = re.compile(r'[a-z0-9]+')
FEATURE_NAMES = (
    'title_token_jaccard', 'title_ref_coverage', 'title_cite_coverage',
    'title_char_similarity', 'bigram_jaccard', 'author_token_overlap',
    'year_agreement', 'year_conflict', 'arxiv_id_exact', 'title_length_ratio',
)


def normalize(value: object) -> str:
    if value is None:
        return ''
    s = str(value)
    s = re.sub(r'\\(?:emph|textbf|textit|em|texttt|url)\b', ' ', s)
    s = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^]]*\])?', ' ', s)
    s = unicodedata.normalize('NFKD', s).lower()
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(_TOK.findall(s))


@lru_cache(maxsize=400_000)
def tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in _TOK.findall(normalize(text)) if t not in _STOP and len(t) > 1)


def bigrams(text: str) -> set[tuple[str, str]]:
    seq = [t for t in _TOK.findall(normalize(text)) if t not in _STOP]
    return set(zip(seq, seq[1:]))


def jaccard(a: set | frozenset, b: set | frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _ids(s: str) -> set[str]:
    return {m.group(1).lower() for m in _ARXIV.finditer(s)} | {x.lower() for x in _OLD.findall(s)}


def _authors(obj: dict, field: str) -> set[str]:
    a = obj.get(field) or []
    if isinstance(a, str):
        a = [a]
    return set().union(*(tokens(str(x)) for x in a)) if a else set()


def make_features(entry: dict, ref: dict) -> tuple[float, ...]:
    raw = str(entry.get('title') or '')
    title = str(ref.get('ref_title') or '')
    a, b = tokens(raw), tokens(title)
    shared = len(a & b)
    length_ratio = min(len(a), len(b)) / max(len(a), len(b)) if a and b else 0.0
    cover_ref = shared / len(b) if b else 0.0
    cover_cite = shared / len(a) if a else 0.0
    # Character similarity is useful primarily for plausible lexical matches.
    char_sim = SequenceMatcher(None, normalize(raw)[:450], normalize(title)[:250], autojunk=False).ratio() if cover_ref >= .2 else 0.0
    first_year = entry.get('year')
    reference_year = str(ref.get('ref_submission_date') or '')[:4]
    y = str(first_year) if first_year else ''
    return (
        jaccard(a, b), cover_ref, cover_cite, char_sim,
        jaccard(bigrams(raw), bigrams(title)) if cover_ref >= .2 else 0.0,
        jaccard(_authors(entry, 'authors'), _authors(ref, 'ref_authors')),
        float(bool(y and reference_year and y == reference_year)),
        float(bool(y and reference_year and y != reference_year)),
        float(str(ref.get('ref_arxiv_id') or '').lower() in _ids(raw + ' ' + str(entry.get('url') or ''))),
        length_ratio,
    )


def heuristic_score(features: tuple[float, ...]) -> float:
    (j, cover, reverse, sim, bigram, author, year, conflict, exact, ratio) = features
    if exact: return 1.0
    return min(0.999, max(.90 * cover * min(1.0, .40 + j + bigram * .3),
                           .56*j + .23*sim + .12*bigram + .09*author + .03*year - .06*conflict,
                           .77*cover + .14*bigram + .07*author + .02*year if cover > .8 else 0))


def candidates(entry: dict, refs: list[dict]) -> list[tuple[dict, tuple[float, ...], float]]:
    scored = [(r, f, heuristic_score(f)) for r in refs if (f := make_features(entry, r)) is not None]
    scored.sort(key=lambda x: (-x[2], str(x[0].get('ref_arxiv_id'))))
    return scored


def weak_match(entry: dict, refs: list[dict], threshold: float = .88, margin: float = .10) -> tuple[str | None, float, list[str]]:
    ranked = candidates(entry, refs)
    top5 = [r['ref_arxiv_id'] for r, _, _ in ranked[:5]]
    if not ranked:
        return None, 0.0, top5
    best, feat, score = ranked[0]
    second = ranked[1][2] if len(ranked) > 1 else 0.0
    confident = bool(feat[8]) or (score >= threshold and score - second >= margin)
    return (best['ref_arxiv_id'] if confident else None), score, top5


def mrr_at_5(rows: list[dict]) -> float:
    """Unmatched ground truth gives 0 by the course's specified convention."""
    if not rows:
        return 0.0
    total = 0.0
    for row in rows:
        truth = row.get('groundtruth_arxiv_id')
        if not truth:
            continue
        for rank in range(1, 6):
            if row.get(f'cand_{rank}') == truth:
                total += 1.0 / rank
                break
    return total / len(rows)
