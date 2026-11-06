# Milestone 2 — Hierarchical Parsing and Standardization

## 1. Overview

Milestone 2 focuses on transforming the raw LaTeX corpus collected in Milestone 1 into structured and standardized data. While Milestone 1 is responsible for discovering publications, downloading their source files, and collecting metadata, Milestone 2 processes the collected LaTeX documents to extract their textual and structural information.

LaTeX documents often consist of multiple source files, complex formatting commands, mathematical expressions, figures, tables, and bibliographic entries. Therefore, processing the source files independently is insufficient to reconstruct the complete document structure.

The main objectives of Milestone 2 are:

- Identify the root LaTeX source file of each publication version.
- Recursively gather relevant source files through `\input` and `\include` commands.
- Extract document components and reconstruct their hierarchical relationships.
- Normalize textual and mathematical content.
- Deduplicate identical elements across different publication versions.
- Extract and standardize bibliographic entries into a unified BibTeX representation.
- Generate structured output tables for subsequent reference-matching tasks.

The implementation is developed in Python and organized into separate modules to support maintainability, testing, and independent processing stages.

The resulting dataset consists of three main tables: `elements`, `hierarchy`, and `bibtex`.

---

## 2. Milestone 2 Processing Pipeline

The overall workflow consists of several sequential processing stages, beginning with the raw LaTeX sources and ending with standardized structured outputs.

### 2.1. Pipeline Architecture

The following diagram illustrates the overall Milestone 2 processing pipeline.

```{mermaid}
flowchart TD
    A["M1 LaTeX Corpus"] --> B["1. Root File Discovery"]
    B --> C["2. Recursive Source Gathering"]
    C --> D["3. LaTeX Parsing"]
    D --> E["4. Document Structure Extraction"]
    E --> F["5. Content Normalization"]
    F --> G["6. Cross-version Deduplication"]
    D --> H["7. Bibliography Extraction"]
    H --> I["8. BibTeX Standardization"]
    G --> J["Elements Table"]
    G --> K["Hierarchy Table"]
    I --> L["BibTeX Table"]
```

*Figure: Overview of the Milestone 2 hierarchical parsing and standardization pipeline.*

### 2.2. Implementation Structure

The implementation is divided into multiple Python modules under the `src/` directory.

| Module | Main Responsibility |
|---|---|
| `latex_gatherer.py` | Discover root files and gather recursively included LaTeX sources |
| `latex_parser.py` | Parse LaTeX documents and extract structural components |
| `sentence_extractor.py` | Extract and clean sentence-level textual content |
| `mixed_extractor.py` | Extract mixed textual and mathematical elements |
| `element_builder.py` | Normalize elements and assign identifiers across versions |
| `hierarchy_builder.py` | Construct parent-child relationships |
| `bibtex_parser.py` | Extract and standardize bibliography entries |
| `m2_pipeline.py` | Coordinate the complete M2 processing workflow |
| `m2_benchmark.py` | Execute the benchmark and collect performance statistics |

This modular architecture separates source gathering, parsing, standardization, bibliography processing, and performance evaluation.

---

## 3. LaTeX Source Discovery and Gathering

### 3.1. Root LaTeX File Identification

A publication may contain multiple `.tex` files, but only one file normally serves as the main entry point of the document.

Processing every `.tex` file independently may introduce duplicated content, unrelated auxiliary files, or incomplete document structures.

To address this issue, the pipeline searches for the root LaTeX file containing the `\documentclass` declaration.

The identified root file becomes the starting point for reconstructing the complete publication.

### 3.2. Recursive Source Gathering

LaTeX documents commonly divide their contents into multiple files using commands such as:

```latex
\input{sections/introduction}
\include{sections/methodology}
```

The source-gathering module recursively follows reachable `\input` and `\include` commands.

The gathering process preserves compilation order so that the resulting document follows the original source organization.

Commented-out commands are excluded to avoid processing files that are not part of the active document.

The implementation also avoids processing unrelated auxiliary files that are not reachable from the root source.

### 3.3. Handling Multiple Publication Versions

Each publication may have several versions, such as `v1`, `v2`, and subsequent revisions.

The pipeline processes each version independently before performing publication-wide element deduplication.

