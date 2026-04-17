# Agent Instructions

This repository uses a `lat` knowledge graph in `lat.md/`. The graph documents
design decisions, domain concepts, the public API, and test specifications.

## Before You Start

Read the relevant `lat.md/` sections before modifying code. Use:

    python -m lat search <term>      # find relevant sections
    python -m lat section <id>       # display a specific section

For example, before touching retry logic: `python -m lat section job-retry-logic`.

## Before You Finish

Always run:

    python -m lat check

This validates that all `[[wiki links]]` in `lat.md/` resolve, all
`# @lat: [[id]]` source comments point to existing sections, and every
section marked `require-code-mention: true` has at least one source backlink.
Fix any errors reported before committing.

## Annotating Source Changes

When you add or meaningfully modify a function or class that corresponds to a
documented concept, add a `# @lat: [[section-id]]` comment on or just above
the definition. Example:

    class Scheduler:
        # @lat: [[scheduler-engine]]

Then re-run `python -m lat check` to confirm the backlink is valid.

## Adding or Updating Sections

New sections must have a unique `<!-- id: kebab-case-id -->` comment
immediately below the heading. If the concept must have a corresponding code
location, add `<!-- require-code-mention: true -->` on the next line.

To update an existing section, edit the relevant file in `lat.md/` and run
`python -m lat check` afterwards.

## Pre-commit Hook (optional)

To enforce consistency on every commit, add this to `.git/hooks/pre-commit`:

    #!/bin/sh
    python -m lat check
