"""End-to-end M2 pipeline: LaTeX hierarchy, normalized elements and unified BibTeX."""
from __future__ import annotations
import argparse, json, re, time, os
from pathlib import Path
from collections import Counter
from latex_gatherer import find_root_tex, expand_document_content
from latex_parser import parse_heading_content, extract_display_math, normalize_formula
from sentence_extractor import prepare_prose_text, split_sentences
from element_builder import build_elements, normalize_element_content
from hierarchy_builder import build_hierarchy_rows, validate_hierarchy
from bibtex_parser import parse_bibtex_file, parse_bibitems, merge_bibtex_versions, rewrite_citation_keys

REF_HEADINGS={"references","bibliography","works cited","literature cited"}
FIGURE_NAMES={"figure","figure*","table","table*","wrapfigure"}
SPECIAL_BLOCKS={"abstract":"abstract","acknowledgements":"acknowledgements",
                "acknowledgment":"acknowledgements","acknowledgments":"acknowledgements"}
LIST_NAMES={"itemize","enumerate","description"}
ENV_TOKEN=re.compile(r"\\(begin|end)\s*\{([^{}]+)\}")
CAPTION_RE=re.compile(r"\\caption(?:\[[^\]]*\])?\s*\{((?:[^{}]|\{[^{}]*\})*)\}",re.S)

def _clean_heading(value):
    value=re.sub(r"\\texorpdfstring\s*\{([^{}]*)\}\s*\{[^{}]*\}",r"\1",value)
    value=re.sub(r"\\(?:label|index|texorpdfstring)\s*\{[^{}]*\}"," ",value)
    value=re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?"," ",value)
    value=value.replace("{","").replace("}","").replace("~"," ")
    return re.sub(r"\s+"," ",value).strip()

def _is_reference_heading(title):
    cleaned=_clean_heading(title).lower().strip(" .")
    return cleaned in REF_HEADINGS or cleaned.startswith("references ") or cleaned.startswith("bibliography ")

def _matching_environment_end(text,start,name):
    depth=0
    for m in ENV_TOKEN.finditer(text,start):
        action,env=m.group(1),m.group(2)
        if env!=name: continue
        if action=="begin": depth+=1
        else:
            depth-=1
            if depth==0: return m.end(),m.start()
    return None,None

def _environment_blocks(text,names):
    blocks=[]
    for m in ENV_TOKEN.finditer(text):
        name=m.group(2)
        if m.group(1)!="begin" or name not in names: continue
        end,end_start=_matching_environment_end(text,m.start(),name)
        if end is None: continue
        blocks.append({"start":m.start(),"end":end,"name":name,
                       "body_start":m.end(),"body_end":end_start})
    # Drop nested candidates already contained by an outer candidate of same block class.
    result=[]
    for b in sorted(blocks,key=lambda x:(x["start"],-x["end"])):
        if any(x["start"]<=b["start"] and b["end"]<=x["end"] for x in result): continue
        result.append(b)
    return result

def _figure_content(text,block):
    body=text[block["body_start"]:block["body_end"]]
    cap=CAPTION_RE.search(body)
    if cap: content=_clean_heading(cap.group(1))
    else:
        graphics=re.findall(r"\\includegraphics(?:\[[^\]]*\])?\s*\{([^{}]+)\}",body)
        content="; ".join(graphics) if graphics else block["name"]
    label=re.search(r"\\label\s*\{([^{}]+)\}",body)
    if label and content: content=f"{content} [{label.group(1)}]"
    return content or block["name"]

def _top_level_items(body):
    """Split a list body at item commands not nested inside another environment."""
    items=[]; depth=0; starts=[]
    for m in ENV_TOKEN.finditer(body):
        if m.group(1)=="begin": depth+=1
        else: depth=max(0,depth-1)
    # A small token scanner is more reliable than a global regex for nested lists.
    token=re.compile(r"\\begin\s*\{([^{}]+)\}|\\end\s*\{([^{}]+)\}|\\item(?:\s*\[[^\]]*\])?")
    depth=0; current=None
    for m in token.finditer(body):
        if m.group(1):
            depth+=1
        elif m.group(2):
            depth=max(0,depth-1)
        elif m.group(0).startswith("\\item") and depth==0:
            if current is not None: items.append(body[current:m.start()])
            current=m.end()
    if current is not None: items.append(body[current:])
    return items

