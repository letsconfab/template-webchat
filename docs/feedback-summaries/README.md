# Feedback summaries

Canonical, version-controlled 30-day negative-feedback summaries for the
administrator Feedback Case list.

## Authoring

1. Analyze feedback outside the deployed runtime.
2. Write a Markdown artifact with YAML front matter under this directory.
3. Name the file `YYYY-MM-DD-negative-feedback-30d.md`.
4. Declare `privacy_reviewed: true` only after human privacy review.
5. Open a normal repository change for review; shipping a frontend build
   publishes the packaged summary.

## Required front matter

```yaml
schema_version: 1
artifact_id: <stable-kebab-case-id>
title: <human-readable title>
generated_at: <ISO-8601 UTC timestamp>
window_start: <ISO-8601 UTC timestamp>
window_end: <ISO-8601 UTC timestamp>
authoring_workflow: <model/tool and review workflow>
privacy_reviewed: true
```

`window_start` must precede `window_end` and the evidence window must span
exactly 30 days.

## Required body sections

1. `## Executive summary`
2. `## Evidence snapshot`
3. `## Major themes`
4. `## Limitations and caveats`

Optional sections may include visualizations (Mermaid or relative SVG/PNG),
an anonymized inventory, product implications, and related-document links.

## Privacy checklist

Permitted: aggregate statistics, paraphrased themes, sanitized analysis.

Forbidden:

- raw or near-verbatim tester comments, prompts, or answers
- names, emails (including masked), or account identifiers
- user, Chat Session, Feedback Case, or message identifiers
- per-tester breakdowns
- links to production Feedback Cases or private operational records
- secrets and deployment-specific connection details

## Local validation

From `frontend/`:

```bash
npm run prepare-feedback-summaries
```

Invalid artifacts fail the command (and therefore `npm run build`) with
file-specific diagnostics. An empty directory packages a valid empty index.
