#!/usr/bin/env python3
"""
screener_builder.py — Alert Invest Stock Screener WordPress page generator
===========================================================================
Reads 3 Google Sheets CSV tabs → builds a full WordPress HTML page with:
  - Top 10 hero section
  - Sector summary
  - Full interactive screener table (500 stocks)
  - Free tier: first 20 rows visible, rest blurred + Patreon paywall
  - Filters: Graham / Lynch / Buffett / Pass All / Sector

Runs Mon/Wed/Fri via GitHub Actions after the Google Sheet updates.

Usage:
    python screener_builder.py              # deploy to WordPress
    python screener_builder.py --dry-run    # save HTML locally only
"""

import argparse
import csv
import io
import json
import os
import re
import time
from datetime import datetime

import requests

# ─── CONFIG ───────────────────────────────────────────────────────────────────
WP_URL      = "https://alert-invest.com"
WP_USER     = os.environ.get("WP_USER", "Mike")
WP_PASSWORD = os.environ.get("WP_PASSWORD", "")
WP_SLUG     = "stock-screener"

FREE_ROWS   = 20  # rows visible without Patreon

SCREENER_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRAgh9VdS0Ox8xrDf8XYCslQwCNuKfVRwJ9329YkEE7Fn5BtW4bkLrts19MnNjjkHbnp6twVB99Z21I/pub?gid=310948557&single=true&output=csv"
TOP10_CSV    = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRAgh9VdS0Ox8xrDf8XYCslQwCNuKfVRwJ9329YkEE7Fn5BtW4bkLrts19MnNjjkHbnp6twVB99Z21I/pub?gid=1532740227&single=true&output=csv"
SUMMARY_CSV  = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRAgh9VdS0Ox8xrDf8XYCslQwCNuKfVRwJ9329YkEE7Fn5BtW4bkLrts19MnNjjkHbnp6twVB99Z21I/pub?gid=794058568&single=true&output=csv"

PATREON_URL  = "https://www.patreon.com/cw/AlertInvest/membership"

# ─── FETCH CSV ────────────────────────────────────────────────────────────────
def fetch_csv(url: str) -> list:
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return list(csv.reader(io.StringIO(r.text)))

# ─── PARSE SCREENER ───────────────────────────────────────────────────────────
def parse_screener(rows: list) -> list:
    """
    Find the header row (contains 'Ticker') and parse all data rows.
    Returns list of dicts.
    """
    header_idx = None
    for i, row in enumerate(rows):
        if any("Ticker" in str(c) for c in row):
            header_idx = i
            break
    if header_idx is None:
        return []

    headers = [c.strip() for c in rows[header_idx]]
    stocks  = []
    for row in rows[header_idx + 1:]:
        if len(row) < 5:
            continue
        d = {headers[j]: row[j].strip() if j < len(row) else "" for j in range(len(headers))}
        ticker = d.get("Ticker", "").strip()
        if not ticker or ticker == "#":
            continue
        stocks.append(d)
    return stocks

# ─── PARSE TOP 10 ─────────────────────────────────────────────────────────────
def parse_top10(rows: list) -> list:
    """Find the Rank/Ticker header and parse top 10 rows."""
    header_idx = None
    for i, row in enumerate(rows):
        if any("Ticker" in str(c) for c in row):
            header_idx = i
            break
    if header_idx is None:
        return []
    headers = [c.strip() for c in rows[header_idx]]
    top10 = []
    for row in rows[header_idx + 1:]:
        if len(row) < 3:
            continue
        d = {headers[j]: row[j].strip() if j < len(row) else "" for j in range(len(headers))}
        ticker = d.get("Ticker", "").strip()
        if not ticker or "—" in ticker or "no stock" in ticker.lower():
            continue
        # Remove 🆕 emoji if present
        d["Ticker"] = ticker.replace("🆕", "").strip()
        top10.append(d)
    return top10[:10]

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def signal_badge(val: str) -> str:
    v = val.strip()
    if v == "Candidate":
        return f'<span class="scr-badge candidate">{v}</span>'
    if v == "Near Miss":
        return f'<span class="scr-badge near-miss">{v}</span>'
    if v == "PASS":
        return f'<span class="scr-badge pass">PASS</span>'
    if v == "FAIL":
        return f'<span class="scr-badge fail">FAIL</span>'
    return f'<span class="scr-badge none">—</span>'

def mos_badge(val: str) -> str:
    v = val.strip()
    if not v or v == "-":
        return '<span style="color:#94a3b8">—</span>'
    return f'<span class="scr-mos">{v}</span>'

