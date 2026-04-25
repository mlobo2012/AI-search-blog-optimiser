# Improvement 08 Acceptance Test: Off-Page Action Lane

## Fixture

- Run fixture: `fixtures/v0.6.0/off-page-actions/run.json`
- Gap fixture: `outputs/gaps/off-page-actions.json`
- Recommendation output: `outputs/recommendations/off-page-actions.json`
- `peec_actions.overview_top_opportunities` contains two items where `gap_percentage >= 50` and `relative_score >= 2`.
- `gap_domains.top_competitor_cited_domains` includes `techsifted.com` and `techtarget.com`.

## Steps

1. Run `rubric_lint(run_id, "off-page-actions")`.
2. Run the recommender for `off-page-actions`.
3. Read `outputs/recommendations/off-page-actions.json`.

## Assertions

- `recommendations[?category=="off_page"]` has length `>= 2`.
- Every off-page rec has `source == "llm"`.
- `off_page_actions.length >= 2`.
- Every `off_page_actions[]` entry has non-empty `play`, `rationale`, and `evidence`.
- Every off-page rec `fix` matches `/techsifted\.com|techtarget\.com|LISTICLE|COMPARISON|HOMEPAGE|ARTICLE/i`.
- Off-page rec count is `<= 4`.
