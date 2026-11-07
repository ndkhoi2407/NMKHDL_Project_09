
"""Run with `python -m unittest discover -s tests -v` (no internet needed)."""

import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import crawler


class TestCrawler(unittest.TestCase):

    def test_range_exactly_5000(self):
        ids = crawler.parse_range("2607.13694", "2607.18693")

        self.assertEqual(len(ids), 5000)
        self.assertEqual(ids[0], "2607.13694")
        self.assertEqual(ids[-1], "2607.18693")
        self.assertEqual(
            crawler.parse_range("2607.13694", "2607.18693", 3),
            ["2607.13694", "2607.13695", "2607.13696"]
        )

    def test_atom_parsing_and_versions(self):
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:arxiv="http://arxiv.org/schemas/atom">
          <entry><id>http://arxiv.org/abs/2607.13694v3</id>
          <title>  Example   Title  </title>
          <published>2026-07-18T00:00:00Z</published>
          <updated>2026-10-01T00:00:00Z</updated>
          <author><name>Author A</name></author>
          <author><name>Author B</name></author>
          <arxiv:journal_ref>Journal Example</arxiv:journal_ref>
          </entry>
        </feed>'''

        result = crawler.parse_atom(xml)["2607.13694v3"]

        self.assertEqual(result["version"], 3)
        self.assertEqual(result["authors"], ["Author A", "Author B"])
        self.assertEqual(result["venue"], "Journal Example")
        self.assertEqual(result["title"], "Example Title")

    def test_oai_raw_version_dates_are_kept_distinct(self):
        oai = b"""<?xml version="1.0" encoding="utf-8"?>
        <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
        <GetRecord><record><metadata>
        <arXivRaw xmlns="http://arxiv.org/OAI/arXivRaw/">
            <id>2607.13694</id>
            <title>Latest title</title>
            <authors>A, B</authors>
            <abstract>Latest abstract</abstract>
            <version version="v1">
                <date>Mon, 20 Jul 2026 10:00:00 GMT</date>
            </version>
            <version version="v2">
                <date>Tue, 21 Jul 2026 11:00:00 GMT</date>
            </version>
            <version version="v3">
                <date>Wed, 22 Jul 2026 12:00:00 GMT</date>
            </version>
        </arXivRaw></metadata></record></GetRecord></OAI-PMH>"""

        meta, history = crawler.parse_oai_raw(
            oai, "2607.13694"
        )

        # Pylance: narrow Optional[dict] to dict.
        assert meta is not None

        self.assertEqual(meta["version"], 3)
        self.assertEqual(len(history), 3)
        self.assertEqual(
            history[0]["date"],
            "2026-07-20T10:00:00+00:00"
        )
        self.assertEqual(
            meta["metadata_fidelity"],
            "current_fields_with_version_dates"
        )

    def test_discovery_429_is_not_an_empty_success(self):

        class RejectingClient:
            def get(self, *args, **kwargs):
                raise crawler.HTTPError(
                    429,
                    "https://export.arxiv.org/api/query"
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = ["2607.13694"]

            with self.assertRaises(crawler.DiscoveryIncomplete):
                crawler.discover(
                    cast(crawler.PacedClient, RejectingClient()),
                    root,
                    ids,
                    30,
                    "api"
                )

            self.assertFalse(
                (
                    crawler.paper_dir(root, ids[0])
                    / "paper.json"
                ).exists()
            )
            self.assertTrue(
                (
                    crawler.paper_dir(root, ids[0])
                    / "discovery_error.json"
                ).exists()
            )

    def test_oai_backend_creates_version_history_without_inventing_titles(self):

        class FakeResp:
            def __init__(self, content):
                self.content = content

            def close(self):
                pass

        class FakeClient:
            def get(self, domain, url, *, params=None, stream=False):
                assert domain == "oai"
                assert params is not None

                actual = params["identifier"].split(":")[-1]

                xml = (
                    """<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
                    <GetRecord><record><metadata>
                    <arXivRaw xmlns="http://arxiv.org/OAI/arXivRaw/">
                    <id>{id}</id>
                    <title>A</title>
                    <authors>B</authors>
                    <version version="v1">
                        <date>Mon, 20 Jul 2026 10:00:00 GMT</date>
                    </version>
                    <version version="v2">
                        <date>Tue, 21 Jul 2026 11:00:00 GMT</date>
                    </version>
                    </arXivRaw></metadata></record></GetRecord></OAI-PMH>"""
                ).format(id=actual).encode()

                return FakeResp(xml)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            crawler.discover(
                cast(crawler.PacedClient, FakeClient()),
                root,
                ["2607.13694"],
                30,
                "oai"
            )

            paper = crawler.read_json(
                crawler.paper_dir(root, "2607.13694")
                / "paper.json"
            )

            self.assertEqual(paper["latest_version"], 2)

            self.assertTrue(
                (
                    crawler.paper_dir(root, "2607.13694")
                    / "versions_oai.json"
                ).exists()
            )
            self.assertFalse(
                (
                    crawler.paper_dir(root, "2607.13694")
                    / "v1"
                    / "metadata.json"
                ).exists()
            )
            self.assertTrue(
                (
                    crawler.paper_dir(root, "2607.13694")
                    / "v2"
                    / "metadata.json"
                ).exists()
            )

    def test_tar_extract_preserves_tex_and_excludes_figure(self):
        with tempfile.TemporaryDirectory() as tmp:
            arc = Path(tmp) / "source.tar.gz"

            with tarfile.open(arc, "w:gz") as tar:
                for name, payload in [
                    (
                        "main.tex",
                        b"\\begin{figure}\\includegraphics{x.png}\\end{figure}"
                    ),
                    (
                        "bib/refs.bib",
                        b"@article{example,title={Hi}}"
                    ),
                    (
                        "figs/x.png",
                        b"\x89PNG\x00\xff"
                    ),
                    (
                        "../escape.tex",
                        b"invalid"
                    ),
                ]:
                    ti = tarfile.TarInfo(name)
                    ti.size = len(payload)
                    tar.addfile(ti, io.BytesIO(payload))

            count, nbytes, archive_format = crawler.extract_sources(
                arc,
                Path(tmp) / "v1"
            )

            src = Path(tmp) / "v1" / "source"

            self.assertEqual(archive_format, "tar")
            self.assertEqual(count, 2)
            self.assertGreater(nbytes, 0)

            self.assertEqual(
                (src / "main.tex").read_bytes(),
                b"\\begin{figure}\\includegraphics{x.png}\\end{figure}"
            )

            self.assertTrue(
                (src / "bib" / "refs.bib").is_file()
            )
            self.assertFalse(
                (src / "figs" / "x.png").exists()
            )
            self.assertFalse(
                (Path(tmp) / "escape.tex").exists()
            )

    def test_pdf_only_creates_empty_source_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "pdf_only.src"
            archive.write_bytes(b"%PDF-1.7\nfile content\n")

            count, length, _ = crawler.extract_sources(
                archive,
                Path(tmp) / "v1"
            )

            self.assertEqual((count, length), (0, 0))
            self.assertEqual(
                list((Path(tmp) / "v1" / "source").iterdir()),
                []
            )

    def test_export_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = crawler.paper_dir(root, "2607.13694")

            meta = {
                "arxiv_id": "2607.13694",
                "version": 1,
                "title": "Test title",
                "authors": ["Test"],
                "submission_date": "2026-07-16T12:00:00Z",
                "venue": None,
                "version_updated": "2026-07-16T12:00:00Z"
            }

            crawler.write_json(
                folder / "paper.json",
                {
                    "status": "found",
                    "latest_version": 1,
                    "latest_metadata": meta
                }
            )

            crawler.write_json(
                folder / "v1" / "metadata.json",
                meta
            )

            crawler.write_json(
                folder / "v1" / "source_status.json",
                {
                    "status": "ok",
                    "archive_bytes": 120,
                    "latex_bytes": 10,
                    "tex_bib_files": 1
                }
            )

            crawler.write_json(
                folder / "references_all.json",
                {
                    "status": "ok",
                    "references": [
                        {
                            "ref_arxiv_id": "2301.12345",
                            "ref_title": "Reference",
                            "ref_authors": ["Someone"],
                            "ref_s2_id": "abc"
                        },
                        {
                            "ref_arxiv_id": None,
                            "ref_title": "A book"
                        }
                    ]
                }
            )

            conn = crawler.open_ref_cache(root)
            conn.execute(
                "INSERT INTO dates VALUES (?, ?, ?)",
                ("2301.12345", "2023-01-12T00:00:00Z", 1)
            )
            conn.commit()
            conn.close()

            summary = crawler.export_results(
                root,
                ["2607.13694"]
            )

            self.assertEqual(
                summary["discovered_papers"], 1
            )
            self.assertEqual(
                summary["references_total_s2"], 2
            )
            self.assertEqual(
                summary["references_with_arxiv_id"], 1
            )

            rows = [
                json.loads(line)
                for line in (
                    root / "tables" / "references.jsonl"
                ).read_text().splitlines()
            ]

            self.assertEqual(
                rows[0]["ref_submission_date"],
                "2023-01-12T00:00:00Z"
            )

            self.assertEqual(
                set(rows[0]),
                {
                    "arxiv_id",
                    "ref_arxiv_id",
                    "ref_title",
                    "ref_authors",
                    "ref_submission_date",
                    "ref_s2_id"
                }
            )


class TestOfflineEndToEnd(unittest.TestCase):

    def test_two_papers_multiple_versions_and_s2(self):

        class FakeResponse:
            def __init__(self, content=b"", jsondata=None):
                self.content = content
                self._jsondata = jsondata

            def close(self):
                pass

            def iter_content(self, chunk_size=1024 * 1024):
                yield self.content

            def json(self):
                return self._jsondata

        def atom_entry(identifier):
            match = crawler.VERSIONED.fullmatch(identifier)
            assert match is not None

            base = match.group(1)
            version_str = match.group(2)

            assert version_str is not None

            version = int(version_str)

            return (
                f'<entry><id>http://arxiv.org/abs/{identifier}</id>'
                f'<title>Paper {base}</title>'
                f'<published>2026-07-18T00:00:00Z</published>'
                f'<updated>2026-07-{18 + version:02d}T00:00:00Z</updated>'
                f'<author><name>Example</name></author></entry>'
            )

        class FakeClient:

            def get(self, domain, url, *, params=None, stream=False):

                if "api/query" in url:
                    assert params is not None

                    items = params["id_list"].split(",")
                    entries = []

                    for x in items:
                        if x == "2607.13694":
                            x += "v2"
                        elif x == "2607.13695":
                            x += "v1"
                        elif x == "2301.12345":
                            x += "v1"

                        if x.startswith(
                            (
                                "2607.13694",
                                "2607.13695",
                                "2301.12345"
                            )
                        ):
                            entries.append(atom_entry(x))

                    xml = (
                        '<feed xmlns="http://www.w3.org/2005/Atom">'
                        + "".join(entries)
                        + "</feed>"
                    )

                    return FakeResponse(xml.encode())

                if "/src/" in url:
                    identifier = url.rsplit("/", 1)[-1]

                    if identifier == "2607.13694v2":
                        return FakeResponse(b"%PDF-1.7\n")

                    buf = io.BytesIO()

                    with tarfile.open(
                        fileobj=buf,
                        mode="w:gz"
                    ) as tf:
                        content = (
                            b"\\documentclass{article}"
                            b"\\begin{document}"
                            b"Demo"
                            b"\\end{document}"
                        )
                        member = tarfile.TarInfo("main.tex")
                        member.size = len(content)
                        tf.addfile(member, io.BytesIO(content))

                    return FakeResponse(buf.getvalue())

                if domain == "s2":
                    if "2607.13695" in url:
                        raise crawler.HTTPError(404, url)

                    return FakeResponse(
                        jsondata={
                            "data": [
                                {
                                    "citedPaper": {
                                        "paperId": "s2ref",
                                        "title": "Ref",
                                        "authors": [
                                            {"name": "Ref Author"}
                                        ],
                                        "publicationDate": "2023-03-01",
                                        "externalIds": {
                                            "ArXiv": "2301.12345"
                                        }
                                    }
                                },
                                {
                                    "citedPaper": {
                                        "paperId": "s2book",
                                        "title": "Book",
                                        "authors": [],
                                        "externalIds": {}
                                    }
                                }
                            ]
                        }
                    )

                raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = ["2607.13694", "2607.13695"]

            # FakeClient is intentionally a lightweight test double.
            client = cast(crawler.PacedClient, FakeClient())

            crawler.discover(client, root, ids, 2)
            crawler.fetch_version_metadata(
                client, root, ids, 2
            )
            crawler.fetch_sources(
                client, root, ids, 10_000_000
            )
            crawler.fetch_references(
                client, root, ids
            )
            crawler.enrich_reference_dates(
                client,
                root,
                ids,
                2,
                backend="api"
            )

            summ = crawler.export_results(root, ids)

            self.assertEqual(
                summ["total_versions_expected"], 3
            )
            self.assertEqual(
                summ["total_versions_source_checked"], 3
            )
            self.assertEqual(
                summ["versions_with_tex_bib"], 2
            )
            self.assertEqual(
                summ["references_with_arxiv_id"], 1
            )

            self.assertEqual(
                crawler.read_json(
                    crawler.paper_dir(root, ids[0])
                    / "v2"
                    / "source_status.json"
                )["status"],
                "no_latex"
            )

            refs = [
                json.loads(line)
                for line in (
                    root / "tables" / "references.jsonl"
                ).read_text().splitlines()
            ]

            self.assertEqual(
                refs[0]["ref_submission_date"],
                "2026-07-18T00:00:00Z"
            )


if __name__ == "__main__":
    unittest.main()
