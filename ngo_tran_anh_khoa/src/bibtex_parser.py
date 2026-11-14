"""BibTeX/.bibitem parsing, cross-version deduplication and citation-key maps."""
from __future__ import annotations
from pathlib import Path
import re, unicodedata

def _clean_tex(value):
    if value is None: return None
    value=str(value).strip()
    value=re.sub(r"\\\\(?:textit|textbf|emph|url|href)\s*\{([^{}]*)\}(?:\s*\{[^{}]*\})?",r"\1",value)
    value=re.sub(r"\\\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", value)
    value=value.replace("{","").replace("}","").replace("~"," ")
    return re.sub(r"\s+"," ",value).strip() or None

def _authors(value):
    if not value: return []
    return [x for part in re.split(r"\s+and\s+",str(value),flags=re.I)
            if (x:=_clean_tex(part))]

def _parse_balanced(text,start,opener="{",closer="}"):
    depth=0; quoted=False; i=start
    while i<len(text):
        ch=text[i]
        if ch=='"' and (i==0 or text[i-1]!="\\"): quoted=not quoted
        if not quoted:
            if ch==opener: depth+=1
            elif ch==closer:
                depth-=1
                if depth==0: return text[start+1:i],i+1
        i+=1
    return text[start+1:],len(text)

def _split_top_level_fields(s):
    fields={}; i=0; n=len(s)
    while i<n:
        while i<n and (s[i].isspace() or s[i]==","): i+=1
        m=re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*=",s[i:])
        if not m: break
        key=m.group(1).lower(); i+=m.end()
        while i<n and s[i].isspace(): i+=1
        if i>=n: break
        if s[i]=="{":
            val,i=_parse_balanced(s,i,"{","}")
        elif s[i]=='"':
            j=i+1
            while j<n:
                if s[j]=='"' and s[j-1]!="\\": break
                j+=1
            val=s[i+1:j]; i=min(j+1,n)
        else:
            j=i
            while j<n and s[j] not in ",\n": j+=1
            val=s[i:j].strip(); i=j
        fields[key]=_clean_tex(val)
    return fields

def parse_bibtex_text(text: str) -> list[dict]:
    out=[]; pos=0
    while True:
        m=re.search(r"@([A-Za-z]+)\s*([({])",text[pos:])
        if not m: break
        typ=m.group(1).lower(); op=m.group(2); close="}" if op=="{" else ")"
        body_start=pos+m.end()
        body,end=_parse_balanced(text,body_start-1,op,close)
        pos=max(end,pos+m.end())
        if typ in {"comment","preamble","string"}: continue
        comma=body.find(",")
        if comma<0: continue
        key=body[:comma].strip()
        f=_split_top_level_fields(body[comma+1:])
        try: year=int(re.search(r"\d{4}",f.get("year") or "").group())
        except AttributeError: year=None
        record={
            "citation_key":key,"entry_type":typ,
            "title":f.get("title"),"authors":_authors(f.get("author")),
            "year":year,"doi":f.get("doi"),
            "journal":f.get("journal") or f.get("booktitle"),
            "url":f.get("url")
        }
        for k,v in f.items():
            if k not in {"title","author","year","doi","journal","booktitle","url"}:
                record[k]=v
        out.append(record)
    return out

def parse_bibtex_file(bib_path: Path) -> list[dict]:
    path=Path(bib_path)
    if not path.is_file(): return []
    return parse_bibtex_text(path.read_text(encoding="utf-8",errors="replace"))

