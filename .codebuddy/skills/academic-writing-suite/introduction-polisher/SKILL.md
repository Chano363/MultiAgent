---
name: introduction-polisher
description: Academic Introduction section polisher for research papers. Use this skill whenever the user wants to improve, restructure, evaluate, or rewrite the Introduction section of a research paper or term paper. Triggers include: "polish my introduction", "check my intro structure", "my introduction is too weak", "help me revise the background section", or uploading a paper and asking to improve the introduction. Also trigger when the user asks whether their introduction follows correct academic conventions or has a clear research gap.
---

# Introduction Polisher Skill

Polishes and restructures the Introduction section of research papers using the CARS Model (Swales, 1990). Analyzes the existing text, identifies structural gaps, and rewrites or refines accordingly. Default output language is English unless the user specifies otherwise.

---

## Step 1: Read the Input

**File input — use the first applicable method:**
1. Content already in context → process directly
2. File reading tool available → use it
3. Code execution available → `.docx`: python-docx / `.pdf`: pdfplumber / `.txt`: open()
4. Nothing available → ask user to paste the Introduction text

After reading, locate the Introduction section (may be titled "Introduction", "Background", or "1. Introduction").

---

## Step 2: Diagnose the Existing Text

Before rewriting, map the current text against the CARS Model. Identify which Moves and Steps are present, weak, or missing.

Consult `references/cars-model.md` for detailed Move rules.

**Diagnosis output (internal — use to guide revision):**
```
Move 1 (Territory): [present / weak / missing]
  - Step 1 (Centrality claim): ...
  - Step 2 (Topic generalization): ...
  - Step 3 (Literature review): ...
Move 2 (Niche): [present / weak / missing]
  - Step used: [counter-claim / gap / question / tradition]
Move 3 (Niche occupation): [present / weak / missing]
  - Purpose/announcement: ...
  - Findings preview: ...
  - Structure outline: ...
```

Share a brief diagnosis with the user before rewriting, so they understand what will change and why.

---

## Step 3: Polish Using the CARS Model

The Introduction section establishes a research space through three sequential Moves. Read `references/cars-model.md` for full rules, then apply:

**Move 1 — Establishing a Territory**
- Claim the importance and centrality of the topic
- Provide topic generalizations and background
- Review relevant prior research (what has been done)

**Move 2 — Establishing a Niche**
- Identify a gap, problem, or question the current research will address
- This is the rhetorical pivot — without it, Move 3 has no justification
- One of four strategies: counter-claiming, gap-indicating, question-raising, or tradition-continuing

**Move 3 — Occupying the Niche**
- Announce the purpose, objectives, or research questions of the present study (obligatory)
- Optionally: preview principal findings, state the value/contribution, outline paper structure

**Polishing priorities (in order):**
1. Ensure Move 2 is present and specific — this is the most commonly missing or vague element
2. Ensure Move 1 narrows logically from general to specific (funnel structure)
3. Ensure Move 3 clearly states what THIS paper does (not just what the field needs)
4. Apply correct tense and voice per Move (see `references/language.md`)
5. Strengthen lexical signals so each Move is recognizable

---

## Step 4: Apply Language Standards

Consult `references/language.md` for tense, voice, and lexical signal rules by Move.

**Key rules:**
- Move 1 literature review: past simple or present perfect for prior studies; present simple for established facts
- Move 2 gap statement: present simple or present perfect ("has not been studied", "remains unclear")
- Move 3 announcement: present simple ("This paper investigates…") or infinitive ("To address this gap…")
- Passive voice common in Move 1 for literature; active voice preferred in Move 3 for purpose

---

## Step 5: Output

Present the polished Introduction with a brief note explaining:
- What structural changes were made and why
- Which Moves were added, strengthened, or reorganized
- Word count (target: 300–600 words for a term paper; up to 800–1200 for a journal article)

**File output:** write to output location if tools available; otherwise inline.

**Self-check before output:**
- Does Move 1 establish WHY the topic matters?
- Does Move 2 identify a specific gap or problem (not just "little research has been done")?
- Does Move 3 clearly state what THIS paper does?
- Are tenses consistent with each Move's conventions?
- Does the Introduction funnel from general to specific?
