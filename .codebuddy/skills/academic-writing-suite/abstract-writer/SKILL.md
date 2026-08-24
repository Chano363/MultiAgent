---
name: abstract-writer
description: Academic and professional abstract and keyword generator. Use this skill whenever the user needs to write, rewrite, or improve an abstract or keywords for a document. Triggers include: uploading a paper or report and asking for an abstract, asking to "summarize this for submission", requesting keywords for a manuscript, converting an unstructured abstract into a structured one (Background/Methods/Results/Conclusion), writing an executive summary for a business report, or any request to generate or refine an abstract or keyword list. Trigger even if the user just says "write me an abstract" or "what are the keywords for this".
---

# Abstract Writer Skill

Generates and refines abstracts and keyword lists from full-text documents or pasted content. Default output language is English unless the user specifies otherwise.

---

## Step 1: Read the Input

### Pasted text
Process directly.

### File input
Use the first applicable method below:

**1. Content already in context** — if the file content is visible in the conversation, process it directly.

**2. File reading tool available** — if a file-reading, document-parsing, or dedicated skill is available in the current environment, use it.

**3. Code execution available** — if a Python sandbox or code interpreter is available but no dedicated tool exists, read the file with the appropriate library:
- `.docx` → `python-docx`: `Document(path)`, iterate paragraphs
- `.pdf` → `pdfplumber` (preferred) or `pymupdf`: extract text page by page
- `.txt / .md` → standard `open(path).read()`

**4. Nothing available** — ask the user to paste the document content as text. Do not attempt to guess file contents.

After reading, identify:
- Document type (journal article / conference paper / thesis / business report / other)
- Field/discipline (infer from content and terminology)
- Whether the paper reports empirical results or is primarily theoretical/descriptive

---

## Step 2: Clarify Requirements

Before generating, establish the following. Apply defaults silently if not specified.

| Parameter | Default |
|-----------|---------|
| Output language | English |
| Informative vs. indicative | Informative (see Step 3) |
| Abstract format | Infer from document type (see Step 3) |
| Word count | Per type default (see Step 3) |
| Keyword count | 5–8 |
| Keyword vocabulary | Free (no controlled vocabulary) |
| Output mode | Inline text |

If the submission venue has specific requirements (word limit, required sections, structured vs. unstructured), ask one focused question before proceeding.

---

## Step 3: Determine Abstract Category and Format

### Category: Informative vs. Indicative

**Informative abstract** (default):
- Presents all main arguments, methods, results, and conclusions
- Reader can understand the full contribution without reading the paper
- Used for: empirical research papers, engineering reports, most journal articles

**Indicative abstract**:
- Describes only the purpose, scope, and methodology — does not report results or conclusions
- Used for: literature reviews, theoretical papers, book-length works, some conference abstracts
- Signal: paper has no "Results" section, or user explicitly asks for a scope-only summary

If the document has no Results section or is primarily a review/theoretical work, default to indicative and note this to the user.

### Format: Choose the appropriate structure

Consult the relevant reference file for detailed rules:

| Document type | Default format | Reference file |
|--------------|---------------|----------------|
| Clinical / medical research | Structured IMRAD | `references/structured.md` |
| Empirical research (social science, psychology, education) | Structured APA-style | `references/structured.md` |
| Natural science / engineering | Structured IMRAD or unstructured — infer from field norms | `references/structured.md` |
| Humanities / theoretical | Unstructured narrative | `references/unstructured.md` |
| Literature review / survey paper | Indicative, unstructured | `references/unstructured.md` |
| Conference paper | Unstructured informative, tight word limit | `references/unstructured.md` |
| Business report / policy document | Executive Summary | `references/executive.md` |
| Thesis / dissertation | Unstructured informative, longer | `references/unstructured.md` |

If uncertain, default to unstructured informative and offer to convert on request.

---

## Step 4: Extract Key Information Using Reverse Outlining

Before writing, systematically extract the core content from the document. Do not write the abstract yet.

**For each major section of the paper, identify the one or two most important points:**

| Section | Key question to answer |
|---------|----------------------|
| Introduction | Why was this research needed? What gap does it fill? What is the objective? |
| Method | What was done, and how? What is the study design / data source / key technique? |
| Results | What were the main findings? Include specific data, numbers, or effect sizes where present. |
| Conclusion / Discussion | What do the results mean? What is the main takeaway or contribution? |

