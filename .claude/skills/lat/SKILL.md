---
description: After finishing a coding task, sync the lat knowledge graph — annotate changed source files, update lat.md/ sections, and verify lat check passes.
allowed-tools: Read Edit Bash Grep
---

You have just finished a coding task. Synchronise the `lat` knowledge graph with your changes.

## Current state

**Working tree:**
```
!`git status --short 2>/dev/null`
```

**Recent commit:**
```
!`git log --oneline -1 2>/dev/null`
```

**lat check:**
```
!`python -m lat check 2>&1 || true`
```

## Steps

Work through these in order. Do not stop until `lat check` passes cleanly.

### 1. Fix existing errors

If `lat check` reported errors above, resolve them before anything else:

| Tag | Fix |
|-----|-----|
| `[BROKEN LINK]` | A `[[id]]` in `lat.md/` has no matching section — fix the id or create the section |
| `[BROKEN BACKLINK]` | A `# @lat: [[id]]` in source points nowhere — fix the id |
| `[MISSING BACKLINK]` | A section with `require-code-mention: true` has no source annotation — add `# @lat: [[id]]` to the relevant file |
| `[DUPLICATE ID]` | Two sections share an id — rename one |

### 2. Annotate changed source files

For each modified `.py` file in the working tree or last commit:

1. Read the file and identify new or significantly changed classes and functions.
2. Run `python -m lat search <term>` to find the relevant section.
3. If a matching section exists, add `# @lat: [[section-id]]` on or just above the definition.
4. If no matching section exists, create one in step 3 first, then come back and annotate.

### 3. Update lat.md/ for new concepts

For any new concept, design decision, or API surface introduced by this task:

1. Run `python -m lat search <term>` — prefer updating an existing section over creating a new one.
2. If a new section is needed, add it to the appropriate file:
   - `lat.md/architecture.md` — structural components, execution loops, algorithms
   - `lat.md/concepts.md` — domain concepts, state machines, invariants
   - `lat.md/api.md` — public API, parameters, contracts
   - `lat.md/decisions.md` — design decisions and their rationale
3. Format every new section as:
   ```
   ## Title
   <!-- id: kebab-case-id -->
   <!-- require-code-mention: true -->   ← include only if concept must always have a source backlink
   
   Body text. Cross-link with [[related-section-id]].
   ```
4. Cross-link bidirectionally: if section A mentions B, check whether B should mention A.

### 4. Verify

Run `python -m lat check`. If it exits with errors, fix them and run again.
Only finish when the output is:

```
lat check passed — no issues found.
```
