# Bug 14 Acceptance Test: trust_block Promoted Reviewer

## Fixtures

- Regression fixture A: v0.6.1 smoke run `2026-04-25T20-12-28`, article `granola-chat-just-got-smarter`. The source author is `Jack`, while the rendered promoted reviewer and `author_validation.display_name` are `Chris Pedregal`.
- Retention fixture B: v0.6.1 smoke run `2026-04-25T20-12-28`, article `series-c`. This keeps the explicit `reviewer_id` path fixed by Bug 13/Lane F.
- Negative fixture: article with first-name-only source author `Jack`, no selected reviewer, no promoted reviewer in rendered HTML, and failed `author_validation`.

## Steps

```sh
RUN="$HOME/Library/Application Support/ai-search-blog-optimiser/v3/runs/2026-04-25T20-12-28"
python3 dashboard/quality_gate.py "$RUN" granola-chat-just-got-smarter || true
python3 dashboard/quality_gate.py "$RUN" series-c || true

GRANOLA_MANIFEST="$RUN/outputs/optimised/granola-chat-just-got-smarter.manifest.json"
SERIES_C_MANIFEST="$RUN/outputs/optimised/series-c.manifest.json"
```

The command can return non-zero while unrelated blocking issues from other lanes remain. The assertions below are scoped to Bug 14.

## Granola Regression jq Assertions

```sh
jq -e '.author_validation.status == "passed"' "$GRANOLA_MANIFEST"
jq -e '.author_validation.display_name == "Chris Pedregal"' "$GRANOLA_MANIFEST"
jq -e '.author_validation.reviewer_id == null' "$GRANOLA_MANIFEST"
jq -e '.trust_block.passed == true' "$GRANOLA_MANIFEST"
jq -e '.trust_block.author_name == "Chris Pedregal"' "$GRANOLA_MANIFEST"
jq -e '.trust_block.author_name == .author_validation.display_name' "$GRANOLA_MANIFEST"
jq -e '((.trust_block.author_name == "") == (.author_validation.status != "passed"))' "$GRANOLA_MANIFEST"
```

## series-c Retention jq Assertions

```sh
jq -e '.author_validation.status == "passed"' "$SERIES_C_MANIFEST"
jq -e '.author_validation.display_name == "Chris Pedregal"' "$SERIES_C_MANIFEST"
jq -e '.author_validation.reviewer_id == "chris-pedregal"' "$SERIES_C_MANIFEST"
jq -e '.trust_block.passed == true' "$SERIES_C_MANIFEST"
jq -e '.trust_block.author_name == "Chris Pedregal"' "$SERIES_C_MANIFEST"
jq -e '.trust_block.author_name == .author_validation.display_name' "$SERIES_C_MANIFEST"
jq -e '((.trust_block.author_name == "") == (.author_validation.status != "passed"))' "$SERIES_C_MANIFEST"
```

## Negative Path jq Assertions

```sh
NEGATIVE_MANIFEST="outputs/optimised/first-name-only-no-reviewer.manifest.json"
jq -e '.author_validation.status == "failed"' "$NEGATIVE_MANIFEST"
jq -e '.trust_block.passed == false' "$NEGATIVE_MANIFEST"
jq -e '.trust_block.author_name == ""' "$NEGATIVE_MANIFEST"
jq -e '((.trust_block.author_name == "") == (.author_validation.status != "passed"))' "$NEGATIVE_MANIFEST"
```
