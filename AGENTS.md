# opencode-go-pareto

Live: https://jnslmk.github.io/opencode-go-pareto/ · public repo.

AA benchmark scores (y) vs estimated opencode-go credits/request (x, log scale),
with Pareto frontier and a score-source switcher.

## Layout

- `index.html` — static page, renders `data/models.json`, no build step.
- `data/models.json` — generated, never hand-edit. Refreshed daily by CI.
- `scripts/update_models.py` — stdlib-only updater. Model set, prices, limits
  and token mix come from https://opencode.ai/docs/go/; scores from AA model
  pages (`aa_index`) plus benchlm mirrors (`aa`, `frontiercode`, `benchlm_coding`).
- `.github/workflows/update-models.yml` — daily refresh, commits `data/`.
- `.github/workflows/pages.yml` — deploys on push (path-filtered).

## Refresh data

```bash
python3 scripts/update_models.py data/models.json
python3 -m http.server 8321  # open index.html, check chart + table
```

The updater fails loudly on unexpected page shapes or mass misses — a red run
means a source changed format, not a retry issue. Unmatched leaderboard rows
and models without AA pages are reported in `meta.unmatched`, never guessed.

## AA slug policy

AA slugs are usually the Go id with dots as dashes (`qwen3.8-max` →
`qwen3-8-max`). If a model page 404s, use skill `aa-slug-resolve` to find the
newest dated slug available (e.g. `mimo-v2-5-0424`). Record renames in
`AA_SLUGS` in `scripts/update_models.py`; never map across model families.
Free/experimental models may have no AA page — report, don't guess.

## Commits

Conventional Commits: `feat:`/`fix:`/`chore:` + scope, imperative mood,
lowercase, no period.
