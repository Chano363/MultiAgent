---
name: closing-writer
description: Academic closing section writer for research papers and term papers. Use this skill whenever the user needs to write, improve, or analyze the closing section of a research paper. Triggers include: writing a Discussion, Conclusion, or Recommendations section; asking how to wrap up a paper; requesting help with limitations, implications, or future research suggestions; saying "help me write my conclusion" or "how do I end my paper". Also trigger when the user asks to evaluate or restructure an existing closing section.
---

# Closing Writer Skill

Writes and refines the closing section of academic research papers using Move-Step analysis. The closing section may appear under various headings: Discussion, Conclusion, Conclusions and Recommendations, or combined forms. Default output language is English unless the user specifies otherwise.

---

## Step 1: Read the Input

### What the user provides
The user may provide:
- The full paper → extract key information from each section (see Step 3)
- Results section only → write closing based on those results
- A rough draft of the closing → revise and restructure
- A description of their findings → generate the closing from that

### File input
Use the first applicable method:

**1. Content already in context** — process directly.
**2. File reading tool available** — use it.
**3. Code execution available** — use appropriate library:
- `.docx` → `python-docx`
- `.pdf` → `pdfplumber` or `pymupdf`
- `.txt / .md` → `open(path).read()`

**4. Nothing available** — ask the user to paste the relevant content.

---

## Step 2: Clarify Requirements

Establish the following before writing. Apply defaults silently if not specified.

| Parameter | Default |
|-----------|---------|
| Output language | English |
| Section heading | Infer from discipline (see Step 3) |
| Moves to include | All 5 (see Step 4) |
| Word count | 400–700 words |
| Discipline / field | Infer from content |
| Output mode | Inline text |

If the user mentions a target journal or venue, ask if there are specific structural requirements before proceeding.

---

## Step 3: Identify Section Type and Heading

The closing section appears under different headings depending on discipline and emphasis. Infer from context or ask:

| Heading | Typical use | What it emphasizes |
|---------|------------|-------------------|
| Discussion | Sciences, social sciences | Interpretation, comparison with literature, limitations |
| Conclusion / Conclusions | Most disciplines | Summary of findings, implications, future work |
| Discussion and Conclusion | Combined sections | All moves in one section |
| Conclusions and Recommendations | Applied fields, policy, engineering | Strong future-directions emphasis |
| Summary | Some engineering / technical papers | Compact restatement of findings |

**Note:** The heading does not change which Moves are needed — it only signals which Moves to emphasize. A "Discussion" section still draws conclusions; a "Conclusion" section still evaluates the study.

---

## Step 4: Extract Key Information from the Paper

Before writing, identify the following from the paper or user input:

| What to find | Where to look |
|-------------|--------------|
| Research purpose / hypothesis | Introduction |
| Main findings / results | Results section |
| Whether hypothesis was supported | Results / Discussion |
| How results compare to prior literature | Background / related work |
| Limitations of the study | Methods (sample size, design constraints) |
| Strengths of the study | Methods / Results |
| Practical implications | Infer from findings |
| Gaps that remain / future research directions | Infer from limitations |

Use these lexical markers to locate key content quickly:
- Purpose: *aim, objective, purpose, goal, hypothesis, seek to, investigate*
- Results: *found, showed, revealed, demonstrated, observed, indicate*
- Comparison: *consistent with, contrary to, in line with, unlike, differ from*
- Limitation: *limited by, unable to, did not account for, sample size, generalizability*
- Future: *future studies should, further research, recommend, suggest*

---

## Step 5: Write the Closing Section Using Move-Step Structure

The closing section is organized around **5 Moves**, each with specific **Steps** (sub-purposes). Moves do not always occur in strict linear order — Moves 3, 4, and 5 often recur and interleave as the author cycles through different findings.

Consult `references/moves.md` for detailed rules, lexical signals, and tense/voice by Move.

### Move Overview

**Move 1: Preparatory Information**
- Step 1a — Restate the purpose of the study (1–2 sentences)
- Step 1b — Review the hypothesis or research question (1 sentence, if applicable)

**Move 2: Reporting Results**
- Summarize the main findings briefly (1–3 sentences)
- Do not repeat the full Results section — synthesize, don't list

