from pathlib import Path
import sys, unittest, tempfile, json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from element_builder import build_elements
from bibtex_parser import parse_bibtex_text, merge_bibtex_versions, rewrite_citation_keys
from m2_pipeline import process_publication

class M2CoreTests(unittest.TestCase):
    def test_same_clean_content_shares_id_across_versions(self):
        rows,ids=build_elements("2310.12345",{
            "v1":[{"kind":"sentence","content":"Same sentence."}],
            "v2":[{"kind":"sentence","content":"Same   sentence."}]})
        self.assertEqual(len(rows),1)
        self.assertEqual(ids["v1"][0],ids["v2"][0])

    def test_roots_are_version_specific(self):
        rows,ids=build_elements("2310.12345",{
            "v1":[{"kind":"document","content":"Version 1 root"}],
            "v2":[{"kind":"document","content":"Version 2 root"}]})
        self.assertEqual(len(rows),2)
        self.assertNotEqual(ids["v1"][0],ids["v2"][0])

    def test_bibtex_field_union_and_citation_rename(self):
        v1=parse_bibtex_text("@article{old,title={A Study},author={Alice A and Bob B},year={2020}}")
        v2=parse_bibtex_text("@article{new,title={A Study},doi={10.1/example}}")
        merged,maps=merge_bibtex_versions({"v1":v1,"v2":v2})
        self.assertEqual(len(merged),1)
        self.assertEqual(merged[0]["year"],2020)
        self.assertEqual(merged[0]["doi"],"10.1/example")
        self.assertEqual(merged[0]["authors"],["Alice A","Bob B"])
        self.assertEqual(rewrite_citation_keys(r"See \cite{new, other}.",maps["v2"]),
                         r"See \cite{old, other}.")

    def test_sample_publication_integrity(self):
        project=Path(__file__).resolve().parents[1]
        data=project/"data"
        if not (data/"2608-24007"/"v1").exists(): self.skipTest("sample corpus not present")
        elements,hierarchy,bibtex,stats=process_publication(
            {"id":"2608.24007","folder":"2608-24007","versions":["v1","v2"]},data)
        ids={x["element_id"] for x in elements}
        self.assertEqual(stats["versions_parsed"],2)
        self.assertTrue(elements)
        self.assertTrue(hierarchy)
        self.assertTrue(all(row["element_id"] in ids and row["parent_id"] in ids for row in hierarchy))
        self.assertTrue(all(isinstance(row["authors"],list) for row in bibtex))
        self.assertTrue(all(row["year"] is None or isinstance(row["year"],int) for row in bibtex))

if __name__=="__main__": unittest.main()
