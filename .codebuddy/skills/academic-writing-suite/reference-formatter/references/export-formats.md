# Export Formats — BibTeX / RIS (EndNote & NoteExpress)

Use this file when the user requests output as BibTeX, RIS, EndNote, NoteExpress, Zotero, or Mendeley.

---

## Format Compatibility Map

| User says | Output format | File extension |
|-----------|--------------|----------------|
| BibTeX / LaTeX / Overleaf | BibTeX | `.bib` |
| EndNote | RIS | `.ris` |
| NoteExpress | NoteExpress XML or RIS | `.net` / `.ris` |
| Zotero | RIS (recommended) | `.ris` |
| Mendeley | RIS (recommended) | `.ris` |
| JabRef | BibTeX | `.bib` |

RIS is the universal interchange format — when in doubt, output RIS.

---

## BibTeX

### Entry Type Mapping

| Document type | BibTeX type |
|--------------|-------------|
| Journal article | `@article` |
| Book | `@book` |
| Book chapter | `@incollection` |
| Conference paper | `@inproceedings` |
| Thesis / dissertation | `@phdthesis` / `@mastersthesis` |
| Technical report | `@techreport` |
| Webpage / misc | `@misc` |
| Unpublished | `@unpublished` |

### Field Names

| Data | BibTeX field |
|------|-------------|
| Authors | `author` |
| Year | `year` |
| Article title | `title` |
| Journal name | `journal` |
| Book title | `booktitle` |
| Volume | `volume` |
| Issue / number | `number` |
| Pages | `pages` |
| Publisher | `publisher` |
| DOI | `doi` |
| URL | `url` |
| Note | `note` |

### Author Format
- Multiple authors joined with ` and ` (not comma)
- Format: `Last, First and Last, First`
- Organizations: wrap in double braces `{{WHO}}`

### Citation Key Convention
Generate as: `FirstAuthorLastname + Year + FirstTitleWord`
Example: `smith2020effects`
- Lowercase, no spaces, no special characters
- If key would duplicate, append `a`, `b`, etc.

### Page Range
Use double dash: `120--135`

### Full Example — Journal Article
```bibtex
@article{smith2020effects,
  author   = {Smith, John A. and Lee, Bob C.},
  title    = {Effects of climate change on biodiversity},
  journal  = {Nature Reviews},
  year     = {2020},
  volume   = {15},
  number   = {3},
  pages    = {120--135},
  doi      = {10.1038/xxx}
}
```

### Full Example — Book
```bibtex
@book{brown2019understanding,
  author    = {Brown, Laura},
  title     = {Understanding Psychology: A Comprehensive Guide},
  publisher = {Academic Press},
  year      = {2019}
}
```

### Full Example — Conference Paper
```bibtex
@inproceedings{chen2021deep,
  author    = {Chen, A. B.},
  title     = {Deep learning for image recognition},
  booktitle = {Proceedings of the IEEE International Conference on Computer Vision (ICCV)},
  year      = {2021},
  pages     = {1234--1242},
  doi       = {10.1109/xxx}
}
```

### Full Example — Thesis
```bibtex
@phdthesis{wang2022neural,
  author = {Wang, Jing},
  title  = {Neural Architecture Search},
  school = {Massachusetts Institute of Technology},
  year   = {2022}
}
```

### Output File
Write to `/mnt/user-data/outputs/references.bib`

---

## RIS Format (EndNote / Zotero / Mendeley / NoteExpress)

### Entry Type Mapping (TY field)

| Document type | RIS TY tag |
|--------------|-----------|
| Journal article | `JOUR` |
| Book | `BOOK` |
| Book chapter | `CHAP` |
| Conference paper | `CONF` |
| PhD thesis | `THES` |
| Report | `RPRT` |
| Webpage | `ELEC` |
| Generic / misc | `GEN` |

### Field Tags

| Data | RIS tag |
|------|---------|
| Entry type | `TY` (must be first) |
| Author | `AU` (one per line) |
| Year | `PY` |
| Title | `TI` |
| Journal / periodical | `JO` |
| Secondary title (book) | `T2` |
| Volume | `VL` |
| Issue | `IS` |
| Start page | `SP` |
| End page | `EP` |
| Publisher | `PB` |
| Place of publication | `CY` |
| DOI | `DO` |
| URL | `UR` |
| Abstract | `AB` |
| Keywords | `KW` (one per line) |
| End of record | `ER` (must be last, followed by blank line) |

### Formatting Rules
- Each line: `TAG  - Value` (two spaces + hyphen + space)
- Each author on its own `AU` line: `AU  - Last, First`
- `TY` must be the first tag, `ER  - ` must be the last
- Blank line between records
- No trailing spaces

### Full Example — Journal Article
```ris
TY  - JOUR
AU  - Smith, John A.
AU  - Lee, Bob C.
TI  - Effects of climate change on biodiversity
JO  - Nature Reviews
PY  - 2020
VL  - 15
IS  - 3
SP  - 120
EP  - 135
DO  - 10.1038/xxx
ER  - 
```

### Full Example — Book
```ris
TY  - BOOK
AU  - Brown, Laura
TI  - Understanding Psychology: A Comprehensive Guide
PB  - Academic Press
PY  - 2019
ER  - 
```

### Full Example — Conference Paper
```ris
TY  - CONF
AU  - Chen, A. B.
TI  - Deep learning for image recognition
T2  - Proceedings of ICCV 2021
PY  - 2021
SP  - 1234
EP  - 1242
DO  - 10.1109/xxx
ER  - 
```

### Output File
Write to `/mnt/user-data/outputs/references.ris`

---

## NoteExpress (.net)

NoteExpress is a Chinese reference manager widely used in Chinese academic institutions. Its native `.net` format is proprietary XML. **Recommended approach: output RIS (`.ris`) instead**, which NoteExpress imports natively and without data loss.

If user explicitly needs `.net` format:
- NoteExpress `.net` is XML-based and difficult to generate reliably without the application
- Tell the user: output as `.ris`, then import into NoteExpress via File → Import → RIS format
- This is the officially recommended workflow by NoteExpress

---

## General Export Rules

1. **Always output a downloadable file** — do not display raw BibTeX/RIS in conversation for more than 3 entries (it becomes unreadable). Write to file and call `present_files`.
2. **Preserve all available fields** — export formats hold more structured data than human-readable styles; include DOI, abstract, keywords if present in the source
3. **Missing fields** — omit the tag entirely rather than writing empty values; do not write `TI  - [missing]`
4. **Chinese content** — RIS and BibTeX both support UTF-8; write Chinese characters directly, do not transliterate
5. **After outputting**, tell the user which software can import the file:
   - `.bib` → LaTeX / Overleaf / JabRef / Zotero / Mendeley
   - `.ris` → EndNote / NoteExpress / Zotero / Mendeley / most reference managers