def fmt_pct(val: str) -> str:
    v = val.strip().replace("%", "")
    try:
        f = float(v)
        color = "#16a34a" if f > 0 else "#dc2626"
        return f'<span style="color:{color};font-weight:600">{f:+.1f}%</span>'
    except:
        return f'<span style="color:#94a3b8">—</span>'

def fmt_num(val: str, decimals: int = 1) -> str:
    v = val.strip().replace("%", "")
    try:
        f = float(v)
        return f"{f:.{decimals}f}"
    except:
        return "—"

def sector_color(sector: str) -> str:
    colors = {
        "Technology": "#3b82f6", "Communication Services": "#8b5cf6",
        "Healthcare": "#10b981", "Financials": "#f59e0b",
        "Consumer Cyclical": "#f97316", "Consumer Defensive": "#84cc16",
        "Industrials": "#6366f1", "Energy": "#ef4444",
        "Real Estate": "#14b8a6", "Basic Materials": "#a16207",
        "Utilities": "#0ea5e9", "Insurance": "#d97706",
    }
    return colors.get(sector, "#64748b")

# ─── BUILD HTML ───────────────────────────────────────────────────────────────
def build_html(stocks: list, top10: list, updated_at: str) -> str:

    # ── Collect unique sectors ──────────────────────────────────────────────
    sectors = sorted(set(s.get("Sector", "").strip() for s in stocks if s.get("Sector", "").strip()))

    # ── Stats ───────────────────────────────────────────────────────────────
    n_total   = len(stocks)
    n_graham  = sum(1 for s in stocks if s.get("Graham Screen") == "Candidate")
    n_lynch   = sum(1 for s in stocks if s.get("Lynch Screen")  == "Candidate")
    n_buffett = sum(1 for s in stocks if s.get("Buffett Screen") == "Candidate")
    n_pass    = sum(1 for s in stocks if s.get("Pass All?") == "PASS")

    # ── Top 10 cards ────────────────────────────────────────────────────────
    top10_html = ""
    for i, t in enumerate(top10[:10]):
        rank    = i + 1
        ticker  = t.get("Ticker", "")
        company = t.get("Company", "")
        sector  = t.get("Sector", "")
        signals = t.get("Signals", "")
        score   = t.get("Score", "")
        mos     = t.get("Margin of Safety", "—")
        sc      = sector_color(sector)
        rank_color = "#f5c842" if rank == 1 else ("#c0c0c0" if rank == 2 else ("#cd7f32" if rank == 3 else "#64748b"))
        top10_html += f"""
<div class="scr-t10-card">
  <div class="scr-t10-rank" style="color:{rank_color}">#{rank}</div>
  <div class="scr-t10-body">
    <div class="scr-t10-ticker">{ticker}</div>
    <div class="scr-t10-company">{company[:30]}</div>
    <div class="scr-t10-sector" style="background:{sc}18;color:{sc}">{sector}</div>
  </div>
  <div class="scr-t10-right">
    <div class="scr-t10-signals">{signals}</div>
    <div class="scr-t10-score">{score}</div>
    <div class="scr-t10-mos">{mos}</div>
  </div>
</div>"""

    # ── Sector filter pills ──────────────────────────────────────────────────
    sector_pills = '<button class="scr-pill active" onclick="scrFilter(this,\'all\')" data-filter="all">All Sectors</button>'
    for sec in sectors:
        sc = sector_color(sec)
        sector_pills += f'<button class="scr-pill" onclick="scrFilter(this,\'sector\',\'{sec}\')" data-filter="sector" data-val="{sec}" style="--pill-color:{sc}">{sec}</button>'

    # ── Philosophy filter pills ──────────────────────────────────────────────
    phil_pills = """
<button class="scr-pill active" onclick="scrPhil(this,'all')">All</button>
<button class="scr-pill" onclick="scrPhil(this,'graham')" style="--pill-color:#00c896">Graham</button>
<button class="scr-pill" onclick="scrPhil(this,'lynch')" style="--pill-color:#1a56db">Lynch</button>
<button class="scr-pill" onclick="scrPhil(this,'buffett')" style="--pill-color:#6c5ce7">Buffett</button>
<button class="scr-pill" onclick="scrPhil(this,'pass')" style="--pill-color:#f5c842">Pass All</button>
<button class="scr-pill" onclick="scrPhil(this,'any')" style="--pill-color:#f97316">Any Signal</button>"""

    # ── Table rows ──────────────────────────────────────────────────────────
    rows_html = ""
    for i, s in enumerate(stocks):
        ticker  = s.get("Ticker", "")
        company = s.get("Company", "")
        sector  = s.get("Sector", "")
        pe      = s.get("P/E (Live)", "")
        peg     = s.get("PEG (Live)", "")
        de      = s.get("Debt/Equity", "")
        roic    = s.get("ROIC", "")
        graham  = s.get("Graham Screen", "")
        lynch   = s.get("Lynch Screen", "")
        buffett = s.get("Buffett Screen", "")
        pass_   = s.get("Pass All?", "")
        mos     = s.get("Margin of Safety", "")
        rev_gr  = s.get("Rev Gr%", "")
        op_mar  = s.get("Op. Margin", "")
        eps_gr  = s.get("EPS Growth", "")
        net_mar = s.get("Net Margin", "")

        sc = sector_color(sector)

        # Data attributes for JS filtering
        is_graham  = "true" if graham  == "Candidate" else "false"
        is_lynch   = "true" if lynch   == "Candidate" else "false"
        is_buffett = "true" if buffett == "Candidate" else "false"
        is_pass    = "true" if pass_   == "PASS"      else "false"
        any_sig    = "true" if (graham in ("Candidate","Near Miss") or
                                lynch  in ("Candidate","Near Miss") or
                                buffett in ("Candidate","Near Miss") or
                                pass_ == "PASS") else "false"

        # Blur rows beyond FREE_ROWS for non-premium
        blur_class = " scr-locked" if i >= FREE_ROWS else ""

        rows_html += f"""
<tr class="scr-row{blur_class}"
    data-ticker="{ticker.lower()}"
    data-company="{company.lower()}"
    data-sector="{sector}"
    data-graham="{is_graham}"
    data-lynch="{is_lynch}"
    data-buffett="{is_buffett}"
    data-pass="{is_pass}"
    data-any="{any_sig}">
  <td class="scr-td-ticker">
    <span class="scr-ticker">{ticker}</span>
    <span class="scr-company">{company[:28]}</span>
  </td>
  <td><span class="scr-sector-pill" style="background:{sc}18;color:{sc}">{sector}</span></td>
  <td class="scr-num">{fmt_num(pe)}</td>
  <td class="scr-num">{fmt_num(peg, 2)}</td>
  <td class="scr-num">{fmt_num(de, 2)}</td>
  <td class="scr-num">{fmt_num(roic, 1)}%</td>
  <td>{signal_badge(graham)}</td>
  <td>{signal_badge(lynch)}</td>
  <td>{signal_badge(buffett)}</td>
  <td>{signal_badge(pass_)}</td>
  <td>{mos_badge(mos)}</td>
  <td>{fmt_pct(rev_gr)}</td>
  <td>{fmt_pct(eps_gr)}</td>
  <td class="scr-num">{fmt_num(op_mar, 1)}%</td>
</tr>"""

    # ── Paywall overlay ──────────────────────────────────────────────────────
    paywall_html = f"""
<div class="scr-paywall">
  <div class="scr-paywall-card">
    <div class="scr-paywall-lock">🔒</div>
    <div class="scr-paywall-title">Unlock Full Screener</div>
    <div class="scr-paywall-sub">
      You're seeing the top {FREE_ROWS} of <strong>{n_total} stocks</strong>.<br>
      Upgrade to access all results, all filters, and weekly updates.
    </div>
    <div class="scr-paywall-features">
      <span>✅ {n_total} S&P 500 stocks</span>
      <span>✅ Graham / Lynch / Buffett screens</span>
      <span>✅ Margin of Safety</span>
      <span>✅ Updated Mon · Wed · Fri</span>
    </div>
    <a href="{PATREON_URL}" class="scr-paywall-btn">🅿 Unlock with Patreon</a>
    <div class="scr-paywall-note">Cancel anytime · Instant access</div>
  </div>
</div>"""

    # ── Schema.org ──────────────────────────────────────────────────────────
    schema = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "S&P 500 Value Stock Screener — Graham, Lynch & Buffett | Alert Invest",
        "description": f"Screen {n_total} S&P 500 stocks using Graham, Lynch and Buffett criteria. Live P/E, PEG, ROIC, FCF, D/E and Margin of Safety. Updated 3× per week.",
        "url": f"{WP_URL}/stock-screener/",
        "dateModified": updated_at,
        "publisher": {"@type": "Organization", "name": "Alert Invest", "url": WP_URL}
    }

    return f"""<!-- wp:html -->
<!-- screener_builder.py | updated {updated_at} -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=DM+Serif+Display&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<script type="application/ld+json">{json.dumps(schema)}</script>

<style>
/* ── RESET ── */
.scr-wrap{{--blue:#1a56db;--green:#16a34a;--green-lt:#f0fdf4;--red:#dc2626;
  --amber:#d97706;--purple:#6c5ce7;--primary:#0f172a;--text:#334155;
  --muted:#64748b;--border:#e2e8f0;--card:#fff;--bg:#f8fafc;--radius:12px;
  font-family:'DM Sans',sans-serif;color:var(--text);-webkit-font-smoothing:antialiased}}
.scr-wrap *{{box-sizing:border-box;margin:0;padding:0}}
.scr-inner{{max-width:1300px;margin:0 auto;padding:2rem 1.25rem}}
.entry-title,.page-title,h1.title{{display:none!important}}

/* ── HERO ── */
.scr-hero{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:2rem 2.5rem;margin-bottom:1.5rem}}
.scr-hero-badge{{display:inline-flex;align-items:center;gap:6px;
  background:#eff6ff;color:var(--blue);font-size:.7rem;font-weight:700;
  text-transform:uppercase;letter-spacing:.07em;padding:4px 12px;border-radius:99px;margin-bottom:1rem}}
.scr-hero h1{{font-family:'DM Serif Display',serif;font-size:clamp(1.6rem,3vw,2.2rem);
  color:var(--primary);margin-bottom:.5rem;line-height:1.15}}
.scr-hero-sub{{font-size:.9rem;color:var(--muted);max-width:560px;line-height:1.65;margin-bottom:1.5rem}}
.scr-stats{{display:flex;flex-wrap:wrap;gap:.75rem;margin-bottom:1.5rem}}
.scr-stat{{background:#f8fafc;border:1px solid var(--border);border-radius:10px;
  padding:.75rem 1.25rem;display:flex;flex-direction:column;gap:2px}}
.scr-stat-val{{font-family:'DM Serif Display',serif;font-size:1.5rem;color:var(--primary);line-height:1}}
.scr-stat-lbl{{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}}

/* ── TOP 10 ── */
.scr-t10-wrap{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  overflow:hidden;margin-bottom:1.5rem}}
.scr-t10-header{{background:linear-gradient(135deg,#0f172a,#1e293b);padding:1.25rem 1.5rem;
  display:flex;align-items:center;justify-content:space-between}}
.scr-t10-title{{font-family:'DM Serif Display',serif;font-size:1.2rem;color:#fff}}
.scr-t10-sub{{font-size:.78rem;color:rgba(255,255,255,.5)}}
.scr-t10-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:0}}
.scr-t10-card{{display:flex;align-items:center;gap:.875rem;padding:.875rem 1.25rem;
  border-bottom:1px solid var(--border);border-right:1px solid var(--border);
  transition:background .15s}}
.scr-t10-card:hover{{background:#f8fafc}}
.scr-t10-rank{{font-family:'DM Serif Display',serif;font-size:1.4rem;font-weight:400;
  min-width:32px;text-align:center;flex-shrink:0}}
.scr-t10-body{{flex:1;min-width:0}}
.scr-t10-ticker{{font-weight:800;font-size:.95rem;color:var(--primary)}}
.scr-t10-company{{font-size:.75rem;color:var(--muted);margin-top:1px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}}
.scr-t10-sector{{display:inline-block;font-size:.62rem;font-weight:700;
  padding:2px 7px;border-radius:99px;margin-top:3px}}
.scr-t10-right{{text-align:right;flex-shrink:0}}
.scr-t10-signals{{font-size:.72rem;color:var(--blue);font-weight:600;margin-bottom:2px}}
.scr-t10-score{{font-size:.8rem;font-weight:700;color:var(--primary)}}
.scr-t10-mos{{font-size:.72rem;color:var(--muted)}}

/* ── FILTERS ── */
.scr-filters{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:1.25rem 1.5rem;margin-bottom:1rem}}
.scr-filter-row{{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin-bottom:.75rem}}
.scr-filter-row:last-child{{margin-bottom:0}}
.scr-filter-label{{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;
  color:var(--muted);min-width:80px}}
.scr-pill{{border:1px solid var(--border);background:white;color:var(--text);
  font-family:'DM Sans',sans-serif;font-size:.78rem;font-weight:600;
  padding:.35rem .85rem;border-radius:99px;cursor:pointer;transition:all .15s;white-space:nowrap}}
.scr-pill:hover{{border-color:var(--pill-color,var(--blue));color:var(--pill-color,var(--blue))}}
.scr-pill.active{{background:var(--pill-color,var(--blue));border-color:var(--pill-color,var(--blue));
  color:white}}
.scr-search{{flex:1;min-width:200px;padding:.5rem 1rem;border:1px solid var(--border);
  border-radius:99px;font-family:'DM Sans',sans-serif;font-size:.875rem;outline:none}}
.scr-search:focus{{border-color:var(--blue)}}
.scr-count{{font-size:.82rem;color:var(--muted);margin-left:auto;white-space:nowrap}}

/* ── TABLE ── */
.scr-table-wrap{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  overflow:hidden;margin-bottom:1.5rem;position:relative}}
.scr-table-header{{padding:.85rem 1.25rem;border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}}
.scr-table-title{{font-size:.88rem;font-weight:700;color:var(--primary)}}
.scr-updated{{font-size:.72rem;color:var(--muted)}}
.scr-table{{width:100%;border-collapse:collapse;font-size:.8rem}}
.scr-table th{{text-align:left;padding:.6rem 1rem;background:#f8fafc;
  color:var(--muted);font-size:.65rem;text-transform:uppercase;letter-spacing:.06em;
  font-weight:700;border-bottom:1px solid var(--border);white-space:nowrap;cursor:pointer}}
.scr-table th:hover{{color:var(--blue)}}
.scr-table td{{padding:.7rem 1rem;border-bottom:1px solid var(--border);vertical-align:middle}}
.scr-table tr:last-child td{{border-bottom:none}}
.scr-table tbody tr:hover td{{background:#f8fafc}}
.scr-ticker{{display:block;font-weight:800;font-size:.88rem;color:var(--primary)}}
.scr-company{{display:block;font-size:.7rem;color:var(--muted);margin-top:1px}}
.scr-sector-pill{{display:inline-block;font-size:.62rem;font-weight:700;
  padding:2px 7px;border-radius:99px;white-space:nowrap}}
.scr-num{{font-family:'DM Mono',monospace;font-size:.78rem;white-space:nowrap}}
.scr-badge{{display:inline-block;font-size:.65rem;font-weight:700;padding:2px 8px;
  border-radius:6px;white-space:nowrap}}
.scr-badge.candidate{{background:#dcfce7;color:#14532d}}
.scr-badge.near-miss{{background:#fef9c3;color:#713f12}}
.scr-badge.pass{{background:#f5c842;color:#0f172a}}
.scr-badge.fail{{background:#f1f5f9;color:#94a3b8}}
.scr-badge.none{{color:#cbd5e1}}
.scr-mos{{display:inline-block;font-size:.72rem;font-weight:700;color:var(--blue)}}

/* ── LOCKED ROWS ── */
.scr-locked td{{filter:blur(4px);user-select:none;pointer-events:none}}

/* ── PAYWALL ── */
.scr-paywall{{position:relative;margin-top:-120px;z-index:10;padding:0 1.25rem 1.5rem}}
.scr-paywall-card{{background:white;border:1px solid var(--border);border-radius:20px;
  padding:2.5rem;text-align:center;max-width:520px;margin:0 auto;
  box-shadow:0 8px 40px rgba(0,0,0,.12)}}
.scr-paywall-lock{{font-size:2rem;margin-bottom:.75rem}}
.scr-paywall-title{{font-family:'DM Serif Display',serif;font-size:1.5rem;color:var(--primary);
  margin-bottom:.5rem}}
.scr-paywall-sub{{font-size:.875rem;color:var(--muted);line-height:1.6;margin-bottom:1.25rem}}
.scr-paywall-features{{display:flex;flex-wrap:wrap;gap:.4rem;justify-content:center;margin-bottom:1.5rem}}
.scr-paywall-features span{{background:#f0f5ff;color:var(--blue);font-size:.75rem;
  font-weight:600;padding:.2rem .6rem;border-radius:99px}}
.scr-paywall-btn{{display:inline-block;background:var(--blue);color:white;
  font-family:'DM Sans',sans-serif;font-weight:800;font-size:1rem;
  padding:.9rem 2.5rem;border-radius:14px;text-decoration:none;
  box-shadow:0 4px 20px rgba(26,86,219,.35);margin-bottom:.75rem}}
.scr-paywall-note{{font-size:.75rem;color:var(--muted)}}

/* ── FAQ ── */
.scr-faq{{margin-top:2rem}}
.scr-faq-title{{font-family:'DM Serif Display',serif;font-size:1.4rem;color:var(--primary);
  margin-bottom:1rem}}
.scr-faq-item{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  margin-bottom:.6rem;overflow:hidden}}
.scr-faq-q{{padding:1rem 1.25rem;font-weight:700;font-size:.9rem;color:var(--primary);
  cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:1rem}}
.scr-faq-q:hover{{background:#f8fafc}}
.scr-faq-chev{{font-size:.75rem;color:var(--muted);transition:transform .25s;flex-shrink:0}}
.scr-faq-a{{max-height:0;overflow:hidden;transition:max-height .3s ease,opacity .3s;opacity:0}}
.scr-faq-a.open{{opacity:1}}
.scr-faq-a-inner{{padding:.1rem 1.25rem 1rem;font-size:.875rem;line-height:1.75;color:var(--text)}}

/* ── DISCLAIMER ── */
.scr-disc{{font-size:.74rem;color:var(--muted);margin-top:1.5rem;text-align:center;
  line-height:1.6;padding:1rem;border-top:1px solid var(--border)}}

@media(max-width:768px){{
  .scr-t10-grid{{grid-template-columns:1fr}}
  .scr-table th:nth-child(n+5),.scr-table td:nth-child(n+5){{display:none}}
}}
</style>

<div class="scr-wrap">
<div class="scr-inner">

<script type="application/ld+json">{json.dumps(schema)}</script>

<!-- ── HERO ── -->
<div class="scr-hero">
  <div class="scr-hero-badge">📊 Live · Updated Mon · Wed · Fri</div>
  <h1>S&P 500 Value Stock Screener</h1>
  <p class="scr-hero-sub">
    Screen {n_total} stocks using the frameworks of Graham, Lynch and Buffett.
    Live P/E, PEG, ROIC, FCF and Margin of Safety — updated 3× per week.
  </p>
  <div class="scr-stats">
    <div class="scr-stat">
      <div class="scr-stat-val">{n_total}</div>
      <div class="scr-stat-lbl">Stocks Screened</div>
    </div>
    <div class="scr-stat">
      <div class="scr-stat-val" style="color:#00c896">{n_graham}</div>
      <div class="scr-stat-lbl">Graham Candidates</div>
    </div>
    <div class="scr-stat">
      <div class="scr-stat-val" style="color:#1a56db">{n_lynch}</div>
      <div class="scr-stat-lbl">Lynch Candidates</div>
    </div>
    <div class="scr-stat">
      <div class="scr-stat-val" style="color:#6c5ce7">{n_buffett}</div>
      <div class="scr-stat-lbl">Buffett Candidates</div>
    </div>
    <div class="scr-stat">
      <div class="scr-stat-val" style="color:#f5c842">{n_pass}</div>
      <div class="scr-stat-lbl">Pass All Criteria</div>
    </div>
  </div>
  <div style="font-size:.75rem;color:var(--muted)">Last updated: {updated_at}</div>
</div>

<!-- ── TOP 10 ── -->
<div class="scr-t10-wrap">
  <div class="scr-t10-header">
    <div>
      <div class="scr-t10-title">🏆 Top 10 Opportunities This Week</div>
      <div class="scr-t10-sub">Ranked by screening score — Graham + Lynch + Buffett signals combined</div>
    </div>
  </div>
  <div class="scr-t10-grid">
    {top10_html}
  </div>
</div>

<!-- ── FILTERS ── -->
<div class="scr-filters">
  <div class="scr-filter-row">
    <span class="scr-filter-label">Philosophy</span>
    {phil_pills}
    <input type="text" class="scr-search" id="scr-search" placeholder="Search ticker or company…">
    <span class="scr-count" id="scr-count">{n_total} stocks</span>
  </div>
  <div class="scr-filter-row">
    <span class="scr-filter-label">Sector</span>
    {sector_pills}
  </div>
</div>

<!-- ── TABLE ── -->
<div class="scr-table-wrap" id="scr-table-wrap">
  <div class="scr-table-header">
    <div class="scr-table-title">📋 Full Screener — {n_total} S&P 500 Stocks</div>
    <span class="scr-updated">Updated: {updated_at}</span>
  </div>
  <div style="overflow-x:auto">
  <table class="scr-table" id="scr-table">
    <thead>
      <tr>
        <th>Stock</th>
        <th>Sector</th>
        <th title="Price/Earnings TTM">P/E</th>
        <th title="Price/Earnings Growth">PEG</th>
        <th title="Debt/Equity">D/E</th>
        <th title="Return on Invested Capital">ROIC</th>
        <th title="Benjamin Graham screen">Graham</th>
        <th title="Peter Lynch screen">Lynch</th>
        <th title="Warren Buffett screen">Buffett</th>
        <th title="Passes all 5 base criteria">Pass All</th>
        <th title="Margin of Safety">MoS</th>
        <th title="Revenue Growth YoY">Rev Gr</th>
        <th title="EPS Growth">EPS Gr</th>
        <th title="Operating Margin">Op Mar</th>
      </tr>
    </thead>
    <tbody id="scr-tbody">
      {rows_html}
    </tbody>
  </table>
  </div>
</div>

{paywall_html}

<!-- ── FAQ ── -->
<div class="scr-faq">
  <h2 class="scr-faq-title">How the Screener Works</h2>

  <div class="scr-faq-item">
    <div class="scr-faq-q" onclick="scrFaq(this)">
      What is the Graham screen?
      <span class="scr-faq-chev">▼</span>
    </div>
    <div class="scr-faq-a">
      <div class="scr-faq-a-inner">
        Benjamin Graham's Net-Net / Graham Number approach: a stock is a <strong>Candidate</strong> when its price trades below the Graham Number — calculated as √(22.5 × TTM EPS × Book Value Per Share). This represents Graham's ceiling for a fairly valued stock. A <strong>Near Miss</strong> means the price is within 10% of the Graham Number.
      </div>
    </div>
  </div>

  <div class="scr-faq-item">
    <div class="scr-faq-q" onclick="scrFaq(this)">
      What is the Lynch screen?
      <span class="scr-faq-chev">▼</span>
    </div>
    <div class="scr-faq-a">
      <div class="scr-faq-a-inner">
        Peter Lynch's GARP (Growth at a Reasonable Price) approach: <strong>Candidate</strong> requires PEG &lt; 1.0, EPS growth between 10–30%, and Debt/Equity &lt; 0.6. A PEG below 1 means you're paying less than 1× the growth rate — Lynch's core signal for an undervalued growth stock.
      </div>
    </div>
  </div>

  <div class="scr-faq-item">
    <div class="scr-faq-q" onclick="scrFaq(this)">
      What is the Buffett screen?
      <span class="scr-faq-chev">▼</span>
    </div>
    <div class="scr-faq-a">
      <div class="scr-faq-a-inner">
        Warren Buffett's quality moat approach: <strong>Candidate</strong> requires ROIC &gt; 15%, FCF Yield &gt; 5%, Revenue Growth &gt; 5%, and Operating Margin &gt; 15%. These criteria identify durable competitive advantages — companies that can compound capital at high rates over long periods.
      </div>
    </div>
  </div>

  <div class="scr-faq-item">
    <div class="scr-faq-q" onclick="scrFaq(this)">
      How often is the screener updated?
      <span class="scr-faq-chev">▼</span>
    </div>
    <div class="scr-faq-a">
      <div class="scr-faq-a-inner">
        The screener updates automatically three times per week using live data from the FMP (Financial Modeling Prep) API. All metrics use TTM (trailing twelve months) values — not single-quarter or annual figures — for the most accurate picture of current performance.
      </div>
    </div>
  </div>
</div>

<p class="scr-disc">
  For informational purposes only. Not investment advice. Data sourced from Financial Modeling Prep API.
  Metrics are TTM (trailing twelve months). Past screening signals do not guarantee future returns.
  <a href="{WP_URL}">Alert Invest</a> — Value Investing Research.
</p>

</div><!-- /scr-inner -->
</div><!-- /scr-wrap -->

<script>
// ── STATE ─────────────────────────────────────────────────────────
var scrPhilActive    = 'all';
var scrSectorActive  = 'all';
var scrSectorVal     = '';
var scrSearchVal     = '';

// ── FILTER ENGINE ─────────────────────────────────────────────────
function scrApply() {{
  var rows  = document.querySelectorAll('#scr-tbody .scr-row');
  var shown = 0;
  rows.forEach(function(row) {{
    var ticker  = row.dataset.ticker  || '';
    var company = row.dataset.company || '';
    var sector  = row.dataset.sector  || '';

    // Philosophy filter
    var philOk = true;
    if      (scrPhilActive === 'graham')  {{ philOk = row.dataset.graham  === 'true'; }}
    else if (scrPhilActive === 'lynch')   {{ philOk = row.dataset.lynch   === 'true'; }}
    else if (scrPhilActive === 'buffett') {{ philOk = row.dataset.buffett === 'true'; }}
    else if (scrPhilActive === 'pass')    {{ philOk = row.dataset.pass    === 'true'; }}
    else if (scrPhilActive === 'any')     {{ philOk = row.dataset.any     === 'true'; }}

    // Sector filter
    var sectorOk = (scrSectorActive === 'all') || (sector === scrSectorVal);

    // Search
    var searchOk = !scrSearchVal ||
                   ticker.indexOf(scrSearchVal)  !== -1 ||
                   company.indexOf(scrSearchVal) !== -1;

    var visible = philOk && sectorOk && searchOk;
    row.style.display = visible ? '' : 'none';
    if (visible) {{ shown++; }}
  }});
  var el = document.getElementById('scr-count');
  if (el) {{ el.textContent = shown + ' stock' + (shown !== 1 ? 's' : ''); }}
}}

function scrPhil(btn, val) {{
  scrPhilActive = val;
  document.querySelectorAll('.scr-pill[onclick*="scrPhil"]').forEach(function(b) {{ b.classList.remove('active'); }});
  btn.classList.add('active');
  scrApply();
}}

function scrFilter(btn, type, val) {{
  scrSectorActive = type;
  scrSectorVal    = val || '';
  document.querySelectorAll('.scr-pill[onclick*="scrFilter"]').forEach(function(b) {{ b.classList.remove('active'); }});
  btn.classList.add('active');
  scrApply();
}}

document.getElementById('scr-search').addEventListener('input', function() {{
  scrSearchVal = this.value.toLowerCase().trim();
  scrApply();
}});

// ── FAQ ───────────────────────────────────────────────────────────
function scrFaq(btn) {{
  var ans  = btn.nextElementSibling;
  var chev = btn.querySelector('.scr-faq-chev');
  var open = ans.classList.contains('open');
  ans.classList.toggle('open', !open);
  chev.style.transform = open ? '' : 'rotate(180deg)';
  ans.style.maxHeight  = open ? '0' : (ans.scrollHeight + 40) + 'px';
}}
</script>
<!-- /wp:html -->"""

