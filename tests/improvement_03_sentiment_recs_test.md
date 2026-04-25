# Improvement 03 Acceptance Test: Sentiment Recommendations

## Fixture

- Run fixture: `fixtures/v0.6.0/sentiment-floor/run.json`
- Gap fixture: `outputs/gaps/sentiment-floor.json`
- Recommendation output: `outputs/recommendations/sentiment-floor.json`
- Fixture prompt has `brand.sentiment_per_engine.chatgpt-scraper == 64`.
- Fixture prompt has `top_gap_chats[0].excerpt == "Competitors are described as reliable for editable summaries with clear source notes."`

## Steps

1. Run `rubric_lint(run_id, "sentiment-floor")`.
2. Run the recommender for `sentiment-floor`.
3. Read `outputs/recommendations/sentiment-floor.json`.

## Assertions

- `recommendations[?category=="sentiment"]` has length `>= 1`.
- The sentiment rec has `source == "llm"`.
- The sentiment rec has `target_engines == ["chatgpt-scraper"]`.
- The sentiment rec has `signal_types` containing `engine_sentiment`.
- The sentiment rec has `evidence[]` containing the exact fixture excerpt.
- The sentiment rec `description` contains `64` and `65`.
- The sentiment rec `fix` contains a concrete quoted sentence or phrase and does not equal `improve sentiment`.
