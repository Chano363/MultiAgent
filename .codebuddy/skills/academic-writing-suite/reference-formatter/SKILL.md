---
name: reference-formatter
description: Reference citation formatting, conversion, validation, and export tool. Use this skill whenever the user needs to format, convert, detect, or proofread bibliographic references, or export them for use in reference managers. Triggers include: pasting messy references for cleanup, uploading a document with a reference list, converting between citation styles (APA/MLA/Chicago/IEEE/GB/T 7714/Vancouver), checking whether references are correctly formatted, exporting to BibTeX (.bib) for LaTeX/Overleaf, exporting to RIS (.ris) for EndNote/NoteExpress/Zotero/Mendeley, or simply saying "fix my references" or "format my bibliography". Always trigger this skill for any reference or citation formatting task, even if the request seems simple.
---

# Reference Formatter Skill

Formats, converts, detects, and validates bibliographic references. Accepts pasted text or uploaded files. Default output is plain text in-conversation; can also write directly to user-specified files.

---

## Step 1: Understand the Request

Before processing, establish the following (apply defaults silently if not specified):

| Parameter | Default |
|-----------|---------|
| Target format | Ask user, or infer from context (Chinese academic → GB/T 7714; engineering/CS → IEEE; medical → Vancouver) |
| Input source | Pasted text or uploaded file |
| Output mode | Plain text displayed in conversation |
| Output file format | None (inline) — or .bib / .ris / .txt / .docx if user specifies |
| Sort order | Preserve original order |
| Numbering | Numbered ([1][2]... or 1. 2.) |

**Detect export intent** — if the user mentions any of the following, treat as an export request and consult `references/export-formats.md`:
- Software names: EndNote, NoteExpress, Zotero, Mendeley, JabRef, Overleaf, LaTeX
- Format names: BibTeX, RIS, `.bib`, `.ris`, `.net`
- Phrases: "import into", "export for", "download as"

If the user hasn't specified a target format, run **format detection first** (see Step 2B) before formatting.

If a specific output file is requested (.docx / .pdf / .txt), see the Output section.

---

## Step 2A: Read Input

### Pasted text
Process directly. Common issues in raw input:
- Mixed styles across entries
- Missing fields (year, page numbers, DOI)
- Inconsistent punctuation or capitalization

### File input
Use the first applicable method below:

**1. Content already in context** — if the file content is visible in the conversation, process it directly.

**2. File reading tool available** — if a file-reading, document-parsing, or dedicated skill is available in the current environment, use it.

**3. Code execution available** — if a Python sandbox or code interpreter is available but no dedicated tool exists, read the file with the appropriate library:
- `.docx` → `python-docx`: `Document(path)`, iterate paragraphs
- `.pdf` → `pdfplumber` (preferred) or `pymupdf`: extract text page by page
- `.txt / .md` → standard `open(path).read()`

**4. Nothing available** — ask the user to paste the reference list as text. Do not attempt to guess file contents.

After extracting text, locate the reference section (typically at the end, under headings like "References", "Bibliography", "Works Cited", "参考文献").

---

## Step 2B: Format Detection (when no target format is given, or user asks to "check" references)

Analyze the input and identify the most likely existing style. Use these signals:

| Signal | Likely style |
|--------|-------------|
| `Author, A. A. (Year).` with `&` | APA |
| `[1] A. Smith, "Title,"` with abbreviated journal | IEEE |
| `Author AA. Title. Journal. Year;Vol(Issue):Pages.` | Vancouver |
| `Smith, John. "Title." *Journal* vol. X` | MLA |
| `Author. "Title." *Journal* Volume, no. Issue (Year)` | Chicago |
| `作者. 题名[J]. 刊名, 年, 卷(期): 页.` | GB/T 7714 |

Report detection confidence (High / Medium / Low) and list the signals that led to the conclusion. If mixed styles are detected, flag each inconsistent entry.

**Detection output format:**
```
Detected style: APA 7th (High confidence)
Signals: author format "Last, F. F.", year in parentheses after authors, "&" before final author, DOI as https://doi.org/

Issues found:
- Entry 3: Missing DOI
- Entry 5: Journal name not italicized (formatting note)
- Entry 7: Author format inconsistent — appears to be MLA style
```

---

## Step 3: Parse Each Entry

**Identify entry type first** — it determines which formatting rules apply. Use this decision tree:

