---
name: exa-research
description: "Search and research the web using Exa's neural search API. Triggers on: search, find, look up, research, latest news on, recent papers about, companies that, articles on, lead generation, prospect list, ICP, what is the current state of, find me information about. Calls Exa's REST API directly from Python via stdlib — no pip install, no MCP, works on any engine."
allowed-tools: "Bash, Read, Write"
---

# Web research via Exa REST API

When the user asks for anything that needs **current information from the web** — recent news, finding companies / papers / articles, lead generation, "what is the latest", "find me X" — use Exa search via this skill.

The skill calls Exa's REST API directly from Python with `urllib.request` (stdlib). No `pip install`, no MCP server, no SDK. Same code runs unchanged on `gitagent`, `claude-agent-sdk`, and `deepagents`.

## Prerequisites

`EXA_API_KEY` must be in the environment. Check first:

```bash
echo "${EXA_API_KEY:+set}${EXA_API_KEY:-MISSING}"
```

If `MISSING`, tell the user "I need an EXA_API_KEY in my environment to do web research" and stop — don't try to substitute or invent one.

## Choosing the search type

| Use case | `type` | `category` |
|---|---|---|
| General "what's the latest on X" | `"neural"` | none |
| Find companies matching an ICP | `"neural"` | `"company"` |
| Recent news | `"neural"` | `"news"` |
| Academic papers | `"neural"` | `"research paper"` |
| Tweets | `"neural"` | `"tweet"` |
| Specific phrase / exact match | `"keyword"` | none |
| Let Exa decide | `"auto"` | none |

For most ad-hoc research, `type="neural"` + `useAutoprompt=true` gives the best results.

## Quickstart — single query

Write `exa_quick.py` to the workdir and run it:

```python
"""Single Exa search — workdir/exa_quick.py"""
import json, os, sys, urllib.request

API_KEY = os.environ.get("EXA_API_KEY")
if not API_KEY:
    print("ERROR: EXA_API_KEY not set", file=sys.stderr); sys.exit(1)

QUERY = "REPLACE_ME — what to search for"
NUM = 10

req = urllib.request.Request(
    "https://api.exa.ai/search",
    method="POST",
    headers={"x-api-key": API_KEY, "content-type": "application/json"},
    data=json.dumps({
        "query": QUERY,
        "type": "neural",
        "numResults": NUM,
        "useAutoprompt": True,
        "contents": {
            "text": {"maxCharacters": 2000},
            "highlights": {"numSentences": 3},
        },
    }).encode("utf-8"),
)
with urllib.request.urlopen(req, timeout=60) as r:
    data = json.loads(r.read().decode("utf-8"))

with open("exa_results.json", "w") as f:
    json.dump(data, f, indent=2)
print(f"wrote exa_results.json with {len(data.get('results', []))} results")
```

Then `python3 exa_quick.py`, read `exa_results.json`, summarize back to the user.

## Workflow — lead generation / prospect list

When the user asks for a lead list, prospect list, ICP-matched companies, or any "find me companies that…" task:

### 1. Confirm the ICP in one sentence

> "ICP: Series A–C SaaS, 50–500 employees, US, using LangChain. Target: VP Engineering. Need: 15 leads."

If they already gave a clean one-liner, skip the confirmation and just go.

### 2. Generate micro-verticals (no API call yet)

Decide how many search queries to fire:

- ≤20 leads → 2 micro-verticals
- 20–100 leads → `ceil(count / 25)` micro-verticals
- 100+ leads → `ceil(count / 35)` micro-verticals (overshoot for dedup)

Example for "B2B SaaS using LangChain":
- "Series A B2B SaaS startups using LangChain for AI agents in production"
- "Series B/C SaaS companies with autonomous agent platforms built on LangChain"
- "B2B SaaS US-based companies hiring AI engineers who mention LangChain"

State the micro-verticals out loud (1–2 sentences) before launching.

### 3. Write `exa_search.py` to the workdir

```python
"""Multi-query Exa search — workdir/exa_search.py"""
import json, os, sys, urllib.request
from datetime import datetime, timezone

API_KEY = os.environ.get("EXA_API_KEY")
if not API_KEY:
    print("ERROR: EXA_API_KEY not set", file=sys.stderr); sys.exit(1)

QUERIES = [
    # REPLACE with the actual micro-verticals
    "Series A B2B SaaS startups using LangChain for AI agents in production",
    "Series B SaaS companies with autonomous agent platforms on LangChain",
]
NUM_RESULTS_PER_QUERY = 10
OUTPUT_FILE = "exa_results.json"

def search(query: str, n: int) -> dict:
    req = urllib.request.Request(
        "https://api.exa.ai/search",
        method="POST",
        headers={"x-api-key": API_KEY, "content-type": "application/json"},
        data=json.dumps({
            "query": query,
            "type": "neural",
            "category": "company",
            "numResults": n,
            "useAutoprompt": True,
            "contents": {
                "text": {"maxCharacters": 1500},
                "highlights": {"numSentences": 3},
            },
        }).encode("utf-8"),
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))

all_results = []
for q in QUERIES:
    print(f"  query: {q[:70]}…")
    data = search(q, NUM_RESULTS_PER_QUERY)
    for hit in data.get("results", []):
        all_results.append({
            "query": q,
            "title": hit.get("title", ""),
            "url": hit.get("url", ""),
            "published_date": hit.get("publishedDate", ""),
            "author": hit.get("author", ""),
            "text": (hit.get("text") or "")[:1500],
            "highlights": hit.get("highlights", []),
        })
    print(f"    → {len(data.get('results', []))} results")

with open(OUTPUT_FILE, "w") as f:
    json.dump({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queries": QUERIES,
        "total_results": len(all_results),
        "results": all_results,
    }, f, indent=2)
print(f"\nwrote {OUTPUT_FILE} with {len(all_results)} results")
```

