
import re


# ============================================================
# 1. REMOVE NON-SEMANTIC LATEX COMMANDS
# ============================================================

def remove_comments(text: str) -> str:
    """
    Remove LaTeX comments while preserving escaped percent signs.
    """

    result = []

    for line in text.splitlines():
        output = []
        i = 0

        while i < len(line):
            char = line[i]

            if char == "%":
                # Count consecutive backslashes before %.
                backslashes = 0
                j = i - 1

                while j >= 0 and line[j] == "\\":
                    backslashes += 1
                    j -= 1

                # An even number means % starts a comment.
                if backslashes % 2 == 0:
                    break

            output.append(char)
            i += 1

        result.append("".join(output))

    return "\n".join(result)


def remove_environment(
    text: str,
    environment: str,
    preserve_content: bool = False
) -> str:
    """
    Remove an environment or its wrappers.

    preserve_content=True:
        Remove only \\begin and \\end, keeping the body.

    preserve_content=False:
        Remove the entire environment, including its body.

    Supports nested occurrences of the same environment.
    """

    env_name = re.escape(environment)

    begin_pattern = re.compile(
        rf"\\begin\s*\{{{env_name}\}}"
    )

    end_pattern = re.compile(
        rf"\\end\s*\{{{env_name}\}}"
    )

    token_pattern = re.compile(
        rf"\\begin\s*\{{{env_name}\}}"
        rf"|\\end\s*\{{{env_name}\}}"
    )

    result = []
    cursor = 0

    while True:
        begin_match = begin_pattern.search(text, cursor)

        if not begin_match:
            result.append(text[cursor:])
            break

        result.append(text[cursor:begin_match.start()])

        depth = 1
        body_start = begin_match.end()
        body_end = None
        environment_end = None

        for match in token_pattern.finditer(text, body_start):
            if begin_pattern.fullmatch(match.group()):
                depth += 1

            elif end_pattern.fullmatch(match.group()):
                depth -= 1

                if depth == 0:
                    body_end = match.start()
                    environment_end = match.end()
                    break

        if environment_end is None:
            # Malformed environment: preserve remaining source.
            result.append(text[begin_match.start():])
            break

        if preserve_content:
            result.append(text[body_start:body_end])

        cursor = environment_end

    return "".join(result)


def remove_heading_commands(text: str) -> str:
    """
    Remove sectioning commands and their titles.
    """

    pattern = re.compile(
        r"\\(?:part|chapter|section|subsection|subsubsection|"
        r"paragraph|subparagraph)\*?"
        r"(?:\s*\[[^\]]*\])?\s*"
        r"\{(?:[^{}]|\{[^{}]*\})*\}",
        re.DOTALL
    )

    return pattern.sub("\n", text)


def unwrap_formatting_commands(text: str) -> str:
    """
    Unwrap common formatting commands while preserving their content.
    """

    commands = [
        "emph",
        "textbf",
        "textit",
        "texttt",
        "textrm",
        "textnormal",
        "underline",
        "textsc",
        "textsf",
        "mbox",
        "fbox",
    ]

    for command in commands:
        pattern = re.compile(
            rf"\\{command}\s*\{{([^{{}}]*)\}}"
        )

        text = pattern.sub(r"\1", text)

    return text


def remove_layout_commands(text: str) -> str:
    """
    Remove non-semantic layout and font commands.
    """

    # Commands with one required argument.
    text = re.sub(
        r"\\(?:label|index|vspace|hspace|vskip|hskip|"
        r"setlength|addtolength)"
        r"\*?(?:\s*\[[^\]]*\])?\s*\{[^{}]*\}",
        " ",
        text
    )

    # Commands without arguments.
    text = re.sub(
        r"\\(?:noindent|centering|medskip|smallskip|bigskip|"
        r"newpage|clearpage|pagebreak|par|maketitle|"
        r"small|large|Large|LARGE|huge|Huge|"
        r"bfseries|itshape|ttfamily|rmfamily|sffamily|"
        r"raggedright|raggedleft)\b",
        " ",
        text
    )

    return text


# ============================================================
# 2. PREPARE PROSE TEXT
# ============================================================

