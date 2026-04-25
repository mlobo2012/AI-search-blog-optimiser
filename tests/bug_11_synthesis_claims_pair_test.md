# Bug 11 Acceptance Test - Synthesis Claims Pair

Executable checklist for Lane E.

## Setup

- [ ] Use a run with a 3-prompt claim cluster.
- [ ] Run the pipeline through `rubric_lint`, recommender, and `record_recommendations`.
- [ ] Set:

```sh
RUN_DIR="$HOME/Library/Application Support/ai-search-blog-optimiser/v3/runs/<run_id>"
SLUG="<article_slug>"
REC="$RUN_DIR/outputs/recommendations/$SLUG.json"
STATE="$RUN_DIR/state.json"
BAD_REC="$RUN_DIR/outputs/recommendations/$SLUG.bug-11-empty-synthesis-claims.json"
REJECT_LOG="$RUN_DIR/bug-11-record-recommendations.reject.log"
```

## Positive Path Assertions

- [ ] Recommendation artefact exists.

```sh
test -f "$REC"
```

- [ ] The run emitted at least one `claim_synthesis` recommendation.

```sh
jq -e '[.recommendations[]? | select(.category == "claim_synthesis")] | length >= 1' "$REC"
```

- [ ] Top-level `synthesis_claims[]` is populated.

```sh
jq -e '.synthesis_claims | type == "array" and length >= 1' "$REC"
```

- [ ] Each `synthesis_claims[]` entry is complete and covers the 3-prompt threshold.

```sh
jq -e '
  [.synthesis_claims[]?
   | (.claim | type == "string" and length > 0)
     and ((.addresses_prompts // []) | type == "array" and length >= 3)
     and (.section_target | type == "string" and length > 0)
     and ((.evidence_refs // []) | type == "array" and length > 0)]
  | length >= 1 and all
' "$REC"
```

- [ ] Every `claim_synthesis` rec has `addresses_prompts.length >= 3` and is paired to a top-level claim.

```sh
jq -e '
  [.recommendations[]? | select(.category == "claim_synthesis") as $rec
   | any(.synthesis_claims[]?;
       ($rec.addresses_prompts // []) as $rec_prompts
       | ($rec_prompts | length >= 3)
         and all($rec_prompts[]; (.addresses_prompts // []) | index(.))
     )]
  | length >= 1 and all
' "$REC"
```

## Reject Path Assertions

- [ ] Build a bad payload with `claim_synthesis` recs but empty `synthesis_claims[]`.

```sh
jq '.synthesis_claims = []' "$REC" > "$BAD_REC"
```

- [ ] Bad payload preserves the `claim_synthesis` trigger.

```sh
jq -e '[.recommendations[]? | select(.category == "claim_synthesis")] | length >= 1' "$BAD_REC"
```

- [ ] Bad payload has empty top-level `synthesis_claims[]`.

```sh
jq -e '.synthesis_claims | type == "array" and length == 0' "$BAD_REC"
```

- [ ] Call `record_recommendations(run_id, article_slug, recommendations=<contents of BAD_REC>)` and capture the failure.

```sh
test "${RECORD_RECOMMENDATIONS_EXIT:?set by rejected tool call}" -ne 0
```

- [ ] The rejected write raised recommendation validation failure.

```sh
grep -E 'ValueError: Recommendation validation failed|Recommendation validation failed:' "$REJECT_LOG"
```

- [ ] The rejected write added a warning banner with pair-contract details.

```sh
jq -e '
  .banners[-1].severity == "warn"
  and (.banners[-1].message | contains("Recommendation validation failed"))
  and (.banners[-1].message | contains("claim_synthesis recommendations require non-empty top-level synthesis_claims"))
' "$STATE"
```

## Pass Criterion

All positive assertions exit with status `0`; the reject-path `record_recommendations` call exits non-zero and leaves the warning banner assertion green.
