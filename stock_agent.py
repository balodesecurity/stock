#!/usr/bin/env python3
"""
Stock Analysis Agent — AI-powered analysis of Growth & Quality companies.

Uses Claude tool use to autonomously research each company (financials, quarterly
trends, peer comparison, recent news) and produce structured investment analysis.

Usage:
    python stock_agent.py                      # Analyse all Growth & Quality companies
    python stock_agent.py --company ACE        # Analyse a single company by code
    python stock_agent.py --top 20             # Top N companies by green score
    python stock_agent.py --force              # Re-analyse even if recently cached
"""

import json
import os
import sys
import time
import sqlite3
import argparse
import urllib.parse
import feedparser
from datetime import datetime, timedelta
from pathlib import Path

import anthropic

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from constants import DATABASE_PATH, QUARTER_ORDER_DESC

# ── Config ────────────────────────────────────────────────────────────────────

MODEL        = "claude-sonnet-4-6"
MAX_TOKENS   = 4096
CACHE_DAYS   = 3          # Skip re-analysis if result is fresher than this
NEWS_LIMIT   = 6          # Articles per search_news call
COMPANY_GAP  = 3          # Seconds between companies (rate limiting)

RESULTS_DIR  = Path(__file__).parent / "agent_results"
RESULTS_DIR.mkdir(exist_ok=True)

# Matches the portal's "Filter for Growth & Quality" checkbox
FILTER = {
    "max_pe":            105,
    "max_debt":          1.0,
    "min_fcf_cfo":       10,
    "min_promoter":      40,
    "min_sales_growth_5y": 20,
}

# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Indian stock market analyst specialising in fundamental analysis
using Dr. Vijay Malik's framework (SSGR, FCF/CFO, ROCE).

For each company you are asked to analyse:
1. Call get_company_financials first — understand the key numbers.
2. Call get_quarterly_trend — look for acceleration or deceleration in sales/profit.
3. Call get_annual_financials — check multi-year trajectory.
4. Search news at least twice: once for recent results/business updates, once for
   sector tailwinds/headwinds or competitive landscape.
5. Call get_peer_comparison to contextualise valuation and quality.
6. Once you have enough information, call submit_analysis.

Key framework:
- SSGR >40%: exceptional. 20-40%: excellent. <0%: needs external capital.
- FCF/CFO >25%: low capex intensity (green). <0%: cash being consumed.
- ROCE >20%: strong moat. Compare current vs peers.
- Promoter holding trend: sustained selling is a warning sign.
- PEG ratio: <1 is cheap, >3 is expensive relative to growth.

