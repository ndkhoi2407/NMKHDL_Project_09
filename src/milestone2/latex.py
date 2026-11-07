"""Offline, best-effort LaTeX compilation-path and semantic hierarchy parser.

Does not execute LaTeX commands and never modifies Milestone 1 source files.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import re

DOCUMENT_CLASS = re.compile(r"\\documentclass\s*(?:\[[^\]]*\]\s*)?\{", re.I)
BEGIN_DOCUMENT = re.compile(r"\\begin\s*\{document\}")
PLAIN_BYE = re.compile(r"\\bye\b\s*\Z")
PLAIN_TITLE = re.compile(r"(?m)^[ \t]*\\centerline\s*\{")
PLAIN_SECTION = re.compile(r"\\newsec\s*\{([^{}]*)\}")
PLAIN_REFERENCES = re.compile(r"\\centerline\s*\{\s*\\bf\s+references\s*\}", re.I)
INCLUDE = re.compile(r"\\(?:input|include)\s*(?:\{([^{}]+)\}|([^\s%{}]+))")
HEADING = re.compile(r"\\(chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?\s*(?:\[[^\]]*\]\s*)?\{", re.I)
ENV_BLOCK = re.compile(r"\\begin\s*\{(equation\*?|align\*?|gather\*?|multline\*?|eqnarray\*?|displaymath|figure\*?|table\*?)\}(.*?)\\end\s*\{\1\}", re.S | re.I)
DISPLAY_MATH = re.compile(r"\\\[(.*?)\\\]|(?<!\\)\$\$(.*?)(?<!\\)\$\$", re.S)
LIST_EVENT = re.compile(r"\\(begin|end)\s*\{(itemize|enumerate|description)\}|\\item(?:\s*\[[^]]*\])?", re.I)
CITE = re.compile(r"\\(cite\w*|nocite)\s*(\[[^\]]*\]\s*)*\{([^{}]+)\}")
PLACEHOLDER = re.compile(r"⟦M2BLOCK(\d+)⟧")
ABBREVIATIONS = ('e.g.', 'i.e.', 'et al.', 'fig.', 'figs.', 'eq.', 'eqs.', 'vs.',
                 'cf.', 'dr.', 'mr.', 'mrs.', 'prof.', 'approx.', 'etc.', 'ref.', 'no.')
LEVELS = {'chapter': 1, 'section': 2, 'subsection': 3, 'subsubsection': 4,
          'paragraph': 5, 'subparagraph': 6}


@dataclass
class Node:
    kind: str
    content: str
    children: list['Node'] = field(default_factory=list)


def strip_comments(source: str) -> str:
    """Remove unescaped % comments, but preserve newlines and escaped percent signs."""
    lines = []
    for line in source.splitlines(keepends=True):
        for i, char in enumerate(line):
            if char == '%':
                before = line[:i]
                escapes = len(before) - len(before.rstrip('\\'))
                if escapes % 2 == 0:
                    line = before + ('\n' if line.endswith('\n') else '')
                    break
        lines.append(line)
    return ''.join(lines)


def brace_body(text: str, open_at: int) -> tuple[str, int]:
    """Return balanced brace content and position after closing brace."""
    if open_at >= len(text) or text[open_at] != '{':
        return '', open_at
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == '{' and not _escaped(text, i):
            depth += 1
        elif text[i] == '}' and not _escaped(text, i):
            depth -= 1
            if depth == 0:
                return text[open_at + 1:i], i + 1
    return text[open_at + 1:], len(text)


def _escaped(text: str, pos: int) -> bool:
    j = pos - 1
    while j >= 0 and text[j] == '\\':
        j -= 1
    return (pos - j - 1) % 2 == 1


def _safe_resolve(root: Path, current: Path, ref: str) -> Path | None:
    ref = ref.strip().replace('\\', '/')
    if not ref or ref.startswith('/') or ':' in ref or '\x00' in ref:
        return None
    try:
        p = (current.parent / (ref if ref.lower().endswith('.tex') else ref + '.tex')).resolve()
        p.relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return p if p.is_file() and p.suffix.lower() == '.tex' else None


@dataclass
class Gathered:
    source: str
    files: list[str]
    root: str | None
    warnings: list[str]


def gather(source_dir: Path, max_file_bytes: int = 20_000_000) -> Gathered:
    """Identify document root and transitively inline reachable \\input/\\include files."""
    source_dir = source_dir.resolve()
    files = sorted(p for p in source_dir.rglob('*') if p.is_file() and p.suffix.lower() == '.tex')
    if not files:
        return Gathered('', [], None, ['no_tex_files'])
    clean_cache: dict[Path, str] = {}
    warnings: list[str] = []

    def load(p: Path) -> str:
        if p not in clean_cache:
            if p.stat().st_size > max_file_bytes:
                warnings.append('file_too_large:' + p.relative_to(source_dir).as_posix())
                clean_cache[p] = ''
            else:
                clean_cache[p] = strip_comments(p.read_text(encoding='utf-8', errors='replace'))
        return clean_cache[p]

    candidates = [p for p in files if DOCUMENT_CLASS.search(load(p))]
    plain_mode = False
    if not candidates:
        candidates = [p for p in files if PLAIN_BYE.search(load(p))]
        if not candidates:
            return Gathered('', [], None, ['no_documentclass_or_plaintex_root'] + warnings)
        plain_mode = True
        warnings.append('plain_tex_fallback')

    def score(p: Path) -> tuple[int, int, int, int]:
        t = load(p)
        return (int(bool(BEGIN_DOCUMENT.search(t))),
                int(p.stem.lower() in {'main', 'paper', 'manuscript', 'article'}),
                len(INCLUDE.findall(t)), len(t))

    main = max(candidates, key=score)
    used: list[str] = []
    seen: set[Path] = set()

    def expand(p: Path, stack: set[Path]) -> str:
        if p in stack:
            warnings.append('include_cycle:' + p.relative_to(source_dir).as_posix())
            return ''
        if p not in seen:
            seen.add(p)
            used.append(p.relative_to(source_dir).as_posix())
        t = load(p)
        if plain_mode and p == main:
            first_title = PLAIN_TITLE.search(t)
            if first_title:
                t = t[first_title.start():]
            else:
                warnings.append('plain_tex_body_boundary_uncertain')
        def replace(match: re.Match) -> str:
            target = _safe_resolve(source_dir, p, match.group(1) or match.group(2))
            if target is None:
                warnings.append('missing_include:' + (match.group(1) or match.group(2)))
                return ' '
            return '\n' + expand(target, stack | {p}) + '\n'
        return INCLUDE.sub(replace, t)

    expanded = expand(main, set())
    if plain_mode:
        end = PLAIN_BYE.search(expanded)
        if end:
            expanded = expanded[:end.start()]
        expanded = PLAIN_SECTION.sub(lambda m: r'\section{' + m.group(1) + '}', expanded)
        expanded = PLAIN_REFERENCES.sub(lambda _: r'\section*{References}', expanded)
    else:
        m = BEGIN_DOCUMENT.search(expanded)
        if m:
            expanded = expanded[m.end():]
        else:
            warnings.append('no_begin_document')
        stop = re.search(r'\\end\s*\{document\}', expanded)
        if stop:
            expanded = expanded[:stop.start()]
    return Gathered(expanded, used, main.relative_to(source_dir).as_posix(), warnings)


def normalize_math(text: str) -> str:
    text = re.sub(r'\\\((.*?)\\\)', lambda m: '$' + m.group(1).strip() + '$', text, flags=re.S)
    text = re.sub(r'\\begin\{math\}(.*?)\\end\{math\}', lambda m: '$' + m.group(1).strip() + '$', text, flags=re.S)
    return text


def clean_text(text: str) -> str:
    """Normalize meaningful prose without evaluating unsafe/unrecognized macros."""
    text = normalize_math(text)
    text = re.sub(r'\\(?:centering|midrule|toprule|bottomrule|hline|newpage|clearpage|par|noindent|smallskip|medskip|bigskip)\b', ' ', text)
    text = re.sub(r'\\(?:label|vspace\*?|hspace\*?|setlength|addtolength)\s*\{[^{}]*\}', ' ', text)
    text = re.sub(r'\\(?:vspace|hspace)\*?\s*\[[^\]]*\]', ' ', text)
    text = re.sub(r'(?<!\\)~', ' ', text)
    text = re.sub(r'\\(?:textbf|textit|texttt|emph|underline|textsc|mathrm|textrm|mbox|text|textsf)\s*\{([^{}]*)\}', r'\1', text)
    text = re.sub(r'\\(?:begin|end)\s*\{(?:abstract|center|flushleft|flushright|quote|quotation)\}', ' ', text)
    text = re.sub(r'\\(?:small|footnotesize|scriptsize|normalsize|large|Large|huge)\b', ' ', text)
    text = re.sub(r'\\(?:\\|newline)\s*', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip(' \t\n')


def update_citations(text: str, aliases: dict[str, str]) -> str:
    def replace(m: re.Match) -> str:
        keys = [aliases.get(k.strip(), k.strip()) for k in m.group(3).split(',')]
        keys = list(dict.fromkeys(keys))
        return '\\' + m.group(1) + (m.group(2) or '') + '{' + ','.join(keys) + '}'
    return CITE.sub(replace, text)


def split_sentences(raw: str) -> list[str]:
    """Conservatively split terminal punctuation while protecting inline math/abbreviations."""
    s = clean_text(raw)
    if not s:
        return []
    pieces = []
    start = 0
    math = False
    arg_depth = 0
    i = 0
    while i < len(s):
        c = s[i]
        if c == '$' and not _escaped(s, i):
            math = not math
        if not math:
            if c == '{' and not _escaped(s, i):
                arg_depth += 1
            elif c == '}' and not _escaped(s, i):
                arg_depth = max(arg_depth - 1, 0)
            if c in '.!?' and not arg_depth and not _escaped(s, i):
                nxt = i + 1
                if nxt < len(s) and s[nxt].isspace():
                    low = s[start:i + 1].lower()
                    abbreviation = any(low.endswith(x) for x in ABBREVIATIONS)
                    abbreviation |= bool(re.search(r'\b(?:[A-Za-z]\.){1,4}$', low))
                    # URLs and decimals (decimal dots have no intervening space) are guarded.
                    # A period followed by a lowercase word often ends a figure
                    # reference (Fig. 1. is ...) rather than a sentence.
                    k = nxt
                    while k < len(s) and s[k].isspace():
                        k += 1
                    if k < len(s) and s[k].islower():
                        abbreviation = True
                    if not abbreviation and nxt < len(s) - 1:
                        phrase = s[start:i + 1].strip()
                        if phrase:
                            pieces.append(phrase)
                            start = nxt + 1
        i += 1
    tail = s[start:].strip()
    if tail:
        pieces.append(tail)
    return pieces


def _remove_bibliography(text: str) -> str:
    # Remove entire bibliography environment regardless of heading position.
    text = re.sub(r'\\begin\s*\{thebibliography\}(?:\[[^]]*\]|\{[^{}]*\})?.*?\\end\s*\{thebibliography\}', ' ', text, flags=re.S)
    text = re.sub(r'\\(?:bibliography|bibliographystyle|printbibliography|addbibresource)\s*(?:\[[^]]*\])?\s*\{[^{}]*\}', ' ', text)
    # Exclude a standalone references section until any subsequent appendix/acknowledgements.
    pat = re.compile(r'\\(?:chapter|section)\*?\s*\{\s*(?:references|bibliography|works cited)\s*\}', re.I)
    hit = pat.search(text)
    if hit:
        tail = re.search(r'\\appendix\b|\\(?:chapter|section)\*?\s*\{\s*(?:acknowledg\w*|appendix\w*)\b', text[hit.end():], re.I)
        if tail:
            text = text[:hit.start()] + '\n' + text[hit.end() + tail.start():]
        else:
            text = text[:hit.start()]
    return text


def _blocks(text: str) -> tuple[str, dict[str, tuple[str, str]]]:
    artifacts: dict[str, tuple[str, str]] = {}
    def stash(kind: str, content: str) -> str:
        token = f'⟦M2BLOCK{len(artifacts)}⟧'
        artifacts[token] = (kind, content)
        return '\n' + token + '\n'
    def env_replace(m: re.Match) -> str:
        env = m.group(1).lower()
        if env.startswith(('figure', 'table')):
            content = clean_text(m.group(2))
            # Keep figure's meaningful caption and its file references (if present).
            content = re.sub(r'\\(?:includegraphics|caption|subcaption)\s*(?:\[[^]]*\])?\s*\{([^{}]*)\}', r'\1', content)
            return stash('figure', clean_text(content))
        return stash('formula', '\\begin{equation}' + m.group(2).strip() + '\\end{equation}')
    text = ENV_BLOCK.sub(env_replace, text)
    def math_replace(m: re.Match) -> str:
        return stash('formula', '\\begin{equation}' + ((m.group(1) if m.group(1) is not None else m.group(2)) or '').strip() + '\\end{equation}')
    text = DISPLAY_MATH.sub(math_replace, text)
    return text, artifacts


def parse_hierarchy(source: str, aliases: dict[str, str] | None = None) -> Node:
    """Build document > headings > list/item branches > sentence/formula/figure leaves."""
    source = update_citations(source, aliases or {})
    source = _remove_bibliography(source)
    source, artifacts = _blocks(source)
    root = Node('document', '')
    headings: list[tuple[int, Node]] = []
    lists: list[tuple[Node, Node | None]] = []

    def parent() -> Node:
        if lists:
            return lists[-1][1] or lists[-1][0]
        return headings[-1][1] if headings else root

    def write_prose(s: str) -> None:
        pos = 0
        for m in PLACEHOLDER.finditer(s):
            for phrase in split_sentences(s[pos:m.start()]):
                parent().children.append(Node('sentence', phrase))
            if m.group(0) in artifacts:
                kind, content = artifacts[m.group(0)]
                parent().children.append(Node(kind, content))
            pos = m.end()
        for phrase in split_sentences(s[pos:]):
            parent().children.append(Node('sentence', phrase))

    event = re.compile(r'\\(chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?\s*(?:\[[^\]]*\]\s*)?\{|\\(begin|end)\s*\{(itemize|enumerate|description)\}|\\item(?:\s*\[[^]]*\])?', re.I)
    offset = 0
    for m in event.finditer(source):
        if m.start() < offset:
            continue
        write_prose(source[offset:m.start()])
        if m.group(1):
            title, after = brace_body(source, m.end() - 1)
            name = m.group(1).lower()
            level = LEVELS[name]
            lists.clear()
            while headings and headings[-1][0] >= level:
                headings.pop()
            h = Node('heading', clean_text(title))
            (headings[-1][1] if headings else root).children.append(h)
            headings.append((level, h))
            offset = after
        elif m.group(2):
            if m.group(2).lower() == 'begin':
                group = Node('list', m.group(3).lower())
                parent().children.append(group)
                lists.append((group, None))
            elif lists:
                lists.pop()
            offset = m.end()
        else:
            if lists:
                group, _ = lists[-1]
                item = Node('item', '')
                group.children.append(item)
                lists[-1] = (group, item)
            offset = m.end()
    write_prose(source[offset:])
    return root


def count_nodes(root: Node) -> Counter:
    c = Counter()
    def visit(node: Node) -> None:
        c[node.kind] += 1
        for child in node.children:
            visit(child)
    visit(root)
    return c