def parse_bibitems(text: str) -> list[dict]:
    """Extract basic BibTeX-compatible records from thebibliography environments."""
    out=[]
    for env in re.finditer(r"\\begin\s*\{thebibliography\}(.*?)\\end\s*\{thebibliography\}",text,re.S):
        body=env.group(1)
        ms=list(re.finditer(r"\\bibitem(?:\s*\[[^\]]*\])?\s*\{([^{}]+)\}",body))
        for i,m in enumerate(ms):
            raw=body[m.end():ms[i+1].start() if i+1<len(ms) else len(body)]
            raw=re.sub(r"\\newblock\b"," ",raw)
            raw=re.sub(r"\\url\s*\{([^{}]*)\}",r"\1",raw)
            raw=re.sub(r"\\href\s*\{([^{}]*)\}\s*\{([^{}]*)\}",r"\2",raw)
            cleaned=_clean_tex(raw) or ""
            year_match=re.search(r"\b(?:19|20)\d{2}\b",cleaned)
            title=cleaned.split(". ",1)[0].strip(". ") if cleaned else None
            out.append({"citation_key":m.group(1).strip(),"entry_type":"misc",
                        "title":title,"authors":[],"year":int(year_match.group()) if year_match else None,
                        "doi":None,"journal":None,"url":None,"note":cleaned})
    return out

def _norm(s):
    s=unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+"," ",s).strip()

def _identity(entry):
    doi=_norm(entry.get("doi"))
    if doi: return ("doi",doi)
    title=_norm(entry.get("title"))
    authors=_norm(";".join(entry.get("authors") or []))
    year=str(entry.get("year") or "")
    if title: return ("title",title)
    return ("key",_norm(entry.get("citation_key")))

def merge_bibtex_versions(version_records: dict[str,list[dict]]):
    """Merge duplicate works, union fields, and map every old key to one canonical key."""
    merged=[]; aliases={}; maps={}
    def compatible(existing, incoming):
        old_doi=_norm(existing.get("doi")); new_doi=_norm(incoming.get("doi"))
        if old_doi and new_doi:
            return old_doi==new_doi
        old_title=_norm(existing.get("title")); new_title=_norm(incoming.get("title"))
        if not old_title or old_title!=new_title:
            return False
        old_auth={_norm(x) for x in existing.get("authors") or [] if _norm(x)}
        new_auth={_norm(x) for x in incoming.get("authors") or [] if _norm(x)}
        if old_auth and new_auth and not (old_auth & new_auth):
            return False
        old_year=existing.get("year"); new_year=incoming.get("year")
        if old_year and new_year and old_year!=new_year and not (old_auth & new_auth):
            return False
        return True

    for version,records in version_records.items():
        maps[version]={}
        for record in records:
            rec=dict(record); old=(rec.get("citation_key") or "").strip()
            title=_norm(rec.get("title")); doi=_norm(rec.get("doi"))
            candidates=[]
            if doi: candidates.extend(aliases.get(("doi",doi),[]))
            if title: candidates.extend(aliases.get(("title",title),[]))
            target_index=next((idx for idx in dict.fromkeys(candidates)
                               if compatible(merged[idx],rec)),None)
            if target_index is None:
                target_index=len(merged); merged.append(rec)
            else:
                target=merged[target_index]
                for field,value in rec.items():
                    if value in (None,"",[]): continue
                    if target.get(field) in (None,"",[]):
                        target[field]=value
                    elif isinstance(value,list) and isinstance(target.get(field),list):
                        target[field]=list(dict.fromkeys(target[field]+value))
            for alias in ([("doi",doi)] if doi else [])+([("title",title)] if title else []):
                bucket=aliases.setdefault(alias,[])
                if target_index not in bucket: bucket.append(target_index)
            canonical=merged[target_index].get("citation_key") or old
            if old: maps[version][old]=canonical
    return merged,maps

_CITE_RE=re.compile(r"(\\(?:cite|citep|citet|parencite|textcite|autocite|nocite)\*?(?:\[[^\]]*\]){0,2}\s*\{)([^{}]*)(\})")
def rewrite_citation_keys(text: str, key_map: dict[str,str]) -> str:
    """Rewrite comma-separated citation keys without changing citation options."""
    if not key_map: return text
    def repl(m):
        keys=[x.strip() for x in m.group(2).split(",")]
        return m.group(1)+", ".join(key_map.get(k,k) for k in keys)+m.group(3)
    return _CITE_RE.sub(repl,text)