**Move 3: Commenting on Results**
- Step 3a — Interpret results: what do they mean?
- Step 3b — Compare with prior literature: consistent or contradictory? Why?
- Step 3c — Account for unexpected results: explain discrepancies
- Step 3d — Evaluate overall: what is the significance of this pattern?

**Move 4: Evaluating the Study**
- Step 4a — Indicate limitations (sample size, design, scope, methodology)
- Step 4b — Indicate strengths or significance of the contribution
- Step 4c — Evaluate methodology (if relevant)

**Move 5: Deductions from the Research**
- Step 5a — Make practical suggestions or recommendations
- Step 5b — Recommend directions for future research
- Step 5c — Draw broader implications for the field

### Structural flexibility
- Moves 3, 4, and 5 may recur — the author may comment on one finding, evaluate it, suggest future work, then move to the next finding and repeat
- Move 1 is always first; Move 2 comes early; Moves 3–5 can interleave
- Short papers or term papers may compress Moves 1–2 into 1–2 sentences
- Applied / policy papers may expand Move 5 significantly

---

## Step 6: Apply Language Features

Consult `references/language.md` for the full tense, voice, modal verb, and hedging rules.

### Tense and voice by Move (summary)

| Move / Step | Tense | Voice |
|-------------|-------|-------|
| Move 1 — Restate purpose | Past simple | Active preferred |
| Move 2 — Report results | Past simple | Active preferred |
| Move 3 — Comment / interpret | Present simple | Active preferred |
| Move 3 — Compare with literature | Past simple (their findings) / Present (the comparison) | Mixed |
| Move 4 — Limitations | Past simple or past perfect | Passive preferred |
| Move 4 — Strengths | Present simple or present perfect | Active |
| Move 5 — Suggestions / future work | Modal verbs (should, could, may) | Active |
| Move 5 — Implications | Present simple | Active |

### Modal verbs
Modal verbs are heavily used in Moves 4 and 5 to express appropriate epistemic caution:
- **should** — recommendations and obligations (*Future studies should…*)
- **could** — possibilities (*This approach could be applied to…*)
- **may / might** — uncertainty (*These results may reflect…*)
- **would** — hypothetical or conditional (*A larger sample would improve…*)

### Hedging
The closing section requires "confidently uncertain" language — asserting findings while acknowledging uncertainty. Use hedges in:
- Interpreting results: *suggest, indicate, appear to, seem to, tend to*
- Comparing with literature: *may be due to, could be explained by*
- Limitations: *it is possible that, may have affected, cannot be ruled out*
- Implications: *could have implications for, may be applicable to*

Do NOT hedge the restatement of results — report what was found directly. Reserve hedges for interpretation and implication.

---

## Step 7: Self-Check Before Output

- Are all 5 Moves present (or is omission intentional and justified)?
- Is Move 1 concise — not a long summary of the introduction?
- Does Move 3 go beyond restating results to actually interpret them?
- Are limitations specific (not just "further research is needed")?
- Are strengths mentioned, not just limitations?
- Is Move 5 actionable — specific suggestions, not vague calls for "more research"?
- Are tenses consistent within each Move?
- Are hedges used appropriately — present in interpretation, absent in factual reporting?

---

## Step 8: Output

### Default — inline
Present the closing section as running prose with appropriate paragraph breaks. Include the section heading.

### File output
- **.txt / .docx** — write to output location if tools available; otherwise inline
- **Insert into uploaded document** — locate and replace existing closing section if tools allow

### After output, always note:
- Which Moves are present and any that were omitted (with reason)
- Word count
- Any assumptions made about the paper's findings or discipline
- Offer: "I can expand the limitations / strengthen the implications / adjust the heading or length if needed."

---

## Quick Reference — Closing Section at a Glance

```
Move 1  →  Restate purpose + review hypothesis
Move 2  →  Summarize main findings (briefly)
Move 3  →  Interpret + compare with literature + explain discrepancies
Move 4  →  Limitations + strengths + methodology evaluation
Move 5  →  Suggestions + future research + broader implications

[Moves 3–5 may recur and interleave across findings]
```
