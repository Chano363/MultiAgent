---
name: method-polisher
description: Academic Method section polisher for research papers. Use this skill whenever the user wants to improve, restructure, evaluate, or rewrite the Method (or Methods, Methodology) section of a research paper. Triggers include: "polish my methods section", "is my methodology clear enough", "help me describe my procedure", "my methods section is too vague", or uploading a paper and asking to improve the methodology description. Also trigger when the user asks whether their method section has enough detail for replication.
---

# Method Polisher Skill

Polishes and restructures the Method section of research papers using Move-Step analysis. Analyzes the existing text, identifies gaps in coverage or clarity, and rewrites or refines accordingly. Default output language is English unless the user specifies otherwise.

---

## Step 1: Read the Input

**File input — use the first applicable method:**
1. Content already in context → process directly
2. File reading tool available → use it
3. Code execution available → `.docx`: python-docx / `.pdf`: pdfplumber / `.txt`: open()
4. Nothing available → ask user to paste the Method section text

After reading, identify:
- Research type: experimental (lab) vs. empirical (field/survey/observational) vs. computational
- Discipline (affects which Moves are expected and how detailed each should be)
- Current subheadings (Participants, Procedure, Materials, etc.)

---

## Step 2: Diagnose the Existing Text

Map the current text against the four-Move framework. Identify which Moves and Steps are present, unclear, or missing.

Consult `references/moves.md` for detailed Move rules.

**Diagnosis (share briefly with user before rewriting):**
```
Move 1 (Describing subjects/sources): [present / vague / missing]
Move 2 (Describing experiment/procedure): [present / vague / missing]
Move 3 (Describing data): [present / vague / missing]
Move 4 (Introducing analysis method): [present / vague / missing]

Key issues: [list specific problems]
```

---

## Step 3: Polish Using the Move Framework

The Method section must enable replication — every methodological decision that affects results must be stated. Read `references/moves.md` for full rules, then apply:

**Move 1 — Describing subjects / data sources**
- Who/what was studied (sample, corpus, dataset, materials)
- How they were selected or recruited
- Key characteristics (size, demographics, inclusion/exclusion criteria)
- Ethical considerations if applicable

**Move 2 — Describing the experiment / procedure**
- What was done, step by step, in chronological order
- Instruments, equipment, or stimuli used
- Controls and standardization measures

**Move 3 — Describing the data**
- What data was collected or recorded
- Data type, format, and size
- How data was recorded or coded

**Move 4 — Introducing the method of analysis**
- How data was analyzed (statistical tests, frameworks, software)
- Criteria or thresholds used
- Analytical framework or coding scheme

**Polishing priorities:**
1. Check that Move 1 includes sampling rationale, not just sample description
2. Ensure Move 2 is sequential and specific enough to be replicated
3. Verify Move 3 defines key concepts/variables operationally
4. Confirm Move 4 names specific analysis procedures (not just "data was analyzed")
5. Apply consistent past tense and passive voice (see `references/language.md`)

---

## Step 4: Apply Language Standards

Consult `references/language.md` for tense, voice, and lexical signal rules.

**Key rules:**
- Dominant tense: **past simple** throughout (the method was carried out in the past)
- Dominant voice: **passive** (focus on what was done, not who did it)
- Active voice acceptable when the subject is clearly the research team
- Present simple only for definitions and established procedures that are still valid

---

## Step 5: Output

Present the polished Method section with a brief note explaining:
- What structural gaps were filled
- What clarity or precision improvements were made
- Whether subheadings were added or reorganized
- Word count (typical: 300–800 words for a term paper; up to 1500 for a full article)

**Self-check before output:**
- Could another researcher replicate this study from this description?
- Is the sample/data source fully characterized (size, selection, characteristics)?
- Are all instruments, tools, and procedures named specifically?
- Are key concepts operationally defined?
- Is tense consistently past simple? Is passive voice used appropriately?
