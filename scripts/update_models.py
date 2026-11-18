#!/usr/bin/env python3
"""Refresh data/models.json from opencode Go model list + coding-benchmark scores.

Sources:
  - Model set, token prices, context limits, monthly allowance per plan:
    https://opencode.ai/inference/go/v1/models  (OpenAI list shape, JSON)
  - Est. requests / 5 hr and monthly limits per plan (what the Go console
    shows): https://opencode.ai/console/go  ("Included models" table)
  - Score sources (machine-readable mirrors; canonical pages in SOURCES):
    - AA Coding Agent Index: https://benchlm.ai/md/benchmarks/aacodingagents.md
    - FrontierCode 1.1 Main: https://benchlm.ai/md/benchmarks/frontiercode.md
    - BenchLM Coding board:  https://benchlm.ai/md/coding.md
    - AA Intelligence Index: per-model pages on artificialanalysis.ai

Cost metric (x-axis): est. requests per 5 hours on the Go plan, straight from
the console. Implied cost per request = 20% of the monthly Go allowance (the
5-hour window) divided by those requests.

Score matching is exact-only: normalized Go id <-> normalized leaderboard slug
(dashes/dots stripped). Known renames live in SLUG_REMAP (BenchLM) and
AA_SLUGS (AA pages); anything else that does not match exactly is reported in
meta.unmatched, never guessed.

Stdlib only. Fails loudly on unexpected page shapes (the Action surfaces it).
"""
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

GO_DOCS_URL = "https://opencode.ai/docs/go/"
GO_MODELS_URL = "https://opencode.ai/inference/go/v1/models"
GO_CONSOLE_URL = "https://opencode.ai/console/go"
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

# Go model id -> AA model-page slug, for pages the id-derivative slug misses.
# Default derivation is the id with dots as dashes ("qwen3.8-max" ->
# "qwen3-8-max"). AA deprecates old slugs; a page whose record points at its
# own dated successor ("deepseek-v4-1-flash" -> "-1017") is followed once.
# Renames to a different version/family are listed here explicitly, never
# followed automatically.
AA_SLUGS = {
    "hy4": "tencent-hy4",
    "muse-spark-1.2-contributor": "muse-spark-1-2",
    "muse-spark-1.3-contributor": "muse-spark-1-3",
    "qwen3.8-flash": "qwen3-8-flash-next",  # closest published sibling
}

UA = {"User-Agent": "opencode-go-pareto-updater/1.0 (+github pages demo)"}

# BenchLM slug -> Go model id for rows that are the same model under another
# name. Exact matches need no entry. Keep this minimal and explicit.
SLUG_REMAP = {
    "deepseek-v4-1-flash": "deepseek-v4.1-flash",
    "kimi-2-6": "kimi-k2.6",
    "muse-spark-1-2": "muse-spark-1.2-contributor",
    "hy3-preview": "hy3",
    "deepseek-v4-pro-0813": "deepseek-v4-pro",
    "deepseek-v4-flash-0731": "deepseek-v4-flash",
}


def get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def get_json(url):
    return json.loads(get(url))


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def parse_leaderboard(md, key):
    """Parse one benchlm mirror into {go_id: (score, label)}.

    AA rows link every row to the same canonical page (agent config in the
    link text, e.g. "Codex - GPT-6 Luna (Max)" or "Opencode - GLM-5.3"), so
    match on the model part of the text. FrontierCode/Coding rows link
    per-model (/models/<slug>), so match on the exact slug. Both exact-only
    after normalization.
    """
    scores = {}
    rows = re.findall(
        r"\|\s*\d+\s*\|\s*\[(.+?)\]\((.+?)\)\s*\|\s*(.+?)\s*\|\s*([\d.]+)%?\s*\|", md)
    if not rows:
        sys.exit(f"{key}: parsed zero leaderboard rows")
    for label, link, _rest, score in rows:
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
    return scores


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


def aa_record(html, slug):
    """(intelligenceIndex, deprecatedTo) for one model record on an AA page."""
    i = html.find(f'"slug":"{slug}"')
    if i < 0:
        return None, None
    rec = html[i:i + 8000]
    m = re.search(r'"intelligenceIndex":([0-9.]+|null)', rec)
    d = re.search(r'"deprecatedTo":"([^"]+)"', rec)
    return (float(m.group(1)) if m and m.group(1) != "null" else None,
            d.group(1) if d else None)


def fetch_aa_index(go_ids):
    """Scrape AA Intelligence Index per model page: {go_id: (score, label)}.

    No bulk endpoint exists (only 24 chart-selected models inline on
    /models), so fetch each mapped model page and read its own record's
    intelligenceIndex. AA serves escaped JSON; unescape before matching.
    Unmapped or index-less models are reported, never guessed.
    """
    scores, missing = {}, []
    for gid in sorted(go_ids):
        slug = AA_SLUGS.get(gid, gid.replace(".", "-"))
        score = None
        try:
            html = get(f"https://artificialanalysis.ai/models/{slug}").replace("\\", "")
            score, dep = aa_record(html, slug)
            # Same-model dated snapshot only: "x" -> "x-1017". A successor
            # version ("kimi-k3" -> "kimi-k3-1-pro") is NOT the same model.
            if score is None and dep and re.fullmatch(rf"{re.escape(slug)}-\d+", dep):
                slug = dep
                html = get(f"https://artificialanalysis.ai/models/{slug}").replace("\\", "")
                score, _ = aa_record(html, slug)
        except Exception as e:  # noqa: BLE001 - reported, not hidden
            missing.append({"label": gid, "score": None, "error": str(e)})
            time.sleep(1)
            continue
        if score is None:
            missing.append({"label": gid, "score": None,
                            "error": f"no index (aa {slug})"})
        else:
            scores[gid] = (round(score, 1), f"{gid} (AA index, aa {slug})")
        time.sleep(1)
    return scores, missing


