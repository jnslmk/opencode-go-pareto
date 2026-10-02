#!/usr/bin/env python3
"""Refresh data/models.json from official opencode docs + AA coding-agent scores.

Sources:
  - Model set, token prices, monthly limits, canonical IDs:
    https://opencode.ai/docs/go/  (usage-limits + endpoints tables)
  - Typical tokens per request (cost formula inputs): same page, token-mix list
  - AA Coding Agent Index scores (machine-readable mirror of
    https://artificialanalysis.ai/agents/coding-agents):
    https://benchlm.ai/md/benchmarks/aacodingagents.md

Cost metric (x-axis): estimated USD credits per request =
  input/1e6*input_price + cached/1e6*cached_price + output/1e6*output_price.
Peak pricing for DeepSeek peak/off-peak rows, base tier for tiered models.

Stdlib only. Fails loudly on unexpected page shapes (the Action surfaces it).
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

GO_DOCS_URL = "https://opencode.ai/docs/go/"
AA_MD_URL = "https://benchlm.ai/md/benchmarks/aacodingagents.md"
AA_CANONICAL = "https://artificialanalysis.ai/agents/coding-agents"

UA = {"User-Agent": "opencode-go-pareto-updater/1.0 (+github pages demo)"}

# AA leaderboard model-part -> Go model id (only confident mappings; fuzzy
# fallback below handles new rows, unmatched ones are reported, not guessed).
AA_ALIASES = {
    "glm-5.3": "glm-5.3",
    "kimi k3": "kimi-k3",
    "muse spark 1.3": "muse-spark-1.3-contributor",
    "grok 4.7": "grok-4.7",
    "grok 4.6": "grok-4.6",
    "qwen3.8 max": "qwen3.8-max",
    "gpt-5.6 luna": "gpt-5.6-luna",
    "gpt-6 luna": "gpt-6-luna",
    "deepseek v4 pro": "deepseek-v4-pro",
    "deepseek v4 flash": "deepseek-v4-flash",
}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def parse_tables(html):
    return re.findall(r"<table.*?>(.*?)</table>", html, re.S)


def cells(row_html):
    return [re.sub(r"<[^>]+>", "", c).strip()
            for c in re.findall(r"<t[hd].*?>(.*?)</t[hd]>", row_html, re.S)]


def parse_price(s):
    s = s.strip()
    if s in ("-", "Free", ""):
        return 0.0
    m = re.match(r"\$([\d.]+)", s)
    if not m:
        raise ValueError(f"unparseable price: {s!r}")
    return float(m.group(1))


def parse_limit(s):
    s = s.replace("limited time", "").strip()
    if s.lower().startswith("unlimited"):
        return None
    m = re.match(r"\$([\d.]+)", s)
    if not m:
        raise ValueError(f"unparseable monthly limit: {s!r}")
    return float(m.group(1))


def is_pricing_table(t):
    rows = re.findall(r"<tr.*?>(.*?)</tr>", t, re.S)
    return bool(rows) and [c.lower() for c in cells(rows[0])][:5] == [
        "model", "input", "output", "cached read", "cached write"]


def pick_row(rows, *wants):
    """Pick pricing row: prefer Peak for DeepSeek, base (first) tier otherwise."""
    if len(rows) == 1:
        return rows[0]
    for r in rows:
        if "peak" in r[0].lower() and "off-peak" not in r[0].lower():
            return r
    return rows[0]


def main(out_path="data/models.json"):
    html = get(GO_DOCS_URL)

    pricing = [t for t in parse_tables(html) if is_pricing_table(t)]
    if len(pricing) != 2:
        sys.exit(f"expected 2 pricing tables (Go + Go Plus), found {len(pricing)}")
    plans = {}
    for t in pricing:
        rows = [cells(r) for r in re.findall(r"<tr.*?>(.*?)</tr>", t, re.S)][1:]
        plans[rows[0][5].replace("limited time", "").strip()] = rows
    # Identify Go ($10/mo) vs Go Plus by GLM-5.3-Flash monthly limit ($60 vs $180)
    by_flash = {rows[0][5]: rows for rows in plans.values()}
    go_rows = by_flash.get("$60")
    plus_rows = by_flash.get("$180")
    if go_rows is None or plus_rows is None:
        sys.exit(f"could not identify Go/Go Plus tables: {sorted(by_flash)}")

    # Assert token prices identical across plans; index by normalized name
    def index(rows):
        d = {}
        for r in rows:
            d.setdefault(norm(re.sub(r"\s*\(.*", "", r[0])), []).append(r)
        return d
    go_idx, plus_idx = index(go_rows), index(plus_rows)
    if set(go_idx) != set(plus_idx):
        sys.exit("Go/Go Plus model sets differ")
    for k in go_idx:
        a, b = pick_row(go_idx[k]), pick_row(plus_idx[k])
        if a[1:5] != b[1:5]:
            sys.exit(f"price mismatch across plans for {a[0]}")

    ep_tables = parse_tables(html)
    ep = [t for t in ep_tables if "model id" in "|".join(
        cells(re.findall(r"<tr.*?>(.*?)</tr>", t, re.S)[0])).lower()]
    if not ep:
        sys.exit("endpoints table not found")
    ep_rows = [cells(r) for r in re.findall(r"<tr.*?>(.*?)</tr>", ep[0], re.S)][1:]
    endpoints = {}
    for r in ep_rows:
        if len(r) >= 2:
            endpoints[norm(re.sub(r"\s*\(.*", "", r[0]))] = (r[0], r[1])

    # Token mix per request
    i = html.find("token counts per request")
    if i < 0:
        sys.exit("token-mix list not found")
    mix = {}
    for li in re.findall(r"<li>(.*?)</li>", html[i:i + 8000], re.S):
        t = re.sub(r"<[^>]+>", "", li).strip()
        m = re.match(r"(.+?)\s*[—–-]\s*([\d,]+) input,\s*([\d,]+) cached?d?,\s*([\d,]+) output",
                     t)
        if m:
            mix[m.group(1).strip()] = tuple(int(x.replace(",", "")) for x in m.groups()[1:])
    if len(mix) < 20:
        sys.exit(f"too few token-mix entries: {len(mix)}")

    def expand(key):
        # "GLM-5.3/5.2" -> ["GLM-5.3", "GLM-5.2"]; "Kimi K2.7/K2.6" likewise
        parts = [p.strip() for p in re.split(r"/", key)]
        out = [parts[0]]
        for p in parts[1:]:
            out.append(re.sub(r"[A-Za-z]?[\d.]+$", p, parts[0]))
        return out

    def find_mix(name):
        n = norm(name)
        for k, v in mix.items():
            parts = [norm(p) for p in expand(k)]
            if n in parts or any(
                n.startswith(p) or p.startswith(n) or n.endswith(p) for p in parts
            ):
                return v, k
        return None, None

    # AA scores
    md = get(AA_MD_URL)
    scores, unmatched = {}, []
    for m in re.finditer(r"\|\s*\d+\s*\|\s*\[(.+?)\]\(.+?\)\s*\|\s*(.+?)\s*\|\s*([\d.]+)%\s*\|", md):
        label, creator, score = m.group(1), m.group(2), float(m.group(3))
        model_part = re.split(r"\s+-\s+", label, maxsplit=1)[-1]
        model_part = re.sub(r"\s*\(.*?\)\s*", " ", model_part).strip()
        gid = AA_ALIASES.get(norm(model_part), None)
        if gid is None:
            for alias, g in AA_ALIASES.items():
                if norm(alias) in norm(model_part) or norm(model_part) in norm(alias):
                    gid = g
                    break
        if gid is None:
            unmatched.append({"aa_label": label, "creator": creator, "score": score})
        else:
            prev = scores.get(gid)
            if prev is None or score > prev[0]:
                scores[gid] = (score, label)
    if not scores:
        sys.exit("parsed zero AA scores")

    models = []
    missing_mix = []
    for key in sorted(go_idx):
        priced = pick_row(go_idx[key])
        plus = pick_row(plus_idx[key])
        name = re.sub(r"\s*\(.*", "", priced[0]).strip()
        ep_name, gid = endpoints.get(key, (name, None))
        if gid is None:
            # endpoints table lags pricing table; slugify display name
            gid = norm(name).replace(" ", "-")
        inp, outp, cached = (parse_price(priced[1]), parse_price(priced[2]),
                             parse_price(priced[3]))
        mix_v, mix_src = find_mix(name)
        free = inp == 0 and outp == 0
        if mix_v is None and not free:
            missing_mix.append(name)
            cost = None
        elif free:
            cost = 0.0
        else:
            ti, tc, to = mix_v
            cost = round(ti / 1e6 * inp + tc / 1e6 * cached + to / 1e6 * outp, 6)
        sc = scores.get(gid)
        models.append({
            "id": gid,
            "name": ep_name if gid in [e[1] for e in endpoints.values()] else name,
            "input_per_1m": inp,
            "output_per_1m": outp,
            "cached_per_1m": cached,
            "monthly_limit_go": parse_limit(priced[5]),
            "monthly_limit_go_plus": parse_limit(plus[5]),
            "tokens_per_request": ({"input": mix_v[0], "cached": mix_v[1],
                                    "output": mix_v[2], "source": mix_src}
                                   if mix_v else None),
            "cost_per_request_usd": cost,
            "aa_score": sc[0] if sc else None,
            "aa_label": sc[1] if sc else None,
        })
    if missing_mix:
        sys.exit(f"no token mix for priced models: {missing_mix}")
    if len(models) < 20:
        sys.exit(f"too few Go models parsed: {len(models)}")

    data = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "go_docs": GO_DOCS_URL,
            "aa_scores": AA_MD_URL,
            "aa_canonical": AA_CANONICAL,
            "method": ("cost_per_request_usd = input/1e6*input_per_1m + "
                       "cached/1e6*cached_per_1m + output/1e6*output_per_1m; "
                       "peak pricing for DeepSeek, base tier for tiered models"),
            "unmatched_aa_rows": unmatched,
        },
        "models": models,
    }
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    scored = sum(1 for m in models if m["aa_score"] is not None)
    print(f"wrote {out_path}: {len(models)} models, {scored} with AA scores, "
          f"{len(unmatched)} unmatched AA rows")


if __name__ == "__main__":
    main(*sys.argv[1:])