### 4. Compile leads into CSV

```python
"""Compile leads CSV — workdir/compile_leads.py"""
import csv, json
from urllib.parse import urlparse

with open("exa_results.json") as f:
    data = json.load(f)

# Dedupe by domain — most reliable identity for companies.
by_domain = {}
for r in data["results"]:
    try:
        host = urlparse(r["url"]).netloc.lower().lstrip("www.")
    except Exception:
        continue
    if not host: continue
    existing = by_domain.get(host)
    if existing is None or len(r.get("text", "")) > len(existing.get("text", "")):
        by_domain[host] = r

# REPLACE with the ICP keywords for the current run.
ICP_KEYWORDS = ["langchain", "ai agent", "series a", "series b", "saas"]

def score(text: str) -> int:
    t = (text or "").lower()
    return sum(1 for kw in ICP_KEYWORDS if kw.lower() in t)

leads = []
for host, r in by_domain.items():
    leads.append({
        "company": host.split(".")[0].title(),
        "url": r.get("url", ""),
        "domain": host,
        "title_snippet": (r.get("title", "") or "")[:120],
        "icp_fit_score": score(r.get("text", "")),
        "reasoning": (r.get("text", "") or "")[:300].replace("\n", " "),
        "published_date": r.get("published_date", ""),
        "query": r.get("query", ""),
    })

leads.sort(key=lambda x: x["icp_fit_score"], reverse=True)

with open("leads.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(leads[0].keys()))
    w.writeheader()
    for row in leads:
        w.writerow(row)

print(f"wrote leads.csv: {len(leads)} unique companies")
for L in leads[:5]:
    print(f"  {L['icp_fit_score']:>2} | {L['company']:<25} | {L['url']}")
```

### 5. Send the CSV back to Slack

Use the file-attachment marker in your final reply:

```
Generated leads.csv — 23 unique companies (Top finding: Foo Corp, score 4).

[[ATTACH:leads.csv]]
```

## Workflow — single-query general research

For "what is the latest on X" / "find me articles about Y" / "summarize current state of Z":

1. Write a small Python script (or just inline `python3 -c '…'` with the urllib call)
2. Hit `/search` with the user's query — let `useAutoprompt: true` rewrite it
3. Read the top 5–10 hits, synthesize a short summary back to the user
4. Cite each fact with the source URL

Do **not** dump the raw JSON at the user. Read it, distill it, cite it.

## Extracting full page content

The `/search` response already includes a snippet via `contents.text`. For deeper extraction (full article body, structured data), follow up with Exa's `/contents` endpoint:

```python
req = urllib.request.Request(
    "https://api.exa.ai/contents",
    method="POST",
    headers={"x-api-key": API_KEY, "content-type": "application/json"},
    data=json.dumps({
        "ids": [url_or_id, ...],   # IDs returned by /search, OR raw URLs
        "text": {"maxCharacters": 8000},
    }).encode("utf-8"),
)
```

## Common pitfalls

- **`HTTPError: 401`** — `EXA_API_KEY` missing or invalid. Check `echo $EXA_API_KEY | head -c 8`. Don't print the rest.
- **`HTTPError: 429`** — rate-limited. Sleep 30s and retry. Reduce `numResults`.
- **Empty `results` array** — query too narrow. Re-run with `useAutoprompt: true` (the templates already do this). If still empty, broaden the query.
- **`urlopen` timeout** — Exa neural search can take 5–30s per query. Use `timeout=60`.
- **Trash company names** in lead lists — `host.split(".")[0]` works for most domains but fails on `s3-bucket.amazonaws.com` style. For high-quality lists, do a second pass with an LLM to clean names.

## API reference (quick)

- Docs: https://docs.exa.ai/reference/search
- Endpoints: `POST /search`, `POST /contents`
- Auth: `x-api-key: <key>` header
- Key `/search` body fields:
  - `query` (string, required)
  - `type`: `"neural"` (semantic — default) | `"keyword"` (full-text) | `"auto"`
  - `numResults` (1–25)
  - `useAutoprompt` (bool — Exa rewrites the query for relevance)
  - `category`: `"company" | "research paper" | "news" | "tweet" | "github"`
  - `startPublishedDate` / `endPublishedDate` (ISO date — recency filters)
  - `includeDomains` / `excludeDomains` (arrays)
  - `contents`: `{ text: { maxCharacters }, highlights: { numSentences } }`

## Rules

- Always read `$EXA_API_KEY` from env. Never hardcode an API key.
- Never `pip install` anything — `urllib.request` is the universal vehicle.
- Write scripts to the workdir (not `/tmp` outside the workdir) so the harness can fetch outputs.
- Verify the script ran (`/bin/ls -lh <file>`) before reporting completion.
- For lead lists: dedupe by hostname, sort by ICP score descending, use proper CSV quoting via `csv.DictWriter`.
- For general research: summarize and cite — don't dump JSON at the user.
- Don't fabricate results. If Exa returns nothing, say so and propose a broader query.
