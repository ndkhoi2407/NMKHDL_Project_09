# Milestone 1 — Data Crawling

## 1. Overview

Milestone 1 focuses on constructing a raw corpus of arXiv publications from the assigned paper ID range. The crawling pipeline is responsible for discovering the assigned papers, identifying all available versions, downloading their full-text source files, collecting metadata, and retrieving reference metadata.

The collected corpus serves as the foundation for the subsequent milestones, particularly Milestone 2, where the LaTeX source is parsed and standardized.

The assigned range is:

- **Prefix:** `2608`
- **Starting ID:** `24007`
- **Ending ID:** `29006`
- **Number of assigned papers:** 5,000

The implementation is developed in Python and uses the arXiv API, OAI-PMH, direct arXiv source downloads, and the Semantic Scholar API.
## Milestone 1 Data Crawling Pipeline

The following diagram illustrates the overall workflow of the Milestone 1 data crawling process.

```{mermaid}
flowchart TD
    A["Assigned arXiv ID Range"] --> B["1. Paper Discovery<br/>arXiv API"]

    B --> C["2. Source Download<br/>All versions: LaTeX / PDF-only"]
    C --> D["3. Source Processing<br/>Extract archives, remove binary figures,<br/>preserve LaTeX figure commands"]

    B --> E["4. Metadata Collection<br/>arXiv OAI-PMH"]

    B --> F["5. Reference Collection<br/>Semantic Scholar API"]

    D --> G["Final M1 Corpus"]
    E --> G
    F --> G
```

*Figure: Overview of the Milestone 1 data crawling pipeline.*
---

## 2. Data Discovery

### 2.1 Discovery Strategy

The discovery stage resolves the assigned arXiv IDs and determines all available versions of each publication.

The arXiv API is used for targeted discovery because the project provides a specific range of paper IDs. For each assigned ID, the crawler retrieves the corresponding publication information and identifies its available versions.

Each version is subsequently processed independently so that the complete revision history of a publication can be preserved.

The crawler also applies request delays when communicating with the arXiv API to comply with its usage requirements.

### 2.2 Discovery Results

The discovery process successfully identified all papers in the assigned range.

| Metric | Result |
|---|---:|
| Assigned paper IDs | 5,000 |
| Papers found | 5,000 |
| IDs not found | 0 |
| IDs failed during discovery | 0 |
| Total versions identified | 6,037 |

The discovery stage therefore achieved complete coverage of the assigned ID range.

---

## 3. Full-text Source Crawling

### 3.1 Source Download

For every discovered version, the crawler retrieves the original source archive from arXiv.

Each version is stored separately to preserve the relationship between a publication and its revisions.

The crawler handles three possible outcomes:

- **OK:** the source archive was successfully downloaded.
- **PDF-only:** no usable TeX source is available.
- **Error:** the source could not be retrieved.

PDF-only versions are retained in the corpus rather than being discarded, as required by the project specification.

### 3.2 Source Cleaning

After downloading the source archives, the files are extracted and unnecessary binary figure files are removed.

The LaTeX source is preserved, including figure environments and commands such as:

```latex
\includegraphics
```

This allows the textual and structural information required by later parsing stages to remain intact while significantly reducing storage requirements.

The cleaned source contains the relevant `.tex` and `.bib` files for subsequent processing.

### 3.3 Crawling Results

The source crawling stage processed all 6,037 identified versions.

| Version status | Number |
|---|---:|
| Successfully downloaded | 5,734 |
| PDF-only | 284 |
| Withdrawn / HTTP 404 | 19 |
| **Total** | **6,037** |

The 19 HTTP 404 cases correspond to withdrawn versions and were verified against their corresponding arXiv pages.

---

## 4. Metadata Collection

### 4.1 OAI-PMH

Metadata is collected using the arXiv OAI-PMH service:

```text
https://oaipmh.arxiv.org/oai
```

The crawler retrieves the metadata required by the project, including:

- arXiv ID
- title
- authors
- submission date
- revision dates
- venue

The metadata process also preserves information about papers with multiple versions.

### 4.2 Metadata Results

| Metric | Result |
|---|---:|
| Papers processed | 5,000 |
| Metadata successfully collected | 5,000 |
| Metadata success rate | 100% |
| Papers with multiple versions | 879 |

The metadata collection stage therefore achieved complete coverage of the assigned papers.

---

## 5. Reference Collection

### 5.1 Semantic Scholar

Reference metadata is collected using the Semantic Scholar API.

For each paper, the crawler retrieves available references and their associated metadata, including:

- reference title
- authors
- publication date
- Semantic Scholar ID
- arXiv ID when available

All crawled reference metadata is retained locally. References with arXiv identifiers can subsequently be used to construct the final `references` table.