This approach preserves version-specific document structures while allowing unchanged content to be shared across revisions.

The pipeline also accounts for publications without usable TeX sources. Such versions are retained as empty processing records rather than being silently discarded.

---

## 4. Document Structure Extraction

### 4.1. Hierarchical Document Representation

After gathering the complete LaTeX source, the parser extracts document components and reconstructs their structural relationships.

The document is represented as a hierarchy in which higher-level components contain lower-level components.

The main structural levels include:

- Document root.
- Abstract and other special document sections.
- Sections and subsections.
- Paragraphs.
- Sentences.
- Mathematical formulas.
- Figures and tables.
- Lists and individual list items.

The following diagram illustrates a simplified example of the resulting hierarchy.

```{mermaid}
flowchart TD
    A["Document Root"] --> B["Abstract"]
    A --> C["Section 1"]
    A --> D["Section 2"]
    A --> E["References"]

    C --> F["Subsection 1.1"]
    C --> G["Paragraph 1"]
    F --> H["Sentence 1"]
    F --> I["Sentence 2"]
    F --> J["Formula"]

    D --> K["Paragraph 2"]
    D --> L["Figure"]
    D --> M["List"]
    M --> N["List Item 1"]
    M --> O["List Item 2"]
```

*Figure: Simplified hierarchical representation of a parsed LaTeX document. References are processed separately and excluded from the document hierarchy.*

### 4.2. Heading and Section Extraction

The parser recognizes LaTeX sectioning commands and uses them to construct the document hierarchy.

These commands include:

- `\section`
- `\subsection`
- `\subsubsection`
- `\paragraph`
- `\subparagraph`

The extracted headings are represented as structural elements and connected to their corresponding parent sections.

### 4.3. Paragraph and Sentence Extraction

Paragraphs are extracted as groups of related textual content.

The sentence extraction module further divides paragraph content into individual sentences.

Before sentence extraction, the text is cleaned to remove unnecessary formatting commands and normalize whitespace.

This allows sentence-level elements to be represented independently while preserving their original position in the document hierarchy.

### 4.4. Mathematical Formula Extraction

Mathematical expressions are extracted separately from ordinary prose.

The parser handles common inline and display mathematical environments, including expressions enclosed in mathematical delimiters and environments such as:

- `equation`
- `align`
- `gather`
- `multline`
- `displaymath`

Extracted formulas are represented as independent formula elements.

This separation allows mathematical content to be processed and deduplicated independently from textual elements.

### 4.5. Figure, Table, and List Extraction

Figures and tables are represented as structural elements in the hierarchy.

Following the milestone requirements, tables are classified under the figure element category.

Lists are represented as list blocks, with individual list items maintained as their children.

This approach preserves the relationship between a list and its constituent items.

### 4.6. Special Sections and Exclusions

The parser retains important document components, including:

- Abstract.
- Acknowledgements.
- Appendices.

References and bibliography sections are excluded from the ordinary document hierarchy because their entries are handled separately through the bibliography processing stage.

This separation prevents bibliographic entries from being mixed with the publication's ordinary textual content.

---

## 5. Content Standardization and Deduplication

### 5.1. Text Normalization

Raw LaTeX content may contain inconsistent whitespace, Unicode representations, and formatting-related differences.

The implementation applies normalization before assigning element identifiers.

The normalization process includes:

- Unicode normalization using NFKC.
- Standardization of line endings.
- Reduction of repeated spaces and tabs.
- Removal of unnecessary whitespace around line breaks.
- Reduction of excessive consecutive blank lines.
- Trimming of leading and trailing whitespace.

These operations produce a more consistent representation of extracted content.

### 5.2. Element Identification

Each distinct extracted element receives an identifier based on its publication, element type, and assigned counter.

The identifier prefixes distinguish different element categories.

| Element Type | Identifier Prefix |
|---|---|
| Document | `root` |
| Heading | `h` |
| Paragraph | `p` |
| Sentence | `s` |
| Formula | `f` |
| Figure | `fig` |
| List | `list` |
| List item | `li` |
| Abstract | `a` |
| Acknowledgements | `ack` |

For example, an element identifier may follow the format:

```text
2608.24007#s1
2608.24007#s2
2608.24007#f1
```