Be specific — cite actual numbers. Consider Indian context: govt policy, import
competition, rural demand, infrastructure spend, export opportunities."""

# ── Tool Definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_company_financials",
        "description": (
            "Fetch comprehensive financial metrics for a company: valuation (P/E, PEG, "
            "Market Cap), quality (ROCE, SSGR current+prev, NPM), FCF metrics, balance "
            "sheet (D/E), promoter holding trend, sentiment, and current price vs 52W range."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_code": {"type": "string", "description": "NSE/BSE ticker code"}
            },
            "required": ["company_code"]
        }
    },
    {
        "name": "get_quarterly_trend",
        "description": (
            "Get the last 8 quarters of Sales and Net Profit (₹ Cr) to spot growth "
            "momentum, deceleration, or seasonal patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_code": {"type": "string"}
            },
            "required": ["company_code"]
        }
    },
    {
        "name": "get_annual_financials",
        "description": (
            "Get 5 years of annual Sales, Net Profit, EPS, and Borrowings to assess "
            "long-term growth trajectory and debt trend."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_code": {"type": "string"}
            },
            "required": ["company_code"]
        }
    },
    {
        "name": "get_peer_comparison",
        "description": (
            "Compare this company against its industry peers on P/E, ROCE, SSGR, D/E, "
            "FCF/CFO ratio, and Market Cap to contextualise valuation and quality."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_code": {"type": "string"}
            },
            "required": ["company_code"]
        }
    },
    {
        "name": "search_news",
        "description": (
            "Search Google News for recent articles. Use targeted queries e.g. "
            "'Tata Motors EV sales Q3 2025', 'FMCG rural demand India 2025', "
            "'ACE cranes order book'. Returns up to 6 recent articles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Google News search query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "submit_analysis",
        "description": (
            "Submit the final structured analysis. Call this when you have gathered "
            "sufficient information from the other tools."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pros": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-5 key strengths with specific numbers"
                },
                "cons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-4 weaknesses or concerns with specific numbers"
                },
                "growth_path": {
                    "type": "string",
                    "description": "2-3 paragraph narrative on growth trajectory and future outlook"
                },
                "risk_factors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-3 specific risks to monitor"
                },
                "verdict": {
                    "type": "string",
                    "enum": ["Strong Buy", "Buy", "Watch", "Avoid"],
                    "description": "Overall investment verdict"
                },
                "verdict_reason": {
                    "type": "string",
                    "description": "One sentence explaining the verdict"
                }
            },
            "required": ["pros", "cons", "growth_path", "risk_factors", "verdict", "verdict_reason"]
        }
    }
]

# ── Tool Implementations ──────────────────────────────────────────────────────

def get_company_financials(company_code: str) -> dict:
    conn = sqlite3.connect(str(DATABASE_PATH))
    cur = conn.cursor()
    cur.execute("""
        SELECT d.company_name, d.sector, d.industry,
               d.pe_ratio, d.peg_ratio, d.market_cap, d.book_value,
               d.roce, d.ssgr, d.ssgr_prev, d.npm,
               d.total_fcf, d.fcf_cfo_ratio, d.fcf_category,
               d.debt_to_equity, d.promoter_holding, d.promoter_trend_display,
               d.sentiment_rating,
               d.qoq_profit_growth, d.yoy_profit_growth, d.yoy_sales_growth,
               d.year1_sales_growth, d.year2_sales_growth, d.year3_sales_growth,
               p.current_price, p.week_52_high, p.week_52_low
        FROM derived_metrics_analysis d
        LEFT JOIN (
            SELECT company_code, current_price, week_52_high, week_52_low
            FROM screener_daily_prices
            WHERE (company_code, date) IN (
                SELECT company_code, MAX(date) FROM screener_daily_prices GROUP BY company_code
            )
        ) p ON d.company_code = p.company_code
        WHERE d.company_code = ?
    """, (company_code,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"error": f"Company {company_code} not found"}
    keys = [
        "company_name", "sector", "industry",
        "pe_ratio", "peg_ratio", "market_cap_cr", "book_value",
        "roce_pct", "ssgr_pct", "ssgr_prev_pct", "npm_pct",
        "total_fcf_cr", "fcf_cfo_ratio_pct", "fcf_category",
        "debt_to_equity", "promoter_holding_pct", "promoter_trend",
        "sentiment_1to5",
        "qoq_profit_growth_pct", "yoy_profit_growth_pct", "yoy_sales_growth_pct",
        "year1_sales_growth_pct", "year2_sales_growth_pct", "year3_sales_growth_pct",
        "current_price_inr", "week_52_high_inr", "week_52_low_inr"
    ]
    return dict(zip(keys, row))


def get_quarterly_trend(company_code: str) -> dict:
    conn = sqlite3.connect(str(DATABASE_PATH))
    cur = conn.cursor()
    result = {}
    for metric, label in [("Sales+", "sales_cr"), ("Net Profit+", "net_profit_cr")]:
        cur.execute(f"""
            SELECT quarter, CAST(REPLACE(value, ',', '') AS REAL)
            FROM screener_quarterly
            WHERE company_code = ? AND metric = ?
            ORDER BY {QUARTER_ORDER_DESC} LIMIT 8
        """, (company_code, metric))
        result[label] = [{"quarter": r[0], "value": r[1]} for r in cur.fetchall()]
    conn.close()
    return result


def get_annual_financials(company_code: str) -> dict:
    conn = sqlite3.connect(str(DATABASE_PATH))
    cur = conn.cursor()
    result = {}
    for table, metric, label in [
        ("screener_annual_pl",    "Sales+",      "sales_cr"),
        ("screener_annual_pl",    "Net Profit+", "net_profit_cr"),
        ("screener_annual_pl",    "EPS in Rs+",  "eps"),
        ("screener_balance_sheet","Borrowings+", "borrowings_cr"),
    ]:
        cur.execute(f"""
            SELECT year, CAST(REPLACE(value, ',', '') AS REAL)
            FROM {table}
            WHERE company_code = ? AND metric = ? AND year != 'TTM'
              AND value IS NOT NULL AND value != ''
            ORDER BY CAST(SUBSTR(year, -4) AS INTEGER) DESC LIMIT 5
        """, (company_code, metric))
        result[label] = [{"year": r[0], "value": r[1]} for r in cur.fetchall()]
    conn.close()
    return result


def get_peer_comparison(company_code: str) -> dict:
    conn = sqlite3.connect(str(DATABASE_PATH))
    cur = conn.cursor()
    cur.execute(
        "SELECT industry FROM derived_metrics_analysis WHERE company_code = ?",
        (company_code,)
    )
    row = cur.fetchone()
    if not row or not row[0]:
        conn.close()
        return {"error": "Industry not found for this company"}
    industry = row[0]
    cur.execute("""
        SELECT d.company_code, d.company_name,
               d.pe_ratio, d.roce, d.ssgr, d.debt_to_equity, d.fcf_cfo_ratio, d.market_cap
        FROM derived_metrics_analysis d
        JOIN screener_companies c ON d.company_code = c.company_code
        WHERE d.industry = ? AND c.enabled = 1 AND d.company_name IS NOT NULL
        ORDER BY d.market_cap DESC
        LIMIT 6
    """, (industry,))
    peers = cur.fetchall()
    conn.close()
    keys = ["company_code", "company_name", "pe_ratio", "roce_pct",
            "ssgr_pct", "debt_to_equity", "fcf_cfo_ratio_pct", "market_cap_cr"]
    return {
        "industry": industry,
        "peers": [dict(zip(keys, p)) for p in peers]
    }


def search_news(query: str) -> dict:
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
        feed = feedparser.parse(url)
        results = []
        for entry in feed.entries[:NEWS_LIMIT]:
            results.append({
                "title":     entry.get("title", ""),
                "published": entry.get("published", ""),
                "source":    entry.get("source", {}).get("title", ""),
                "summary":   entry.get("summary", "")[:500]
            })
        return {"query": query, "articles": results, "count": len(results)}
    except Exception as e:
        return {"error": str(e), "query": query, "articles": []}


def execute_tool(name: str, inputs: dict):
    if name == "get_company_financials":
        return get_company_financials(inputs["company_code"])
    elif name == "get_quarterly_trend":
        return get_quarterly_trend(inputs["company_code"])
    elif name == "get_annual_financials":
        return get_annual_financials(inputs["company_code"])
    elif name == "get_peer_comparison":
        return get_peer_comparison(inputs["company_code"])
    elif name == "search_news":
        return search_news(inputs["query"])
    elif name == "submit_analysis":
        return inputs  # Pass through — signals end of loop
    else:
        return {"error": f"Unknown tool: {name}"}

# ── Agent Loop ────────────────────────────────────────────────────────────────

def analyse_company(client: anthropic.Anthropic, company_code: str, company_name: str) -> dict:
    """Run the agentic loop for a single company. Returns structured analysis dict."""
    print(f"  Analysing {company_name} ({company_code})...")

    messages = [{
        "role": "user",
        "content": (
            f"Analyse {company_name} (ticker: {company_code}) as a potential investment. "
            f"Research thoroughly using the available tools, then call submit_analysis."
        )
    }]

    tool_call_count = 0

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )

        # Collect text output for logging
        for block in response.content:
            if hasattr(block, "text") and block.text:
                print(f"    Agent: {block.text[:120]}{'...' if len(block.text) > 120 else ''}")

        if response.stop_reason == "end_turn":
            print(f"    ⚠ Agent finished without calling submit_analysis")
            return {"error": "Agent did not call submit_analysis", "company_code": company_code}

        if response.stop_reason == "tool_use":
            tool_results = []
            final_analysis = None

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_call_count += 1
                print(f"    → {block.name}({json.dumps(block.input)[:80]})")

                result = execute_tool(block.name, block.input)

                if block.name == "submit_analysis":
                    final_analysis = block.input
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Analysis submitted successfully."
                    })
                else:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str)
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user",       "content": tool_results})

            if final_analysis:
                final_analysis["company_code"]  = company_code
                final_analysis["company_name"]  = company_name
                final_analysis["analysed_at"]   = datetime.now().isoformat()
                final_analysis["tool_calls"]    = tool_call_count
                print(f"    ✓ Done ({tool_call_count} tool calls) — Verdict: {final_analysis.get('verdict')}")
                return final_analysis

# ── Data Fetching ─────────────────────────────────────────────────────────────

def get_growth_quality_companies(top_n: int = None) -> list[dict]:
    """Return companies passing the Growth & Quality filter, ranked by green score."""
    conn = sqlite3.connect(str(DATABASE_PATH))
    cur = conn.cursor()
    cur.execute("""
        SELECT d.company_code, d.company_name, d.sector, d.industry,
               d.pe_ratio, d.ssgr, d.roce, d.fcf_cfo_ratio,
               -- green score
               (CASE WHEN d.fcf_cfo_ratio >= 25        THEN 1 ELSE 0 END +
                CASE WHEN d.ssgr > 0                   THEN 1 ELSE 0 END +
                CASE WHEN d.qoq_profit_growth > 0      THEN 1 ELSE 0 END +
                CASE WHEN d.yoy_profit_growth > 0      THEN 1 ELSE 0 END +
                CASE WHEN d.yoy_sales_growth > 0       THEN 1 ELSE 0 END) AS green_score
        FROM derived_metrics_analysis d
        JOIN screener_companies c ON d.company_code = c.company_code
        LEFT JOIN (
            SELECT company_code,
                   CAST(REPLACE(
                       (SELECT value FROM screener_annual_pl a2
                        WHERE a2.company_code = a.company_code AND metric IN ('Sales+','Revenue+')
                          AND year != 'TTM' ORDER BY CAST(SUBSTR(year,-4) AS INTEGER) DESC LIMIT 1),
                        ',', '') AS REAL) as latest_sales,
                   CAST(REPLACE(
                       (SELECT value FROM screener_annual_pl a3
                        WHERE a3.company_code = a.company_code AND metric IN ('Sales+','Revenue+')
                          AND year != 'TTM' ORDER BY CAST(SUBSTR(year,-4) AS INTEGER) DESC LIMIT 1 OFFSET 5),
                        ',', '') AS REAL) as oldest_sales
            FROM screener_annual_pl a GROUP BY company_code
        ) s5 ON d.company_code = s5.company_code
        WHERE c.enabled = 1
          AND d.company_name IS NOT NULL
          AND (d.pe_ratio        <= :max_pe   OR d.pe_ratio IS NULL)
          AND (d.debt_to_equity  <= :max_debt OR d.debt_to_equity IS NULL)
          AND d.fcf_cfo_ratio    >= :min_fcf_cfo
          AND d.promoter_holding >= :min_promoter
          AND s5.oldest_sales > 0
          AND ROUND((POWER(s5.latest_sales / s5.oldest_sales, 1.0/5) - 1) * 100, 2) >= :min_cagr
        ORDER BY green_score DESC, d.ssgr DESC
    """, {
        "max_pe":    FILTER["max_pe"],
        "max_debt":  FILTER["max_debt"],
        "min_fcf_cfo": FILTER["min_fcf_cfo"],
        "min_promoter": FILTER["min_promoter"],
        "min_cagr":  FILTER["min_sales_growth_5y"],
    })
    rows = cur.fetchall()
    conn.close()
    keys = ["company_code", "company_name", "sector", "industry",
            "pe_ratio", "ssgr", "roce", "fcf_cfo_ratio", "green_score"]
    companies = [dict(zip(keys, r)) for r in rows]
    if top_n:
        companies = companies[:top_n]
    return companies

# ── Result Caching ────────────────────────────────────────────────────────────

def load_cache() -> dict:
    """Load the latest results file as a dict keyed by company_code."""
    files = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
    if not files:
        return {}
    with open(files[0]) as f:
        data = json.load(f)
    return data.get("companies", {})


def is_stale(result: dict) -> bool:
    """True if the cached result is older than CACHE_DAYS."""
    analysed_at = result.get("analysed_at")
    if not analysed_at:
        return True
    return datetime.fromisoformat(analysed_at) < datetime.now() - timedelta(days=CACHE_DAYS)


def save_results(results: dict, run_meta: dict):
    """Save the full run to a timestamped JSON file."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"analysis_{ts}.json"
    with open(path, "w") as f:
        json.dump({"meta": run_meta, "companies": results}, f, indent=2, default=str)
    print(f"\nResults saved to {path}")
    return path