The implementation includes request delays, retries, and handling for temporary API errors.

### 5.2 Reference Results

| Metric | Result |
|---|---:|
| Papers processed | 5,000 |
| Successful Semantic Scholar records | 4,992 |
| Papers without S2 record | 8 |
| Reference collection success rate | 99.84% |

The reference collection stage therefore achieved high coverage while retaining papers for which no Semantic Scholar record was available.

---

## 6. Corpus Organization

The corpus is organized by publication and version so that source files, metadata, and reference information can be processed independently.

The general organization is:

```text
data/
├── sources/
│   └── <arxiv_id>/
│       ├── v1/
│       │   ├── *.tex
│       │   └── *.bib
│       ├── v2/
│       │   ├── *.tex
│       │   └── *.bib
│       └── ...
├── metadata/
└── references/
```

This structure preserves version information and separates the raw source corpus from metadata and reference data.

---

## 7. Final Corpus Statistics

The resulting corpus contains 5,000 assigned papers and 6,037 identified versions.

| Statistic | Value |
|---|---:|
| Assigned papers | 5,000 |
| Papers discovered | 5,000 |
| Total versions | 6,037 |
| Successfully downloaded versions | 5,734 |
| PDF-only versions | 284 |
| Withdrawn / 404 versions | 19 |
| Metadata success rate | 100% |
| Reference collection success rate | 99.84% |
| Average references per paper | 32.75 |

The discovery process achieved complete coverage of the assigned paper range. The main source-level exceptions were PDF-only versions and withdrawn versions.
### Distribution of Crawled Versions

The following chart shows the distribution of the 6,037 crawled versions by download status.

```{mermaid}
pie showData
    title Distribution of Crawled Versions
    "Successfully Downloaded" : 5734
    "PDF-only" : 284
    "Withdrawn / HTTP 404" : 19
```

*Figure: Distribution of crawled versions by download status.*

Successfully downloaded versions account for approximately 94.98% 
of the total corpus, while PDF-only versions represent 4.70%. 
Withdrawn versions account for only 0.31% of all crawled versions.

---

## 8. Performance Evaluation

The crawling pipeline was evaluated on a CPU-only Google Colab environment.

The benchmark records the total execution time, average processing time per paper, execution time of individual pipeline stages, memory consumption, disk usage, and final corpus size.

### 8.1 Runtime

The measured performance is summarized below.

| Metric | Result |
|---|---:|
| Total runtime | 50.16 hours |
| Average time per paper | 36.11 seconds |
| Discovery | 0.29 seconds/paper |
| Source download | 6.93 seconds/paper |
| Source cleaning | 0.0006 seconds/paper |
| Metadata | 26.11 seconds/paper |
| References | 3.07 seconds/paper |

The metadata collection stage is the main performance bottleneck, accounting for the largest proportion of the total execution time.

### Average Runtime per Paper

The following chart compares the average execution time of each crawling stage per paper, based on the benchmark.

```{mermaid}
xychart-beta
    title "Average Runtime per Paper"
    x-axis ["Discovery", "Download", "Processing", "Metadata", "References"]
    y-axis "Time (seconds)" 0 --> 30
    bar [0.0058, 6.9316, 0.0006, 26.109, 3.0666]
```

*Figure: Average execution time per paper across the five pipeline stages.*

Metadata collection is the most time-consuming stage, accounting for the largest portion of the total processing time.

### 8.2 Memory Usage

The crawler was monitored throughout execution to measure its memory consumption.

| Metric | Result |
|---|---:|
| Peak RAM | 49.37 MB |
| Average RAM | 34.10 MB |

The measured memory usage remains relatively small compared with the available memory of the execution environment.

### Memory Usage Evaluation

The following chart presents the peak and average memory consumption during the 5000-paper benchmark.

```{mermaid}
xychart-beta
    title "Memory Usage"
    x-axis ["Average RAM", "Peak RAM"]
    y-axis "Memory (MB)" 0 --> 60
    bar [34.10, 49.37]
```

*Figure: Average and peak memory usage during the benchmark.*

The pipeline consumed an average of 34.10 MB of memory, with a peak usage of 49.37 MB. These results indicate that the crawling process maintained relatively low memory consumption during the benchmark.

### 8.3 Disk Usage

Disk usage was monitored during the crawling process.

| Metric | Result |
|---|---:|
| Peak additional disk usage | 26.75 MB |
| Final corpus size | 1.08 GB |

The source-cleaning process reduces the amount of storage required by removing binary figure files while preserving the corresponding LaTeX commands.

### Disk Usage

The following chart compares the peak additional disk usage during the benchmark with the final corpus size.

