---
name: discussion-polisher
description: Academic Discussion section polisher for research papers. Use this skill whenever the user wants to improve, restructure, evaluate, or rewrite the Discussion section of a research paper. Triggers include: "polish my discussion", "my discussion is too descriptive", "I'm just repeating my results", "help me write a stronger discussion", or uploading a paper and asking to improve the discussion. Also trigger when the user asks how to interpret findings, how to compare with literature, or how to structure the discussion section.
---

# Discussion Polisher Skill

Polishes and restructures the Discussion section of research papers using Yang & Allison's (2003) seven-Move framework — the most comprehensive and widely validated model for Discussion sections across disciplines. Default output language is English unless the user specifies otherwise.

---

## Step 1: Read the Input

**File input — use the first applicable method:**
1. Content already in context → process directly
2. File reading tool available → use it
3. Code execution available → `.docx`: python-docx / `.pdf`: pdfplumber / `.txt`: open()
4. Nothing available → ask user to paste the Discussion section (and Results if available)

After reading, identify:
- Whether Discussion is combined with Results ("Results and Discussion")
- Whether findings supported or contradicted the hypothesis
- Key findings to be interpreted

---

## Step 2: Diagnose the Existing Text

Map the current text against the seven-Move framework. Identify which Moves are present, missing, or underdeveloped.

Consult `references/moves.md` for detailed Move rules.

**The most common Discussion problems:**
- Over-reporting: repeating results instead of interpreting them (confusing Move 2 with Move 3)
- Missing Move 3: no interpretation — just "results showed X" with no "this means Y"
- Missing Move 4: no comparison with prior literature
- Vague limitations: "this study has some limitations" without specifying them
- Weak Move 7: no implications or future directions

Share a brief diagnosis before rewriting.

---

## Step 3: Polish Using the Yang & Allison Seven-Move Framework

Read `references/moves.md` for full rules, then apply. Moves 2–6 may recur and interleave across multiple findings — this cycling is expected.

**Move 1 — Background information**
Restate the research context and purpose briefly.

**Move 2 — Reporting results**
Summarize key findings (brief — not a repeat of the Results section).

**Move 3 — Summarizing results**
Integrate findings into a coherent overall picture.

**Move 4 — Commenting on results** ← The intellectual core
- Interpret what results mean
- Compare with prior literature (agree or disagree, and why)
- Account for unexpected or contradictory findings

**Move 5 — Summarizing the study**
Draw an overall conclusion from the full set of findings.

**Move 6 — Evaluating the study**
Assess the study itself: limitations, strengths, and methodological considerations.

**Move 7 — Deductions from the research**
Look forward: implications for theory, practice, or future research.

**Polishing priorities:**
1. Ensure Move 3 is present — the most commonly missing move (mere result repetition is not interpretation)
2. Ensure Move 4 compares with specific prior studies (not vague "prior research")
3. Ensure Move 6 limitations are specific (not generic)
4. Ensure Move 7 suggestions are actionable (not just "more research is needed")
5. Apply correct tense/voice and hedging per Move (see `references/language.md`)

---

## Step 4: Apply Language Standards

Consult `references/language.md` for tense, voice, modal verb, and hedging rules.

**Key rules:**
- Results reporting (Move 2): past simple, active
- Interpretation (Move 3/4): present simple, active, with hedges
- Literature comparison (Move 4): past for their findings, present for comparison
- Limitations (Move 6): past simple or past perfect, passive preferred
- Implications / future work (Move 7): modal verbs (should, could, may)

---

## Step 5: Output

Present the polished Discussion section with a brief note explaining:
- Which Moves were added, strengthened, or reorganized
- Interpretive sentences added vs. result-repetition removed
- Specific literature comparisons added (or flagged as needing author input)
- Word count (typical: 500–1000 words for term paper; up to 2000 for journal article)

**Self-check before output:**
- Does Move 4 interpret, not just describe?
- Does Move 4 mention specific prior work (not just "previous studies")?
- Are limitations specific (sample size? design? scope?) in Move 6?
- Does Move 7 have actionable suggestions with rationale?
- Is hedging appropriate — present in interpretation, absent in factual reporting?
- Are Moves 2–6 cycling naturally across findings, not just appearing once?
