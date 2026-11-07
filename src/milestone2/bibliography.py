"""Per-version BibTeX / \\bibitem extraction with cross-version field union and aliasing."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import re
from .latex import brace_body, clean_text, strip_comments

ENTRY = re.compile(r'@([A-Za-z]+)\s*([\{(])\s*([^,\s]+)\s*,', re.I)
BIBITEM = re.compile(r'\\bibitem\s*(?:\[[^]]*\]\s*)?\{([^{}]+)\}')
BIB_REQUEST = re.compile(r'\\(?:bibliography|addbibresource)\s*(?:\[[^]]*\]\s*)?\{([^{}]+)\}', re.I)
FIELDS = ('title', 'authors', 'year', 'doi', 'journal', 'url')


def _plain(value: str) -> str:
    value = value.strip()
    while len(value) > 1 and ((value[0] == '{' and value[-1] == '}') or
                              (value[0] == '"' and value[-1] == '"')):
        value = value[1:-1].strip()
    value = re.sub(r'\\(?:emph|textbf|textit|url|href)\s*\{([^{}]*)\}', r'\1', value)
    return clean_text(value).strip('{}" ')


def _field_values(body: str) -> dict[str, str]:
    """Split BibTeX field/value pairs without breaking at commas in balanced braces."""
    found: dict[str, str] = {}
    pos = 0
    while pos < len(body):
        match = re.search(r'([A-Za-z_][\w-]*)\s*=\s*', body[pos:])
        if not match:
            break
        key = match.group(1).lower()
        start = pos + match.end()
        if start >= len(body):
            break
        if body[start] == '{':
            val, end = brace_body(body, start)
        elif body[start] == '"':
            end = start + 1
            while end < len(body):
                if body[end] == '"' and body[end - 1] != '\\':
                    break
                end += 1
            val = body[start + 1:end]
            end += 1
        else:
            end = start
            while end < len(body) and body[end] not in ',\n':
                end += 1
            val = body[start:end].strip()
        found[key] = _plain(val)
        pos = end
    return found


def _record(key: str, entry_type: str, fields: dict[str, str]) -> dict:
    author_text = fields.get('author') or fields.get('authors') or ''
    authors = [_plain(a) for a in re.split(r'\s+and\s+', author_text, flags=re.I) if a.strip()]
    year_raw = fields.get('year', '')
    year_match = re.search(r'(?:18|19|20|21)\d{2}', year_raw)
    result = dict(citation_key=key.strip(), entry_type=entry_type.lower(),
                  title=_plain(fields.get('title', '')), authors=authors,
                  year=int(year_match.group()) if year_match else None,
                  doi=_plain(fields.get('doi', '')).removeprefix('https://doi.org/'),
                  journal=_plain(fields.get('journal') or fields.get('booktitle', '')),
                  url=_plain(fields.get('url', '')))
    return result


def parse_bibtex(text: str) -> list[dict]:
    text = strip_comments(text)
    entries = []
    pos = 0
    while match := ENTRY.search(text, pos):
        entry_type, opener, key = match.groups()
        opening_pos = match.start(2)
        close = '}' if opener == '{' else ')'
        depth = 0
        in_quote = False
        end = len(text)
        for i in range(opening_pos, len(text)):
            c = text[i]
            if c == '"' and (i == 0 or text[i - 1] != '\\'):
                in_quote = not in_quote
            if in_quote:
                continue
            if c == opener:
                depth += 1
            elif c == close:
                depth -= 1
                if depth == 0:
                    end = i
                    break
        pos = end + 1
        if entry_type.lower() in ('string', 'preamble', 'comment'):
            continue
        body = text[match.end():end]
        entries.append(_record(key, entry_type, _field_values(body)))
    return entries


def parse_bibitems(source: str) -> list[dict]:
    items = []
    for env in re.finditer(r'\\begin\s*\{thebibliography\}.*?\\end\s*\{thebibliography\}',
                           source, flags=re.S | re.I):
        sub = env.group()
        found = list(BIBITEM.finditer(sub))
        for i, item in enumerate(found):
            description = sub[item.end():found[i + 1].start() if i + 1 < len(found) else sub.find('\\end{thebibliography}')]
            description = clean_text(description)
            year = re.search(r'\b(?:18|19|20|21)\d{2}\b', description)
            doi = re.search(r'(?:doi:|doi\.org/)(10\.\d{4,9}/[^\s,}]+)', description, re.I)
            url = re.search(r'https?://[^\s{}]+', description)
            title = ''
            quoted = re.search(r'[“"`]{1,2}([^"”`]{8,200})[”"\']', description)
            if quoted:
                title = quoted.group(1)
            elif (block := re.search(r'\\newblock\s*(.{8,250}?)(?:\.|\\newblock|$)', description)):
                title = block.group(1)
            else:
                # A deterministic fallback; do not claim this is verified bibliographic metadata.
                title = description[:240]
            items.append(_record(item.group(1), 'misc', {
                'title': title,
                'year': year.group(0) if year else '',
                'doi': doi.group(1) if doi else '',
                'url': url.group(0) if url else '',
            }))
    return items


def collect_references(source_dir: Path, compiled: str) -> list[dict]:
    """Read only bibliography files requested by active compilation path, if any."""
    refs = parse_bibitems(compiled)
    wanted = set()
    for match in BIB_REQUEST.finditer(compiled):
        for name in match.group(1).split(','):
            n = name.strip().replace('\\', '/')
            if n:
                wanted.add(n.lower().removesuffix('.bib'))
    bibs = sorted(p for p in source_dir.rglob('*.bib') if p.is_file())
    if wanted:
        bibs = [p for p in bibs if p.stem.lower() in wanted or p.relative_to(source_dir).as_posix().lower().removesuffix('.bib') in wanted]
    elif len(bibs) > 1:
        # Avoid unrelated template bibliography files in ambiguous multi-bib archives.
        bibs = []
    for bib in bibs:
        refs.extend(parse_bibtex(bib.read_text(encoding='utf-8', errors='replace')))
    return refs


def _identities(item: dict) -> list[str]:
    identities = []
    doi = (item.get('doi') or '').lower().strip()
    if doi:
        identities.append('doi:' + re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi))
    title = re.sub(r'[^\w]+', '', (item.get('title') or '').casefold())
    if len(title) >= 8:
        identities.append('title:' + title)
    return identities


@dataclass
class ReferenceStore:
    """One canonical citation key per reference; union metadata fields across versions."""
    records: list[dict] = field(default_factory=list)
    aliases: dict[int, dict[str, str]] = field(default_factory=lambda: defaultdict(dict))
    _identities: dict[str, int] = field(default_factory=dict)
    _keys: dict[str, int] = field(default_factory=dict)
    before: int = 0

    def add(self, version: int, entries: list[dict]) -> None:
        for ent in entries:
            self.before += 1
            key = ent.get('citation_key', '').strip()
            if not key:
                continue
            identities = _identities(ent)
            index = next((self._identities[x] for x in identities if x in self._identities), None)
            if index is not None and self.records[index].get('doi') and ent.get('doi') and self.records[index]['doi'] != ent['doi']:
                index = None
            if index is None and key in self._keys:
                old = self.records[self._keys[key]]
                # Same key is not sufficient if both have conflicting known titles/DOIs.
                old_ident = set(_identities(old))
                # Same citation key may refer to different papers across versions.
                conflicting_doi = (old.get('doi') and ent.get('doi') and old['doi'] != ent['doi'])
                conflicting_title = (old.get('title') and ent.get('title') and
                                     not old_ident.intersection(identities))
                if not (conflicting_doi or conflicting_title):
                    index = self._keys[key]
            if index is None:
                canonical = key
                number = 2
                while canonical in self._keys:
                    canonical = f'{key}_m2_{number}'
                    number += 1
                row = {name: ent.get(name, [] if name == 'authors' else None) for name in
                       ('citation_key', 'entry_type', *FIELDS)}
                row['citation_key'] = canonical
                index = len(self.records)
                self.records.append(row)
                self._keys[canonical] = index
            else:
                row = self.records[index]
                for field in FIELDS:
                    old, new = row.get(field), ent.get(field)
                    if field == 'authors':
                        row['authors'] = list(dict.fromkeys((old or []) + (new or [])))
                    elif not old and new:
                        row[field] = new
                if (not row.get('entry_type') or row['entry_type'] == 'misc') and ent.get('entry_type'):
                    row['entry_type'] = ent['entry_type']
            for identity in _identities(self.records[index]):
                self._identities.setdefault(identity, index)
            self.aliases[version][key] = self.records[index]['citation_key']
