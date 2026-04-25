# Improvement 02 Acceptance Test - Signal Richness

Executable checklist for Lane C.

## Setup

- [ ] Use a run with an article that has rich Peec coverage, such as `granola-chat-just-got-smarter` or `series-c`.
- [ ] Run the pipeline through the Peec gap-reader stage.
- [ ] Set:

```sh
RUN_DIR="$HOME/Library/Application Support/ai-search-blog-optimiser/v3/runs/<run_id>"
SLUG="granola-chat-just-got-smarter"
GAP="$RUN_DIR/outputs/gaps/$SLUG.json"
```

## Required Assertions

- [ ] Gap artefact exists.

```sh
test -f "$GAP"
```

- [ ] Article has at least 5 matched prompts.

```sh
jq -e '.matched_prompts | type == "array" and length >= 5' "$GAP"
```

- [ ] Every matched prompt has `position_per_engine`, `sentiment_per_engine`, and `citation_score_per_engine`.

```sh
jq -e '
  [.matched_prompts[]
   | (.brand | has("position_per_engine"))
     and (.brand | has("sentiment_per_engine"))
     and (.brand | has("citation_score_per_engine"))]
  | all
' "$GAP"
```

- [ ] Every cited competitor has enum `classification`.

```sh
jq -e '
  [.matched_prompts[].cited_competitors[]
   | .classification | IN("COMPETITOR","EDITORIAL","CORPORATE","UGC","REFERENCE")]
  | all
' "$GAP"
```

- [ ] At least 2 prompts have non-empty `top_gap_chats`.

```sh
jq -e '[.matched_prompts[] | select((.top_gap_chats // []) | length > 0)] | length >= 2' "$GAP"
```

- [ ] Every populated gap chat has `chat_id`, `engine`, `excerpt`, and `cited_urls`.

```sh
jq -e '
  [.matched_prompts[].top_gap_chats[]?
   | has("chat_id")
     and has("engine")
     and has("excerpt")
     and has("cited_urls")]
  | all
' "$GAP"
```

- [ ] Every gap chat excerpt is 200 characters or shorter.

```sh
jq -e '[.matched_prompts[].top_gap_chats[]?.excerpt | length <= 200] | all' "$GAP"
```

## Pass Criterion

All assertions exit with status `0`.
