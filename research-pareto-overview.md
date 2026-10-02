# Research: does an official opencode overview page exist comparing benchmark scores vs opencode credits with a Pareto frontier line?

**Date:** 2026-10-02
**Verdict: DOES NOT EXIST** — No official opencode.dev / opencode GitHub page combines benchmark scores and opencode credits/Go cost on one chart with a Pareto frontier line. The pieces exist separately (pricing tables, usage-limit tables, per-model benchmark tables, third-party Pareto charts), but no single official overview page draws the Pareto line.

## 1. Official opencode pages checked

### 1.1 OpenCode Zen marketing page — no benchmarks, no Pareto chart
- URL: https://opencode.ai/zen
- Claims Zen models are "tested and benchmarked specifically for coding agents" but shows **no benchmark scores, no pricing table, no chart** on the page — only signup/testimonial/FAQ content.

### 1.2 OpenCode Zen docs — pricing table only, no benchmark scores, no Pareto line
- URL: https://opencode.ai/docs/zen/
- Contains a full **per-1M-token pricing table** (input / output / cached read / cached write) for all Zen models, including Go-relevant ones:
  - MiniMax M2.5/M2.7/M3: $0.30 in / $1.20 out / $0.06 cached (https://opencode.ai/docs/zen/#pricing)
  - GLM 5.3 Flash: $0.15 / $0.50 / $0.03; GLM 5.3/5.2: $1.40 / $4.40 / $0.26 (https://opencode.ai/docs/zen/#pricing)
  - DeepSeek V4.1 Flash: $0.30 / $1.20; V4 Flash: $0.14 / $0.28; V4 Pro: $1.74 / $3.48 (https://opencode.ai/docs/zen/#pricing)
- States "Benchmark the best models/providers for coding agents" as a **goal** (https://opencode.ai/docs/zen/#goals) but publishes **no scores and no chart**.
- Model endpoint/ID list only (https://opencode.ai/docs/zen/#endpoints); metadata API at `https://opencode.ai/zen/v1/models` (https://opencode.ai/docs/zen/#models).

### 1.3 OpenCode Go docs — subscription limits + request estimates, no benchmarks, no Pareto line
- URL: https://opencode.ai/docs/go/
- Go = $10/mo, Go Plus = $40/mo; each model has a monthly dollar limit and 5h (20%) / weekly (50%) caps (https://opencode.ai/docs/go/#usage-limits).
- Per-model "estimated requests" table derived from typical token counts per request, e.g. MiniMax M2.7 ~3,400 req/5h, GLM-5.3-Flash ~6,320 req/5h, DeepSeek V4.1 Flash ~26,000 req/5h (https://opencode.ai/docs/go/#estimated-requests).
- Lists current Go models: GLM-5.3-Flash/5.3/5.2, Kimi K3/K2.7/K2.6, Qwen3.8 Max/Flash, Qwen3.7 Plus, MiniMax M3/M2.7, DeepSeek V4.1 Flash/V4 Pro/V4 Flash, MiMo, GPT 6 Luna, Grok 4.6/4.7, Muse Spark, Hy3/Hy4, free Space Bunny/LongCat (https://opencode.ai/docs/go/#how-it-works).
- **No benchmark scores, no score-vs-cost chart.**

### 1.4 OpenCode Go marketing page — same limits view, no Pareto
- URL: https://opencode.ai/go
- Shows est. requests/5h + monthly usage per model; no benchmarks or Pareto line.

### 1.5 OpenCode Data (usage/cost, per-model benchmarks, but no Pareto line)
- Index: https://opencode.ai/data/ — ranks models by real usage tokens/users, plus session cost, token prices, cache ratio, retention. No benchmark scores on the index, no Pareto chart.
- Per-model pages DO combine usage + pricing + benchmark scores in one table, e.g.:
  - DeepSeek V4.1 Flash page: rank #2, $0.30/$1.20 per 1M, benchmark table (GPQA Diamond 90.9, Terminal-Bench variants, DeepSWE variants, etc., sourced to Hugging Face): https://opencode.ai/data/deepseek/deepseek-v4-1-flash.md
- But: benchmarks are vendor-reported aggregates per model (not opencode-run coding-agent scores), there is **no cross-model score-vs-credits scatter and no Pareto line** anywhere on opencode.ai/data.

### 1.6 opencode GitHub (sst/anomalyco/opencode) — no model overview page
- Repo: https://github.com/sst/opencode (now anomalyco/opencode). No docs page with benchmark table or Pareto chart found.
- Only automation touching model data: `models-snapshot.yml` workflow refreshes a bundled models.dev snapshot (`packages/core/src/models-dev/snapshot.txt`) — pricing/metadata plumbing, not a benchmark overview.
- Community benchmark repos exist but are unofficial: `grigio/opencode-benchmark-dashboard` (speed/correctness harness), topic `opencode-zen` comparison projects.

### 1.7 anomalyco/opencode-bench — harness scores, bar/radar charts only, no Pareto, no credits
- Repo: https://github.com/anomalyco/opencode-bench
- Runs agents against production commits, multi-judge scoring across 5 dimensions (https://github.com/anomalyco/opencode-bench).
- Chart utils build only radar + horizontal bar charts via QuickChart (`src/util/charts.ts`) — no scatter, no Pareto-line code.

## 2. Closest alternatives (third-party Pareto charts, NOT official, NOT opencode credits)

### 2.1 Artificial Analysis Coding Agents leaderboard — HAS a Pareto line (closest match for the chart type)
- URL: https://artificialanalysis.ai/agents/coding-agents
- Has an "Artificial Analysis Coding Agent Index vs. Cost per Task" scatter with an explicit **"Pareto line"** toggle, color-by model/agent, "most attractive quadrant" annotation.
- Index = composite of DeepSWE v1.1 + Terminal-Bench 4.0 + SWE-Atlas-QnA (methodology at https://artificialanalysis.ai/agents/coding-agents + https://artificialanalysis.ai/methodology/coding-agents-benchmarking).
- Includes an `Opencode - GLM-5.3` row (53.6% in the 2026-09-30 snapshot mirror: https://benchlm.ai/benchmarks/aacodingagents).
- **Why it is not what was asked:** third-party (not opencode.dev), cost axis is pay-per-token API cost per task — not opencode Zen credits or Go subscription limits.
- Secondary pointer: r/opencodeCLI thread "New Pareto Line - Cost vs Intelligence" (https://www.reddit.com/r/opencodeCLI/comments/1vmyz16/new_pareto_line_cost_vs_intelligence/) — Reddit blocked to scrapers; title only.

### 2.2 Faros "Open Source vs Frontier" study — Pareto views with OpenCode routes, single cohort
- URL: https://www.faros.ai/blog/open-models-vs-frontier-models
- 211 real tasks × 7 harness+model routes; "Quality vs. projected cost: the seven-way Pareto view" and "Quality vs. runtime" / "Consistency vs. projected cost" Pareto charts featuring OpenCode+GLM-5.2, OpenCode+Kimi K2.6, OpenCode+Opus 4.8.
- **Why not:** vendor blog experiment (Faros Time Machine), projected list-price costs, not opencode credits; not a maintained overview page.

### 2.3 Artificial Curiosity Labs Pareto-frontier explainer — general LLM Pareto, not opencode-specific
- URL: https://artificialcuriositylabs.ai/posts/pareto-frontier-is-the-model-market-map/
- Defines intelligence-price Pareto frontier on Artificial Analysis data (13/351 models on frontier, 2026-06-02 snapshot); names MiniMax-M2.7, MiMo-V2.5-Pro, Kimi K2.6, Qwen3.x on the frontier. Educational, not an opencode overview.

## 3. Web searches run (2026-10-02)
- `opencode models pareto` → Zen page, OpenCode Data page, OpenRouter "Pareto Code Router" (unrelated product: https://openrouter.ai/openrouter/pareto-code), YouTube "Pareto Front chart" tutorial snippet.
- `opencode.dev models benchmark credits` → Zen docs, Go review blogs, Dax Raad benchmarking talk (https://www.youtube.com/watch?v=FtxY5qRJAYw).
- `opencode zen models overview pareto frontier` → Zen pages + unrelated Jeff Dean frontier post.
- `opencode.ai docs benchmark coding models scores table` → no official benchmark table; only usage data + third-party leaderboards.
- `"opencode" "pareto" benchmark cost chart line models` → Artificial Analysis Pareto line, Faros Pareto views, r/opencodeCLI Pareto thread.

## 4. Conclusion
No official opencode overview page plots benchmark scores against opencode credits/Go cost with a Pareto frontier line. Anyone building an opencode-go Pareto view would be creating something new, sourcing scores from Artificial Analysis coding-agent index (https://artificialanalysis.ai/agents/coding-agents) or opencode Data per-model benchmark tables (e.g. https://opencode.ai/data/deepseek/deepseek-v4-1-flash.md) and costs from Zen pricing (https://opencode.ai/docs/zen/#pricing) / Go limits (https://opencode.ai/docs/go/#usage-limits).
