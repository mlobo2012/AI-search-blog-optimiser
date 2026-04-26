# Bug 24 Acceptance Test: recommender Count Cap

## Fixtures

- Strong coverage fixture A: a `peec-prompt-matched` article where Peec gaps, engine asymmetry,
  source displacement, sentiment, and off-page signals previously led the recommender to emit 10
  LLM-source recommendations.
- Weak coverage fixture B: a `peec-prompt-matched` article where the admissible evidence supports
  exactly 4 LLM-source recommendations.

## Steps

Run the recommender through the controller for each fixture and then read the recommendation
artefact.

```sh
REC="$RUN/outputs/recommendations/$ARTICLE_SLUG.json"
RECOMMENDER_LOG="$RUN/recommender.log"
```

The command can return non-zero while unrelated blockers from other lanes remain. The assertions
below are scoped to Bug 24.

## Strong Coverage Fixture A Assertions

Input signal examples:

```json
{
  "mode": "peec-prompt-matched",
  "matched_prompts": ["pr_001", "pr_002", "pr_003", "pr_004", "pr_005", "pr_006"],
  "signals": ["engine_asymmetry", "sentiment_floor", "source_displacement", "off_page_actions"]
}
```

Expected recommender behavior:

- Merge or drop the lowest-priority candidates instead of emitting 9 or 10 LLM-source recs.
- Preserve the highest-priority evidence-backed recommendations.
- Avoid the validator retry banner.

```sh
jq -e '.mode == "peec-prompt-matched"' "$REC"
jq -e '[.recommendations[]? | select(.source == "llm")] | length >= 3 and length <= 8' "$REC"
! grep -E 'LLM-source recommendation count must be 3-8' "$RECOMMENDER_LOG"
```

The expected steady-state count is 8 when the fixture still has at least 8 useful candidates after
merging; fewer is acceptable only when the dropped candidates were lower priority and redundant.

## Weak Coverage Fixture B Assertions

Input signal examples:

```json
{
  "mode": "peec-prompt-matched",
  "matched_prompts": ["pr_101", "pr_102", "pr_103"],
  "signals": ["prompt_visibility", "citation_rate", "gap_chat_excerpt"]
}
```

Expected recommender behavior:

- Keep the natural 4-rec output.
- Do not inflate the set just because the prompt mentions an 8-rec cap.
- Avoid the validator retry banner.

```sh
jq -e '.mode == "peec-prompt-matched"' "$REC"
jq -e '[.recommendations[]? | select(.source == "llm")] | length == 4' "$REC"
! grep -E 'LLM-source recommendation count must be 3-8' "$RECOMMENDER_LOG"
```
