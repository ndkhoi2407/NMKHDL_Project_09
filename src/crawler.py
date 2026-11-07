#!/usr/bin/env python3
"""HCMUS IntroDS Milestone 1 PRO: resumable, auditable arXiv source crawler.

Core behavior:
- Discover all assigned base IDs, resolving the LATEST version via the arXiv Atom API.
- Fetch version-specific Atom metadata AND version-specific /src archives.
- Keep ONLY .tex/.bib; save an empty, explicit source record for PDF-only versions.
- Obtain Semantic Scholar references once per publication, paginated; retain all locally.
- Look up arXiv submission dates of cited works using a deduplicated SQLite cache.
- Export paper/reference tables and auditable run metrics. No invented metadata.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zipfile

import requests

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
OAI = "{http://www.openarchives.org/OAI/2.0/}"
RAW = "{http://arxiv.org/OAI/arXivRaw/}"
BASE_PATTERN = re.compile(r"^(\d{4})\.(\d{4,5})$")
ANY_ARXIV_ID = re.compile(r"^(?:\d{4}\.\d{4,5}|[\w.-]+/\d{7})(?:v\d+)?$")
VERSIONED = re.compile(r"^(.*?)(?:v(\d+))?$")
RETRY_CODES = {408, 425, 429, 500, 502, 503, 504}
LOG = logging.getLogger("milestone1")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, item: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".atomic_", suffix=".json", delete=False) as fp:
        temp = Path(fp.name)
        json.dump(item, fp, ensure_ascii=False, indent=2)
    temp.replace(path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_range(start: str, end: str, max_papers: int | None = None) -> list[str]:
    a, b = BASE_PATTERN.fullmatch(start), BASE_PATTERN.fullmatch(end)
    if not a or not b or a.group(1) != b.group(1):
        raise ValueError("Use IDs YYMM.##### with matching YYMM, e.g. 2607.13694")
    lo, hi = int(a.group(2)), int(b.group(2))
    if lo > hi:
        raise ValueError("Start ID must not exceed end ID")
    width = len(a.group(2))
    ids = [f"{a.group(1)}.{i:0{width}d}" for i in range(lo, hi + 1)]
    return ids[:max_papers] if max_papers else ids


def paper_dir(root: Path, arxiv_id: str) -> Path:
    return root / "records" / arxiv_id.replace(".", "-").replace("/", "_")


def normalize_ref_id(s: str | None) -> str | None:
    if not s:
        return None
    s = str(s).strip().removeprefix("arXiv:")
    s = re.sub(r"v\d+$", "", s)
    return s if ANY_ARXIV_ID.fullmatch(s) else None


class HTTPError(RuntimeError):
    def __init__(self, status: int, url: str, retry_after: str | None = None):
        super().__init__(f"HTTP {status}: {url}")
        self.status = status
        self.retry_after = retry_after


class RateLimitStop(RuntimeError):
    """Pause an entire phase on HTTP 429 rather than flood a throttling API."""


class AccessDeniedStop(RuntimeError):
    """HTTP 403 means no access; waiting/retrying automatically will not grant permission."""


class PacedClient:
    def __init__(self, arxiv_delay=3.2, s2_delay=3.2, s2_key: str | None = None,
                 retries=5, contact=""):
        self.session = requests.Session()
        agent = "Arxiv-DataScience-Crawler/2.0 (educational research; single-threaded crawler)"
        if contact:
            agent += f" contact={contact}"
        self.session.headers.update({"User-Agent": agent, "Accept": "*/*"})
        self.next_call = {"arxiv": 0.0, "oai": 0.0, "s2": 0.0}
        self.delays = {"arxiv": max(arxiv_delay, 3.0),
                       "oai": max(arxiv_delay, 3.0), "s2": max(s2_delay, 1.0)}
        self.retries = retries
        self.key = s2_key
        self.lock = threading.Lock()

    def request(self, method: str, domain: str, url: str, *, params=None,
                json_data=None, stream=False):
        """Shared pacing for GET and POST. 429 is a stop signal, not a retry storm.

        Respect Retry-After for other transient errors. This does not bypass a
        provider's throttling; callers preserve checkpoints and retry later.
        """
        headers = {"x-api-key": self.key} if domain == "s2" and self.key else None
        for attempt in range(self.retries + 1):
            with self.lock:
                wait = self.next_call[domain] - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self.next_call[domain] = time.monotonic() + self.delays[domain]
            try:
                response = self.session.request(
                    method, url, params=params, json=json_data, headers=headers,
                    timeout=(15, 90), stream=stream, allow_redirects=True)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    LOG.error("HTTP 429 from %s; pause requests to this service%s: %s",
                              domain, f" (Retry-After: {retry_after})" if retry_after else "",
                              response.url)
                    status, final_url = response.status_code, response.url
                    response.close()
                    raise HTTPError(status, final_url, retry_after)
                if response.status_code in RETRY_CODES:
                    if attempt == self.retries:
                        status, final_url = response.status_code, response.url
                        response.close()
                        raise HTTPError(status, final_url)
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        extra = max(0.0, float(retry_after))
                    except ValueError:
                        try:
                            remaining = (parsedate_to_datetime(retry_after).astimezone(timezone.utc)
                                         - datetime.now(timezone.utc)).total_seconds()
                            extra = max(0.0, remaining)
                        except (TypeError, ValueError, OverflowError):
                            extra = 0.0
                    LOG.warning("Retry HTTP %s (%s/%s): %s", response.status_code,
                                attempt + 1, self.retries, response.url)
                    response.close()
                    time.sleep(max(extra, min(60, 2 ** attempt + 1)))
                    continue
                if response.status_code >= 400:
                    status, final_url = response.status_code, response.url
                    response.close()
                    raise HTTPError(status, final_url)
                return response
            except (requests.RequestException, OSError) as exc:
                if attempt == self.retries:
                    raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc
                LOG.warning("Network retry (%s/%s): %s", attempt + 1, self.retries, exc)
                time.sleep(min(60, 2 ** attempt + 1))
        raise AssertionError("unreachable")

    def get(self, domain: str, url: str, *, params=None, stream=False):
        return self.request("GET", domain, url, params=params, stream=stream)

    def post(self, domain: str, url: str, *, params=None, json_data=None):
        return self.request("POST", domain, url, params=params, json_data=json_data)


def parse_atom(xml_bytes: bytes) -> dict[str, dict]:
    root = ET.fromstring(xml_bytes)
    if root.tag != ATOM + "feed":
        raise ValueError("Unexpected arXiv response: not an Atom feed")
    out = {}
    for entry in root.findall(ATOM + "entry"):
        url = entry.findtext(ATOM + "id", "")
        if "/api/errors" in url:
            raise ValueError(f"arXiv Atom API error: {entry.findtext(ATOM + 'summary', '')}")
        identifier = url.split("/abs/")[-1].strip()
        v = VERSIONED.fullmatch(identifier)
        if not v or not v.group(2):
            raise ValueError(f"API did not identify an explicit version for {identifier!r}")
        base, ver = v.group(1), int(v.group(2))
        if not ANY_ARXIV_ID.fullmatch(base):
            raise ValueError(f"Unexpected arXiv ID {identifier!r}")
        title = " ".join(entry.findtext(ATOM + "title", "").split())
        authors = [" ".join(n.text.split()) for n in entry.findall(
            f"{ATOM}author/{ATOM}name") if n.text]
        out[identifier] = {
            "arxiv_id": base,
            "version": ver,
            "versioned_id": identifier,
            "title": title,
            "authors": authors,
            "abstract": " ".join(entry.findtext(ATOM + "summary", "").split()),
            "submission_date": entry.findtext(ATOM + "published", ""),
            "version_updated": entry.findtext(ATOM + "updated", ""),
            "venue": entry.findtext(ARXIV + "journal_ref"),
            "doi": entry.findtext(ARXIV + "doi"),
            "metadata_source": "arxiv_atom_api",
            "metadata_fidelity": "exact_version",
            "retrieved_at": utc_now(),
        }
    return out


def arxiv_lookup(client: PacedClient, identifiers: list[str]) -> dict[str, dict]:
    resp = client.get("arxiv", "https://export.arxiv.org/api/query",
                      params={"id_list": ",".join(identifiers),
                              "start": 0, "max_results": len(identifiers)})
    try:
        return parse_atom(resp.content)
    finally:
        resp.close()


def parse_oai_raw(xml_bytes: bytes, arxiv_id: str) -> tuple[dict | None, list[dict]]:
    """Parse arXiv's official OAI-PMH arXivRaw record.

    arXivRaw exposes version DATES, but title/authors/abstract are only those of the
    current paper. Provisional per-version records say so explicitly.
    """
    root = ET.fromstring(xml_bytes)
    if root.tag != OAI + "OAI-PMH":
        raise ValueError("Unexpected OAI-PMH response")
    err = root.find(OAI + "error")
    if err is not None:
        if err.get("code") == "idDoesNotExist":
            return None, []
        raise ValueError(f"OAI-PMH error {err.get('code')}: {err.text}")
    raw = root.find(f".//{RAW}arXivRaw")
    if raw is None:
        raise ValueError("OAI-PMH response has no arXivRaw metadata")
    actual_id = (raw.findtext(RAW + "id") or "").strip()
    if actual_id != arxiv_id:
        raise ValueError(f"Wrong OAI-PMH ID: {actual_id!r} expected {arxiv_id!r}")
    versions = []
    for v in raw.findall(RAW + "version"):
        match = re.fullmatch(r"v(\d+)", v.get("version", ""))
        if not match:
            raise ValueError("arXivRaw version missing or malformed")
        raw_date = (v.findtext(RAW + "date") or "").strip()
        try:
            iso_date = parsedate_to_datetime(raw_date).astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"Bad OAI-PMH version date {raw_date!r}") from exc
        versions.append({"version": int(match.group(1)), "date": iso_date})
    versions.sort(key=lambda x: x["version"])
    if not versions or [v["version"] for v in versions] != list(range(1, versions[-1]["version"] + 1)):
        raise ValueError("Incomplete arXivRaw version history; will not guess revisions")
    authors_raw = (raw.findtext(RAW + "authors") or "").strip()
    latest = versions[-1]
    metadata = {
        "arxiv_id": arxiv_id, "version": latest["version"],
        "versioned_id": f"{arxiv_id}v{latest['version']}",
        "title": " ".join((raw.findtext(RAW + "title") or "").split()),
        "authors": [" ".join(x.split()) for x in authors_raw.split(",") if x.strip()],
        "authors_raw": authors_raw,
        "abstract": " ".join((raw.findtext(RAW + "abstract") or "").split()),
        "submission_date": versions[0]["date"],
        "version_updated": latest["date"],
        "venue": raw.findtext(RAW + "journal-ref"),
        "doi": raw.findtext(RAW + "doi"),
        "metadata_source": "oai_arxivRaw",
        "metadata_fidelity": "current_fields_with_version_dates",
        "retrieved_at": utc_now(),
    }
    return metadata, versions


def arxiv_oai_lookup(client: PacedClient, arxiv_id: str) -> tuple[dict | None, list[dict]]:
    resp = client.get("oai", "https://oaipmh.arxiv.org/oai", params={
        "verb": "GetRecord", "identifier": f"oai:arXiv.org:{arxiv_id}",
        "metadataPrefix": "arXivRaw",
    })
    try:
        return parse_oai_raw(resp.content, arxiv_id)
    finally:
        resp.close()


class DiscoveryIncomplete(RuntimeError):
    pass


def batches(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def discover(client: PacedClient, root: Path, ids: list[str], batch_size: int,
             backend: str = "api", progress_every: int = 3) -> None:
    pending = [i for i in ids if read_json(paper_dir(root, i) / "paper.json", {}).get("status")
               not in ("found", "not_found")]
    LOG.info("Discovery: %d remaining / %d assigned (backend=%s)", len(pending), len(ids), backend)
    completed = 0
    t_progress = time.monotonic()
    for block in batches(pending, 1 if backend == "oai" else batch_size):
        t0 = time.monotonic()
        try:
            if backend == "oai":
                result, revision_dates = arxiv_oai_lookup(client, block[0])
                by_base = {block[0]: result} if result else {}
            else:
                entries = arxiv_lookup(client, block)
                by_base = {item["arxiv_id"]: item for item in entries.values()}
                revision_dates = None
            for i in block:
                latest = by_base.get(i)
                record = {
                    "arxiv_id": i,
                    "status": "found" if latest else "not_found",
                    "latest_version": latest["version"] if latest else 0,
                    "latest_metadata": latest,
                    "discovery_backend": backend,
                    "discovered_at": utc_now(),
                }
                write_json(paper_dir(root, i) / "paper.json", record)
                error_path = paper_dir(root, i) / "discovery_error.json"
                if error_path.exists():
                    error_path.unlink()
                if latest:
                    write_json(paper_dir(root, i) / f"v{latest['version']}" / "metadata.json", latest)
                    if revision_dates is not None:
                        write_json(paper_dir(root, i) / "versions_oai.json", revision_dates)
                        # Do not present current title/abstract as historical revision metadata.
                metrics = read_json(paper_dir(root, i) / "metrics.json", {})
                metrics["discovery_seconds"] = metrics.get("discovery_seconds", 0) + (
                    time.monotonic() - t0) / len(block)
                write_json(paper_dir(root, i) / "metrics.json", metrics)
        except Exception as exc:
            LOG.error("Discovery failed for %s: %s", ",".join(block), exc)
            # Keep transient errors pending; never mark them as 'not_found'.
            for i in block:
                write_json(paper_dir(root, i) / "discovery_error.json",
                           {"at": utc_now(), "error": str(exc)})
            if isinstance(exc, HTTPError) and exc.status == 429:
                message = (
                    "HTTP 429 from arXiv API. Stop requesting this endpoint and retry later. "
                    "Alternatively use --discovery-backend oai --phase discover "
                    "for the official OAI-PMH metadata interface."
                    if backend == "api" else
                    "HTTP 429 from arXiv OAI-PMH too. Stop the crawl and wait for the "
                    "service to allow requests; do not repeatedly retry."
                )
                raise DiscoveryIncomplete(message) from exc
        completed += len(block)
        if completed % progress_every == 0 or completed == len(pending):
            elapsed = time.monotonic() - t_progress
            remaining_count = len(pending) - completed
            estimate = elapsed / completed * remaining_count if completed else 0
            LOG.info("Discover progress: %d/%d new IDs processed (%.1f%%); ETA ~%.1f min", 
                     completed, len(pending), 100 * completed / max(1, len(pending)), estimate / 60)
    remaining = [i for i in ids if read_json(paper_dir(root, i) / "paper.json", {}).get("status")
                 not in ("found", "not_found")]
    if remaining:
        raise DiscoveryIncomplete(f"Discovery incomplete: {len(remaining)} IDs still pending")


def fetch_version_metadata(client: PacedClient, root: Path, ids: list[str],
                           batch_size: int) -> None:
    todo = []
    for i in ids:
        paper = read_json(paper_dir(root, i) / "paper.json", {})
        for version in range(1, paper.get("latest_version", 0) + 1):
            p = paper_dir(root, i) / f"v{version}" / "metadata.json"
            data = read_json(p, {})
            if data.get("metadata_fidelity") != "exact_version":
                todo.append(f"{i}v{version}")
    LOG.info("Version metadata: %d requests through %d-entry batches", len(todo), batch_size)
    for block in batches(todo, batch_size):
        t0 = time.monotonic()
        try:
            returned = arxiv_lookup(client, block)
            for identifier in block:
                m = returned.get(identifier)
                if not m:
                    LOG.warning("Metadata for %s not returned; retry in a later run", identifier)
                    continue
                dest = paper_dir(root, m["arxiv_id"]) / f"v{m['version']}"
                write_json(dest / "metadata.json", m)
                paper_path = paper_dir(root, m["arxiv_id"]) / "paper.json"
                current = read_json(paper_path, {})
                if current.get("latest_version") == m["version"]:
                    current["latest_metadata"] = m
                    write_json(paper_path, current)
                metrics_path = paper_dir(root, m["arxiv_id"]) / "metrics.json"
                metrics = read_json(metrics_path, {})
                metrics["metadata_seconds"] = metrics.get("metadata_seconds", 0) + (
                    time.monotonic() - t0) / len(block)
                write_json(metrics_path, metrics)
        except Exception as exc:
            LOG.error("Version metadata batch failed (%s): %s", block[0], exc)
            if isinstance(exc, HTTPError) and exc.status == 429:
                raise RateLimitStop("arXiv Atom metadata throttled (HTTP 429): pause and retry later; "
                                    "previously saved versions remain intact") from exc


def safe_member_name(name: str) -> Path | None:
    name = name.replace("\\", "/")
    path = PurePosixPath(name)
    if name.startswith("/") or any(part in ("..", "") for part in path.parts):
        return None
    if path.suffix.lower() not in (".tex", ".bib"):
        return None
    if len(path.parts) > 16 or len(name) > 240 or ":" in name:
        return None
    return Path(*path.parts)


def windows_long_path(path: Path) -> Path:
    """Use Windows extended-length paths for deeply nested arXiv sources.

    This changes *only* local filesystem path handling. It does not alter
    archive member names, directory layout or persisted checkpoints.
    """
    if os.name != "nt":
        return path

    absolute = os.path.abspath(os.fspath(path))
    if absolute.startswith("\\\\?\\"):
        return Path(absolute)
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)


def bounded_copy(source, destination: Path, state: dict, max_individual: int,
                 max_total: int) -> int:
    destination = windows_long_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with destination.open("wb") as fp:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            state["extracted"] += len(chunk)
            if size > max_individual or state["extracted"] > max_total:
                raise ValueError("Extracted .tex/.bib size exceeded safety limit")
            fp.write(chunk)
    return size


def looks_like_text(payload: bytes) -> bool:
    """Avoid mistaking HTTP/HTML error bodies for standalone TeX sources."""
    if not payload or payload.startswith(b"%PDF") or b"\0" in payload[:4096]:
        return False
    prefix = payload[:4096]
    bad = sum(ch < 9 or 13 < ch < 32 for ch in prefix)
    if bad / len(prefix) >= 0.04:
        return False
    low = prefix.lstrip().lower()
    if low.startswith((b"<!doctype html", b"<html", b"<?xml", b"{\"error\"")):
        return False
    # TeX may begin with comments; a single-file source still needs TeX syntax.
    return any(marker in prefix for marker in (
        b"\\documentclass", b"\\begin{document}", b"\\def\\", b"\\input{",
        b"\\usepackage", b"\\documentstyle", b"\\section{", b"\\relax"))


def extract_sources(archive: Path, target_dir: Path,
                    max_file=256 * 1024 * 1024,
                    max_extracted=512 * 1024 * 1024) -> tuple[int, int, str]:
    """Extract only LaTeX/BibTeX bytes; never extract a symlink or other binary."""
    stage = windows_long_path(target_dir / "_extract_in_progress")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    state = {"extracted": 0}
    count = 0
    kind = "unknown"
    try:
        if tarfile.is_tarfile(archive):
            kind = "tar"
            with tarfile.open(archive, "r:*") as tf:
                for member in tf:
                    path = safe_member_name(member.name)
                    if path is None or not member.isfile():
                        continue
                    if member.size > max_file:
                        raise ValueError(
                            f"Oversized source member: {member.name} "
                            f"({member.size / 1024**2:.2f} MiB; "
                            f"per-file limit {max_file / 1024**2:.2f} MiB)"
                        )
                    stream = tf.extractfile(member)
                    if stream is None:
                        continue
                    with stream:
                        bounded_copy(stream, stage / path, state, max_file, max_extracted)
                    count += 1
        elif zipfile.is_zipfile(archive):
            kind = "zip"
            with zipfile.ZipFile(archive) as zf:
                for member in zf.infolist():
                    path = safe_member_name(member.filename)
                    if path is None or member.is_dir():
                        continue
                    if (member.external_attr >> 16) & 0o170000 == 0o120000:
                        continue  # ZIP symlink
                    if member.file_size > max_file:
                        raise ValueError(
                            f"Oversized source member: {member.filename} "
                            f"({member.file_size / 1024**2:.2f} MiB; "
                            f"per-file limit {max_file / 1024**2:.2f} MiB)"
                        )
                    with zf.open(member) as fp:
                        bounded_copy(fp, stage / path, state, max_file, max_extracted)
                    count += 1
        else:
            with archive.open("rb") as f:
                signature = f.read(8)
            if signature.startswith(b"\x1f\x8b"):
                kind = "single_gzip"
                with gzip.open(archive, "rb") as gz:
                    prefix = gz.read(4096)
                    if looks_like_text(prefix):
                        stream = io.BytesIO(prefix + gz.read(max_file + 1))
                        bounded_copy(stream, stage / "source.tex", state, max_file, max_extracted)
                        count = 1
                    else:
                        kind = "non_tex"
            else:
                kind = "plain"
                with archive.open("rb") as fp:
                    prefix = fp.read(4096)
                    if looks_like_text(prefix):
                        fp.seek(0)
                        bounded_copy(fp, stage / "source.tex", state, max_file, max_extracted)
                        count = 1
                    else:
                        kind = "non_tex"
        destination = windows_long_path(target_dir / "source")
        if destination.exists():
            shutil.rmtree(destination)
        stage.replace(destination)
        return count, state["extracted"], kind
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def download_source(client: PacedClient, root: Path, identifier: str,
                    max_archive_bytes: int) -> None:
    v = VERSIONED.fullmatch(identifier)
    assert v and v.group(2)
    base, version = v.group(1), int(v.group(2))
    destination = paper_dir(root, base) / f"v{version}"
    status_path = destination / "source_status.json"
    prev = read_json(status_path, {})
    if prev.get("status") in ("ok", "no_latex", "no_source"):
        return
    destination.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    tempfile_dir = root / "_temp"
    tempfile_dir.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        response = client.get("arxiv", f"https://export.arxiv.org/src/{identifier}", stream=True)
        try:
            with tempfile.NamedTemporaryFile(dir=tempfile_dir, delete=False, suffix=".archive") as fp:
                temp_path = Path(fp.name)
                size = 0
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > max_archive_bytes:
                        raise ValueError("Archive exceeded --max-archive-mb")
                    fp.write(chunk)
        finally:
            response.close()
        count, latex_bytes, kind = extract_sources(temp_path, destination)
        write_json(status_path, {
            "status": "ok" if count else "no_latex",
            "versioned_id": identifier, "archive_format": kind,
            "archive_bytes": size, "latex_bytes": latex_bytes,
            "tex_bib_files": count, "checked_at": utc_now(),
        })
    except HTTPError as exc:
        if exc.status in (404, 410):
            write_json(status_path, {"status": "no_source", "versioned_id": identifier,
                                     "archive_bytes": 0, "latex_bytes": 0,
                                     "tex_bib_files": 0, "checked_at": utc_now()})
        else:
            LOG.warning("Source %s: %s", identifier, exc)
            write_json(status_path, {"status": "error", "error": str(exc),
                                     "checked_at": utc_now()})
            if exc.status == 429:
                raise RateLimitStop(f"Source downloads throttled at {identifier}; "
                                    "resume later, existing archives are preserved") from exc
            if exc.status == 403:
                raise AccessDeniedStop(
                    f"arXiv source access forbidden (HTTP 403) at {identifier}. "
                    "Stopping instead of continuing with thousands of requests."
                ) from exc
    except Exception as exc:
        LOG.warning("Source %s: %s", identifier, exc)
        write_json(status_path, {"status": "error", "error": str(exc),
                                 "checked_at": utc_now()})
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
        path = paper_dir(root, base) / "metrics.json"
        metrics = read_json(path, {})
        metrics["source_seconds"] = metrics.get("source_seconds", 0) + time.monotonic() - t0
        write_json(path, metrics)


def fetch_sources(client: PacedClient, root: Path, ids: list[str], max_archive_bytes,
                  progress_every: int = 3) -> None:
    for idx, i in enumerate(ids, 1):
        paper = read_json(paper_dir(root, i) / "paper.json", {})
        for v in range(1, paper.get("latest_version", 0) + 1):
            download_source(client, root, f"{i}v{v}", max_archive_bytes)
        if idx % progress_every == 0 or idx == len(ids):
            LOG.info("Sources progress: %d/%d assigned IDs inspected", idx, len(ids))


# Batch API fields are nested under "references", unlike the paginated
# /references endpoint, which wraps cited papers in "citedPaper".
S2_BATCH_FIELDS = ("referenceCount,references.title,references.authors,"
                   "references.year,references.publicationDate,"
                   "references.venue,references.externalIds")
S2_REFERENCE_FIELDS = "title,authors,year,publicationDate,venue,externalIds"


def normalize_s2_cited(cited: dict) -> dict:
    ext = cited.get("externalIds") or {}
    authors = cited.get("authors") or []
    return {
        "ref_arxiv_id": normalize_ref_id(ext.get("ArXiv")),
        "ref_title": cited.get("title") or "",
        "ref_authors": [a.get("name", "") for a in authors if isinstance(a, dict)],
        "ref_publication_date_s2": cited.get("publicationDate") or "",
        "ref_year_s2": cited.get("year"),
        "ref_venue_s2": cited.get("venue"),
        "ref_s2_id": cited.get("paperId") or "",
    }


def save_s2_references(root: Path, arxiv_id: str, refs: list[dict],
                       status: str = "ok", backend: str = "single") -> None:
    folder = paper_dir(root, arxiv_id)
    write_json(folder / "references_all.json", {
        "status": status, "arxiv_id": arxiv_id, "retrieved_at": utc_now(),
        "backend": backend, "references": refs,
    })
    old_error = folder / "references_error.json"
    if old_error.exists():
        old_error.unlink()


def reference_is_complete(root: Path, arxiv_id: str) -> bool:
    return read_json(paper_dir(root, arxiv_id) / "references_all.json", {}).get(
        "status") in ("ok", "not_found")


def fetch_s2_references(client: PacedClient, root: Path, arxiv_id: str) -> None:
    """Page through all references when batch cannot prove completeness."""
    if reference_is_complete(root, arxiv_id):
        return
    t0 = time.monotonic()
    refs = []
    offset = 0
    try:
        while True:
            url = ("https://api.semanticscholar.org/graph/v1/paper/"
                   f"{quote('arXiv:' + arxiv_id, safe=':')}/references")
            resp = client.get("s2", url, params={
                "fields": S2_REFERENCE_FIELDS, "limit": 1000, "offset": offset})
            try:
                payload = resp.json()
            finally:
                resp.close()
            page = payload.get("data")
            if not isinstance(page, list):
                raise ValueError("Semantic Scholar response lacks data list")
            for row in page:
                cited = row.get("citedPaper") if isinstance(row, dict) else None
                if isinstance(cited, dict):
                    refs.append(normalize_s2_cited(cited))
            # S2 may use 'next' to indicate another page; don't silently
            # truncate a short page when an explicit next offset exists.
            next_offset = payload.get("next")
            if isinstance(next_offset, int) and next_offset > offset:
                offset = next_offset
            elif len(page) == 1000:
                offset += len(page)
            else:
                break
            if offset > 20000:
                raise ValueError("Excessive references pagination; manual review required")
        save_s2_references(root, arxiv_id, refs)
    except HTTPError as exc:
        if exc.status == 404:
            save_s2_references(root, arxiv_id, [], status="not_found")
        else:
            LOG.warning("S2 %s: %s", arxiv_id, exc)
            write_json(paper_dir(root, arxiv_id) / "references_error.json",
                       {"at": utc_now(), "error": str(exc)})
            if exc.status == 429:
                raise RateLimitStop(f"Semantic Scholar throttled at {arxiv_id}; "
                                    "pause and resume later") from exc
            if exc.status == 403:
                raise AccessDeniedStop(
                    f"Semantic Scholar denied paper references (HTTP 403) at {arxiv_id}. "
                    "Verify account/key permissions; stopping without retrying 4,987 papers."
                ) from exc
    except Exception as exc:
        LOG.warning("S2 %s: %s", arxiv_id, exc)
        write_json(paper_dir(root, arxiv_id) / "references_error.json",
                   {"at": utc_now(), "error": str(exc)})
    finally:
        path = paper_dir(root, arxiv_id) / "metrics.json"
        metrics = read_json(path, {})
        metrics["references_seconds"] = metrics.get("references_seconds", 0) + time.monotonic() - t0
        write_json(path, metrics)


def fetch_s2_batch_block(client: PacedClient, root: Path, block: list[str]) -> None:
    """Fetch S2 reference lists for a SMALL batch, verify counts before saving.

    For truncation/unknown counts, fall back to the proven paginated endpoint.
    Split responses that are too large rather than discarding any references.
    """
    if not block:
        return
    started = time.monotonic()
    url = "https://api.semanticscholar.org/graph/v1/paper/batch"
    try:
        resp = client.post("s2", url, params={"fields": S2_BATCH_FIELDS},
                           json_data={"ids": ["ARXIV:" + i for i in block]})
        try:
            payload = resp.json()
        finally:
            resp.close()
    except HTTPError as exc:
        if exc.status == 429:
            # No data for this block is marked as complete.
            raise RateLimitStop("Semantic Scholar batch endpoint throttled (HTTP 429); "
                                "pause and resume later") from exc
        if exc.status == 403:
            raise AccessDeniedStop(
                "Semantic Scholar batch endpoint returned HTTP 403. "
                "This is an access/permission problem, not a rate-limiting signal. "
                "Stopping the batch phase; all completed references remain saved."
            ) from exc
        if exc.status in (400, 413, 414, 422) and len(block) > 1:
            LOG.warning("S2 batch of %d IDs failed (HTTP %d); split and retry small batches",
                        len(block), exc.status)
            middle = len(block) // 2
            fetch_s2_batch_block(client, root, block[:middle])
            fetch_s2_batch_block(client, root, block[middle:])
            return
        if exc.status in (400, 413, 414, 422) and len(block) == 1:
            LOG.warning("S2 batch unsupported for %s (HTTP %d); use single reference endpoint",
                        block[0], exc.status)
            fetch_s2_references(client, root, block[0])
            return
        raise
    if not isinstance(payload, list) or len(payload) != len(block):
        raise ValueError("S2 batch response shape/length mismatch: not saving partial data")

    duration_per_id = (time.monotonic() - started) / len(block)
    for arxiv_id, paper in zip(block, payload):
        if paper is None:
            save_s2_references(root, arxiv_id, [], status="not_found", backend="batch")
            continue
        if not isinstance(paper, dict):
            raise ValueError(f"Invalid S2 batch paper payload for {arxiv_id}")
        refs = paper.get("references")
        ref_count = paper.get("referenceCount")
        if (not isinstance(refs, list) or not isinstance(ref_count, int)
                or ref_count < 0 or len(refs) != ref_count
                or any(not isinstance(x, dict) for x in refs)):
            LOG.info("S2 batch %s returned %s references, expected %s; verifying via paginated API",
                     arxiv_id, len(refs) if isinstance(refs, list) else None, ref_count)
            fetch_s2_references(client, root, arxiv_id)
            continue
        normalized = [normalize_s2_cited(x) for x in refs]
        save_s2_references(root, arxiv_id, normalized, backend="batch")
        path = paper_dir(root, arxiv_id) / "metrics.json"
        metrics = read_json(path, {})
        metrics["references_seconds"] = metrics.get("references_seconds", 0) + duration_per_id
        write_json(path, metrics)


def fetch_references(client: PacedClient, root: Path, ids: list[str],
                     progress_every: int = 3, backend: str = "single",
                     batch_size: int = 5) -> None:
    if backend == "batch":
        pending = [i for i in ids if
                   read_json(paper_dir(root, i) / "paper.json", {}).get("status") == "found"
                   and not reference_is_complete(root, i)]
        LOG.info("References batch: %d pending IDs, batch size %d", len(pending), batch_size)
        for index, block in enumerate(batches(pending, batch_size), 1):
            fetch_s2_batch_block(client, root, block)
            LOG.info("References batch progress: %d/%d pending IDs inspected",
                     min(index * batch_size, len(pending)), len(pending))
    else:
        for idx, i in enumerate(ids, 1):
            paper = read_json(paper_dir(root, i) / "paper.json", {})
            if paper.get("status") == "found":
                fetch_s2_references(client, root, i)
            if idx % progress_every == 0 or idx == len(ids):
                LOG.info("References progress: %d/%d assigned IDs inspected", idx, len(ids))


def open_ref_cache(root: Path) -> sqlite3.Connection:
    db = root / "ref_submission_dates.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE IF NOT EXISTS dates (arxiv_id TEXT PRIMARY KEY, "
                 "submission_date TEXT NOT NULL, found INTEGER NOT NULL)")
    return conn


def enrich_reference_dates(client: PacedClient, root: Path, ids: list[str],
                           batch_size: int, backend: str = "oai",
                           progress_every: int = 3,
                           max_ids: int | None = None) -> None:
    # S2 publicationDate is NOT necessarily the initial arXiv submission date.
    # Resolve the true value via arXiv API instead of mislabeling S2 metadata.
    unique_refs = set()
    for i in ids:
        data = read_json(paper_dir(root, i) / "references_all.json", {})
        for ref in data.get("references", []):
            if ref.get("ref_arxiv_id"):
                unique_refs.add(ref["ref_arxiv_id"])
    conn = open_ref_cache(root)
    try:
        # Only successful dates are complete. Missing/empty API results remain retryable.
        existing = {row[0] for row in conn.execute(
            "SELECT arxiv_id FROM dates WHERE found = 1 AND submission_date <> ''")}
        pending = sorted(unique_refs - existing)
        if max_ids is not None:
            pending = pending[:max_ids]
        LOG.info("Reference-date enrichment: processing %d IDs (batch=%d), "
                 "%d successful dates cached / %d referenced",
                 len(pending), batch_size, len(existing), len(unique_refs))
        completed = 0
        for block in batches(pending, 1 if backend == "oai" else batch_size):
            attempt = 0
            while True:
                try:
                    if backend == "oai":
                        ident = block[0]
                        paper_meta, _ = arxiv_oai_lookup(client, ident)
                        rows = [(ident,
                                 paper_meta.get("submission_date", "") if paper_meta else "",
                                 int(bool(paper_meta and paper_meta.get("submission_date"))))]
                    else:
                        result = arxiv_lookup(client, block)
                        by_base = {x["arxiv_id"]: x for x in result.values()}
                        rows = [(identifier,
                                 by_base.get(identifier, {}).get("submission_date", ""),
                                 int(bool(by_base.get(identifier, {}).get("submission_date"))))
                                for identifier in block]
                    conn.executemany("INSERT OR REPLACE INTO dates VALUES (?, ?, ?)", rows)
                    conn.commit()
                    break
                except HTTPError as exc:
                    if exc.status != 429 or attempt >= client.retries:
                        LOG.error("Date enrichment batch starting %s failed: %s", block[0], exc)
                        if exc.status == 429:
                            raise RateLimitStop(
                                "Reference-date enrichment exhausted HTTP 429 retries; "
                                "successful batches are checkpointed") from exc
                        raise
                    attempt += 1
                    retry_after = exc.retry_after or ""
                    try:
                        delay = max(0.0, float(retry_after))
                    except ValueError:
                        try:
                            delay = max(0.0, (
                                parsedate_to_datetime(retry_after).astimezone(timezone.utc)
                                - datetime.now(timezone.utc)).total_seconds())
                        except (TypeError, ValueError, OverflowError):
                            delay = 0.0
                    delay = max(delay, client.delays["arxiv"], min(300.0, 2 ** attempt + 1))
                    LOG.warning("arXiv API returned 429; retry %d/%d in %.1f seconds",
                                attempt, client.retries, delay)
                    time.sleep(delay)
                except Exception as exc:
                    LOG.error("Date enrichment batch starting %s failed: %s", block[0], exc)
                    raise
            completed += len(block)
            if completed % progress_every == 0 or completed == len(pending):
                LOG.info("Reference dates: %d/%d unique arXiv IDs inspected", completed, len(pending))
    finally:
        conn.close()


def directory_size(path: Path) -> int:
    total = 0
    for folder, _, filenames in os.walk(path):
        for filename in filenames:
            try:
                total += (Path(folder) / filename).stat().st_size
            except OSError:
                pass
    return total


class MemorySampler:
    def __init__(self, interval=0.3):
        self.interval = interval
        self.samples = []
        self.stop_event = threading.Event()
        self.proc = psutil.Process() if psutil else None
        self.thread = None

    def start(self):
        if self.proc is None:
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        # Local guards let Pylance narrow both Optional values safely.
        proc = self.proc
        psutil_module = psutil
        if proc is None or psutil_module is None:
            return
        while not self.stop_event.is_set():
            try:
                self.samples.append(proc.memory_info().rss)
            except (OSError, psutil_module.Error):
                pass
            self.stop_event.wait(self.interval)

    def finish(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        return {"peak_ram_bytes": max(self.samples) if self.samples else None,
                "average_ram_bytes": round(sum(self.samples) / len(self.samples)) if self.samples else None,
                "ram_samples": len(self.samples)}


def export_results(root: Path, ids: list[str], run_metrics: dict | None = None) -> dict:
    papers = []
    refs_rows = []
    statuses = []
    per_paper_seconds = []
    total_versions = ok_versions = checked_versions = exact_metadata_versions = 0
    archive_bytes = latex_bytes = latex_files = 0
    max_downloaded_archive_bytes = 0
    refs_count_total = refs_valid_count = 0
    refs_s2_ok = 0
    discovery_seconds = 0.0
    conn = open_ref_cache(root)
    try:
        dates = dict(conn.execute("SELECT arxiv_id, submission_date FROM dates"))
    finally:
        conn.close()
    for i in ids:
        folder = paper_dir(root, i)
        paper = read_json(folder / "paper.json", {})
        latest = paper.get("latest_metadata")
        status = paper.get("status", "pending")
        versions = paper.get("latest_version", 0)
        total_versions += versions
        version_meta = []
        version_statuses = []
        for v in range(1, versions + 1):
            meta = read_json(folder / f"v{v}" / "metadata.json")
            if meta:
                version_meta.append(meta)
                if meta.get("metadata_fidelity") == "exact_version":
                    exact_metadata_versions += 1
            src = read_json(folder / f"v{v}" / "source_status.json", {})
            version_statuses.append(src.get("status", "pending"))
            if src.get("status") in ("ok", "no_latex", "no_source"):
                checked_versions += 1
            if src.get("status") == "ok":
                ok_versions += 1
            archive_bytes += src.get("archive_bytes", 0)
            max_downloaded_archive_bytes = max(max_downloaded_archive_bytes,
                                               src.get("archive_bytes", 0))
            latex_bytes += src.get("latex_bytes", 0)
            latex_files += src.get("tex_bib_files", 0)
        if latest:
            revisions = [m["version_updated"] for m in sorted(
                version_meta, key=lambda m: m["version"]) if m["version"] > 1]
            oai_history = read_json(folder / "versions_oai.json", [])
            if oai_history and len(revisions) < versions - 1:
                revisions = [v["date"] for v in oai_history if v["version"] > 1]
            papers.append({"arxiv_id": i, "title": latest.get("title", ""),
                           "authors": latest.get("authors", []),
                           "submission_date": latest.get("submission_date", ""),
                           "revised_dates": revisions,
                           "venue": latest.get("venue")})
        refs_data = read_json(folder / "references_all.json", {})
        if refs_data.get("status") == "ok":
            refs_s2_ok += 1
        ref_items = refs_data.get("references", [])
        refs_count_total += len(ref_items)
        for ref in ref_items:
            ref_id = ref.get("ref_arxiv_id")
            if not ref_id:
                continue
            refs_valid_count += 1
            refs_rows.append({
                "arxiv_id": i, "ref_arxiv_id": ref_id,
                "ref_title": ref.get("ref_title", ""),
                "ref_authors": ref.get("ref_authors", []),
                "ref_submission_date": dates.get(ref_id, ""),
                "ref_s2_id": ref.get("ref_s2_id", ""),
            })
        metrics = read_json(folder / "metrics.json", {})
        elapsed = sum(float(metrics.get(k, 0)) for k in (
            "discovery_seconds", "metadata_seconds", "source_seconds", "references_seconds"))
        discovery_seconds += metrics.get("discovery_seconds", 0)
        if status == "found":
            per_paper_seconds.append(elapsed)
        statuses.append({
            "arxiv_id": i, "discovery_status": status, "latest_version": versions,
            "versions_with_metadata": len(version_meta),
            "versions_metadata_exact": sum(m.get("metadata_fidelity") == "exact_version"
                                           for m in version_meta),
            "versions_source_checked": sum(x in ("ok", "no_latex", "no_source") for x in version_statuses),
            "versions_with_tex_bib": version_statuses.count("ok"),
            "s2_status": refs_data.get("status", "pending"),
            "s2_reference_count": len(ref_items),
            "arxiv_reference_count": sum(bool(x.get("ref_arxiv_id")) for x in ref_items),
            "elapsed_seconds_observed": round(elapsed, 3),
        })
    table_path = root / "tables"
    write_jsonl(table_path / "papers.jsonl", papers)
    write_jsonl(table_path / "references.jsonl", refs_rows)
    csv_path = table_path / "status.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(statuses[0]) if statuses else
                                ["arxiv_id", "discovery_status"])
        writer.writeheader()
        writer.writerows(statuses)
    succeeded_papers = sum(p["versions_with_tex_bib"] == p["latest_version"] and
                           p["latest_version"] > 0 for p in statuses)
    discovered = sum(x["discovery_status"] == "found" for x in statuses)
    summary = {
        "generated_at": utc_now(), "assigned_ids": len(ids),
        "assigned_start": ids[0] if ids else None,
        "assigned_end": ids[-1] if ids else None,
        "discovered_papers": discovered,
        "unavailable_ids": sum(x["discovery_status"] == "not_found" for x in statuses),
        "pending_discovery": sum(x["discovery_status"] == "pending" for x in statuses),
        "total_versions_expected": total_versions,
        "total_versions_source_checked": checked_versions,
        "total_versions_metadata_exact": exact_metadata_versions,
        "pending_exact_version_metadata": max(0, total_versions - exact_metadata_versions),
        "versions_with_tex_bib": ok_versions,
        "papers_all_versions_with_tex_bib": succeeded_papers,
        "publication_source_success_rate": round(succeeded_papers / discovered, 4) if discovered else None,
        "version_source_success_rate": round(ok_versions / total_versions, 4) if total_versions else None,
        "total_source_archive_bytes": archive_bytes,
        "total_extracted_latex_bytes": latex_bytes,
        "tex_bib_file_count": latex_files,
        "average_archive_bytes_per_checked_version": round(archive_bytes / checked_versions) if checked_versions else None,
        "average_latex_bytes_per_checked_version": round(latex_bytes / checked_versions) if checked_versions else None,
        "s2_successful_papers": refs_s2_ok,
        "reference_metadata_success_rate": round(refs_s2_ok / discovered, 4) if discovered else None,
        "references_total_s2": refs_count_total,
        "references_with_arxiv_id": refs_valid_count,
        "pending_s2_papers": sum(x["s2_status"] not in ("ok", "not_found") and
                                  x["discovery_status"] == "found" for x in statuses),
        "pending_source_versions": max(0, total_versions - checked_versions),
        "average_references_per_s2_paper": round(refs_count_total / refs_s2_ok, 2) if refs_s2_ok else None,
        "reference_date_enrichment_rate": round(sum(bool(x["ref_submission_date"]) for x in refs_rows) / len(refs_rows), 4) if refs_rows else None,
        "total_observed_discovery_seconds": round(discovery_seconds, 3),
        "average_observed_paper_seconds": round(sum(per_paper_seconds) / len(per_paper_seconds), 3) if per_paper_seconds else None,
        "maximum_observed_paper_seconds": round(max(per_paper_seconds), 3) if per_paper_seconds else None,
        "output_disk_bytes": 0,
    }
    # Avoid counting summary twice by defining clearly when measurement occurs.
    summary["output_disk_bytes"] = directory_size(root)
    # Only one source archive is kept temporarily at a time. Final working-data
    # bytes + largest temporary archive is a conservative approximate upper bound,
    # not a claim of direct, continuous peak-disk measurement.
    summary["approx_peak_disk_upper_bound_bytes"] = (
        summary["output_disk_bytes"] + max_downloaded_archive_bytes)
    if run_metrics:
        summary["last_run"] = run_metrics
    write_json(root / "summary.json", summary)
    LOG.info("Export: %d papers, %d reference rows, %d/%d source versions", len(papers),
             len(refs_rows), ok_versions, total_versions)
    return summary


def run(args) -> None:
    root = Path(args.output).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    ids = parse_range(args.start, args.end, args.max_papers)
    if not ids:
        raise ValueError("No assigned IDs")
    LOG.info("Assigned %s through %s: %d IDs", ids[0], ids[-1], len(ids))
    client = PacedClient(
        arxiv_delay=args.arxiv_delay,
        s2_delay=args.s2_delay,
        s2_key=os.environ.get("S2_API_KEY"),
        retries=args.retries,
        contact=os.environ.get("CRAWLER_CONTACT", ""),
    )
    sampler = MemorySampler()
    started = time.monotonic()
    sampler.start()
    phases = (["discover", "metadata", "sources", "references", "enrich-refs"]
              if args.phase == "all" else [args.phase])
    if args.discovery_backend == "oai" and args.phase == "all":
        phases = ["discover", "sources", "references", "enrich-refs"]
        LOG.warning("OAI-PMH provides accurate version dates but NOT historical titles/abstracts. "
                    "Exact-version metadata must be completed later via --phase metadata "
                    "when arXiv Atom API becomes available.")
    phase_wall = {}
    interrupted_error = None
    try:
        for phase in phases:
            t0 = time.monotonic()
            LOG.info("----- Phase: %s -----", phase)
            cooldowns = 0
            while True:
                try:
                    if phase == "discover":
                        discover(client, root, ids, args.batch_size, args.discovery_backend,
                                 args.progress_every)
                    elif phase == "metadata":
                        fetch_version_metadata(client, root, ids, args.batch_size)
                    elif phase == "sources":
                        fetch_sources(client, root, ids,
                                      int(args.max_archive_mb * 1024 * 1024),
                                      args.progress_every)
                    elif phase == "references":
                        fetch_references(client, root, ids, args.progress_every,
                                         backend=args.s2_backend,
                                         batch_size=args.s2_batch_size)
                    elif phase == "enrich-refs":
                        enrich_reference_dates(client, root, ids, args.batch_size,
                                               args.enrich_backend,
                                               args.progress_every,
                                               args.enrich_max_ids)
                    elif phase != "export":
                        raise ValueError(f"Unknown phase: {phase}")
                    break
                except RateLimitStop as exc:
                    if not args.wait_on_429 or cooldowns >= args.max_cooldowns:
                        raise
                    # Respect throttling: long pauses, no parallel workers, and
                    # never bypass access checks. Previously saved data is skipped.
                    minutes = args.cooldown_minutes * (2 ** cooldowns)
                    cooldowns += 1
                    LOG.warning(
                        "HTTP 429: %s. Cooling down for %.1f minutes "
                        "(%d/%d); press Ctrl+C safely to stop.",
                        exc, minutes, cooldowns, args.max_cooldowns,
                    )
                    time.sleep(minutes * 60)
                    LOG.info("Resuming %s from saved checkpoint", phase)
            phase_wall[phase] = round(time.monotonic() - t0, 3)
    except BaseException as exc:
        interrupted_error = str(exc)
        raise
    finally:
        memory = sampler.finish()
        metrics = {"at": utc_now(), "seconds": round(time.monotonic() - started, 3),
                   "interrupted_error": interrupted_error,
                   "phase_wall_seconds": phase_wall,
                   "discovery_backend": args.discovery_backend,
                   "arxiv_delay_seconds": client.delays["arxiv"],
                   "s2_delay_seconds": client.delays["s2"], **memory}
        metrics["output_disk_bytes_before_export"] = directory_size(root)
        logs = root / "runs.jsonl"
        with logs.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(metrics, ensure_ascii=False) + "\n")
        # A --max-papers trial must not replace a 5,000-paper report with a
        # misleading 20-paper summary. Export the complete assigned range.
        export_ids = parse_range(args.start, args.end)
        summary = export_results(root, export_ids, metrics)
        if interrupted_error:
            LOG.error("Run INTERRUPTED (%s). Checkpoint written: %s", interrupted_error,
                      root / "summary.json")
        else:
            gaps = {k: summary[k] for k in ("pending_discovery", "pending_source_versions",
                      "pending_s2_papers", "pending_exact_version_metadata")}
            LOG.info("Phase finished; coverage still to review: %s", gaps)
            LOG.info("Checkpoint saved: %s; %d discovered paper rows", root / "summary.json",
                     summary["discovered_papers"])


def main():
    parser = argparse.ArgumentParser(description="Full arXiv Milestone 1 crawler for HCMUS")
    parser.add_argument("--start", default="2607.13694")
    parser.add_argument("--end", default="2607.18693")
    parser.add_argument("--max-papers", type=int, default=None,
                        help="Trial only: process the first N IDs from the assigned range")
    parser.add_argument("--output", default="data", help="Working corpus directory")
    parser.add_argument("--phase", choices=["all", "discover", "metadata", "sources",
                                           "references", "enrich-refs", "export"], default="all")
    parser.add_argument("--discovery-backend", choices=["api", "oai"], default="oai",
                        help="oai uses official OAI-PMH arXivRaw when Atom API is rate-limited")
    parser.add_argument("--enrich-backend", choices=["api", "oai"], default="oai",
                        help="Use OAI-PMH for reference first-submission dates when Atom API blocks requests")
    parser.add_argument("--progress-every", type=int, default=3,
                        help="Emit a progress update after every N assigned IDs")
    parser.add_argument("--batch-size", type=int, default=30,
                        help="arXiv lookup batch size (1-100; reference-date API accepts 100)")
    parser.add_argument("--enrich-max-ids", type=int, default=None,
                        help="Limit IDs inspected by enrich-refs; useful for resumable trials")
    parser.add_argument("--arxiv-delay", type=float, default=3.2)
    parser.add_argument("--s2-delay", type=float, default=5.0,
                        help="Spacing between S2 requests; unauthenticated rate limits can still apply")
    parser.add_argument("--s2-backend", choices=["single", "batch"], default="single",
                        help="Use batch to request references for several papers at once")
    parser.add_argument("--s2-batch-size", type=int, default=5,
                        help="Keep small (1-10) due to S2 batch response-size limits")
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--max-archive-mb", type=float, default=200)
    parser.add_argument("--wait-on-429", action="store_true",
                        help="On rate limit, sleep and resume from saved checkpoint")
    parser.add_argument("--cooldown-minutes", type=float, default=60.0,
                        help="First HTTP 429 cooldown; subsequent waits double (default 60)")
    parser.add_argument("--max-cooldowns", type=int, default=2,
                        help="Limit of automatic waits for each phase (default 2)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.batch_size < 1 or args.batch_size > 100:
        parser.error("--batch-size must be from 1 to 100")
    if args.enrich_max_ids is not None and args.enrich_max_ids < 1:
        parser.error("--enrich-max-ids must be >= 1")
    if args.progress_every < 1:
        parser.error("--progress-every must be >= 1")
    if args.arxiv_delay < 3:
        parser.error("--arxiv-delay must be >= 3 seconds to respect arXiv rules")
    if not 1 <= args.s2_batch_size <= 20:
        parser.error("--s2-batch-size must be from 1 to 20")
    if args.s2_delay < 1:
        parser.error("--s2-delay must be >= 1 second")
    if args.max_papers is not None and args.max_papers < 1:
        parser.error("--max-papers must be >= 1")
    if args.cooldown_minutes < 15:
        parser.error("--cooldown-minutes must be at least 15; never hammer throttled APIs")
    if args.max_cooldowns < 0 or args.max_cooldowns > 10:
        parser.error("--max-cooldowns must be 0 to 10")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        run(args)
    except KeyboardInterrupt:
        LOG.error("Interrupted. Completed records were saved; rerun the same command to resume.")
        sys.exit(130)
    except (DiscoveryIncomplete, RateLimitStop, AccessDeniedStop) as exc:
        LOG.error("INCOMPLETE: %s", exc)
        LOG.error("Saved work is safe. Rerun the same command later to resume.")
        sys.exit(2)


if __name__ == "__main__":
    main()
