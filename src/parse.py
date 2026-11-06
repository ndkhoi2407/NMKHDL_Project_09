"""Milestone 2 - Phan tich LaTeX thanh cay phan cap, chuan hoa va khu trung.

Voi moi bai trong data/discovery.json:
  1. Gather: voi moi version, tim file goc (co \\documentclass), theo \\input /
     \\include de quy (bo qua lenh bi comment), chi parse file nam tren duong
     bien dich.
  2. Hierarchy: Document -> heading (section/subsection/...) -> sentence /
     equation (block) / figure (ke ca table) / list -> item. Muc heading duoc
     tu suy ra tu cac lenh thuc su dung trong bai. Bo qua phan References,
     giu Acknowledgements va Appendix.
  3. Cleanup: bo \\centering, [htbp], \\midrule, \\label...; toan inline ve $...$,
     toan block ve \\begin{equation}...\\end{equation}.
  4. Reference: \\bibitem -> BibTeX bang regex; doc them cac file .bib; khu trung
     entry (cung noi dung khac key) xuyen cac version, doi ten \\cite{}, hop
     nhat (union) cac truong.
  5. Khu trung noi dung: element giong het nhau (sau cleanup) giua cac version
     chi ghi mot lan, dung chung mot element_id.

Dau ra:
    data/{folder}/parsed.json      elements / hierarchy / bibtex cua bai (3 bang)
    data/parse_status.json         trang thai + thong ke tung bai
    data/tables/*.jsonl            (--export) gop ba bang cho ca corpus

Chay tu thu muc goc project:
    python src/parse.py --limit 5
    python src/parse.py                       # chay tiep duoc, bo qua bai da xong
    python src/parse.py --workers 4 --force
    python src/parse.py --export-only
"""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import signal
import sys
import time
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

sys.setrecursionlimit(5000)

DATA_DIR = Path("data")
DISCOVERY = DATA_DIR / "discovery.json"
DOWNLOAD_STATUS = DATA_DIR / "download_status.json"
STATUS_FILE = DATA_DIR / "parse_status.json"
TABLES_DIR = DATA_DIR / "tables"
PARSED_NAME = "parsed.json"
EMPTY_DL_STATES = {"pdf_only", "other_format", "no_tex"}   # M1: ban ghi rong
MAX_INCLUDE_DEPTH = 20


# ====================================================================== tien ich

def read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def save_json(path: Path, obj, **kw):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, **kw), encoding="utf-8")
    os.replace(tmp, path)


def read_group(text: str, i: int, open_ch: str = "{", close_ch: str = "}"):
    """text[i] == open_ch -> (noi dung ben trong, vi tri sau dau dong). Khong can bang -> (None, i)."""
    depth, j, n = 0, i, len(text)
    while j < n:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
        j += 1
    return None, i


def skip_space(text: str, j: int) -> int:
    while j < len(text) and text[j].isspace():
        j += 1
    return j


def find_env_end(text: str, start: int, name: str):
    """Tim \\end{name} tuong ung (tinh long nhau). Tra ve (vi tri \\end, vi tri sau \\end) hoac None."""
    pat = re.compile(r"\\(begin|end)\{" + re.escape(name) + r"\}")
    depth = 1
    for m in pat.finditer(text, start):
        if m.group(1) == "begin":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return m.start(), m.end()
    return None


# ====================================================================== 1. GATHER

COMMENT_RE = re.compile(r"(?<!\\)((?:\\\\)*)%[^\n]*")
INPUT_RE = re.compile(r"\\(input|include|subfile)(?![A-Za-z@])\s*(?:\{([^{}]*)\}|([^\s{}\\]+))")
BIBLIO_RE = re.compile(r"\\(?:bibliography|addbibresource)(?![A-Za-z])\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}")


