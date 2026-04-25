# Improvement 04 Acceptance Test: Claim Synthesis

## Fixture

- Run fixture: `fixtures/v0.6.0/claim-cluster/run.json`
- Gap fixture: `outputs/gaps/claim-cluster.json`
- Recommendation output: `outputs/recommendations/claim-cluster.json`
- Gap fixture contains four matched prompts with ids `pr_team_1`, `pr_team_2`, `pr_team_3`, `pr_team_4`.
- All four prompts share the claim: `Granola is the AI note taker built for distributed and async teams.`

## Steps

1. Run `rubric_lint(run_id, "claim-cluster")`.
2. Run the recommender for `claim-cluster`.
3. Read `outputs/recommendations/claim-cluster.json`.

## Assertions

- `synthesis_claims[]` has length `>= 1`.
- At least one `synthesis_claims[]` entry has `claim == "Granola is the AI note taker built for distributed and async teams."`.
- That synthesis entry has `addresses_prompts` containing at least three of the four fixture prompt ids.
- That synthesis entry has non-empty `section_target`.
- That synthesis entry has non-empty `evidence_refs`.
- `recommendations[?category=="claim_synthesis"]` has length `>= 1`.
- The matching claim-synthesis rec has `source == "llm"` and `addresses_prompts.length >= 3`.