# ── Markdown Report ───────────────────────────────────────────────────────────

def generate_markdown(results: dict) -> str:
    lines = [
        f"# Stock Agent Analysis",
        f"Generated: {datetime.now().strftime('%d %b %Y %H:%M')}",
        f"Filter: Growth & Quality ({len(results)} companies)\n",
        "---\n"
    ]
    # Group by verdict
    for verdict in ["Strong Buy", "Buy", "Watch", "Avoid"]:
        group = [r for r in results.values() if r.get("verdict") == verdict]
        if not group:
            continue
        lines.append(f"## {verdict} ({len(group)})\n")
        for r in group:
            lines.append(f"### {r['company_name']} ({r['company_code']})")
            lines.append(f"**Verdict:** {r['verdict']} — {r['verdict_reason']}\n")
            lines.append("**Pros:**")
            for p in r.get("pros", []):
                lines.append(f"- {p}")
            lines.append("\n**Cons:**")
            for c in r.get("cons", []):
                lines.append(f"- {c}")
            lines.append(f"\n**Growth Path:**\n{r.get('growth_path', '')}")
            lines.append("\n**Risks:**")
            for risk in r.get("risk_factors", []):
                lines.append(f"- {risk}")
            lines.append("\n---\n")
    return "\n".join(lines)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Stock Analysis Agent")
    parser.add_argument("--company", help="Analyse a single company by code")
    parser.add_argument("--top",     type=int, help="Analyse top N companies by green score")
    parser.add_argument("--force",   action="store_true", help="Re-analyse even if recently cached")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Determine companies to analyse
    if args.company:
        conn = sqlite3.connect(str(DATABASE_PATH))
        cur = conn.cursor()
        cur.execute(
            "SELECT company_code, company_name FROM screener_companies WHERE company_code = ?",
            (args.company.upper(),)
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            print(f"Company {args.company} not found in DB.")
            sys.exit(1)
        companies = [{"company_code": row[0], "company_name": row[1]}]
    else:
        companies = get_growth_quality_companies(top_n=args.top)
        print(f"Found {len(companies)} companies passing Growth & Quality filter")

    # Load cache
    cache = {} if args.force else load_cache()

    results = dict(cache)  # Start with cached results
    run_meta = {
        "started_at": datetime.now().isoformat(),
        "model": MODEL,
        "filter": FILTER,
        "total_companies": len(companies),
    }

    analysed = 0
    skipped  = 0

    for i, company in enumerate(companies, 1):
        code = company["company_code"]
        name = company["company_name"]

        # Check cache
        if code in cache and not is_stale(cache[code]) and not args.force:
            print(f"[{i}/{len(companies)}] {name} — skipping (cached {cache[code].get('analysed_at', '')[:10]})")
            skipped += 1
            continue

        print(f"\n[{i}/{len(companies)}] {name} ({code})")

        try:
            result = analyse_company(client, code, name)
            results[code] = result
            analysed += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results[code] = {"error": str(e), "company_code": code, "company_name": name}

        # Save incrementally after each company
        save_results(results, run_meta)

        if i < len(companies):
            time.sleep(COMPANY_GAP)

    # Final save + markdown report
    run_meta["completed_at"] = datetime.now().isoformat()
    run_meta["analysed"] = analysed
    run_meta["skipped"]  = skipped
    path = save_results(results, run_meta)

    # Write markdown
    md_path = path.with_suffix(".md")
    with open(md_path, "w") as f:
        f.write(generate_markdown(results))
    print(f"Markdown report saved to {md_path}")

    # Summary
    verdicts = {}
    for r in results.values():
        v = r.get("verdict", "Error")
        verdicts[v] = verdicts.get(v, 0) + 1
    print(f"\n{'='*50}")
    print(f"Analysis complete: {analysed} analysed, {skipped} from cache")
    for v, count in sorted(verdicts.items()):
        print(f"  {v}: {count}")


if __name__ == "__main__":
    main()