def parse_tables(html):
    return re.findall(r"<table.*?>(.*?)</table>", html, re.S)


def cells(row_html):
    return [re.sub(r"<[^>]+>", "", c).strip()
            for c in re.findall(r"<t[hd].*?>(.*?)</t[hd]>", row_html, re.S)]


def money(s):
    s = s.strip().replace(",", "")
    if s.startswith("∞"):
        return None
    m = re.match(r"\$?([\d.]+)", s)
    if not m:
        raise ValueError(f"unparseable money: {s!r}")
    return float(m.group(1))


def count(s):
    s = s.strip().replace(",", "")
    if s.startswith("∞"):
        return None
    m = re.match(r"(\d+)", s)
    if not m:
        raise ValueError(f"unparseable count: {s!r}")
    return int(m.group(1))


def parse_console(html):
    """Console Go page "Included models" table -> {norm(name): row}.

    Each row carries screen-reader copies of its cells, e.g.
    "Go: 43,300; Go Plus: 86,700" and "Go: $100; Go Plus: $200"; read those.
    """
    tables = [t for t in parse_tables(html)
              if "est. requests" in "|".join(cells(re.findall(
                  r"<tr.*?>(.*?)</tr>", t, re.S)[0])).lower()]
    if len(tables) != 1:
        sys.exit(f"expected 1 console limits table, found {len(tables)}")
    rows = [cells(r) for r in re.findall(r"<tr.*?>(.*?)</tr>", tables[0], re.S)][1:]
    out = {}
    for r in rows:
        if len(r) < 4 or not r[2]:
            continue
        req = re.search(r"Go: ([^;]+); Go Plus: ([^;]+)", r[2])
        mon = re.search(r"Go: ([^;]+); Go Plus: ([^;]+)", r[3])
        if not req or not mon:
            sys.exit(f"console row shape changed: {r}")
        out[norm(r[0])] = {
            "requests_5h": count(req.group(1)),
            "monthly_go": money(mon.group(1)),
            "monthly_plus": money(mon.group(2)),
        }
    if len(out) < 20:
        sys.exit(f"too few console model rows: {len(out)}")
    return out


def main(out_path="data/models.json"):
    api = get_json(GO_MODELS_URL)["data"]
    console = parse_console(get(GO_CONSOLE_URL))

    # Map console rows (display names + badges) onto API ids: longest
    # normalized API name that prefixes the normalized row text.
    by_name = sorted(((norm(m["name"]), m["id"]) for m in api),
                     key=lambda p: len(p[0]), reverse=True)
    rows = {}
    for key, row in console.items():
        for n, gid in by_name:
            if key.startswith(n):
                rows[gid] = row
                break
    if len(rows) != len(api):
        missing = sorted(m["id"] for m in api if m["id"] not in rows)
        sys.exit(f"console rows unmatched for models: {missing}")

    go_ids = [m["id"] for m in api]
    raw = [(key, parse_leaderboard(get(src["url"]), key))
           for key, src in SOURCES.items() if key != "aa_index"]
    matched, unmatched = match_scores(raw, go_ids)
    aa_scores, aa_missing = fetch_aa_index(go_ids)
    matched["aa_index"], unmatched["aa_index"] = aa_scores, aa_missing
    for key in SOURCES:
        if not matched[key]:
            sys.exit(f"{key}: zero scores matched to Go models")

    models = []
    for m in api:
        gid = m["id"]
        row = rows[gid]
        usage = m.get("go", {}).get("monthly_usage") or {}
        monthly_go = usage.get("go")
        monthly_plus = usage.get("go-plus")
        # The console table is the published view; a drift means one of the
        # two sources changed shape.
        if monthly_go != row["monthly_go"] or monthly_plus != row["monthly_plus"]:
            sys.exit(f"monthly limit mismatch for {gid}: api {monthly_go}/"
                     f"{monthly_plus} vs console {row['monthly_go']}/"
                     f"{row['monthly_plus']}")
        text_cost = (m.get("cost") or {}).get("text") or {}
        inp = (text_cost.get("input") or {}).get("price")
        outp = (text_cost.get("output") or {}).get("price")
        cached = ((text_cost.get("input") or {}).get("cache") or {}).get("read")
        req5h = row["requests_5h"]
        if monthly_go is None:
            cost = 0.0 if inp == 0 and outp == 0 else None
        elif req5h:
            cost = round(0.2 * monthly_go / req5h, 6)
        else:
            cost = None
        scores = {}
        for skey in SOURCES:
            sc = matched[skey].get(gid)
            scores[skey] = {"score": sc[0], "label": sc[1]} if sc else None
        aa = scores["aa"]
        models.append({
            "id": gid,
            "name": m["name"],
            "input_per_1m": inp,
            "output_per_1m": outp,
            "cached_per_1m": cached or 0.0,
            "monthly_limit_go": monthly_go,
            "monthly_limit_go_plus": monthly_plus,
            "requests_per_5h": req5h,
            "cost_per_request_usd": cost,
            "aa_score": aa["score"] if aa else None,  # compat; prefer scores.*
            "aa_label": aa["label"] if aa else None,
            "scores": scores,
        })
    if len(models) < 20:
        sys.exit(f"too few Go models parsed: {len(models)}")

    data = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "go_docs": GO_DOCS_URL,
            "sources": {k: v for k, v in SOURCES.items()},
            "method": ("requests_per_5h from the Go console limits table; "
                       "cost_per_request_usd = 0.2 * monthly_limit_go / "
                       "requests_per_5h; token prices are base Go prices "
                       "(cost multipliers not applied)"),
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