def strip_comments(text: str) -> str:
    """Bo comment %... (dau % thoat bang \\% khong tinh) va moi truong comment."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = COMMENT_RE.sub(r"\1", text)
    return re.sub(r"\\begin\{comment\}.*?\\end\{comment\}", "", text, flags=re.S)


def collect_files(vdir: Path, suffix: str) -> dict:
    """{duong_dan_tuong_doi_chu_thuong: Path} cho moi file *suffix duoi vdir."""
    index = {}
    for p in vdir.rglob("*"):
        try:
            if p.is_file() and p.suffix.lower() == suffix:
                index[p.relative_to(vdir).as_posix().lower()] = p
        except OSError:
            continue
    return index


def resolve_name(name: str, cur_dir: str, index: dict, exts=(".tex",)):
    """Tim file duoc \\input / \\bibliography tro toi; tra ve key trong index hoac None."""
    name = name.strip().strip('"').replace("\\", "/")
    if name.startswith("./"):
        name = name[2:]
    if not name:
        return None
    cands = []
    for base in (cur_dir, ""):
        joined = posixpath.normpath(posixpath.join(base, name)).lower()
        cands += [joined] + [joined + e for e in exts]
    for c in cands:
        if c in index:
            return c
    base = posixpath.basename(name).lower()
    for e in ("",) + tuple(exts):
        for k in index:
            if posixpath.basename(k) == base + e:
                return k
    return None


def pick_root(texts: dict, index: dict):
    """File goc: co \\documentclass, khong bi file khac include, uu tien main/paper..."""
    included = set()
    for k, t in texts.items():
        for m in INPUT_RE.finditer(t):
            r = resolve_name(m.group(2) or m.group(3) or "", posixpath.dirname(k), index)
            if r and r != k:
                included.add(r)
    cands = [k for k, t in texts.items() if r"\documentclass" in t]
    if not cands:
        cands = [k for k, t in texts.items() if r"\begin{document}" in t]
    if not cands:
        return None
    prefer = ("main", "paper", "ms", "arxiv", "article", "manuscript")

    def score(k):
        t = texts[k]
        stem = posixpath.splitext(posixpath.basename(k))[0]
        return (r"\begin{document}" in t, k not in included, stem in prefer, len(t))
    return max(cands, key=score)


def expand(key: str, texts: dict, index: dict, stack: tuple, used: set) -> str:
    """Thay moi \\input/\\include (khong bi comment) bang noi dung file, de quy."""
    used.add(key)

    def repl(m):
        target = resolve_name(m.group(2) or m.group(3) or "", posixpath.dirname(key), index)
        if target is None or target in stack or len(stack) >= MAX_INCLUDE_DEPTH:
            return ""
        return "\n" + expand(target, texts, index, stack + (target,), used) + "\n"
    return INPUT_RE.sub(repl, texts[key])


def body_of(text: str) -> str:
    m = re.search(r"\\begin\{document\}", text)
    if m:
        text = text[m.end():]
    j = text.rfind(r"\end{document}")
    return text[:j] if j >= 0 else text


# ====================================================================== 2. CLEANUP

ARG_CMDS = {
    "label": 1, "vspace": 1, "hspace": 1, "thispagestyle": 1, "pagestyle": 1,
    "pagenumbering": 1, "setlength": 2, "addtolength": 2, "setcounter": 2,
    "addtocounter": 2, "usepackage": 2, "documentclass": 2, "bibliographystyle": 1,
    "bibliography": 1, "addbibresource": 2, "graphicspath": 1, "hypersetup": 1,
    "newcommand": 4, "renewcommand": 4, "providecommand": 4, "DeclareRobustCommand": 4,
    "newenvironment": 5, "renewenvironment": 5, "DeclareMathOperator": 2,
    "newtheorem": 3, "theoremstyle": 1, "title": 2, "author": 2, "date": 1,
    "thanks": 1, "affiliation": 2, "institute": 1, "address": 1, "email": 1,
    "keywords": 1, "index": 1, "nocite": 1, "captionsetup": 2, "definecolor": 3,
    "linespread": 1, "geometry": 1,
}
ARG_RE = re.compile(r"\\(%s)(?![A-Za-z])\*?" % "|".join(sorted(ARG_CMDS, key=len, reverse=True)))
DEF_RE = re.compile(r"\\(?:def|gdef|edef)\s*\\[A-Za-z]+(?:#\d)*\s*\{")

BARE_CMDS = [
    "centering", "raggedright", "raggedleft", "noindent", "indent", "smallskip",
    "medskip", "bigskip", "newpage", "clearpage", "cleardoublepage", "pagebreak",
    "linebreak", "nolinebreak", "nopagebreak", "maketitle", "tableofcontents",
    "listoffigures", "listoftables", "appendix", "small", "footnotesize",
    "scriptsize", "tiny", "normalsize", "large", "Large", "LARGE", "huge", "Huge",
    "normalfont", "bfseries", "itshape", "rmfamily", "sffamily", "ttfamily",
    "mdseries", "upshape", "slshape", "scshape", "bf", "it", "rm", "sc", "sf",
    "tt", "em", "sl", "xspace", "protect", "relax", "strut", "midrule", "toprule",
    "bottomrule", "hline", "nonumber", "notag", "hfill", "vfill", "newline",
]
BARE_RE = re.compile(r"\\(?:%s)(?![A-Za-z])" % "|".join(sorted(BARE_CMDS, key=len, reverse=True)))
TABLE_RULE_RE = re.compile(r"\\cmidrule\s*(?:\([^)]*\))?\s*\{[^}]*\}|\\cline\s*\{[^}]*\}")
FMT_RE = re.compile(r"\\(?:textbf|textit|emph|textrm|textsf|texttt|textsc|textsl|textup|"
                    r"textmd|underline|uline|mbox|hbox)\s*\{")
ITEM_LEFTOVER_RE = re.compile(r"\\item(?![A-Za-z])\s*(?:\[[^\]]*\])?")


def remove_arg_cmds(text: str) -> str:
    """Bo cac lenh khong mang y nghia noi dung (\\label, \\vspace, \\newcommand...) cung doi so."""
    text = _remove_defs(text)
    out, pos = [], 0
    while True:
        m = ARG_RE.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        out.append(text[pos:m.start()])
        j = m.end()
        for _ in range(ARG_CMDS[m.group(1)]):
            k = skip_space(text, j)
            if "\n\n" in text[j:k]:
                break
            if k < len(text) and text[k] in "{[":
                g, e = read_group(text, k, text[k], "}" if text[k] == "{" else "]")
                if g is None:
                    break
                j = e
            else:
                break
        pos = j
    return "".join(out)


def _remove_defs(text: str) -> str:
    while True:
        m = DEF_RE.search(text)
        if not m:
            return text
        g, e = read_group(text, m.end() - 1)
        text = text[:m.start()] + (text[e:] if g is not None else text[m.end():])


def clean_common(text: str) -> str:
    text = remove_arg_cmds(text)
    text = TABLE_RULE_RE.sub(" ", text)
    return BARE_RE.sub(" ", text)


def unwrap_formatting(text: str) -> str:
    """\\textbf{x} -> x (giu noi dung, bo dinh dang)."""
    pos = 0
    while True:
        m = FMT_RE.search(text, pos)
        if not m:
            return text
        g, e = read_group(text, m.end() - 1)
        if g is None:
            text = text[:m.start()] + text[m.end():]
        else:
            text = text[:m.start()] + g + text[e:]
        pos = m.start()


def math_spans(text: str):
    """[(start, end, kind)] cho toan inline $...$ va \\(...\\)."""
    spans, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            if text.startswith("\\(", i):
                j = text.find("\\)", i + 2)
                if j != -1:
                    spans.append((i, j + 2, "paren"))
                    i = j + 2
                    continue
            i += 2
            continue
        if c == "$":
            j = i + 1
            while j < n and text[j] != "$":
                j += 2 if text[j] == "\\" else 1
            if j < n:
                spans.append((i, j + 1, "dollar"))
                i = j + 1
                continue
        i += 1
    return spans


def normalize_inline_math(text: str) -> str:
    """Moi toan inline ve dang $...$ (bo khoang trang thua)."""
    out, pos = [], 0
    for a, b, kind in math_spans(text):
        inner = text[a + 2:b - 2] if kind == "paren" else text[a + 1:b - 1]
        out.append(text[pos:a])
        out.append("$" + re.sub(r"\s+", " ", inner.strip()) + "$")
        pos = b
    out.append(text[pos:])
    return "".join(out)


def apply_outside_math(text: str, fn) -> str:
    out, pos = [], 0
    for a, b, _ in math_spans(text):
        out.append(fn(text[pos:a]))
        out.append(text[a:b])
        pos = b
    out.append(fn(text[pos:]))
    return "".join(out)


_LONE_BRACE = re.compile(r"(?<![\\A-Za-z0-9\]\}\*])\{([^{}\\$]*)\}")


def _plain_fix(seg: str) -> str:
    seg = seg.replace("~", " ")
    seg = re.sub(r"\\[ ,;:!]", " ", seg)
    for _ in range(3):
        seg = _LONE_BRACE.sub(r"\1", seg)
    return seg


# ---------------------------------------------------------------- tach cau

ABBREV = {
    "e.g", "i.e", "fig", "figs", "eq", "eqs", "sec", "secs", "sect", "ref", "refs",
    "tab", "tabs", "cf", "vs", "al", "resp", "approx", "no", "nos", "vol", "vols",
    "pp", "p", "dr", "mr", "mrs", "ms", "prof", "st", "ca", "thm", "lem", "prop",
    "cor", "def", "alg", "ch", "app", "eds", "ed", "inc", "ltd", "jr", "sr", "u.s",
    "ph.d", "viz", "ibid",
}
BOUNDARY_RE = re.compile(r"([.!?])([)\]}'\"\u201d\u2019]*)\s+(?=[A-Z\\$\"'\u201c\u2018(\[])")
_MASK = str.maketrans({".": "\x00", "?": "\x01", "!": "\x02"})
_UNMASK = str.maketrans({"\x00": ".", "\x01": "?", "\x02": "!"})


def mask_protected(text: str) -> str:
    """Che dau . ? ! ben trong toan, doi so cua lenh (\\cite, \\url, \\footnote...)."""
    spans = [(a, b) for a, b, _ in math_spans(text)]
    for m in re.finditer(r"\\[A-Za-z]+\*?", text):
        j = m.end()
        while j < len(text) and text[j] in "[{":
            g, e = read_group(text, j, text[j], "}" if text[j] == "{" else "]")
            if g is None:
                break
            spans.append((j, e))
            j = e
    chars = list(text)
    for a, b in spans:
        for k in range(a, b):
            chars[k] = chars[k].translate(_MASK)
    return "".join(chars)


def split_sentences(par: str) -> list:
    if not par:
        return []
    masked = mask_protected(par)
    cuts = [0]
    for m in BOUNDARY_RE.finditer(masked):
        if m.group(1) == ".":
            w = re.search(r"([A-Za-z][A-Za-z.]*)$", masked[:m.start()])
            if w:
                word = w.group(1)
                if word.lower() in ABBREV or (len(word) == 1 and word.isupper()):
                    continue
        cuts.append(m.end())
    pieces = [masked[a:b] for a, b in zip(cuts, cuts[1:] + [len(masked)])]
    return [p.translate(_UNMASK).strip() for p in pieces
            if re.search(r"[A-Za-z0-9]", p)]


def prose_to_sentences(raw: str) -> list:
    t = remove_arg_cmds(raw)
    t = re.sub(r"\\par(?![A-Za-z])", "\n\n", t)
    t = TABLE_RULE_RE.sub(" ", t)
    t = BARE_RE.sub(" ", t)
    t = ITEM_LEFTOVER_RE.sub(" ", t)
    t = unwrap_formatting(t)
    t = re.sub(r"\\\\(?:\[[^\]]*\])?", " ", t)
    t = normalize_inline_math(t)
    t = apply_outside_math(t, _plain_fix)
    out = []
    for par in re.split(r"\n\s*\n", t):
        out.extend(split_sentences(re.sub(r"\s+", " ", par).strip()))
    return out


def clean_title(t: str) -> str:
    t = remove_arg_cmds(t)
    t = BARE_RE.sub(" ", unwrap_formatting(t))
    t = re.sub(r"\\\\(?:\[[^\]]*\])?", " ", t)
    t = apply_outside_math(normalize_inline_math(t), _plain_fix)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------- block

WRAP = {"align": "aligned", "alignat": "aligned", "flalign": "aligned",
        "eqnarray": "aligned", "multline": "aligned", "gather": "gathered"}
MATH_ENVS = {"equation", "displaymath", "align", "alignat", "gather", "multline",
             "eqnarray", "flalign"}
FLOAT_ENVS = {"figure", "table", "wrapfigure", "wraptable", "sidewaysfigure",
              "sidewaystable", "algorithm", "tabular", "tabularx", "longtable",
              "tikzpicture", "verbatim", "lstlisting", "minted"}
LIST_ENVS = {"itemize": "itemize", "enumerate": "enumerate", "description": "description",
             "compactitem": "itemize", "compactenum": "enumerate",
             "asparaitem": "itemize", "inparaenum": "enumerate"}
RANK = {"part": 0, "chapter": 1, "section": 2, "subsection": 3,
        "subsubsection": 4, "paragraph": 5, "subparagraph": 6}
TOKEN_RE = re.compile(
    r"\\begin\{(?P<env>[A-Za-z*]+)\}"
    r"|\\(?P<sec>part|chapter|section|subsection|subsubsection|paragraph|subparagraph)(?![A-Za-z])"
    r"|(?P<dd>\$\$)"
    r"|(?<!\\)(?P<br>\\\[)")
ITEM_RE = re.compile(r"\\(begin|end)\{(?:itemize|enumerate|description|compactitem|"
                     r"compactenum|asparaitem|inparaenum)\*?\}|\\item(?![A-Za-z])")
REF_TITLE_RE = re.compile(r"(?i)\s*(references?|bibliography|literature cited|works cited)\s*[:.]?\s*")


class Node:
    __slots__ = ("kind", "content", "children")

    def __init__(self, kind: str, content: str = ""):
        self.kind, self.content, self.children = kind, content, []


def norm_equation(env: str, inner: str):
    base = env.rstrip("*")
    if base == "alignat":
        k = skip_space(inner, 0)
        if k < len(inner) and inner[k] == "{":
            _, e = read_group(inner, k)
            inner = inner[e:]
    body = re.sub(r"\\label\s*\{[^{}]*\}|\\nonumber(?![A-Za-z])|\\notag(?![A-Za-z])", " ", inner)
    body = re.sub(r"\s+", " ", body).strip()
    body = re.sub(r"(\\\\\s*)+$", "", body).strip()
    if not body:
        return None
    if base in WRAP:
        body = f"\\begin{{{WRAP[base]}}} {body} \\end{{{WRAP[base]}}}"
    return f"\\begin{{equation}}\n{body}\n\\end{{equation}}"


def norm_figure(env: str, inner: str) -> str:
    base = env.rstrip("*")
    inner = re.sub(r"^\s*\[[^\]]*\]", "", inner)           # [htbp]
    inner = clean_common(inner)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in inner.splitlines()]
    body = "\n".join(ln for ln in lines if ln)
    return f"\\begin{{{base}}}\n{body}\n\\end{{{base}}}"


def split_items(body: str) -> list:
    items, depth, start = [], 0, None
    for m in ITEM_RE.finditer(body):
        kind = m.group(1)
        if kind == "begin":
            depth += 1
        elif kind == "end":
            depth -= 1
        elif depth == 0:
            if start is not None:
                items.append(body[start:m.start()])
            start = m.end()
    if start is not None:
        items.append(body[start:])
    return [re.sub(r"^\s*\[[^\]]*\]", "", it) for it in items]


def read_heading(text: str, j: int):
    if j < len(text) and text[j] == "*":
        j += 1
    j = skip_space(text, j)
    if j < len(text) and text[j] == "[":
        g, e = read_group(text, j, "[", "]")
        if g is None:
            return None
        j = skip_space(text, e)
    if j < len(text) and text[j] == "{":
        g, e = read_group(text, j)
        if g is not None:
            return g, e
    return None


def parse_blocks(text: str) -> list:
    """Tach van ban thanh danh sach block:
    ('heading', lenh, tieu_de, muc_ep) | ('prose', raw) | ('equation', str)
    | ('figure', str) | ('list', env, [danh_sach_block_moi_item])."""
    blocks, pos, last = [], 0, 0

    def flush(upto):
        chunk = text[last:upto]
        if chunk.strip():
            blocks.append(("prose", chunk))

    while True:
        m = TOKEN_RE.search(text, pos)
        if not m:
            break
        if m.group("env"):
            name = m.group("env")
            base = name.rstrip("*")
            end = find_env_end(text, m.end(), name)
            if end is None:
                pos = m.end()
                continue
            flush(m.start())
            inner = text[m.end():end[0]]
            if base in MATH_ENVS:
                eq = norm_equation(name, inner)
                if eq:
                    blocks.append(("equation", eq))
            elif base in FLOAT_ENVS:
                blocks.append(("figure", norm_figure(name, inner)))
            elif base in LIST_ENVS:
                items = [parse_blocks(it) for it in split_items(inner)]
                blocks.append(("list", LIST_ENVS[base], items))
            elif base == "abstract":
                blocks.append(("heading", None, "Abstract", 1))
                blocks.extend(parse_blocks(inner))
            elif base == "thebibliography":
                pass
            else:                                           # moi truong trong suot
                if base == "minipage":
                    inner = re.sub(r"^\s*(\[[^\]]*\])?\s*\{[^{}]*\}", "", inner)
                else:
                    inner = re.sub(r"^\s*\[[^\]\n]{0,120}\]", "", inner)
                blocks.extend(parse_blocks(inner))
            pos = last = end[1]
        elif m.group("sec"):
            h = read_heading(text, m.end())
            if h is None:
                pos = m.end()
                continue
            flush(m.start())
            blocks.append(("heading", m.group("sec"), clean_title(h[0]), None))
            pos = last = h[1]
        elif m.group("dd"):
            j = text.find("$$", m.end())
            if j < 0:
                pos = m.end()
                continue
            flush(m.start())
            eq = norm_equation("equation", text[m.end():j])
            if eq:
                blocks.append(("equation", eq))
            pos = last = j + 2
        else:                                               # \[ ... \]
            j = text.find("\\]", m.end())
            if j < 0:
                pos = m.end()
                continue
            flush(m.start())
            eq = norm_equation("equation", text[m.end():j])
            if eq:
                blocks.append(("equation", eq))
            pos = last = j + 2
    flush(len(text))
    return blocks


def blocks_to_nodes(blocks: list, parent: Node):
    """Dua block khong phai heading vao parent."""
    for b in blocks:
        t = b[0]
        if t == "prose":
            for s in prose_to_sentences(b[1]):
                parent.children.append(Node("sentence", s))
        elif t == "equation":
            parent.children.append(Node("equation", b[1]))
        elif t == "figure":
            parent.children.append(Node("figure", b[1]))
        elif t == "list":
            lst = Node("list", b[1])
            for item_blocks in b[2]:
                item = Node("item", "")
                blocks_to_nodes([x for x in item_blocks if x[0] != "heading"], item)
                lst.children.append(item)
            parent.children.append(lst)


def build_tree(blocks: list) -> Node:
    """Heading -> cay. Muc tu suy ra tu cac lenh thuc su co mat trong bai."""
    used = sorted({b[1] for b in blocks if b[0] == "heading" and b[1]}, key=RANK.get)
    level_of = {cmd: i + 1 for i, cmd in enumerate(used)}
    root = Node("document", "")
    stack = [(0, root)]
    skip_level = None
    for b in blocks:
        if b[0] == "heading":
            level = b[3] or level_of[b[1]]
            while len(stack) > 1 and stack[-1][0] >= level:
                stack.pop()
            if skip_level is not None:
                if level <= skip_level:
                    skip_level = None
                else:
                    continue
            if REF_TITLE_RE.fullmatch(b[2] or ""):
                skip_level = level
                continue
            node = Node("heading", b[2])
            stack[-1][1].children.append(node)
            stack.append((level, node))
        elif skip_level is None:
            blocks_to_nodes([b], stack[-1][1])
    return root


def count_nodes(node: Node) -> int:
    return 1 + sum(count_nodes(c) for c in node.children)


def walk(node: Node):
    yield node
    for c in node.children:
        yield from walk(c)


# ====================================================================== 3. BIBTEX

def _clean_bib_value(v: str) -> str:
    v = re.sub(r"[{}]", "", v or "")
    v = v.replace("\\&", "&").replace("\\_", "_").replace("\\%", "%").replace("~", " ")
    return re.sub(r"\s+", " ", v).strip()


def norm_doi(d):
    if not d:
        return None
    d = re.sub(r"(?i)^(https?://(dx\.)?doi\.org/|doi:\s*)", "", d.strip()).strip().rstrip(".,;")
    return d.lower() or None


def make_entry(key: str, typ: str, fields: dict) -> dict:
    authors_txt = _clean_bib_value(fields.get("author") or fields.get("editor") or "")
    authors = [a.strip() for a in re.split(r"\s+and\s+", authors_txt, flags=re.I) if a.strip()]
    ym = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", fields.get("year") or fields.get("date") or "")
    url = _clean_bib_value(fields.get("url", "")) or None
    doi = norm_doi(_clean_bib_value(fields.get("doi", "")))
    if not doi and url and "doi.org/" in url:
        doi = norm_doi(url)
    eprint = _clean_bib_value(fields.get("eprint", ""))
    if not url and eprint and "arxiv" in (fields.get("archiveprefix", "") + fields.get("eprinttype", "")).lower():
        url = f"https://arxiv.org/abs/{eprint}"
    return {
        "citation_key": key,
        "entry_type": typ,
        "title": _clean_bib_value(fields.get("title", "")) or None,
        "authors": authors,
        "year": int(ym.group(1)) if ym else None,
        "doi": doi,
        "journal": _clean_bib_value(fields.get("journal") or fields.get("booktitle") or "") or None,
        "url": url,
    }


def parse_bib(text: str) -> list:
    """Doc file .bib -> danh sach entry (dict)."""
    head = re.compile(r"(?m)^[ \t]*@[ \t]*([A-Za-z]+)[ \t]*([{(])")
    name_re = re.compile(r"[A-Za-z][A-Za-z0-9_\-:]*")
    entries, pos = [], 0
    while True:
        m = head.search(text, pos)
        if not m:
            break
        typ = m.group(1).lower()
        close = "}" if m.group(2) == "{" else ")"
        body, end = read_group(text, m.end() - 1, m.group(2), close)
        if body is None:
            pos = m.end()
            continue
        pos = end
        i = body.find(",")
        if typ in ("string", "comment", "preamble") or i < 0:
            continue
        key, fields, j, n = body[:i].strip(), {}, i + 1, len(body)
        while j < n:
            while j < n and body[j] in " \t\r\n,":
                j += 1
            nm = name_re.match(body, j)
            if not nm:
                break
            j = skip_space(body, nm.end())
            if j >= n or body[j] != "=":
                break
            j = skip_space(body, j + 1)
            if j >= n:
                break
            if body[j] == "{":
                val, e = read_group(body, j)
                if val is None:
                    break
                j = e
            elif body[j] == '"':
                k, depth = j + 1, 0
                while k < n:
                    c = body[k]
                    if c == "\\":
                        k += 2
                        continue
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                    elif c == '"' and depth == 0:
                        break
                    k += 1
                val, j = body[j + 1:k], k + 1
            else:
                k = j
                while k < n and body[k] != ",":
                    k += 1
                val, j = body[j:k].strip(), k
            while j < n and body[j] != ",":                  # bo qua `# noi chuoi`
                j += 1
            fields[nm.group(0).lower()] = val
        if key:
            entries.append(make_entry(key, typ, fields))
    return entries


BIBITEM_RE = re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}")
INITIALS_RE = re.compile(r"(?:[A-Z]\.?[\s\-]*)+")


def _ref_text(s: str) -> str:
    s = unwrap_formatting(s)
    s = re.sub(r"\\url\s*\{[^}]*\}|\\doi\s*\{[^}]*\}|\\href\s*\{[^}]*\}", " ", s)
    s = s.replace("\\&", "&").replace("~", " ")
    s = re.sub(r"\\[ ,;]", " ", s)
    s = re.sub(r"[{}]", "", s)
    return re.sub(r"\s+", " ", s).strip(" ,.;")


def _split_authors(txt: str) -> list:
    txt = re.sub(r"(?i),?\s*\bet\.?\s*al\.?", "", txt)
    parts = []
    for tok in re.split(r"\s+and\s+|\s*&\s*|;", txt):
        for p in tok.split(","):
            p = p.strip()
            if not p:
                continue
            if parts and INITIALS_RE.fullmatch(p):
                parts[-1] += ", " + p
            else:
                parts.append(p)
    return [p for p in parts if p]


def bibitem_to_entry(key: str, raw: str) -> dict:
    """Doi mot \\bibitem thanh entry BibTeX bang regex/heuristic."""
    doi_m = re.search(r"10\.\d{4,9}/[^\s,}\\]+", raw)
    doi = norm_doi(doi_m.group(0)) if doi_m else None
    url_m = re.search(r"\\url\s*\{([^}]*)\}|(https?://[^\s,}\\]+)", raw)
    url = (url_m.group(1) or url_m.group(2)) if url_m else None
    work = re.sub(r"\\url\s*\{[^}]*\}|https?://[^\s,}\\]+", " ", raw)
    blocks = [_ref_text(b) for b in re.split(r"\\newblock", work)]
    blocks = [b for b in blocks if b]
    authors_txt = title = venue = ""
    quoted = re.search(r"``(.+?)(?:''|\")|\"(.+?)\"", work, re.S)
    if len(blocks) >= 3:
        authors_txt, title, venue = blocks[0], blocks[1], " ".join(blocks[2:])
    elif quoted:
        title = _ref_text(quoted.group(1) or quoted.group(2))
        authors_txt = _ref_text(work[:quoted.start()])
        venue = _ref_text(work[quoted.end():])
    else:
        flat = _ref_text(work)
        segs = re.split(r"(?<![A-Z])\.\s+", flat, maxsplit=2)
        if len(segs) >= 2:
            authors_txt, title = segs[0], segs[1]
            venue = segs[2] if len(segs) > 2 else ""
        else:
            title = flat
    years = re.findall(r"\b(?:19|20)\d\d[a-z]?\b", _ref_text(work))
    year = int(years[-1][:4]) if years else None
    venue = re.sub(r"\s+", " ", venue).strip(" ,.;") or None
    if venue and re.search(r"(?i)\b(in|proc|proceedings|conference|workshop|symposium)\b", venue):
        etype = "inproceedings"
    elif venue and year:
        etype = "article"
    else:
        etype = "misc"
    return {"citation_key": key, "entry_type": etype, "title": title.strip(" ,.;") or None,
            "authors": _split_authors(authors_txt), "year": year, "doi": doi,
            "journal": venue, "url": url}


def extract_bibitems(text: str):
    """Tach moi truong thebibliography ra khoi text -> (text_con_lai, [entry])."""
    entries = []

    def repl(m):
        body = m.group(1)
        ms = list(BIBITEM_RE.finditer(body))
        for i, b in enumerate(ms):
            end = ms[i + 1].start() if i + 1 < len(ms) else len(body)
            entries.append(bibitem_to_entry(b.group(1).strip(), body[b.end():end]))
        return " "
    text = re.sub(r"\\begin\{thebibliography\}(?:\{[^{}]*\})?(.*?)\\end\{thebibliography\}",
                  repl, text, flags=re.S)
    return text, entries


# ---------------------------------------------------------------- khu trung reference

CITE_RE = re.compile(r"(\\[A-Za-z]*cite[A-Za-z]*\*?(?:\s*\[[^\]]*\]){0,2}\s*\{)([^{}]*)(\})")


def cited_keys(node: Node) -> set:
    keys = set()
    for n in walk(node):
        for m in CITE_RE.finditer(n.content):
            keys.update(k.strip() for k in m.group(2).split(",") if k.strip())
    return keys


def rename_cites(text: str, mapping: dict) -> str:
    def repl(m):
        keys = [mapping.get(k.strip(), k.strip()) for k in m.group(2).split(",")]
        return m.group(1) + ",".join(keys) + m.group(3)
    return CITE_RE.sub(repl, text)


def norm_title(t) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def dedup_bib(version_bibs: dict):
    """version_bibs: {v: {key: entry}} -> (bang_bibtex, {v: {key_cu: key_moi}}).

    Hai entry la mot khi: cung DOI, hoac cung tieu de chuan hoa, hoac cung key
    (khi mot ben khong co tieu de hoac tieu de trung). Key duoc chon la key xuat
    hien nhieu nhat; hoa thi lay key cua version moi nhat. Cac truong duoc hop nhat,
    uu tien gia tri cua version moi hon."""
    nodes = [(v, k) for v in sorted(version_bibs) for k in version_bibs[v]]
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_doi, by_title, by_key = {}, {}, defaultdict(list)
    for n in nodes:
        e = version_bibs[n[0]][n[1]]
        if e.get("doi"):
            union(n, by_doi.setdefault(e["doi"], n))
        nt = norm_title(e.get("title"))
        if len(nt) >= 12 or (nt and e.get("year")):
            tk = nt if len(nt) >= 12 else (nt, e.get("year"))
            union(n, by_title.setdefault(tk, n))
        by_key[n[1]].append(n)
    for key, group in by_key.items():
        for n in group[1:]:
            for m in group:
                if m == n:
                    break
                tn, tm = (norm_title(version_bibs[x[0]][x[1]].get("title")) for x in (n, m))
                if not tn or not tm or tn == tm:
                    union(n, m)
    groups = defaultdict(list)
    for n in nodes:
        groups[find(n)].append(n)

    rows, maps, assigned = [], defaultdict(dict), set()
    for members in sorted(groups.values(), key=lambda g: (g[0][0], nodes.index(g[0]))):
        cnt = Counter(k for _, k in members)
        latest_key = max(members, key=lambda n: n[0])[1]
        best = max(cnt.items(), key=lambda kv: (kv[1], kv[0] == latest_key))[0]
        chosen = best
        if chosen in assigned:
            alts = [k for k in cnt if k not in assigned]
            chosen, i = (alts[0] if alts else best), 2
            while chosen in assigned:
                chosen, i = f"{best}_{i}", i + 1
        assigned.add(chosen)
        merged = {"citation_key": chosen}
        ordered = sorted(members, key=lambda n: -n[0])
        for f in ("entry_type", "title", "authors", "year", "doi", "journal", "url"):
            vals = [version_bibs[v][k].get(f) for v, k in ordered]
            if f == "entry_type":
                vals = [x for x in vals if x and x != "misc"] + vals
            merged[f] = next((x for x in vals if x), None if f != "authors" else [])
        rows.append(merged)
        for v, k in members:
            maps[v][k] = chosen
    return rows, maps


# ====================================================================== 4. ID + KHU TRUNG NOI DUNG

ID_PREFIX = {"document": "root", "heading": "h", "sentence": "s", "equation": "e",
             "figure": "f", "list": "l", "item": "i"}


def assign_ids(folder: str, arxiv_id: str, trees: dict):
    """trees: {v: Node} -> (elements, hierarchy, tong_node_truoc_khu_trung).

    Element giong het (kind + noi dung sau cleanup) giua cac version dung chung id.
    Trong mot version, noi dung lap lai lay id rieng de cay van la cay."""
    registry = defaultdict(list)
    counter = Counter()
    elements, hierarchy, before = [], [], 0

    def new_id(kind):
        counter[kind] += 1
        return f"{folder}#{ID_PREFIX[kind]}{counter[kind]}"

    for v in sorted(trees):
        root_id = f"{folder}#root{v}"
        elements.append({"element_id": root_id, "arxiv_id": arxiv_id,
                         "kind": "document", "content": f"Version {v} root"})
        used = Counter()

        def visit(node, parent_id):
            nonlocal before
            for ch in node.children:
                before += 1
                key = (ch.kind, ch.content)
                idx = used[key]
                used[key] += 1
                if idx < len(registry[key]):
                    eid = registry[key][idx]
                else:
                    eid = new_id(ch.kind)
                    registry[key].append(eid)
                    elements.append({"element_id": eid, "arxiv_id": arxiv_id,
                                     "kind": ch.kind, "content": ch.content})
                hierarchy.append({"arxiv_id": arxiv_id, "version": v,
                                  "element_id": eid, "parent_id": parent_id})
                visit(ch, eid)
        visit(trees[v], root_id)
        before += 1                                         # tinh ca root
    return elements, hierarchy, before


# ====================================================================== 5. XU LY MOT VERSION / MOT BAI

def find_version_dir(pub_dir: Path, pid: str, folder: str, v: int, n_versions: int):
    if not pub_dir.is_dir():
        return None
    for name in (f"v{v}", f"{pid}v{v}", f"{folder}v{v}", f"{folder}-v{v}", f"{pid}_v{v}", str(v)):
        if (pub_dir / name).is_dir():
            return pub_dir / name
    for d in sorted(pub_dir.iterdir()):
        if d.is_dir() and re.search(rf"(?:^|\D)v{v}$", d.name):
            return d
    if n_versions == 1 and any(p.suffix.lower() == ".tex" for p in pub_dir.iterdir() if p.is_file()):
        return pub_dir
    return None


def merge_bib_entry(entries: dict, incoming: dict, conflicts: list):
    """Union repeated identical keys, retaining conflicting originals for audit.

    Later non-empty definitions win; a specific type takes priority over misc.
    Missing fields never erase values from an earlier definition.
    """
    key = incoming["citation_key"]
    if key not in entries:
        entries[key] = dict(incoming)
        return
    current = entries[key]
    for field, value in incoming.items():
        if field == "citation_key" or not value:
            continue
        old = current.get(field)
        if old and old != value:
            conflicts.append({"citation_key": key, "field": field,
                              "earlier": old, "later": value})
        if field == "entry_type" and value == "misc" and old and old != "misc":
            continue
        current[field] = value


def parse_version(vdir: Path) -> dict:
    """Gather + parse mot version. Tra ve dict: status, reason, tree, bib, thong ke."""
    tex = collect_files(vdir, ".tex")
    if not tex:
        return {"status": "empty", "reason": "no_tex_files"}
    texts = {k: strip_comments(read_text(p)) for k, p in tex.items()}
    root = pick_root(texts, tex)
    if root is None:
        return {"status": "failed", "reason": "no_root_file"}
    used: set = set()
    full = expand(root, texts, tex, (root,), used)

    bibs = collect_files(vdir, ".bib")
    bib_keys = []
    for m in BIBLIO_RE.finditer(full):
        for name in m.group(1).split(","):
            k = resolve_name(name, posixpath.dirname(root), bibs, (".bib",))
            if k and k not in bib_keys:
                bib_keys.append(k)
    entries, bib_conflicts = {}, []
    for k in bib_keys:
        for e in parse_bib(read_text(bibs[k])):
            merge_bib_entry(entries, e, bib_conflicts)

    body, bibitems = extract_bibitems(body_of(full))
    for e in bibitems:
        merge_bib_entry(entries, e, bib_conflicts)
    tree = build_tree(parse_blocks(body))
    if not tree.children:
        return {"status": "failed", "reason": "no_content"}
    return {"status": "ok", "reason": "", "tree": tree, "bib": entries,
            "bib_files_all": {k: bibs[k] for k in bibs}, "root_file": root,
            "files_used": len(used), "files_total": len(tex),
            "bib_field_conflicts": bib_conflicts}


class ParseTimeout(Exception):
    pass


def process_publication(job: dict) -> dict:
    """Xu ly tat ca version cua mot bai, ghi parsed.json. Tra ve dict trang thai."""
    t0 = time.perf_counter()
    p = job["paper"]
    pid, folder = p["id"], p["folder"]
    pub_dir = DATA_DIR / folder
    versions = sorted({int(re.sub(r"\D", "", str(v)) or 0) for v in p.get("versions") or []})
    vinfo, parsed = {}, {}
    for v in versions:
        dl = job["dl"].get(v)
        if dl in EMPTY_DL_STATES:
            vinfo[v] = {"status": "empty", "reason": f"download:{dl}"}
            continue
        vdir = find_version_dir(pub_dir, pid, folder, v, len(versions))
        if vdir is None:
            if dl == "ok":
                listing = sorted(x.name for x in pub_dir.iterdir())[:8] if pub_dir.is_dir() else []
                vinfo[v] = {"status": "failed", "reason": f"version_dir_not_found {listing}"}
            else:
                vinfo[v] = {"status": "empty", "reason": "no_source_dir"}
            continue
        try:
            r = parse_version(vdir)
        except ParseTimeout:
            raise
        except Exception as exc:
            r = {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
        vinfo[v] = {k: r[k] for k in ("status", "reason") if k in r}
        if r["status"] == "ok":
            parsed[v] = r
            vinfo[v].update(root_file=r["root_file"], files_used=r["files_used"],
                            files_total=r["files_total"],
                            bib_field_conflicts=r["bib_field_conflicts"])

    # --- reference: khu trung xuyen version, doi ten \cite
    version_bibs = {}
    for v, r in parsed.items():
        entries = r["bib"]
        if job["cited_only"]:
            cited = cited_keys(r["tree"])
            entries = {k: e for k, e in entries.items() if k in cited}
        version_bibs[v] = entries
    bib_rows, rename = dedup_bib(version_bibs) if version_bibs else ([], {})
    bib_before = sum(len(b) for b in version_bibs.values())
    for v, r in parsed.items():
        mapping = {k: n for k, n in rename.get(v, {}).items() if k != n}
        if mapping:
            for node in walk(r["tree"]):
                if "cite" in node.content:
                    node.content = rename_cites(node.content, mapping)

    # --- khu trung noi dung xuyen version + gan id
    trees = {v: r["tree"] for v, r in parsed.items()}
    elements, hierarchy, before = assign_ids(folder, pid, trees)
    for v in vinfo:
        vinfo[v]["nodes"] = count_nodes(trees[v]) if v in trees else 0
    bib_out = [dict(arxiv_id=pid, **row) for row in bib_rows]

    out = {"arxiv_id": pid, "folder": folder,
           "versions": {str(v): vinfo[v] for v in vinfo},
           "elements": elements, "hierarchy": hierarchy, "bibtex": bib_out}
    (DATA_DIR / folder).mkdir(parents=True, exist_ok=True)
    save_json(pub_dir / PARSED_NAME, out, separators=(",", ":"))

    counts = Counter(i["status"] for i in vinfo.values())
    n_failed = counts["failed"]
    return {"status": "partial" if n_failed else "ok",
            "versions": len(vinfo), "versions_ok": counts["ok"],
            "versions_empty": counts["empty"], "versions_failed": n_failed,
            "elements_before_dedup": before if trees else 0,
            "elements_after_dedup": len(elements),
            "hierarchy_rows": len(hierarchy),
            "bib_before_dedup": bib_before, "bib_after_dedup": len(bib_rows),
            "seconds": round(time.perf_counter() - t0, 3)}


def worker(job: dict) -> tuple:
    pid = job["paper"]["id"]
    timeout = job["timeout"]
    use_alarm = timeout and hasattr(signal, "SIGALRM")
    if use_alarm:
        def handler(signum, frame):
            raise ParseTimeout(f"qua {timeout}s")
        signal.signal(signal.SIGALRM, handler)
        signal.alarm(timeout)
    try:
        return pid, process_publication(job)
    except BaseException as exc:                            # ke ca timeout / recursion
        if isinstance(exc, KeyboardInterrupt):
            raise
        return pid, {"status": "error", "note": f"{type(exc).__name__}: {exc}"}
    finally:
        if use_alarm:
            signal.alarm(0)


# ====================================================================== export + main

def export_tables(papers: list):
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    files = {n: open(TABLES_DIR / f"{n}.jsonl", "w", encoding="utf-8")
             for n in ("elements", "hierarchy", "bibtex")}
    try:
        for p in papers:
            f = DATA_DIR / p["folder"] / PARSED_NAME
            if not f.exists():
                continue
            d = json.loads(f.read_text(encoding="utf-8"))
            for name, fh in files.items():
                for row in d[name]:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    counts[name] += 1
    finally:
        for fh in files.values():
            fh.close()
    print(f"[PARSE] Export {TABLES_DIR}: {dict(counts)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=None, help="chi xu ly N bai dau")
    ap.add_argument("--ids", default=None, help="chi xu ly cac ID nay (cach nhau dau phay)")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--timeout", type=int, default=300, help="giay toi da cho moi bai (Linux)")
    ap.add_argument("--force", action="store_true", help="chay lai ca bai da xong")
    ap.add_argument("--cited-only", action="store_true",
                    help="bibtex chi giu entry duoc \\cite trong bai (mac dinh: giu tat ca)")
    ap.add_argument("--export", action="store_true", help="gop ba bang ra data/tables/*.jsonl")
    ap.add_argument("--export-only", action="store_true")
    args = ap.parse_args()

    if not DISCOVERY.exists():
        raise SystemExit(f"Khong tim thay {DISCOVERY.resolve()}. Chay tu thu muc goc project.")
    papers = json.loads(DISCOVERY.read_text(encoding="utf-8"))["papers"]
    if args.ids:
        wanted = {x.strip() for x in args.ids.split(",")}
        papers = [p for p in papers if p["id"] in wanted]
    if args.limit:
        papers = papers[:args.limit]
    if args.export_only:
        export_tables(papers)
        return 0

    status = json.loads(STATUS_FILE.read_text(encoding="utf-8")) if STATUS_FILE.exists() else {}
    dl_all = json.loads(DOWNLOAD_STATUS.read_text(encoding="utf-8")) if DOWNLOAD_STATUS.exists() else {}
    jobs, skipped = [], 0
    for p in papers:
        done = (DATA_DIR / p["folder"] / PARSED_NAME).exists() and \
            status.get(p["id"], {}).get("status") in ("ok", "partial")
        if done and not args.force:
            skipped += 1
            continue
        dl = {}
        for v in p.get("versions") or []:
            info = dl_all.get(f"{p['id']}{v}")
            dl[int(re.sub(r"\D", "", str(v)) or 0)] = info.get("status") if isinstance(info, dict) else None
        jobs.append({"paper": p, "dl": dl, "cited_only": args.cited_only, "timeout": args.timeout})
    print(f"[PARSE] Bo qua {skipped} bai da xong; xu ly {len(jobs)} bai bang {args.workers} tien trinh.")

    t0, n_done = time.perf_counter(), 0
    try:
        if jobs:
            with Pool(max(1, args.workers), maxtasksperchild=200) as pool:
                for pid, res in pool.imap_unordered(worker, jobs, chunksize=1):
                    status[pid] = res
                    n_done += 1
                    if res["status"] == "error":
                        print(f"[PARSE] LOI {pid}: {res['note']}")
                    else:
                        print(f"[PARSE] {n_done}/{len(jobs)} {pid}: {res['status']} "
                              f"v_ok={res['versions_ok']}/{res['versions']} "
                              f"elem {res['elements_before_dedup']}->{res['elements_after_dedup']} "
                              f"bib {res['bib_before_dedup']}->{res['bib_after_dedup']}")
                    if n_done % 25 == 0:
                        save_json(STATUS_FILE, status, indent=2)
    finally:
        save_json(STATUS_FILE, status, indent=2)
    counts = Counter(s["status"] for s in status.values())
    print(f"[PARSE] Xong sau {time.perf_counter() - t0:.1f}s:", dict(counts))
    if args.export:
        export_tables(papers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
