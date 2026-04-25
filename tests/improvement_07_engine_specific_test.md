# Improvement 07 Acceptance Test: Engine-Specific Tactics

## Fixture

- Run fixture: `fixtures/v0.6.0/engine-asymmetry/run.json`
- Gap fixture: `outputs/gaps/engine-asymmetry.json`
- Recommendation output: `outputs/recommendations/engine-asymmetry.json`
- Matched prompt `pr_asymmetry_1` has visibility:
  - `chatgpt-scraper: 0`
  - `perplexity-scraper: 0`
  - `google-ai-overview-scraper: 0.71`
- Matched prompt `pr_asymmetry_1.engines_lost == ["chatgpt-scraper", "perplexity-scraper"]`.

## Steps

1. Run `rubric_lint(run_id, "engine-asymmetry")`.
2. Run the recommender for `engine-asymmetry`.
3. Read `outputs/recommendations/engine-asymmetry.json`.

## Assertions

- At least one LLM rec has `category == "engine_specific"` or `signal_types` containing `engine_pattern_asymmetry`.
- That rec has `target_engines` containing `chatgpt-scraper`.
- That rec has `target_engines` containing `perplexity-scraper`.
- That rec has `per_engine_lift.chatgpt-scraper` and `per_engine_lift.perplexity-scraper`.
- The two per-engine lift narratives are distinct; cosine string similarity must be `< 0.85`.
- The rec evidence includes `peec_signal_engine_pattern_asymmetry` or equivalent prompt evidence for `pr_asymmetry_1`.
