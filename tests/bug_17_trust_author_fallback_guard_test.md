# Bug 17 Acceptance Test: trust author fallback guard

## Fixtures

- Fixture A: v0.6.2 smoke run `2026-04-25T21-32-17`, article `granola-chat-just-got-smarter`. `author_validation` has already passed with `display_name = "Chris Pedregal"` while the source article author is missing.
- Fixture B: article with empty `reviewers.json`, full-name source author, and `author_validation.source = "article_author_fallback"`.
- Fixture C: article with failed `author_validation`, non-empty `reviewers.json`, and no source author.

## Steps

```sh
RUN="$HOME/Library/Application Support/ai-search-blog-optimiser/v3/runs/2026-04-25T21-32-17"
python3 dashboard/quality_gate.py "$RUN" granola-chat-just-got-smarter || true

FIXTURE_A_MANIFEST="$RUN/outputs/optimised/granola-chat-just-got-smarter.manifest.json"
FIXTURE_B_MANIFEST="outputs/optimised/article-author-fallback.manifest.json"
FIXTURE_C_MANIFEST="outputs/optimised/missing-author-with-reviewers.manifest.json"
```

The command can return non-zero while unrelated blocking issues remain. The assertions below are scoped to the Bug 17 trust author fallback guard.

## Fixture A jq Assertions

```sh
jq -e '.author_validation.status == "passed"' "$FIXTURE_A_MANIFEST"
jq -e '.author_validation.display_name == "Chris Pedregal"' "$FIXTURE_A_MANIFEST"
jq -e '.trust_block.passed == true' "$FIXTURE_A_MANIFEST"
jq -e '.trust_block.author_name == "Chris Pedregal"' "$FIXTURE_A_MANIFEST"
jq -e '.trust_block.author_name == .author_validation.display_name' "$FIXTURE_A_MANIFEST"
```

## Fixture B jq Assertions

```sh
jq -e '.author_validation.status == "passed"' "$FIXTURE_B_MANIFEST"
jq -e '.author_validation.source == "article_author_fallback"' "$FIXTURE_B_MANIFEST"
jq -e '.trust_block.source == "article_author_fallback"' "$FIXTURE_B_MANIFEST"
jq -e '.trust_block.passed == true' "$FIXTURE_B_MANIFEST"
jq -e '.trust_block.author_name == .author_validation.display_name' "$FIXTURE_B_MANIFEST"
```

## Fixture C jq Assertions

```sh
jq -e '.author_validation.status == "failed"' "$FIXTURE_C_MANIFEST"
jq -e '.trust_block.passed == false' "$FIXTURE_C_MANIFEST"
jq -e '.trust_block.author_name == ""' "$FIXTURE_C_MANIFEST"
```

## Negative Regression jq Assertions

```sh
jq -e '(.trust_block.author_name == "") == (.author_validation.status != "passed")' "$FIXTURE_A_MANIFEST"
jq -e '(.trust_block.author_name == "") == (.author_validation.status != "passed")' "$FIXTURE_B_MANIFEST"
jq -e '(.trust_block.author_name == "") == (.author_validation.status != "passed")' "$FIXTURE_C_MANIFEST"
```
