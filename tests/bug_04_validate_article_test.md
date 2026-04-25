# Bug 4 Acceptance Test - Draft Manifest Contract, Path B

Manual reproduction sequence for Lane A Path B.

## Setup

Use any clean run with one crawled article, one evidence pack, and one recommendation artifact.

## Steps

1. Confirm the removed validator tool token is absent from the Lane A prompt/playbook files:

```text
rg 'validate[_]article' agents/generator.md skills/blog-optimiser-pipeline/SKILL.md tests/bug_04_*_test.md
```

2. Inspect `agents/generator.md`.
3. Inspect `skills/blog-optimiser-pipeline/SKILL.md` Stage 7.
4. Run the generator for one article.
5. Read `optimised/{slug}.manifest.json`.
6. Read `runs/{run_id}/state.json`.

## Required Assertions

- The search in step 1 returns zero matches.
- The generator prompt contains an explicit self-rubric write contract for `optimised/{article_slug}.manifest.json`.
- The pipeline playbook tells the generator to write `audit_before`, `audit_after`, `breakdown`, and `quality_gate` into the manifest.
- `optimised/{slug}.manifest.json` exists and parses as JSON.
- The manifest includes `audit_before`, `audit_after`, `breakdown`, and `quality_gate`.
- `quality_gate` is `pass` only when `audit_after >= 32` and there are no missing required modules or blocking trust, evidence, schema, or scope issues; otherwise it is `fail`.
- `state.json` has `articles[].stages.draft.audit_after` matching the manifest.
- `state.json` has `articles[].stages.draft.quality_gate` set from the manifest result.

## Pass Criterion

All assertions pass. The draft stage does not depend on a separate server-side quality-gate call.