**Use lexical markers to locate key information quickly:**

- Aim/objective markers: *aim, purpose, goal, objective, intend to, seek to, investigate, examine, explore, propose, present*
- Method markers: *adopt, use, employ, apply, develop, design, collect, analyze, measure, compare*
- Result markers: *find, show, reveal, demonstrate, indicate, observe, obtain, establish, conclude*
- Contribution markers: *contribute, suggest, imply, provide, offer, extend, advance, improve, outperform*

Once you have the key point from each section, move to Step 5.

---

## Step 5: Write the Abstract

Read the relevant reference file for format-specific rules, then compose the abstract using the Move structure:

**The five Moves — every informative abstract should cover these in order:**

| Move | Communicative purpose | Typical signals |
|------|-----------------------|-----------------|
| 1. Background | Establish why the research matters; provide context | *Recently… / It is known that… / X has become…* |
| 2. Present work | Announce what this paper does; state the objective | *This paper investigates… / We propose… / The aim is to…* |
| 3. Methodology | Describe how it was done | *We developed… / Data were collected… / Using X method…* |
| 4. Results | Report main findings with specifics | *Results show… / We found that… / X achieved Y%…* |
| 5. Conclusion | Draw the takeaway; state significance or implications | *We conclude… / These findings suggest… / This approach enables…* |

For **indicative abstracts**: include Moves 1–3 only; omit or generalize Moves 4–5.

**General writing rules:**
- Each Move should be 1–3 sentences; do not pad
- Do not introduce any information not present in the document
- Do not include in-text citations, figure/table references, or footnotes
- The abstract must stand alone — define any acronyms used
- Match tense and voice conventions for each Move (see reference files for details)

**Sentence condensation — how to compress original text:**
- Take the topic sentence of each section as the starting point
- Remove hedges, qualifications, and examples unless they are the main point
- Merge related clauses: "X was done. Y was also done." → "X and Y were done."
- Replace long noun phrases with shorter equivalents where meaning is preserved

**Self-check before finalizing:**
- Does each of the five Moves appear (or is omission intentional for indicative)?
- Is every sentence carrying new information?
- Is the word count within range?
- Does it stand alone without reading the paper?
- Are tenses consistent within each Move?

---

## Step 6: Generate Keywords

**Selection criteria (in priority order):**
1. Core topic terms — the main subject(s) of the document
2. Method terms — key methodologies, frameworks, or techniques
3. Domain/field terms — the discipline or subfield
4. Outcome/contribution terms — what was achieved or discovered
5. Population or context terms — who/what/where was studied

**Formatting rules:**
- Default: 5–8 keywords, comma-separated, title case
- Prefer phrases over single words where meaningful ("machine learning" not just "learning")
- Avoid terms already in the title — they are indexed separately
- Avoid overly broad terms ("research", "study", "analysis") unless modified
- If user requests a controlled vocabulary (MeSH, ERIC, PsycINFO, etc.), consult `references/controlled-vocab.md`

**Output format:**
```
Keywords: Term One, Term Two, Term Three, Term Four, Term Five
```

---

## Step 7: Output

### Default — inline
```
Abstract

[Abstract text]

Keywords: [keyword list]
```

### File output
- **.txt** — write to output location if tools available; otherwise display inline
- **.docx** — use any available Word editing tool/skill; otherwise output inline with instruction to paste
- **Insert into uploaded document** — locate and replace existing abstract section if tools allow; otherwise output inline

### After output, always note:
- Abstract category (informative / indicative) and format used
- Word count
- Any assumptions made (language, type, length)
- Offer: "I can also generate a [structured/unstructured/indicative] version or adjust the word count if needed."

---

## Quick Reference

| Format | Structure | Typical length |
|--------|-----------|----------------|
| Structured IMRAD | Background / Objective / Methods / Results / Conclusion | 250–350 words |
| Structured APA | Background / Objective / Method / Results / Conclusions & Implications | 150–250 words |
| Unstructured informative | Single paragraph, all 5 Moves | 150–300 words |
| Unstructured indicative | Single paragraph, Moves 1–3 only | 100–200 words |
| Conference abstract | Single paragraph, tight limit | 150–250 words |
| Executive Summary | Context / Findings / Recommendations | 300–500 words |
| Thesis abstract | All 5 Moves, broader scope | 300–500 words |