def prepare_prose_text(text: str) -> str:
    """
    Prepare LaTeX source for sentence extraction.

    - Remove comments.
    - Remove section headings.
    - Remove figures and tables.
    - Remove display mathematics.
    - Preserve academic environment contents.
    - Unwrap formatting and layout environments.
    - Preserve citations and inline mathematics.
    - Remove non-semantic commands.
    """

    # 1. Remove comments.
    text = remove_comments(text)

    # 2. Remove sectioning commands.
    text = remove_heading_commands(text)

    # 3. Remove figures and tables completely.
    structural_environments = [
        "figure",
        "figure*",
        "wrapfigure",
        "table",
        "table*",
    ]

    for environment in structural_environments:
        text = remove_environment(
            text,
            environment,
            preserve_content=False
        )

    # 4. Remove display math delimiters.
    text = re.sub(
        r"(?<!\\)\\\[.*?(?<!\\)\\\]",
        "\n",
        text,
        flags=re.DOTALL
    )

    text = re.sub(
        r"(?<!\$)\$\$.*?\$\$(?!\$)",
        "\n",
        text,
        flags=re.DOTALL
    )

    # 5. Remove display math environments.
    math_environments = [
        "equation",
        "equation*",
        "align",
        "align*",
        "gather",
        "gather*",
        "multline",
        "multline*",
        "displaymath",
    ]

    for environment in math_environments:
        text = remove_environment(
            text,
            environment,
            preserve_content=False
        )

    # 6. Preserve academic environment contents.
    academic_environments = [
        "datasetting",
        "trainingsetup",
        "initializationsetting",
        "setting",
        "model",
        "initialization",
        "theorem",
        "lemma",
        "corollary",
        "proposition",
        "definition",
        "example",
        "remark",
        "claim",
        "assumption",
        "proof",
    ]

    for environment in academic_environments:
        text = remove_environment(
            text,
            environment,
            preserve_content=True
        )

    # 7. Unwrap common layout environments.
    wrapper_environments = [
        "center",
        "flushleft",
        "flushright",
        "abstract",
        "minipage",
    ]

    for environment in wrapper_environments:
        text = remove_environment(
            text,
            environment,
            preserve_content=True
        )

    # 8. Unwrap common formatting commands.
    text = unwrap_formatting_commands(text)

    # 9. Remove non-semantic layout commands.
    text = remove_layout_commands(text)

    # 10. Remove document-control and bibliography commands.
    text = re.sub(
        r"\\(?:FloatBarrier|appendix|clearpage|newpage|pagebreak)\b",
        " ",
        text
    )

    text = re.sub(
        r"\\(?:bibliographystyle|bibliography)\s*\{[^{}]*\}",
        " ",
        text
    )

    # 11. Normalize inline math delimiters.
    text = re.sub(
        r"\\\((.*?)\\\)",
        lambda match: "$" + match.group(1).strip() + "$",
        text,
        flags=re.DOTALL
    )

    # 12. Remove redundant outer groups.
    text = unwrap_outer_groups(text)

    # 13. Normalize whitespace.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    return text.strip()

# ============================================================
# 3. PROTECT SPECIAL PERIODS
# ============================================================

def protect_special_periods(text: str) -> str:
    """
    Protect periods that should not be treated as sentence endings.
    """

    protected = text

    # Protect inline math: $...$ and \\(...\\).
    math_patterns = [
        r"\$.*?\$",
        r"\\\(.*?\\\)",
    ]

    for pattern in math_patterns:
        protected = re.sub(
            pattern,
            lambda match: match.group(0).replace(".", "<DOT>"),
            protected,
            flags=re.DOTALL
        )

    # Protect decimal numbers, e.g. 3.14.
    protected = re.sub(
        r"(?<=\d)\.(?=\d)",
        "<DOT>",
        protected
    )

    # Protect common abbreviations.
    abbreviations = [
        "e.g.",
        "i.e.",
        "et al.",
        "Fig.",
        "Figs.",
        "Eq.",
        "Eqs.",
        "Sec.",
        "Secs.",
        "Dr.",
        "Prof.",
        "vs.",
        "approx.",
        "No.",
        "Vol.",
        "pp.",
        "al.",
    ]

    for abbreviation in abbreviations:
        protected = re.sub(
            re.escape(abbreviation),
            lambda match: match.group(0).replace(".", "<DOT>"),
            protected,
            flags=re.IGNORECASE
        )

    # Protect URLs.
    protected = re.sub(
        r"https?://\S+",
        lambda match: match.group(0).replace(".", "<DOT>"),
        protected
    )

    # Protect common LaTeX citation and reference keys.
    protected = re.sub(
        r"\\(?:cite|citep|citet|ref|eqref)\{[^{}]*\}",
        lambda match: match.group(0).replace(".", "<DOT>"),
        protected
    )

    return protected


# ============================================================
# 4. SPLIT SENTENCES
# ============================================================

def split_sentences(text: str) -> list[str]:
    """
    Split prose into sentences.

    - Preserve paragraph boundaries.
    - Treat single newlines as whitespace.
    - Protect decimal points, abbreviations, URLs and inline math.
    """

    text = text.strip()

    if not text:
        return []

    # Split paragraphs using blank lines.
    paragraphs = re.split(
        r"\n\s*\n+",
        text
    )

    sentences = []

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        # Normalize single newlines into spaces.
        paragraph = re.sub(
            r"\s+",
            " ",
            paragraph
        )

        # Protect special periods.
        protected = protect_special_periods(paragraph)

        # Split at sentence-ending punctuation.
        parts = re.split(
            r'(?<=[.!?])\s+(?=[A-Z0-9"(\[])',
            protected
        )

        for part in parts:
            sentence = part.replace("<DOT>", ".").strip()

            if sentence:
                sentences.append(sentence)

    return sentences


# ============================================================
# 5. REMOVE REDUNDANT OUTER GROUPS
# ============================================================

def unwrap_outer_groups(text: str) -> str:
    text = text.strip()

    while text.startswith("{") and text.endswith("}"):
        depth = 0
        is_outer_group = True

        for i, char in enumerate(text):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1

            if depth == 0 and i < len(text) - 1:
                is_outer_group = False
                break

        if is_outer_group and depth == 0:
            text = text[1:-1].strip()
        else:
            break

    return text