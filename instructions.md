# LLM Wiki — Schema & Operating Instructions

## Purpose
Persistent, compounding knowledge base maintained entirely by the LLM. Sources go in raw; the LLM builds and maintains the wiki. Domain is open — the wiki takes shape from whatever sources are ingested.

## Directory layout

```
llm_wiki/
├── instructions.md             ← this file (schema + instructions)
├── raw/                  ← immutable source documents (never modify)
│   └── assets/           ← locally downloaded images
└── wiki/
    ├── index.md          ← content catalog (update on every ingest)
    ├── log.md            ← append-only operation log
    ├── overview.md       ← evolving high-level synthesis
    ├── sources/          ← one page per ingested source
    ├── entities/         ← people, organizations, places, works
    └── concepts/         ← ideas, theories, methods, frameworks
```

## File conventions

### Frontmatter (all wiki pages)
```yaml
---
title: "Page Title"
type: source | entity | concept | overview | index | log
tags: [tag1, tag2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
source_count: N        # entities/concepts only — how many sources mention this
---
```

### Links
- Use `[[Page Name]]` (Obsidian wiki-links) for all internal cross-references.
- Link liberally. A concept mentioned in a source page → link to concept page.
- If a linked page doesn't exist yet, create it (stub is fine).

### Sources directory naming
`sources/YYYY-MM-DD_slug.md` where slug is a short kebab-case title.

---

## Operations

### INGEST
Trigger: user drops a file in `raw/` and says "ingest [filename]".

Steps (in order):
1. Read the source file fully. For PDFs, read all pages. For images, view them.
2. **Discuss** key takeaways with the user before writing anything.
3. Write `wiki/sources/YYYY-MM-DD_slug.md` — structured summary (see template below).
4. Update `wiki/index.md` — add source entry under Sources section.
5. For each key entity mentioned: update or create `wiki/entities/EntityName.md`.
6. For each key concept mentioned: update or create `wiki/concepts/ConceptName.md`.
7. Update `wiki/overview.md` — revise synthesis to reflect new source. Note contradictions with existing pages explicitly.
8. Append entry to `wiki/log.md`.

Source page template:
```markdown
---
title: "Full Source Title"
type: source
tags: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
authors: []
year: YYYY
---

## Summary
[2–4 paragraph synthesis of the source]

## Key claims
- Claim 1
- Claim 2

## Key entities
[[Entity1]], [[Entity2]]

## Key concepts
[[Concept1]], [[Concept2]]

## Notable quotes
> Quote here (p. N)

## Contradictions / tensions
[Anything that conflicts with existing wiki pages — explicit callout]

## Source file
`raw/filename.pdf`
```

Entity page template:
```markdown
---
title: "Entity Name"
type: entity
tags: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
source_count: N
---

## Overview
[Who/what this is]

## Appearances in sources
- [[source-slug]] — role or context

## Related
[[Concept1]], [[Entity2]]
```

Concept page template:
```markdown
---
title: "Concept Name"
type: concept
tags: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
source_count: N
---

## Definition
[What this concept means in this wiki's context]

## How sources treat it
| Source | Stance | Notes |
|--------|--------|-------|
| [[source]] | supports / challenges / uses | ... |

## Tensions / open questions
[Contradictions across sources, unresolved questions]

## Related
[[Concept2]], [[Entity1]]
```

### QUERY
Trigger: user asks a question.

Steps:
1. Read `wiki/index.md` to identify relevant pages.
2. Read relevant pages fully.
3. Synthesize answer with inline citations to wiki pages and sources.
4. If answer is substantive (comparative analysis, synthesis, discovered connection): offer to file it as a new concept or analysis page in the wiki.

### LINT
Trigger: user says "lint the wiki" or "health-check".

Check for:
- Pages referenced by `[[link]]` that don't exist → create stubs or flag
- Concept/entity pages with `source_count: 1` that could be merged into the source page
- Claims in older pages superseded by newer sources → update with note
- Overview.md still reflects the full corpus
- Log.md is complete and current

Report findings, then fix with user approval.

---

## Log format
Each entry in `wiki/log.md`:
```
## [YYYY-MM-DD] operation | Title or description
Brief note on what changed. Pages touched: N.
```

---

## Dataview hints
Frontmatter is Dataview-compatible. Useful queries the user can run in Obsidian:

List all sources by year:
```dataview
TABLE year, authors FROM "wiki/sources" SORT year DESC
```

Most-referenced concepts:
```dataview
TABLE source_count FROM "wiki/concepts" SORT source_count DESC
```

---

## Growth notes
- At ~50+ sources, suggest adding a `searches/` dir for filed query answers.
- At ~200+ pages, consider integrating qmd (local markdown search engine with MCP server) for faster retrieval than reading index.md.
- The schema itself should evolve — update this file when conventions change.