def _add_paragraphs(text,parent_idx,nodes):
    """Create paragraph components and sentence leaves from a prose region."""
    text=re.sub(r"(\\begin\s*\{(?:theorem|lemma|corollary|proposition|definition|example|remark|claim|assumption|proof)\})\s*\[[^\]]*\]",r"\1",text)
    text=prepare_prose_text(text)
    if not text.strip(): return
    # Blank lines are authoritative paragraph separators; a long single source
    # block remains one paragraph even if it contains several sentences.
    chunks=[x.strip() for x in re.split(r"\n\s*\n+",text) if x.strip()]
    for chunk in chunks:
        sentences=[normalize_element_content(x) for x in split_sentences(chunk)]
        sentences=[x for x in sentences if x]
        if not sentences: continue
        paragraph_content=" ".join(sentences)
        pidx=len(nodes)
        nodes.append({"kind":"paragraph","content":paragraph_content,"parent":parent_idx})
        for sentence in sentences:
            nodes.append({"kind":"sentence","content":sentence,"parent":pidx})

def _process_region(text,parent_idx,nodes):
    """Process a heading/list-item body into prose paragraphs, formulas and figures."""
    if not text: return
    # Remove the bibliography body before leaf extraction.
    text=re.sub(r"\\begin\s*\{thebibliography\}.*?\\end\s*\{thebibliography\}","",text,flags=re.S)
    formulas=extract_display_math(text)
    figures=_environment_blocks(text,FIGURE_NAMES)
    lists=_environment_blocks(text,LIST_NAMES)
    special=_environment_blocks(text,set(SPECIAL_BLOCKS))
    events=[]
    for f in formulas:
        events.append((f["start"],f["end"],"formula",f))
    for b in figures:
        events.append((b["start"],b["end"],"figure",b))
    for b in lists:
        events.append((b["start"],b["end"],"list",b))
    for b in special:
        events.append((b["start"],b["end"],"special",b))
    events.sort(key=lambda x:(x[0],-(x[1]-x[0])))
    cursor=0
    for start,end,kind,data in events:
        if start<cursor: continue
        _add_paragraphs(text[cursor:start],parent_idx,nodes)
        if kind=="formula":
            content=data["content"]
            if content:
                nodes.append({"kind":"formula","content":content,"parent":parent_idx})
        elif kind=="figure":
            nodes.append({"kind":"figure","content":_figure_content(text,data),"parent":parent_idx})
        elif kind=="special":
            special_idx=len(nodes)
            nodes.append({"kind":SPECIAL_BLOCKS[data["name"]],
                          "content":SPECIAL_BLOCKS[data["name"]].title(),
                          "parent":parent_idx})
            _process_region(text[data["body_start"]:data["body_end"]],special_idx,nodes)
        elif kind=="list":
            list_idx=len(nodes)
            nodes.append({"kind":"list","content":data["name"],"parent":parent_idx})
            body=text[data["body_start"]:data["body_end"]]
            for item_no,item_text in enumerate(_top_level_items(body),1):
                # Preserve a meaningful item component; sentences become its children.
                cleaned=prepare_prose_text(item_text)
                item_content=" ".join(split_sentences(cleaned)) or f"Item {item_no}"
                item_idx=len(nodes)
                nodes.append({"kind":"list_item","content":item_content,"parent":list_idx})
                # Recursively parse each item so nested lists and display formulas
                # become descendants rather than being flattened into prose.
                _process_region(item_text,item_idx,nodes)
        cursor=end
    _add_paragraphs(text[cursor:],parent_idx,nodes)

def _parse_version(root_tex,version,key_map):
    segments=expand_document_content(root_tex)
    root={"kind":"document","content":f"Version {version[1:]} root","parent":None}
    nodes=[root]
    # heading stack stores (hierarchy level, node index)
    stack=[(0,0)]
    skip_references=False
    seen_document_body=False
    for seg in segments:
        content=rewrite_citations(seg["content"],key_map)
        # Title/author/affiliation blocks before the abstract or first section are
        # front matter, not body-text sentence leaves.
        if not seen_document_body:
            abs_match=re.search(r"\\begin\s*\{abstract\}",content)
            first_heading=re.search(r"\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?(?:\s*\[[^\]]*\])?\s*\{",content)
            candidates=[m.start() for m in (abs_match,first_heading) if m]
            if candidates:
                start=min(candidates)
                content=content[start:]
                seg=dict(seg); seg["start"]=seg.get("start",0)+start
                seen_document_body=True
            elif content.strip():
                # If the first segment is only title boilerplate, defer until a
                # structural body marker is found in a later included segment.
                continue
        headings=parse_heading_content(content,seg["file"],seg.get("start",0))
        events=[]
        for h in headings:
            local=h["position"]-seg.get("start",0)
            events.append((local,"heading",h))
        events.sort(key=lambda x:x[0])
        cursor=0
        for pos,kind,data in events+[(len(content),"end",None)]:
            if pos<cursor: continue
            region=content[cursor:pos]
            if region.strip() and not skip_references:
                _process_region(region,stack[-1][1],nodes)
            if kind=="heading":
                title=_clean_heading(data["title"])
                if _is_reference_heading(title):
                    skip_references=True
                else:
                    skip_references=False
                    # LaTeX levels: section=1, subsection=2 ...; chapter is a top-level peer.
                    level=max(1,int(data["level"])-2)
                    while len(stack)>1 and stack[-1][0]>=level: stack.pop()
                    parent=stack[-1][1]
                    idx=len(nodes)
                    nodes.append({"kind":"heading","content":title,"parent":parent})
                    stack.append((level,idx))
            cursor=pos
    return nodes,segments

