# Bug 13 Acceptance Test: trust_block Author Consistency

## Fixture

- Positive fixture: v0.6.0 smoke run `2026-04-25T19-21-10`, article `series-c`.
- Negative fixture: article with `reviewer_id: null` and visible first-name-only byline `Jack`.

## Steps

```sh
RUN="$HOME/Library/Application Support/ai-search-blog-optimiser/v3/runs/2026-04-25T19-21-10"
python3 dashboard/quality_gate.py "$RUN" series-c
MANIFEST="$RUN/outputs/optimised/series-c.manifest.json"
```

## jq Assertions

```sh
jq -e '.author_validation.status == "passed"' "$MANIFEST"
jq -e '.author_validation.reviewer_id == null' "$MANIFEST"
jq -e '.author_validation.display_name == "Chris Pedregal"' "$MANIFEST"
jq -e '.trust_block.passed == true' "$MANIFEST"
jq -e '.trust_block.author_name == "Chris Pedregal"' "$MANIFEST"
jq -e '.trust_block.author_name == .author_validation.display_name' "$MANIFEST"
jq -e '((.author_validation.status == "passed") == (.trust_block.author_name != ""))' "$MANIFEST"
```

## Negative Path jq Assertions

```sh
NEGATIVE_MANIFEST="outputs/optimised/first-name-only.manifest.json"
jq -e '.author_validation.status == "failed"' "$NEGATIVE_MANIFEST"
jq -e '.trust_block.passed == false' "$NEGATIVE_MANIFEST"
jq -e '.trust_block.author_name == ""' "$NEGATIVE_MANIFEST"
jq -e '((.author_validation.status == "passed") == (.trust_block.author_name != ""))' "$NEGATIVE_MANIFEST"
```
