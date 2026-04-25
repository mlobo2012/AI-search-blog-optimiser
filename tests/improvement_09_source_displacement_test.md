# Improvement 09 Acceptance Test: Source Displacement

## Fixture

- Run fixture: `fixtures/v0.6.0/editorial-dominance/run.json`
- Gap fixture: `outputs/gaps/editorial-dominance.json`
- Recommendation output: `outputs/recommendations/editorial-dominance.json`
- At least four matched prompts are dominated by `EDITORIAL` classified cited competitors.
- Editorial domains include `techsifted.com` and `techtarget.com`.

## Steps

1. Run `rubric_lint(run_id, "editorial-dominance")`.
2. Run the recommender for `editorial-dominance`.
3. Read `outputs/recommendations/editorial-dominance.json`.

## Assertions

- `recommendations[?category=="source_displacement"]` has length `>= 1`.
- The source-displacement rec has `source == "llm"`.
- The source-displacement rec has non-empty `competitors_displaced[]`.
- `competitors_displaced[]` contains at least one `EDITORIAL` fixture domain.
- `recommendations[?category=="off_page"]` has length `>= 1`.
- At least one off-page rec `fix` matches `/listicle/i`.
- `competition_lens.strategy_implication` matches `/outreach|editorial/i`.
