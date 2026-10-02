# opencode-go Pareto

AA coding-agent index vs estimated opencode-go credits per request, with Pareto frontier.

Live: https://jnslmk.github.io/opencode-go-pareto/

- Page: `index.html` (static SVG scatter + frontier), data: `data/models.json`
- Updater: `scripts/update_models.py` (stdlib only) — sources:
  - models/prices/limits/token mix: https://opencode.ai/docs/go/
  - AA scores mirror: https://benchlm.ai/md/benchmarks/aacodingagents.md
    (canonical: https://artificialanalysis.ai/agents/coding-agents)
- Cost metric: input·in + cached·cache + output·out per typical request
  (peak pricing for DeepSeek, base tier for tiered models, free = $0).
- Models no longer listed in the Go docs drop out automatically; new ones are picked up.
- `.github/workflows/update-models.yml` refreshes `data/models.json` daily.
