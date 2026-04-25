# Bug 12 Acceptance Test: audit_after Is Numeric

## Fixture

- Positive fixture: v0.6.0 smoke run `2026-04-25T19-21-10`, article `granola-chat-just-got-smarter`.
- Negative fixture: any copied run with `optimised/{slug}.schema.json` removed.

## Steps

```sh
RUN="$HOME/Library/Application Support/ai-search-blog-optimiser/v3/runs/2026-04-25T19-21-10"
python3 dashboard/quality_gate.py "$RUN" granola-chat-just-got-smarter
MANIFEST="$RUN/outputs/optimised/granola-chat-just-got-smarter.manifest.json"
```

## jq Assertions

```sh
jq -e '.quality_gate.passed == true' "$MANIFEST"
jq -e '(.audit_after | type) == "number"' "$MANIFEST"
jq -e '.audit_after >= 0 and .audit_after <= 40' "$MANIFEST"
jq -e '.audit_after >= 32' "$MANIFEST"
jq -e 'if .quality_gate.passed == true then .audit_after != null else true end' "$MANIFEST"
jq -e 'if .module_checks.failed_count == 0 then .audit_after != null else true end' "$MANIFEST"
jq -e '(.score_breakdown.score | type) == "number"' "$MANIFEST"
jq -e '.score_breakdown.score >= 0 and .score_breakdown.score <= 40' "$MANIFEST"
jq -e '(.quality_gate.passed == true and .audit_after == null) | not' "$MANIFEST"
```

## Negative Path

```sh
BROKEN_RUN="/tmp/bug-12-missing-schema-run"
rm -rf "$BROKEN_RUN"
cp -R "$RUN" "$BROKEN_RUN"
rm "$BROKEN_RUN/outputs/optimised/granola-chat-just-got-smarter.schema.json"
! python3 dashboard/quality_gate.py "$BROKEN_RUN" granola-chat-just-got-smarter
```
