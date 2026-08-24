---
name: results-polisher
description: Academic Results section polisher for research papers. Use this skill whenever the user wants to improve, restructure, evaluate, or rewrite the Results (or Findings) section of a research paper. Triggers include: "polish my results section", "help me present my findings more clearly", "my results are hard to follow", "how should I organize my results", or uploading a paper and asking to improve the results presentation. Also trigger when the user asks whether their results are properly separated from interpretation.
---

# Results Polisher Skill

Polishes and restructures the Results section of research papers using Move-Step analysis. The Results section presents new findings — it reports, not interprets. Default output language is English unless the user specifies otherwise.

---

## Step 1: Read the Input

**File input — use the first applicable method:**
1. Content already in context → process directly
2. File reading tool available → use it
3. Code execution available → `.docx`: python-docx / `.pdf`: pdfplumber / `.txt`: open()
4. Nothing available → ask user to paste the Results section text

After reading, identify:
- Whether the section is purely Results or Results + Discussion (combined)
- Whether data is quantitative, qualitative, or mixed
- Whether figures/tables are referenced

---

## Step 2: Diagnose the Existing Text

Map the current text against the two-Move framework. Identify issues in structure, precision, or boundary violations.

Consult `references/moves.md` for detailed Move rules.

**Common problems to check:**
- Is Move 1 (preparatory information) missing — does the section start with raw data and no context?
- Are results reported with sufficient specificity (numbers, statistics)?
- Is interpretation bleeding into the Results section (belongs in Discussion)?
- Are figures/tables properly located and announced?
- Are commentary sentences present where needed?

Share a brief diagnosis before rewriting.

---

## Step 3: Polish Using the Move Framework

The Results section contains two Moves, with Move 2 potentially recurring across multiple findings. Read `references/moves.md` for full rules, then apply:

**Move 1 — Preparatory information**
- Orient the reader to what is being presented
- State the source of data (which table, figure, or dataset)
- Provide any necessary context (e.g., participant split, data subset)

**Move 2 — Reporting results**
For each finding or data block, apply the Locate → Explain → Report → Comment sequence:
- **Locate:** Point to the table/figure containing the result
- **Explain:** Clarify the structure of the data if needed
- **Report:** State the finding directly, with specific numbers
- **Comment:** Optionally highlight the most notable aspect

**Critical boundary:** The Results section reports findings. Do NOT interpret (why did this happen?), compare with literature, or draw conclusions. Those belong in the Discussion section.

**Polishing priorities:**
1. Add Move 1 if the section starts abruptly with data
2. Ensure each data block follows the Locate → Report pattern
3. Replace vague result statements with specific numbers
4. Remove any interpretive language (save for Discussion)
5. Ensure commentary stays descriptive, not interpretive
6. Apply correct tense and voice (see `references/language.md`)

---

## Step 4: Apply Language Standards

Consult `references/language.md` for tense, voice, and lexical signal rules.

**Key rules:**
- Move 1: past simple for what was done; present for table/figure content
- Move 2 reporting: past simple for what was found
- Table/figure references: present simple ("Table 1 shows…")
- Commentary: present simple for pattern statements; past for specific observations

---

## Step 5: Output

Present the polished Results section with a brief note explaining:
- Structural changes made (Move 1 added, result blocks reorganized, etc.)
- Precision improvements (vague → specific)
- Any interpretive sentences removed (and suggestion to move them to Discussion)
- Word count

**Self-check before output:**
- Does the section start with orienting information (Move 1)?
- Is every result stated with specific numbers or data?
- Are tables/figures properly announced before they are referenced?
- Is there any interpretation that should be moved to Discussion?
- Is tense consistently past simple for findings?
- Does the section end clearly — is it obvious where Results ends?