def _bib_files(version_dir):
    return sorted(version_dir.rglob("*.bib"))

def _load_papers(discovery_path,data_root):
    if discovery_path and Path(discovery_path).is_file():
        obj=json.loads(Path(discovery_path).read_text(encoding="utf-8"))
        return obj.get("papers",[]) if isinstance(obj,dict) else obj
    papers=[]
    for folder in sorted(Path(data_root).iterdir()):
        if folder.is_dir() and re.match(r"\d{4}-\d{4,5}$",folder.name):
            versions=sorted([p.name for p in folder.iterdir() if p.is_dir() and re.fullmatch(r"v\d+",p.name)],
                            key=lambda v:int(v[1:]))
            papers.append({"id":folder.name.replace("-", ".",1),"folder":folder.name,
                           "versions":versions or ["v1"]})
    return papers

def process_publication(paper,data_root):
    arxiv_id=paper.get("id") or paper.get("arxiv_id")
    folder=paper.get("folder") or arxiv_id.replace(".","-",1)
    versions=paper.get("versions") or [f"v{i}" for i in range(1,int(paper.get("latest_version",1))+1)]
    raw_bib={}; version_sources={}; version_status={}
    # Pass 1: gather every version's bibliography before parsing text, so citation
    # keys can be rewritten consistently in every element.
    bib_before=0
    for version in versions:
        vdir=Path(data_root)/folder/version
        if not vdir.exists():
            raw_bib[version]=[]; version_sources[version]=None; version_status[version]="empty"; continue
        try:
            root=find_root_tex(vdir)
            segs=expand_document_content(root)
            raw="\n".join(s["content"] for s in segs)
            records=[]
            for bibfile in _bib_files(vdir): records.extend(parse_bibtex_file(bibfile))
            records.extend(parse_bibitems(raw))
            raw_bib[version]=records; version_sources[version]=(root,segs)
            version_status[version]="ready"
            bib_before+=len(records)
        except FileNotFoundError:
            raw_bib[version]=[]; version_sources[version]=None; version_status[version]="empty"
        except Exception as exc:
            raw_bib[version]=[]; version_sources[version]=None
            version_status[version]="error"; version_status[version+"_error"]=f"{type(exc).__name__}: {exc}"
    merged_bib,key_maps=merge_bibtex_versions(raw_bib)
    version_nodes={}; version_parents={}; parse_errors={}
    for version in versions:
        source=version_sources.get(version)
        if source is None: continue
        try:
            root,_=source
            nodes,_=_parse_version(root,version,key_maps.get(version,{}))
            version_nodes[version]=nodes
            version_parents[version]=[n["parent"] for n in nodes]
            version_status[version]="parsed"
        except Exception as exc:
            parse_errors[version]=f"{type(exc).__name__}: {exc}"
            version_status[version]="error"
    # Stable shared store across all versions, including a distinct root per version.
    version_items={v:[{"kind":n["kind"],"content":n["content"]} for n in ns]
                   for v,ns in version_nodes.items()}
    elements,ids_by_version=build_elements(arxiv_id,version_items)
    hierarchy=[]
    for version,ids in ids_by_version.items():
        parents=version_parents[version]
        hierarchy.extend(build_hierarchy_rows(
            arxiv_id=arxiv_id, version=int(version[1:]),
            element_ids=ids, parent_indices=parents
        ))
    bibtex=[]
    for entry in merged_bib:
        row={k:entry.get(k) for k in ("citation_key","entry_type","title","authors","year","doi","journal","url")}
        row["authors"]=row["authors"] or []
        row["arxiv_id"]=arxiv_id
        bibtex.append(row)
    before_elements=sum(len(ns) for ns in version_nodes.values())
    stats={"arxiv_id":arxiv_id,"versions_expected":len(versions),
           "versions_parsed":sum(x=="parsed" for x in version_status.values()),
           "versions_empty":sum(x=="empty" for x in version_status.values()),
           "versions_error":sum(x=="error" for x in version_status.values()),
           "version_status":{v:version_status.get(v,"empty") for v in versions},
           "elements_before_dedup":before_elements,"elements_after_dedup":len(elements),
           "hierarchy_rows":len(hierarchy),"bibtex_before_dedup":bib_before,
           "bibtex_after_dedup":len(bibtex),"parse_errors":parse_errors}
    return elements,hierarchy,bibtex,stats

