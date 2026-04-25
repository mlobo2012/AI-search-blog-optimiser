# Improvement 06 Acceptance Test: Lens Framing Block

## Fixture

- Run fixture: `fixtures/v0.6.0/rich-peec/run.json`
- Gap fixture: `outputs/gaps/rich-peec.json`
- Recommendation output: `outputs/recommendations/rich-peec.json`
- Gap fixture has rich matched prompts, topic data, visibility per engine, and classified competitors.

## Steps

1. Run `rubric_lint(run_id, "rich-peec")`.
2. Run the recommender for `rich-peec`.
3. Read `outputs/recommendations/rich-peec.json`.

## Assertions

- Top-level `category_lens`, `brand_lens`, and `competition_lens` exist.
- `category_lens.topic_cluster` is non-empty.
- `category_lens.category_leaders.length >= 1`.
- `category_lens.dominant_content_shape` is one of `LISTICLE`, `COMPARISON`, `HOMEPAGE`, or `ARTICLE`.
- `category_lens.summary`, `brand_lens.summary`, and `competition_lens.summary` are each 30-150 words.
- `brand_lens.visibility_per_engine` has keys `chatgpt-scraper`, `perplexity-scraper`, and `google-ai-overview-scraper`.
- `brand_lens.dark_engines.length >= 1` when any fixture engine visibility is `< 0.30`.
- If `EDITORIAL` is the largest `competition_lens.by_classification` group, `competition_lens.strategy_implication` matches `/outreach|listicle|editorial/i`.
- If `COMPETITOR` is largest, `competition_lens.strategy_implication` matches `/comparison|positioning/i`.