The identifiers allow elements to be referenced consistently across the output tables.

### 5.3. Cross-version Deduplication

Different versions of the same publication frequently contain unchanged paragraphs, sentences, headings, or formulas.

Storing every repeated element separately would increase the size of the output dataset and make subsequent processing less efficient.

To address this issue, the implementation performs deduplication using the normalized element type and content.

Two elements are considered identical when they have the same element type and the same normalized content.

Identical elements across different versions share the same `element_id`.

Document root nodes are treated separately because each publication version represents a distinct document structure.

The deduplication process reduces redundant content while preserving version-specific hierarchy information.

### 5.4. Position Preservation

During element construction, the implementation preserves the positional alignment between the original extracted nodes and their assigned identifiers.

Empty nodes receive `None` rather than being removed from the identifier list.

This prevents index mismatches during hierarchy construction and allows the hierarchy builder to maintain the correct parent-child relationships.

---

## 6. Bibliography Processing

### 6.1. Bibliography Extraction

Bibliographic information can be stored in external `.bib` files or embedded directly in LaTeX documents through `\bibitem` commands.

The bibliography processing module handles these sources and converts embedded bibliography entries into a BibTeX-compatible representation.

The resulting records provide standardized bibliographic information for downstream reference matching.

### 6.2. BibTeX Standardization

The pipeline extracts bibliographic entries and processes their available metadata.

Typical BibTeX fields include:

- Citation key.
- Entry type.
- Title.
- Author.
- Year.
- Journal or conference.
- DOI.
- URL.

Entries with incomplete metadata are retained when possible, rather than requiring every field to be present.

### 6.3. Cross-version Bibliography Deduplication

The same reference may appear in different publication versions under different citation keys.

The implementation merges bibliography records across versions and combines available fields.

When duplicate records are identified, a unified citation key is selected and citation references are rewritten to use the selected key.

This ensures that the final bibliography representation is more consistent across publication versions.

---

## 7. Output Data Structure

The M2 pipeline produces three primary output tables.

### 7.1. Elements Table

The `elements` table stores distinct normalized document components.

| Field | Description |
|---|---|
| `element_id` | Identifier of the extracted element |
| `arxiv_id` | Publication identifier |
| `kind` | Element category |
| `content` | Normalized textual or mathematical content |

Each distinct normalized element is stored once per publication.

### 7.2. Hierarchy Table

The `hierarchy` table represents the structural relationships between elements in each publication version.

| Field | Description |
|---|---|
| `arxiv_id` | Publication identifier |
| `version` | Publication version |
| `element_id` | Identifier of the child element |
| `parent_id` | Identifier of its parent element |

Unlike the elements table, the hierarchy table preserves version-specific structural relationships.

An element shared across multiple versions can therefore have different parent-child relationships depending on the document structure of each version.

### 7.3. BibTeX Table

The `bibtex` table stores standardized bibliographic records.

It contains the publication identifier, citation key, entry type, and available bibliographic fields.

The table is designed to provide a consistent reference representation for the reference-matching stage in Milestone 3.

### 7.4. Output Files

The pipeline generates the following JSONL files:

```text
m2_benchmark_output/
├── elements.jsonl
├── hierarchy.jsonl
├── bibtex.jsonl
├── paper_stats.jsonl
├── summary.json
└── benchmark.json
```

Each JSONL file contains one JSON record per line, allowing the outputs to be processed incrementally without loading the complete dataset into memory.

The summary and benchmark files provide aggregated processing statistics and performance measurements.

---

## 8. Testing and Validation

### 8.1. Unit Testing

The implementation includes dedicated tests for the main parsing and standardization components.

The test suite covers:

- Root source identification and compilation order.
- Document order reconstruction.
- Heading extraction and hierarchy construction.
- Sentence cleaning and extraction.
- Mathematical environment extraction.
- Formula context handling.
- Element identifier assignment.
- Cross-version deduplication.
- Bibliography processing.
- Hierarchy integrity.

The core automated test suite completed successfully, with four tests passing.

Additional diagnostic scripts were used to evaluate specific parsing cases and identify edge cases in LaTeX processing.

### 8.2. Hierarchy Integrity Validation

