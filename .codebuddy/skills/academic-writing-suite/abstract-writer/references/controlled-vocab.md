# Controlled Vocabulary Keywords

Used when the user requests keywords from a specific indexing thesaurus.

## When to Use This File

Only consult this file if the user explicitly requests a controlled vocabulary, e.g.:
- "Use MeSH terms"
- "I'm submitting to PubMed / MEDLINE"
- "Use ERIC descriptors"
- "Use PsycINFO thesaurus terms"

Otherwise, generate free keywords per the main SKILL.md rules.

---

## MeSH (Medical Subject Headings)
**Used by:** PubMed, MEDLINE, NLM databases
**Access:** https://www.ncbi.nlm.nih.gov/mesh

### Rules
- Use the exact MeSH term spelling and capitalization
- Prefer the most specific available term over a broader one
- Major MeSH terms (starred) represent the paper's primary focus
- Do not invent MeSH-sounding terms — only use terms that exist in the thesaurus
- If a concept has no MeSH term, use a free-text keyword and note it

### Process
1. Identify 3–5 core concepts from the document
2. For each concept, suggest the most likely MeSH term
3. Flag any concepts that may not have a MeSH equivalent
4. Recommend the user verify terms at https://www.ncbi.nlm.nih.gov/mesh before submission

### Output format
```
MeSH Terms: [Term One]; [Term Two]; [Term Three]
Additional keywords (free text): [term]
```

---

## ERIC Thesaurus
**Used by:** Education research, ERIC database
**Access:** https://eric.ed.gov/

### Rules
- Use ERIC Descriptors (preferred terms) where available
- Format: title case, no quotation marks
- Typically 3–6 descriptors

### Output format
```
ERIC Descriptors: Term One, Term Two, Term Three
```

---

## PsycINFO / APA Thesaurus
**Used by:** Psychology and behavioral science journals
**Access:** APA PsycINFO database (subscription required)

### Rules
- Use APA Thesaurus of Psychological Index Terms
- Suggest likely thesaurus terms based on content
- Flag terms to verify — thesaurus is behind a paywall and cannot be accessed directly

---

## General Guidance for All Controlled Vocabularies

- Always tell the user which vocabulary was used
- Always recommend they verify terms in the official thesaurus before submission — Claude cannot guarantee exact match to the current version of any thesaurus
- If the user's concept is not in the vocabulary, provide both the closest controlled term and a free-text alternative
