"""LaTeX root discovery and source-order expansion of reachable TeX files."""
from __future__ import annotations
from pathlib import Path
import re

def remove_comments(text: str) -> str:
    """Remove unescaped TeX comments while preserving line breaks and offsets."""
    out=[]
    for line in text.splitlines(keepends=True):
        chars=[]; i=0
        while i<len(line):
            if line[i]=="%":
                backslashes=0; j=i-1
                while j>=0 and line[j]=="\\": backslashes+=1; j-=1
                if backslashes%2==0:
                    newline="\n" if line.endswith("\n") else ""
                    chars.append(newline); break
            chars.append(line[i]); i+=1
        out.append("".join(chars))
    return "".join(out)

def find_root_tex(source_dir: Path) -> Path:
    source_dir=Path(source_dir)
    if source_dir.is_file():
        return source_dir.resolve()
    candidates=[]
    for path in sorted(source_dir.rglob("*.tex")):
        try: content=remove_comments(path.read_text(encoding="utf-8",errors="replace"))
        except OSError: continue
        if re.search(r"\\documentclass(?:\s*\[[^\]]*\])?\s*\{",content):
            candidates.append(path.resolve())
    if not candidates:
        raise FileNotFoundError(f"No .tex file with \\\\documentclass in {source_dir}")
    if len(candidates)>1:
        # Prefer a conventional root file only if it is the sole conventional candidate.
        conventional=[p for p in candidates if p.name.lower() in {"main.tex","paper.tex","ms.tex"}]
        if len(conventional)==1: return conventional[0]
        raise ValueError("Multiple root TeX candidates: "+", ".join(map(str,candidates)))
    return candidates[0]

def _candidate_paths(tex_file: Path, name: str, root_dir: Path | None):
    name=name.strip().strip('"').strip("'")
    # TeX normally resolves paths from the compilation working directory (root).
    bases=[]
    p=Path(name)
    if p.is_absolute(): bases=[Path("/")]
    else:
        if root_dir is not None: bases.append(Path(root_dir))
        bases.append(Path(tex_file).parent)
    seen=set()
    for base in bases:
        target=p if p.is_absolute() else base/p
        variants=[target]
        if target.suffix=="": variants.append(target.with_suffix(".tex"))
        for candidate in variants:
            resolved=candidate.resolve()
            if resolved not in seen:
                seen.add(resolved); yield resolved

def resolve_tex_path(tex_file: Path, name: str, root_dir: Path | None=None) -> Path:
    candidates=list(_candidate_paths(Path(tex_file),name,root_dir))
    for candidate in candidates:
        if candidate.is_file(): return candidate
    return candidates[0] if candidates else (Path(tex_file).parent/name).resolve()

_INCLUDE_RE=re.compile(r"\\(?:input|include)(?![A-Za-z])\s*(?:\{([^{}]+)\}|([^\s{}]+))")

def _include_name(match):
    return (match.group(1) or match.group(2)).strip()

def find_included_files(tex_file: Path, root_dir: Path | None=None) -> list[Path]:
    content=remove_comments(Path(tex_file).read_text(encoding="utf-8",errors="replace"))
    return [p for m in _INCLUDE_RE.finditer(content)
            if (p:=resolve_tex_path(Path(tex_file),_include_name(m),root_dir)).is_file()]

def gather_compilation_path(source_dir: Path) -> list[Path]:
    root=find_root_tex(source_dir); root_dir=root.parent
    visited=set(); ordered=[]
    def visit(path):
        path=Path(path).resolve()
        if path in visited: return
        visited.add(path); ordered.append(path)
        for child in find_included_files(path,root_dir): visit(child)
    visit(root)
    return ordered

def _expand_tex_segments(tex_file: Path, active_stack=None, root_dir: Path | None=None):
    path=Path(tex_file).resolve()
    active_stack=set() if active_stack is None else set(active_stack)
    if path in active_stack: raise ValueError(f"Circular TeX include: {path}")
    if not path.is_file(): raise FileNotFoundError(path)
    active_stack.add(path)
    root_dir=Path(root_dir).resolve() if root_dir else path.parent
    content=remove_comments(path.read_text(encoding="utf-8",errors="replace"))
    segments=[]; cursor=0
    for match in _INCLUDE_RE.finditer(content):
        if match.start()>cursor:
            segments.append({"file":path,"content":content[cursor:match.start()],
                             "start":cursor,"end":match.start()})
        child=resolve_tex_path(path,_include_name(match),root_dir)
        if child.is_file():
            segments.extend(_expand_tex_segments(child,active_stack,root_dir))
        else:
            print(f"Warning: skipped missing TeX include: {child}")
        cursor=match.end()
    if cursor<len(content):
        segments.append({"file":path,"content":content[cursor:],
                         "start":cursor,"end":len(content)})
    return segments

def expand_document_content(root_tex: Path) -> list[dict]:
    root=Path(root_tex).resolve()
    if not root.is_file(): raise FileNotFoundError(root)
    content=remove_comments(root.read_text(encoding="utf-8",errors="replace"))
    begin=re.search(r"\\begin\s*\{document\}",content)
    end=re.search(r"\\end\s*\{document\}",content)
    if not begin or not end or end.start()<begin.end():
        raise ValueError(f"Cannot locate valid document boundaries in {root}")
    body_start,body_end=begin.end(),end.start()
    body=content[body_start:body_end]
    # Expand only document body; includes in preamble are not body content.
    # A temporary expansion helper preserves offsets in each original file.
    segments=[]; cursor=0; root_dir=root.parent
    for match in _INCLUDE_RE.finditer(body):
        if match.start()>cursor:
            segments.append({"file":root,"content":body[cursor:match.start()],
                             "start":body_start+cursor,"end":body_start+match.start()})
        child=resolve_tex_path(root,_include_name(match),root_dir)
        if child.is_file():
            segments.extend(_expand_tex_segments(child,root_dir=root_dir))
        else: print(f"Warning: skipped missing TeX include: {child}")
        cursor=match.end()
    if cursor<len(body):
        segments.append({"file":root,"content":body[cursor:],
                         "start":body_start+cursor,"end":body_end})
    return segments