A key validation requirement is ensuring that every hierarchy reference points to a valid element.

The pipeline checks hierarchy integrity after element construction and deduplication.

The recovery and final processing runs reported zero hierarchy integrity errors.

This indicates that the generated hierarchy records maintained valid element references in those runs.

### 8.3. Full Dataset Processing

The pipeline was executed on the complete dataset of 5,000 publications.

During the initial execution, some publications encountered processing errors caused by positional misalignment between extracted nodes and assigned element identifiers.

The implementation was subsequently corrected to preserve positional alignment, including empty nodes.

The affected publications were processed again using a recovery run, and the results were merged with the original output.

The final merged dataset contained no publication-level processing errors, although some publications were classified as partially processed.

---

## 9. Benchmark and Performance Evaluation

### 9.1. Experimental Environment

The benchmark evaluates the M2 pipeline using a CPU-based Python execution environment and the complete input dataset of 5,000 publications. The benchmark records processing statistics, wall-clock runtime, memory consumption, and the storage size of the generated outputs.

| Configuration | Value |
|---|---|
| Execution mode | CPU-based |
| Python Version | 3.14.2 |
| CPU Architecture | x86_64 |
| Input Publications | 5,000 |
| Hardware Accelerator | Not used |

The environment details above describe the software and execution mode relevant to interpreting the benchmark. Runtime and memory measurements may vary across machines and execution sessions.

### 9.2. Dataset Statistics

The dataset contains 5,000 publications. A scan of the available version directories produced the following distribution:

| Number of Versions | Publications |
|---:|---:|
| 1 | 4,137 |
| 2 | 739 |
| 3 | 98 |
| 4 | 22 |
| 5 | 3 |
| 6 | 1 |

```{mermaid}
xychart-beta
    title "Publication Version Distribution"
    x-axis ["1 version", "2 versions", "3 versions", "4 versions", "5 versions", "6 versions"]
    y-axis "Number of Publications" 0 --> 4500
    bar [4137, 739, 98, 22, 3, 1]
```

*Figure: Distribution of available version directories across the 5,000 publications.*

The directory scan accounts for 6,018 version directories. The benchmark metadata records 6,037 expected versions; therefore, the two counts are reported separately rather than treated as interchangeable. Most publications have one available version, while only a small proportion contain multiple revisions.

### 9.3. Processing Statistics

The following table summarizes the processing results for the complete dataset.

| Metric | Result |
|---|---:|
| Publications requested | 5,000 |
| Publications successfully processed | 4,909 |
| Publications partially processed | 91 |
| Publications with errors | 0 |
| Expected versions | 6,037 |
| Parsed versions | 5,631 |
| Empty versions | 305 |
| Versions with parsing errors | 101 |
| Version parse success rate | 98.24% |
| Elements before deduplication | 3,682,739 |
| Elements after deduplication | 3,039,897 |
| Hierarchy rows | 3,676,875 |
| Hierarchy integrity errors | 0 |
| BibTeX entries before deduplication | 858,163 |
| BibTeX entries after deduplication | 539,202 |

A publication classified as partially processed may contain one or more versions that are empty or could not be parsed, even though the publication itself did not result in a publication-level processing error.

### 9.4. Runtime Performance

The benchmark records total wall-clock time and average processing time per requested publication.

| Performance Metric | Result |
|---|---:|
| Pipeline wall-clock runtime | 2,624.851 seconds (43.75 minutes) |
| Total benchmark wall-clock runtime, including benchmark overhead | 2,647.479 seconds (44.12 minutes) |
| Average pipeline runtime per publication | 0.525 seconds |

The average processing time is calculated as:

\[
T_{\text{avg}} = \frac{T_{\text{total}}}{N}
\]

where:

- \(T_{\text{total}}\) is the total benchmark wall-clock time.
- \(N\) is the number of requested publications.

The average is calculated from the pipeline wall-clock runtime (2,624.851 seconds), excluding the additional benchmark overhead. For 5,000 publications, this gives approximately 0.525 seconds per publication.

### 9.5. Memory Usage

Memory consumption is sampled during execution to estimate the peak RAM usage.

| Memory Metric | Result |
|---|---:|
| Peak RAM usage (sampled) | 3,084.94 MB |
| RAM at benchmark completion | 2,930.10 MB |

