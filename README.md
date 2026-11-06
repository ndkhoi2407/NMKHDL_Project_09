# arXiv Data Crawling and Processing Pipeline

## 1. Project Overview

This project develops a data crawling and processing pipeline for arXiv publications. The goal is to collect scientific publications, retrieve their source files and metadata, and transform raw LaTeX documents into structured data for subsequent analysis and reference matching.

The project is organized into multiple milestones, with each milestone implementing a specific stage of the data processing workflow.

### Main Objectives

- Discover arXiv publications within a specified ID range.
- Download available versions of publication source files.
- Collect publication metadata and bibliographic references.
- Parse LaTeX documents and reconstruct their hierarchical structures.
- Normalize and deduplicate extracted document elements.
- Standardize bibliography records for downstream reference matching.

## 2. Project Milestones

### Milestone 1 – Data Crawling and Dataset Construction

Milestone 1 focuses on collecting the raw arXiv dataset and organizing the downloaded information.

Main functionalities:

- Discover publications within a specified arXiv ID range.
- Identify and download available versions of source files.
- Preserve the original LaTeX source structure.
- Remove unnecessary binary files from the downloaded corpus.
- Collect publication metadata.
- Retrieve bibliographic references using Semantic Scholar.
- Organize the collected data and generate dataset statistics.

### Milestone 2 – Hierarchical Parsing and Standardization

Milestone 2 transforms the raw LaTeX corpus from Milestone 1 into structured and standardized data.

Main functionalities:

- Identify the root LaTeX source file of each publication version.
- Recursively gather source files referenced through `\input` and `\include`.
- Extract document components, including headings, paragraphs, sentences, formulas, figures, tables, and lists.
- Reconstruct parent-child relationships between document elements.
- Normalize textual and mathematical content.
- Deduplicate identical elements across publication versions.
- Extract and standardize bibliography entries.
- Generate structured output tables for subsequent processing.

The main output consists of three datasets:

| Dataset | Description |
|---|---|
| `elements` | Stores distinct normalized document elements. |
| `hierarchy` | Stores version-specific parent-child relationships. |
| `bibtex` | Stores standardized bibliographic records. |

## 3. Dataset and Benchmark

Milestone 2 was evaluated using a dataset of 5,000 publications.

### Processing Statistics

| Metric | Result |
|---|---:|
| Publications requested | 5,000 |
| Publications OK | 4,909 |
| Publications partially processed | 91 |
| Publications with errors | 0 |
| Expected versions | 6,037 |
| Parsed versions | 5,631 |
| Empty versions | 305 |
| Versions with parsing errors | 101 |
| Version parsing success rate | 98.24% |
| Elements after deduplication | 3,039,897 |
| Hierarchy records | 3,676,875 |
| BibTeX records after deduplication | 539,202 |
| Hierarchy integrity errors | 0 |

### Performance Results

| Metric | Result |
|---|---:|
| Total benchmark runtime | 2,647.479 seconds |
| Average time per publication | 0.525 seconds |
| Peak RAM sampled | 3,084.94 MB |
| Output storage | 1,454.708 MB |

These results demonstrate the pipeline's ability to process a large collection of LaTeX publications and produce structured outputs while maintaining hierarchy integrity.

## 4. Project Structure

```text
NMKHDL_Project_09/
├── src/
│   ├── latex_gatherer.py
│   ├── latex_parser.py
│   ├── sentence_extractor.py
│   ├── mixed_extractor.py
│   ├── hierarchy_builder.py
│   ├── element_builder.py
│   ├── bibtex_parser.py
│   ├── m2_pipeline.py
│   ├── m2_benchmark.py
│   └── ...
├── tests/
├── .gitignore
└── README.md
```

The `src/` directory contains the implementation modules for LaTeX source gathering, parsing, element extraction, hierarchy construction, bibliography processing, and benchmarking.

The `tests/` directory contains automated tests for validating the main processing components.

## 5. Reports and Documentation

Detailed reports for each milestone are maintained in a separate report repository.

**Report Repository:**  
[https://github.com/khoabautroi/NMKHDL_G09_report](https://github.com/khoabautroi/NMKHDL_G09_report)

- [Milestone 1 – Data Crawling](https://github.com/khoabautroi/NMKHDL_G09_report/blob/24127061/milestone1/milestone1.md)
- [Milestone 2 – Hierarchical Parsing and Standardization](https://github.com/khoabautroi/NMKHDL_G09_report/blob/24127061/milestone2/milestone2.md)

The reports provide detailed explanations of the methodology, implementation, data organization, validation, and benchmark results.

## 6. Technologies

- **Python** – Main programming language.
- **LaTeX** – Source document format processed by the pipeline.
- **JSONL** – Structured output format.
- **Git and GitHub** – Version control and project collaboration.
- **Jupyter Book / Markdown / Mermaid** – Technical documentation and report visualization.

## 7. Future Work

The structured datasets generated by Milestones 1 and 2 provide the foundation for subsequent processing stages.

The next stage will focus on reference matching and connecting bibliographic information with the extracted document content.

Further improvements may include:

- More comprehensive support for custom LaTeX commands and environments.
- Improved mathematical expression normalization.
- More robust bibliography matching.
- Better memory and processing efficiency for larger datasets.

## 8. Project Documentation

The detailed reports for each project milestone are available through the project's GitHub Pages website.

**View Full Project Reports:**

[https://khoabautroi.github.io/NMKHDL_G09_report/](https://khoabautroi.github.io/NMKHDL_G09_report/)

The documentation includes:

- Milestone 1 – Data Crawling and Dataset Construction
- Milestone 2 – Hierarchical Parsing and Standardization
- Future milestone reports and project documentation.