```{mermaid}
xychart-beta
    title "Estimated Disk Usage for 5,000 Papers"
    x-axis ["Peak Additional Disk", "Final Corpus"]
    y-axis "Storage (GB)" 0 --> 3
    bar [2.81, 1.08]
```

*Figure: Estimated peak additional disk usage and final corpus.*

The benchmark reached a peak additional disk usage of approximately 28.11 MB. After processing, the final corpus occupied approximately 10.79 MB. These measurements indicate that the pipeline maintained relatively low disk usage during the 50-paper benchmark.

---

## 9. Performance Analysis

### 9.1 Runtime Analysis

The crawling pipeline is estimated to require approximately 50.16 hours to process the assigned 5,000 papers, with an average processing time of 36.11 seconds per paper.

Metadata collection is the most time-consuming stage, requiring approximately 26.11 seconds per paper. Source downloading takes approximately 6.93 seconds, while reference collection requires approximately 3.07 seconds per paper. In comparison, paper discovery and source processing contribute very little to the overall execution time.

These results indicate that external data retrieval operations account for most of the pipeline's execution time.

### 9.2 Bottleneck Analysis

Metadata collection represents the primary performance bottleneck, accounting for approximately 72.3% of the estimated total runtime.

This is mainly associated with OAI-PMH requests and the required request intervals. The pipeline must respect the service's access limitations, which affects the overall collection speed.

Source downloading is the second most time-consuming stage because the crawler retrieves source archives for multiple versions of each paper. Reference collection also requires external API requests and is subject to rate limits.

Therefore, improving request handling, retry strategies, and data retrieval efficiency could help reduce the overall execution time while maintaining compliance with external API restrictions.

### 9.3 Resource Usage Analysis

The pipeline records an average memory usage of approximately 34.10 MB and a peak memory usage of 49.37 MB.

The estimated peak additional disk usage is approximately 2.81 GB, while the estimated final corpus size is approximately 1.08 GB.

These results indicate that storage requirements remain manageable for the assigned dataset. Memory consumption is also relatively low, suggesting that the pipeline can process the collected data without requiring substantial memory resources.

### 9.4 Scalability Analysis

The crawling pipeline is designed to process the assigned dataset through separate discovery, downloading, metadata collection, and reference collection stages.

For the full range of 5,000 papers, the estimated execution time is approximately 50.16 hours, with an estimated final storage requirement of approximately 1.08 GB.

The main scalability challenge is the time required for external metadata and reference requests. Appropriate request scheduling, retry mechanisms, and incremental data saving are important for maintaining reliability when processing larger datasets.

---

## 10. Discussion

The implementation of Milestone 1 satisfies the main requirements of the assigned data crawling task and establishes a structured raw corpus for subsequent processing.

First, the discovery stage achieves complete coverage of the assigned range, identifying all 5,000 papers and their 6,037 available versions. The crawler also preserves different source availability cases, including PDF-only versions and withdrawn versions, ensuring that these records are not silently excluded from the dataset.

Second, metadata and reference information are collected through the required external services. The integration of arXiv OAI-PMH and Semantic Scholar provides essential bibliographic information and reference metadata for further analysis.

Third, the source-processing stage prepares the collected documents for Milestone 2. Binary figure files are removed to reduce storage requirements, while the original LaTeX source files, figure environments, and figure-related commands are preserved. This approach maintains the structural information needed for subsequent parsing.

Despite achieving the main crawling objectives, the pipeline faces several limitations. Its performance depends heavily on external APIs, whose request-rate restrictions limit the maximum collection speed. Metadata collection is the primary performance bottleneck, while source downloading and reference collection also require considerable network access.

Overall, the implementation provides a reliable foundation for the next milestone. However, processing larger datasets would benefit from improved request scheduling, more efficient network handling, and robust recovery mechanisms to minimize the impact of external service interruptions.

---

## 11. Conclusion

Milestone 1 successfully establishes the raw arXiv corpus required for the subsequent stages of the project. The crawling pipeline covers all 5,000 assigned papers and 6,037 versions, collecting source files, bibliographic metadata, and reference information.

The resulting corpus preserves the original LaTeX structure while removing unnecessary binary figure files, making it suitable for hierarchical parsing and standardization in Milestone 2.

The performance evaluation estimates a total execution time of approximately 50.16 hours, with an average processing time of 36.11 seconds per paper. Memory consumption reaches approximately 49.37 MB at peak, while the estimated final corpus size is approximately 1.08 GB.

Although external API rate limits remain the main constraint on crawling performance, the implemented pipeline provides the necessary data collection, storage, and recovery mechanisms to support the project's subsequent stages.

The completed corpus serves as the input for Milestone 2, which focuses on parsing LaTeX documents, constructing hierarchical structures, standardizing document elements, and extracting references into a unified format.