# ─── WORDPRESS DEPLOY ─────────────────────────────────────────────────────────
def wp_auth() -> str:
    try:
        r = requests.post(
            f"{WP_URL}/wp-json/jwt-auth/v1/token",
            json={"username": WP_USER, "password": WP_PASSWORD},
            timeout=15
        )
        return r.json().get("token", "")
    except Exception as e:
        print(f"  WP auth error: {e}")
        return ""

def deploy_page(html_content: str, updated_at: str) -> bool:
    token = wp_auth()
    if not token:
        print("  ✗ Could not get WP token")
        return False

    headers = {"Authorization": f"Bearer {token}"}
    title   = "S&P 500 Value Stock Screener — Graham, Lynch & Buffett | Alert Invest"

    payload = {
        "title":   title,
        "content": html_content,
        "status":  "publish",
        "slug":    WP_SLUG,
    }

    # Find existing page
    search = requests.get(
        f"{WP_URL}/wp-json/wp/v2/pages",
        params={"slug": WP_SLUG},
        headers=headers, timeout=15
    ).json()

    if search and isinstance(search, list) and len(search) > 0:
        pid = search[0]["id"]
        r   = requests.post(f"{WP_URL}/wp-json/wp/v2/pages/{pid}",
                            headers=headers, json=payload, timeout=120)
        action = "Updated"
    else:
        r = requests.post(f"{WP_URL}/wp-json/wp/v2/pages",
                          headers=headers, json=payload, timeout=120)
        action = "Created"

    if r.status_code in [200, 201]:
        print(f"  ✅ {action}: {WP_URL}/{WP_SLUG}/")
        return True
    else:
        print(f"  ✗ WP error {r.status_code}: {r.text[:200]}")
        return False

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*60}")
    print(f"  Alert Invest Screener Builder — {updated_at}")
    print(f"{'='*60}\n")

    # Fetch CSVs
    print("  Fetching Screener CSV...")
    screener_rows = fetch_csv(SCREENER_CSV)
    print(f"  → {len(screener_rows)} rows")

    print("  Fetching Top 10 CSV...")
    top10_rows = fetch_csv(TOP10_CSV)
    print(f"  → {len(top10_rows)} rows")

    # Parse
    stocks = parse_screener(screener_rows)
    top10  = parse_top10(top10_rows)
    print(f"\n  Parsed {len(stocks)} stocks, {len(top10)} top 10 entries")

    if not stocks:
        print("  ✗ No stocks parsed — check CSV URLs")
        return

    # Build HTML
    print("  Building HTML...")
    html = build_html(stocks, top10, updated_at)
    print(f"  → {len(html):,} chars")

    # Deploy or save
    if args.dry_run:
        import os
        os.makedirs("output", exist_ok=True)
        with open("output/screener.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("  Saved: output/screener.html")
    else:
        print("  Deploying to WordPress...")
        deploy_page(html, updated_at)

    print(f"\n{'='*60}")
    print(f"  Done.\n")

if __name__ == "__main__":
    main()
