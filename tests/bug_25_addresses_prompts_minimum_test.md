# Bug 25 Acceptance Test: addresses_prompts Minimum

## Fixtures

- Narrow rec fixture A: a `peec-prompt-matched` article where the recommender previously emitted
  one LLM-source recommendation with only 2 prompt ids in `addresses_prompts`.
- Already-compliant fixture B: a `peec-prompt-matched` article where every LLM-source
  recommendation already addressed at least 3 prompt ids.

## Steps

Run the recommender through the controller for each fixture and then read the recommendation
artefact.

```sh
REC="$RUN/outputs/recommendations/$ARTICLE_SLUG.json"
RECOMMENDER_LOG="$RUN/recommender.log"
```

The command can return non-zero while unrelated blockers from other lanes remain. The assertions
below are scoped to Bug 25.

## Narrow Rec Fixture A Assertions

Input recommendation pattern that previously failed:

```json
{
  "id": "rec-005",
  "source": "llm",
  "category": "engine_specific",
  "addresses_prompts": ["pr_single_engine_1", "pr_single_engine_2"]
}
```

Expected recommender behavior:

- Broaden the recommendation to at least 3 related prompt ids when the same fix applies to an
  adjacent prompt cluster.
- Drop the recommendation when it cannot honestly address 3 related prompt ids.
- Avoid the validator retry banner.

```sh
jq -e '.mode == "peec-prompt-matched"' "$REC"
jq -e '
  [.recommendations[]?
   | select(.source == "llm")
   | ((.addresses_prompts // []) | type == "array" and length >= 3)]
  | all
' "$REC"
! grep -E 'addresses_prompts must contain at least 3 prompt ids' "$RECOMMENDER_LOG"
```

If the formerly narrow recommendation is still present, its `addresses_prompts` array must contain
at least 3 prompt ids. If it cannot be broadened honestly, it must be absent from the final rec set.

## Already-Compliant Fixture B Assertions

Input recommendation pattern:

```json
{
  "id": "rec-002",
  "source": "llm",
  "category": "claim_synthesis",
  "addresses_prompts": ["pr_team_1", "pr_team_2", "pr_team_3"]
}
```

Expected recommender behavior:

- Preserve existing 3+ prompt coverage.
- Do not drop otherwise valid recommendations.
- Avoid the validator retry banner.

```sh
jq -e '.mode == "peec-prompt-matched"' "$REC"
jq -e '
  [.recommendations[]?
   | select(.source == "llm")
   | ((.addresses_prompts // []) | type == "array" and length >= 3)]
  | all
' "$REC"
! grep -E 'addresses_prompts must contain at least 3 prompt ids' "$RECOMMENDER_LOG"
```
