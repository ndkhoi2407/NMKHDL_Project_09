from sentence_extractor import (
    prepare_prose_text,
    split_sentences
)

sample = r"""
\begin{center}
{\Large\bfseries
Revenge of Monosemanticity
\par}
\end{center}

\begin{abstract}
Understanding how neural networks learn is important.
We study specialized neurons in MLPs.
\end{abstract}

\section{Introduction}

Neural networks learn useful representations.
This improves data efficiency.
"""

cleaned = prepare_prose_text(sample)

print("=== CLEANED TEXT ===")
print(cleaned)

print("\n=== SENTENCES ===")
for index, sentence in enumerate(split_sentences(cleaned), 1):
    print(f"{index}. {sentence}")