The peak value is the maximum observed by the sampling process; it is not a guaranteed instantaneous system-wide maximum. Memory usage is relevant because the pipeline processes many source files and creates large collections of extracted elements and hierarchy records.

### 9.6. Output Storage

The benchmark measures the total storage occupied by the generated output files.

| Storage Metric | Result |
|---|---:|
| Total output storage | 1,454.708 MB (approximately 1.42 GiB) |

The available benchmark summary reports the aggregate output size. Individual file sizes are not included here because separate per-file measurements are not available in the recorded results. The measurement covers generated outputs rather than the original input corpus.

### 9.7. Deduplication Effectiveness

Deduplication reduces the number of stored element and bibliography records.

| Dataset | Before Deduplication | After Deduplication | Records Removed |
|---|---:|---:|---:|
| Elements | 3,682,739 | 3,039,897 | 642,842 |
| BibTeX | 858,163 | 539,202 | 318,961 |

```{mermaid}
xychart-beta
    title "Records Before and After Deduplication"
    x-axis ["Elements before", "Elements after", "BibTeX before", "BibTeX after"]
    y-axis "Number of Records" 0 --> 4000000
    bar [3682739, 3039897, 858163, 539202]
```

*Figure: Record counts before and after deduplication for elements and bibliography entries.*

The results show that deduplication removed 642,842 repeated element records and 318,961 repeated bibliography records. This reduces redundant storage while the hierarchy table continues to preserve version-specific structural relationships.

### 9.8. Benchmark Analysis

The benchmark provides evidence of the pipeline's processing efficiency and output characteristics:

1. **Processing efficiency:** The pipeline processed 5,000 requested publications in approximately 44.12 minutes, with an average of 0.525 seconds per publication.
2. **Processing completeness:** No publication-level errors remained in the final results. However, 91 publications were partially processed, and 101 expected versions were recorded as parsing errors. These cases should be distinguished from fully parsed versions.
3. **Memory usage:** The sampled peak RAM usage was approximately 3.01 GiB, indicating the memory required for processing this corpus under the measured execution conditions.
4. **Storage efficiency:** The generated output occupied approximately 1.42 GiB. Deduplication removed a substantial number of repeated element and bibliography records.
5. **Structural consistency:** The benchmark reported zero hierarchy integrity errors, indicating that all generated hierarchy references passed the implemented integrity check.

These measurements provide a quantitative baseline for evaluating future optimizations and comparing subsequent milestones. They should be interpreted in the context of the recorded execution environment and benchmark procedure.

---

## 10. Limitations and Future Improvements

Although the implementation handles the main requirements of hierarchical LaTeX parsing and standardization, several limitations remain.

First, LaTeX documents may contain custom commands, uncommon environments, or complicated formatting conventions that are difficult to interpret consistently.

Second, mathematical expressions may be represented in different syntactic forms despite having equivalent meanings. The current normalization approach primarily addresses textual and syntactic consistency rather than complete mathematical equivalence.

Third, bibliography entries may contain incomplete or inconsistent metadata. Such differences can make it difficult to identify duplicate references reliably.

Fourth, complex document structures and unusual nesting patterns may require additional parsing rules to improve hierarchy reconstruction.

Future improvements could focus on expanding support for custom LaTeX environments, improving formula normalization, strengthening bibliography matching, and optimizing memory usage for larger corpora.

---

## 11. Conclusion

Milestone 2 establishes a structured representation of the arXiv publications collected in Milestone 1.

The implemented pipeline identifies root LaTeX files, reconstructs multi-file documents, extracts hierarchical components, normalizes textual and mathematical content, deduplicates repeated elements across publication versions, and standardizes bibliography records.

The resulting `elements`, `hierarchy`, and `bibtex` tables provide the structured information required for subsequent reference-matching operations in Milestone 3.

Unit testing and full-dataset processing demonstrate the implementation of the main parsing and standardization components. The benchmark provides quantitative evidence of the pipeline's processing efficiency, memory requirements, output storage, and hierarchy consistency.

Overall, Milestone 2 transforms the raw LaTeX corpus into a standardized dataset that serves as the foundation for the next stage of the project.