```
Has a journal name (periodical)?
├── Yes → JOURNAL ARTICLE
│         Fields: authors, year, article title, journal name,
│                 volume, issue, pages, DOI
└── No → Has a publisher (not a journal)?
          ├── Has an editor / "In [Book Title]" / chapter title?
          │   ├── Conference proceedings? → CONFERENCE PAPER
          │   │   Fields: authors, year, paper title, proceedings title,
          │   │            editor, location, pages, DOI
          │   └── Edited book chapter? → BOOK CHAPTER
          │       Fields: authors, year, chapter title, editor(s),
          │               book title, edition, publisher, place, pages
          ├── University + "thesis/dissertation"? → THESIS
          │   Fields: authors, year, title, degree type,
          │           institution, place
          ├── URL / website / no publisher? → WEBPAGE
          │   Fields: authors (if any), date, page title,
          │           site name, URL, access date
          ├── "Report" / org as author / report number? → REPORT
          │   Fields: authors, year, title, org, report number, URL
          └── Standalone volume, no journal → BOOK
              Fields: authors, year, title, edition,
                      publisher, place, DOI
```

**Common ambiguous cases:**
- Conference paper published in a journal → treat as JOURNAL ARTICLE
- Book with single author (no editor) → BOOK, not BOOK CHAPTER
- PhD thesis from an institutional repository → THESIS, not WEBPAGE
- Preprint (arXiv, bioRxiv) → treat as REPORT with URL unless published version exists

After identifying type, extract all available fields. Mark missing fields as `[missing]` — do not invent data.

---

## Step 4: Apply Target Format

Consult the relevant reference file for detailed rules:

| Target | Reference file |
|--------|---------------|
| APA 7th | `references/apa.md` |
| IEEE | `references/ieee.md` |
| MLA 9th | `references/mla-chicago-vancouver.md` |
| Chicago 17th | `references/mla-chicago-vancouver.md` |
| Vancouver | `references/mla-chicago-vancouver.md` |
| GB/T 7714-2015 | `references/gbt7714.md` |
| BibTeX / `.bib` | `references/export-formats.md` |
| RIS / EndNote / NoteExpress / Zotero / Mendeley | `references/export-formats.md` |

**Formatting principles:**
- Strictly follow punctuation, italics, and capitalization rules for the target style
- For missing fields: infer where unambiguous, otherwise mark `[missing]` and list at the end
- If input is already correct, make only minimal corrections — do not reformat unnecessarily
- Preserve the original language of each entry (Chinese entries in Chinese conventions, English entries in English conventions)

**Output structure:**
```
[Formatted reference list]

---
⚠️ Notes:
- Entry 3: Publication year missing — marked [missing]
- Entry 7: DOI format invalid — please verify
```

---

## Step 5: Output

### Default — inline text
Display formatted references in a code block to preserve spacing:

```
[1] ...
[2] ...
```

### Export file output (.bib / .ris)
Consult `references/export-formats.md` for exact syntax rules, then:
1. Generate the full BibTeX or RIS content
2. If file writing tools are available, save to an appropriate output path (e.g. `references.bib` or `references.ris`) and offer a download link
3. If no file writing tools are available, display the full content inline in a code block
4. Note which software can import the file

**Prefer file output over inline for more than 3 entries** — inline BibTeX/RIS is hard to read and copy reliably.

### User specifies a text file output

**.txt / .bib / .ris output:**
If file writing tools are available, write to an appropriate output location and provide a download link. Otherwise display inline in a code block.

**.docx output (replace reference section in document):**
Use any available Word document editing tool or skill. If none available, output formatted text inline and advise the user to paste it into their document manually.

**.pdf output:**
Use any available PDF editing tool or skill. If none available, output formatted text inline.

**Modifying a user-uploaded file in place:**
If file tools are available:
1. Read the uploaded file
2. Locate and replace the reference section
3. Save the modified file and offer a download link

If not available, output the formatted references inline and advise the user to replace the section manually.

---

## Quick Reference — Journal Article Across Styles

| Style | Example |
|-------|---------|
| APA 7th | Smith, J. A., & Lee, B. (2020). Title of article. *Journal Name*, *12*(3), 45–67. https://doi.org/xxx |
| IEEE | J. A. Smith and B. Lee, "Title of article," *Journal Name*, vol. 12, no. 3, pp. 45–67, Mar. 2020, doi: 10.xxxx/xxx. |
| MLA 9th | Smith, John A., and Bob Lee. "Title of Article." *Journal Name*, vol. 12, no. 3, 2020, pp. 45–67. |
| Chicago | Smith, John A., and Bob Lee. "Title of Article." *Journal Name* 12, no. 3 (2020): 45–67. |
| Vancouver | Smith JA, Lee B. Title of article. J Name. 2020;12(3):45-67. |
| GB/T 7714 | Smith J A, Lee B. Title of article[J]. Journal Name, 2020, 12(3): 45-67. |

---

## Key Rules (All Styles)

- **Never fabricate missing data** — always mark `[missing]` for unknown authors, years, or titles
- **DOI format** — always render as `https://doi.org/xxxxx`
- **Author limits** — each style caps the number of listed authors; consult the relevant reference file
- **Language** — mixed-language lists: apply each style's conventions per entry language
