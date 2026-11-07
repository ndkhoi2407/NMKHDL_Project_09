# Milestone 3 — Reference Matching (HCMUS)

Statement: https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/matching/

Only NEW files under `src/milestone3/` and `tests/test_milestone3.py` implement this extension. All original Milestone 1 and 2 code/data remain untouched. Inputs are the already-exported JSONL tables under `data/tables` and `data/milestone2/tables`.

## Process

1. **Cleaning**: Unicode normalization, LaTeX command stripping, case folding, token filtering, DOI/arXiv-pattern extraction.
2. **Human labels**: `prepare` selects at least `5 * K` papers with 20+ BibTeX entries each and produces an **UNREVIEWED** CSV. Each member manually examines 5 papers, at least 20 entries each, with 100+ labels/member; set `label_status` to `matched` (and provide a valid `groundtruth_arxiv_id`) or `none` (blank ground truth). The suggestion columns are only annotation aids, never ground truth. Any reference must occur in that publication's Milestone 1 `references` rows. If manual labels are expanded, each additional entry must be uniquely identified.
3. **Automatic labels**: all BibTeX entries in >=10% of the *remaining 5,000-publication pool* (and >=2*K papers) are matched by conservative fuzzy-title/arXiv heuristics. A weak `auto_none` label means the matcher did not find a sufficiently confident match; it is not human confirmation of a nonmatch.
4. **Features and rationale**:
   - `title_token_jaccard` measures order-independent title vocabulary overlap.
   - `title_ref_coverage` and `title_cite_coverage` capture the two directions of title containment, including abbreviated titles.
   - `title_char_similarity` captures spelling and formatting variants after sufficient lexical overlap.
   - `bigram_jaccard` adds local phrase order to the unordered token signals.
   - `author_token_overlap` provides a separate identity cue from author metadata.
   - `year_agreement` is supporting evidence when the citation and reference years agree; `year_conflict` flags disagreement rather than silently treating it as agreement.
   - `arxiv_id_exact` detects a directly embedded arXiv identifier, a strong identifier cue.
   - `title_length_ratio` represents relative title completeness alongside directional coverage.
5. **Model**: supervised binary Logistic Regression with standardization and class balancing, trained on all publication-scoped entry–reference candidate pairs from the training papers. `train` refuses to run without reviewed manual labels, and holds out `K` manually labeled and `K` automatically labeled publications in *each* of validation and test. Publications do not leak between splits.
6. **Evaluation**: MRR@5 on every labeled BibTeX entry, with absent/top-5-missed truth contributing zero. Report separate manual-test and weak-auto-test scores; the latter is NOT proof of real matching accuracy.
7. **Outputs**: `data/milestone3/predictions.jsonl`, model joblib, split/label summaries, and six Parquet tables via exporter (requires `pyarrow`). Prediction rows cover **only selected train/valid/test publications**.

The report notebook recomputes all 10 implemented features for candidate pairs from the reviewed labels and shows a descriptive positive-vs-negative table and chart. For the 100 reviewed citations (five publications), this produces 1,220 pairs (41 positive, 1,179 negative). Mean title-reference coverage is 0.970 vs 0.130 and character similarity is 0.869 vs 0.110 for positive vs negative pairs. Mean year-conflict values are 0.512 vs 0.833; this is a supporting signal because publication years and arXiv submission years may differ. These sample statistics illustrate feature behavior; they are not feature-importance estimates or generalization evidence.

## Windows PowerShell (from `source_repo`)

```powershell
$env:PYTHONPATH = "$PWD;$PWD\src"
py -m pip install -r .\src\milestone3\requirements.txt
py -m src.milestone3.cli prepare --root . --output data\milestone3 --members 1
# Determine actual group size and RE-RUN prepare --members K before manual labeling.
# Train from the existing authoritative manual_labels_REVIEWED.csv.
# Do not run prepare or review again unless intentionally replacing these labels.
py -m src.milestone3.cli train --root . --output data\milestone3 --members 1
py -m src.milestone3.export --root . --output data\milestone3\huggingface_dataset --predictions data\milestone3\predictions.jsonl --min-id 2607.13694 --max-id 2607.18693
py -m unittest discover -s tests -v
```

The `--members 1` shown is an example for one member; replace with your actual K. No team member count was supplied, so **preparation is not a certified completed group assignment**.

### Public Hugging Face submission

The local source tables currently contain 5,000 distinct IDs from `2607.13694` through `2607.18693`, and every row in the six export inputs falls within that interval. Verify that these endpoints match the official registration sheet before publishing; the publisher requires both bounds and validates every row, preventing an unfiltered/group-wide corpus from being uploaded. The exporter removes only its previous `part-*.parquet` files in each table directory before writing the selected range, preventing stale shards from an earlier wider export from being included.

After confirming the range and export, authenticate locally and publish to a **public dataset repository on your own Hugging Face account**:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python314\Scripts\hf.exe" auth login
py -m src.milestone3.export --root . --output data\milestone3\huggingface_dataset --predictions data\milestone3\predictions.jsonl --min-id 2607.13694 --max-id 2607.18693
py -m src.milestone3.publish --dataset data\milestone3\huggingface_dataset --repo-id YOUR_USERNAME/YOUR_DATASET --min-id 2607.13694 --max-id 2607.18693 --confirm-public
```

Replace the example owner/name and use the exact range from the registration sheet if different. The publishing command validates every Parquet shard, table row total, and row ID before uploading; it refuses private repositories and does not change an existing repository's visibility. It uses the locally stored Hugging Face login. Never put an access token in this repository, a command argument, or a chat message. After it prints the public URL, open it in a logged-out browser, confirm all six Parquet configurations load, and paste the link in Moodle.

The current bundle is local and has not been published yet. Public publishing is blocked until manual review and retraining are complete. The personal repository ID is still required; the course submission is not complete until the public link is verified and submitted through Moodle.

## Limitations and release checklist
- `manual_labels_REVIEWED.csv` is the sole authoritative manual-label file: 100 entries (41 `matched`, 59 `none`). Do not use or retain alternate manual-label copies as training input.
- Year conflict is common even among positive pairs because BibTeX publication year and arXiv submission year may differ; treat year features as supporting signals, not hard identity rules.
- `pyarrow` is needed for Parquet export and `huggingface_hub` is needed for publishing. The exporter creates six sharded configurations; the separate publisher validates the individual range and uploads only the dataset card, export summary, and Parquet shards.
- Per-person Hugging Face datasets must be sliced by each student's officially assigned arXiv ID range; do not upload the group's complete range as an individual's assigned data.
- Do not commit datasets / raw TeX / model artifacts to GitHub source repo.
- Dataset labels must reflect the truth available at labeling time; automatically inferred `none` is a weak label, and should be audited manually.
