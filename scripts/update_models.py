#!/usr/bin/env python3
"""Refresh data/models.json from opencode Go docs + coding-benchmark scores.

Sources:
  - Model set, token prices, monthly limits, canonical IDs:
    https://opencode.ai/docs/go/  (usage-limits + endpoints tables)
  - Typical tokens per request (cost formula inputs): same page, token-mix list
  - Score sources (machine-readable mirrors; canonical pages in SOURCES):
    - AA Coding Agent Index: https://benchlm.ai/md/benchmarks/aacodingagents.md
    - FrontierCode 1.1 Main: https://benchlm.ai/md/benchmarks/frontiercode.md
    - BenchLM Coding board:  https://benchlm.ai/md/coding.md

Cost metric (x-axis): estimated USD credits per request =
  input/1e6*input_price + cached/1e6*cached_price + output/1e6*output_price.
Peak pricing for DeepSeek peak/off-peak rows, base tier for tiered models.

Score matching is exact-only: normalized Go id <-> normalized leaderboard slug
(dashes/dots stripped). Known renames live in SLUG_REMAP; anything else that
does not match exactly is reported in meta.unmatched, never guessed.

Stdlib only. Fails loudly on unexpected page shapes (the Action surfaces it).
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

GO_DOCS_URL = "https://opencode.ai/docs/go/"
SOURCES = {
    "aa_index": {
        "label": "AA Intelligence Index",
        "url": "https://artificialanalysis.ai/models",
        "canonical": "https://artificialanalysis.ai/models",
    },
    "aa": {
        "label": "AA Coding Agent Index",
        "url": "https://benchlm.ai/md/benchmarks/aacodingagents.md",
        "canonical": "https://artificialanalysis.ai/agents/coding-agents",
    },
    "frontiercode": {
        "label": "FrontierCode 1.1 Main",
        "url": "https://benchlm.ai/md/benchmarks/frontiercode.md",
        "canonical": "https://cognition.com/frontiercode",
    },
    "benchlm_coding": {
        "label": "BenchLM Coding board",
        "url": "https://benchlm.ai/md/coding.md",
        "canonical": "https://benchlm.ai/coding",
    },
}

# AA model-page slug -> Go model id. AA slugs are usually the Go id with dots
# as dashes ("qwen3-8-max" vs "qwen3.8-max"), covered by normalization; only
# true renames go here.
AA_SLUGS = {
    "deepseek-v4.1-flash": ["deepseek-v4-1-flash"],
    "deepseek-v4-flash": ["deepseek-v4-flash"],
    "deepseek-v4-flash-vision-exp": ["deepseek-v4-flash-vision"],
    "deepseek-v4-pro": ["deepseek-v4-pro"],
    "kimi-k2.6": ["kimi-k2-6"],
    "mimo-v2.5": ["mimo-v2-5-0424"],  # base V2.5 page; -pro has its own
    "muse-spark-1.2-contributor": ["muse-spark-1-2"],
    "muse-spark-1.3-contributor": ["muse-spark-1-3"],
    "hy3": ["hy3"],
    "qwen3.8-max": ["qwen3-8-max"],
    "qwen3.8-flash": ["qwen3-8-flash-next"],  # closest published sibling
}

UA = {"User-Agent": "opencode-go-pareto-updater/1.0 (+github pages demo)"}

# BenchLM slug -> Go model id for rows that are the same model under another
# name. Exact matches need no entry. Keep this minimal and explicit.
SLUG_REMAP = {
    "deepseek-v4-1-flash": "deepseek-v4.1-flash",
    "kimi-2-6": "kimi-k2.6",
    "muse-spark-1-2": "muse-spark-1.2-contributor",
    "muse-spark-1-1": "muse-spark-1.3-contributor",  # closest older sibling
    "hy3-preview": "hy3",
    "deepseek-v4-pro-0813": "deepseek-v4-pro",
    "deepseek-v4-flash-0731": "deepseek-v4-flash",
    "kimi-k2-7-code": "kimi-k2.7-code",
}

def parse_leaderboard(md, key):
    """Parse one benchlm mirror into {go_id: (score, label)} + unmatched rows.

    AA rows link every row to the same canonical page (agent config in the
    link text, e.g. "Opencode - GLM-5.3"), so match on the model part of the
    text. FrontierCode/Coding rows link per-model (/models/<slug>), so match
    on the exact slug. Both exact-only after normalization.
    """
    scores, unmatched = {}, []
    rows = re.findall(
        r"\|\s*\d+\s*\|\s*\[(.+?)\]\((.+?)\)\s*\|\s*(.+?)\s*\|\s*([\d.]+)%?\s*\|", md)
    if not rows:
        sys.exit(f"{key}: parsed zero leaderboard rows")
    for label, link, rest, score in rows:
        score = float(score)
        if link.startswith("/models/"):
            slug = link.split("/models/")[1].split("/")[0].split("#")[0]
            gid = SLUG_REMAP.get(slug, slug)
        else:
            part = re.split(r"\s+-\s+", label, maxsplit=1)[-1]
            part = re.sub(r"\s*\(.*?\)\s*", " ", part).strip()
            gid = SLUG_REMAP.get(norm(part), norm(part))
        if gid in scores and scores[gid][0] >= score:
            continue
        scores[gid] = (score, label)
    return scores, unmatched


def fetch_aa_index(go_ids):
    """Scrape AA Intelligence Index per model page: {go_id: (score, label)}.

    No bulk endpoint exists (only 24 chart-selected models inline on
    /models), so fetch each mapped model page and read intelligenceIndex.
    Unmapped Go ids (free/experimental models with no AA page) are skipped
    and reported. Fails loudly on shape changes or mass misses.
    """
    import time
    scores, missing = {}, []
    for gid in sorted(go_ids):
        slug = AA_SLUGS.get(gid, [gid])[0].replace(".", "-")
        html = None
        try:
            html = get(f"https://artificialanalysis.ai/models/{slug}")
        except Exception as e:  # noqa: BLE001 - reported, not hidden
            missing.append({"label": gid, "score": None, "error": str(e)})
        if html is None:
            continue
        m = re.search(r'intelligenceIndex\\?":([0-9.]+|null)', html)
        me = re.search(r'intelligenceIndexIsEstimated\\?":(true|false)', html)
        if not m or m.group(1) == "null":
            missing.append({"label": gid, "score": None, "error": "no index"})
            time.sleep(1)
            continue
        scores[gid] = (round(float(m.group(1)), 1),
                       f"{gid} (AA index"
                       f"{', estimated' if me and me.group(1) == 'true' else ''})")
        time.sleep(1)
    return scores, missing


def match_scores(scores_list, go_ids):
    """Split parsed score dicts into matched {gid: ...} and unmatched lists.

    Exact normalized match first; fallback to a UNIQUE prefix match in either
    direction ("musespark13" <-> "musespark13contributor"). Ambiguous or
    missing matches are reported, never guessed.
    """
    by_id = {norm(g): g for g in go_ids}
    matched, unmatched = {}, {}
    for key, scores in scores_list:
        m, u = {}, []
        for gid, (score, label) in scores.items():
            gid = SLUG_REMAP.get(gid, gid)
            target = by_id.get(norm(gid))
            if target is None:
                cands = [g for n, g in by_id.items()
                         if n.startswith(norm(gid)) or norm(gid).startswith(n)]
                target = cands[0] if len(cands) == 1 else None
            if target is None:
                u.append({"label": label, "score": score})
            else:
                prev = m.get(target)
                if prev is None or score > prev[0]:
                    m[target] = (score, label)
        matched[key], unmatched[key] = m, u
    return matched, unmatched


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

    # BenchLM-mirror score sources
    raw = []
    for key, src in SOURCES.items():
        if key == "aa_index":
            continue
        raw.append((key, parse_leaderboard(get(src["url"]), key)[0]))
    go_ids_pre = []
    for key in sorted(go_idx):
        priced = pick_row(go_idx[key])
        name = re.sub(r"\s*\(.*", "", priced[0]).strip()
        _, gid = endpoints.get(key, (name, None))
        go_ids_pre.append(gid or norm(name).replace(" ", "-"))
    matched, unmatched = match_scores(raw, go_ids_pre)
    # AA Intelligence Index: per-model pages (no bulk endpoint)
    aa_scores, aa_missing = fetch_aa_index(go_ids_pre)
    matched["aa_index"], unmatched["aa_index"] = aa_scores, aa_missing
    for key, src in SOURCES.items():
        if not matched[key]:
            sys.exit(f"{key}: zero scores matched to Go models")

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
        scores = {}
        for skey in SOURCES:
            sc = matched[skey].get(gid)
            scores[skey] = {"score": sc[0], "label": sc[1]} if sc else None
        aa = scores["aa"]
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
            "aa_score": aa["score"] if aa else None,  # compat; prefer scores.*
            "aa_label": aa["label"] if aa else None,
            "scores": scores,
        })
    if missing_mix:
        sys.exit(f"no token mix for priced models: {missing_mix}")
    if len(models) < 20:
        sys.exit(f"too few Go models parsed: {len(models)}")

    data = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "go_docs": GO_DOCS_URL,
            "sources": {k: v for k, v in SOURCES.items()},
            "method": ("cost_per_request_usd = input/1e6*input_per_1m + "
                       "cached/1e6*cached_per_1m + output/1e6*output_per_1m; "
                       "peak pricing for DeepSeek, base tier for tiered models"),
            "unmatched": unmatched,
        },
        "models": models,
    }
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    cov = {k: sum(1 for m in models if m["scores"][k]) for k in SOURCES}
    print(f"wrote {out_path}: {len(models)} models, coverage {cov}")


if __name__ == "__main__":
    main(*sys.argv[1:])
