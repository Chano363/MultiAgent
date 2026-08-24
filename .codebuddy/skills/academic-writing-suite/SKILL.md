---
name: academic-writing-suite
description: All-in-one academic writing toolkit for research papers and term papers. Use this skill for any of the following: formatting, converting, or exporting references (APA, MLA, Chicago, IEEE, GB/T 7714, Vancouver, BibTeX, RIS, EndNote, Zotero); writing or improving abstracts and keywords; writing a conclusion, discussion, or closing section; polishing an Introduction (CARS structure, research gap); polishing a Method section (replication clarity, passive voice); polishing a Results section (reporting precision, separating interpretation); polishing a Discussion section (interpretation, literature comparison, limitations, implications). Trigger whenever the user asks for help with any section of a research paper or with references.
---

# Academic Writing Suite

A unified toolkit covering seven academic writing functions. This skill reads the user's request, identifies which function is needed, then loads the corresponding sub-skill.

---

## Routing Table

Read the user's request and match it to one of the seven functions below. Then load the corresponding sub-skill file and follow its instructions completely.

| User need | Sub-skill to load |
|-----------|------------------|
| Format, convert, detect, or export references (APA / MLA / Chicago / IEEE / GB/T 7714 / Vancouver / BibTeX / RIS / EndNote / Zotero / NoteExpress) | `reference-formatter/SKILL.md` |
| Write, rewrite, or improve an abstract or keyword list | `abstract-writer/SKILL.md` |
| Write or improve a Conclusion / Discussion / Closing section | `closing-writer/SKILL.md` |
| Polish or restructure an Introduction section | `introduction-polisher/SKILL.md` |
| Polish or restructure a Method / Methods / Methodology section | `method-polisher/SKILL.md` |
| Polish or restructure a Results / Findings section | `results-polisher/SKILL.md` |
| Polish or restructure a Discussion section | `discussion-polisher/SKILL.md` |

---

## Handling Ambiguous Requests

**"Help me with my paper"** — ask which section or function the user needs, then route.

**"Polish my discussion/conclusion"** — Note: the closing section of a paper may be labeled Discussion, Conclusion, or both. Route as follows:
- If the user wants to interpret findings, compare with literature, evaluate limitations → `discussion-polisher/SKILL.md`
- If the user wants to wrap up the paper, state implications, make future recommendations → `closing-writer/SKILL.md`
- If the section combines both functions → load both, apply discussion-polisher logic first, then closing-writer for the deductions

**Multiple sections at once** — if the user uploads a full paper and asks for general improvements, handle one section at a time: Introduction → Method → Results → Discussion/Closing → Abstract. Ask the user which to start with, or proceed in IMRAD order if they say "all of them".

---

## File Input

Use the first applicable method to read any uploaded file:
1. Content already in context → process directly
2. File reading tool available → use it
3. Code execution available → `.docx`: python-docx / `.pdf`: pdfplumber / `.txt`: open()
4. Nothing available → ask the user to paste the relevant content

---

## Output Language

Default: **English**. Follow user instructions if another language is specified.