def rewrite_citations(text,key_map):
    return rewrite_citation_keys(text,key_map)

def write_jsonl(path,rows):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8") as f:
        for row in rows: f.write(json.dumps(row,ensure_ascii=False)+"\n")

def run_pipeline(data_dir="data",output_dir="m2_output",discovery="discovery.json",limit=None):
    data_root=Path(data_dir).resolve()
    disc=Path(discovery)
    if not disc.is_absolute():
        candidates=[Path.cwd()/disc,data_root.parent/disc]
        disc=next((p for p in candidates if p.exists()),candidates[0])
    papers=_load_papers(disc,data_root)
    if limit is not None: papers=papers[:limit]
    out=Path(output_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
    elements_all=[]; hierarchy_all=[]; bibtex_all=[]; stats_all=[]
    t0=time.perf_counter()
    for i,paper in enumerate(papers,1):
        started=time.perf_counter()
        try:
            elements,hierarchy,bibtex,stats=process_publication(paper,data_root)
            elements_all.extend(elements); hierarchy_all.extend(hierarchy); bibtex_all.extend(bibtex)
            stats["status"]="ok" if stats["versions_error"]==0 else "partial"
        except Exception as exc:
            stats={"arxiv_id":paper.get("id"),"status":"error","error":f"{type(exc).__name__}: {exc}",
                   "versions_expected":len(paper.get("versions",[]))}
        stats["seconds"]=round(time.perf_counter()-started,4)
        stats_all.append(stats)
        if i%100==0: print(f"Processed {i}/{len(papers)} publications")
    elapsed=time.perf_counter()-t0
    integrity_errors=validate_hierarchy(elements_all,hierarchy_all)
    write_jsonl(out/"elements.jsonl",elements_all)
    write_jsonl(out/"hierarchy.jsonl",hierarchy_all)
    write_jsonl(out/"bibtex.jsonl",bibtex_all)
    write_jsonl(out/"paper_stats.jsonl",stats_all)
    try:
        import psutil
        ram=psutil.Process(os.getpid()).memory_info().rss/(1024**2)
    except Exception: ram=None
    storage=sum(p.stat().st_size for p in out.glob("*.jsonl"))/(1024**2)
    summary={"publications_requested":len(papers),
             "publications_ok":sum(x.get("status")=="ok" for x in stats_all),
             "publications_partial":sum(x.get("status")=="partial" for x in stats_all),
             "publications_error":sum(x.get("status")=="error" for x in stats_all),
             "versions_expected":sum(x.get("versions_expected",0) for x in stats_all),
             "versions_parsed":sum(x.get("versions_parsed",0) for x in stats_all),
             "versions_empty":sum(x.get("versions_empty",0) for x in stats_all),
             "versions_error":sum(x.get("versions_error",0) for x in stats_all),
             "elements_rows":len(elements_all),"hierarchy_rows":len(hierarchy_all),
             "hierarchy_integrity_errors":len(integrity_errors),
             "bibtex_rows":len(bibtex_all),
             "elements_before_dedup":sum(x.get("elements_before_dedup",0) for x in stats_all),
             "bibtex_before_dedup":sum(x.get("bibtex_before_dedup",0) for x in stats_all),
             "version_parse_success_rate":round(sum(x.get("versions_parsed",0) for x in stats_all)/
                 max(sum(x.get("versions_expected",0)-x.get("versions_empty",0) for x in stats_all),1),4),
             "wall_seconds":round(elapsed,3),
             "average_seconds_per_publication":round(elapsed/max(len(papers),1),4),
             "process_rss_mb_at_end":round(ram,2) if ram is not None else None,
             "output_storage_mb":round(storage,3)}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary

def main():
    p=argparse.ArgumentParser(description="Milestone 2 LaTeX parser")
    p.add_argument("--data",default="data"); p.add_argument("--output",default="m2_output")
    p.add_argument("--discovery",default="discovery.json"); p.add_argument("--limit",type=int)
    a=p.parse_args(); run_pipeline(a.data,a.output,a.discovery,a.limit)
if __name__=="__main__": main()
