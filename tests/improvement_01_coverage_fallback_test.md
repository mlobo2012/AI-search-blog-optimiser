# Improvement 01 Acceptance Test - Coverage Fallback

Executable checklist for Lane C.

## Setup

- [ ] Use a run with article slug `so-you-think-its-easy-to-change-an-app-icon`.
- [ ] Run the pipeline through the Peec gap-reader stage.
- [ ] Set:

```sh
RUN_DIR="$HOME/Library/Application Support/ai-search-blog-optimiser/v3/runs/<run_id>"
SLUG="so-you-think-its-easy-to-change-an-app-icon"
GAP="$RUN_DIR/outputs/gaps/$SLUG.json"
```

## Required Assertions

- [ ] Gap artefact exists.

```sh
test -f "$GAP"
```

- [ ] Article has zero matched prompts.

```sh
jq -e '.matched_prompts | type == "array" and length == 0' "$GAP"
```

- [ ] Gap artefact uses topic-level evidence.

```sh
jq -e '.match_mode == "topic-level"' "$GAP"
```

- [ ] `topic_level_signals.category_gap` is present and non-empty.

```sh
jq -e '.topic_level_signals.category_gap | type == "object" and length > 0' "$GAP"
```

- [ ] `topic_level_signals.dominant_competitor_domains` is present and non-empty.

```sh
jq -e '.topic_level_signals.dominant_competitor_domains | type == "array" and length > 0' "$GAP"
```

- [ ] Every dominant competitor domain has `domain` and enum `classification`.

```sh
jq -e '
  [.topic_level_signals.dominant_competitor_domains[]
   | has("domain")
     and (.classification | IN("COMPETITOR","EDITORIAL","CORPORATE","UGC","REFERENCE"))]
  | all
' "$GAP"
```

- [ ] `topic_level_signals.engine_sentiment` is present and non-empty.

```sh
jq -e '.topic_level_signals.engine_sentiment | type == "object" and length > 0' "$GAP"
```

- [ ] `peec_actions.overview_top_opportunities` has at least 3 entries.

```sh
jq -e '.peec_actions.overview_top_opportunities | type == "array" and length >= 3' "$GAP"
```

## Pass Criterion

All assertions exit with status `0`.
