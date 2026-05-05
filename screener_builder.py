#!/usr/bin/env python3
import argparse, csv, io, json, os, re
from datetime import datetime
import requests

WP_URL      = "https://alert-invest.com"
WP_USER     = os.environ.get("WP_USER", "")
WP_PASSWORD = os.environ.get("WP_PASSWORD", "")
WP_SLUG     = "stock-screener"
FREE_ROWS    = 5
GOOGLE_ROWS  = 20

PATREON_CLIENT_ID   = "LOmI5CCfm8qswJK2JuO-cmVfeN2HiE3S0SneCiICAztq7jH4fWgDfpYbFkzn05yv"
PATREON_CAMPAIGN_ID = "14741872"
PATREON_REDIRECT    = "https://alert-invest.com/stock-screener/"
PATREON_TIER        = "Portfolio Builder"
PATREON_JOIN_URL    = "https://www.patreon.com/cw/AlertInvest/membership"

SCREENER_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRAgh9VdS0Ox8xrDf8XYCslQwCNuKfVRwJ9329YkEE7Fn5BtW4bkLrts19MnNjjkHbnp6twVB99Z21I/pub?gid=310948557&single=true&output=csv"
TOP10_CSV    = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRAgh9VdS0Ox8xrDf8XYCslQwCNuKfVRwJ9329YkEE7Fn5BtW4bkLrts19MnNjjkHbnp6twVB99Z21I/pub?gid=1532740227&single=true&output=csv"

# ─────────────────────────────────────────────────────────────────────
def fetch_csv(url):
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            return list(csv.reader(io.StringIO(r.text)))
        except Exception as e:
            if attempt == 2: raise
            print(f"  Retry {attempt+1}/3 after error: {e}")
            import time; time.sleep(5)

def parse_screener(rows):
    hi = next((i for i,r in enumerate(rows) if any("Ticker" in str(c) for c in r)), None)
    if hi is None: return []
    headers = [c.strip() for c in rows[hi]]
    out = []
    for row in rows[hi+1:]:
        if len(row)<5: continue
        d = {headers[j]: row[j].strip() if j<len(row) else "" for j in range(len(headers))}
        tk = d.get("Ticker","").strip()
        if tk and tk != "#": out.append(d)
    return out

def parse_top10(rows):
    hi = next((i for i,r in enumerate(rows) if any("Ticker" in str(c) for c in r)), None)
    if hi is None: return []
    headers = [c.strip() for c in rows[hi]]
    out = []
    for row in rows[hi+1:]:
        if len(row)<3: continue
        d = {headers[j]: row[j].strip() if j<len(row) else "" for j in range(len(headers))}
        tk = re.sub(r'[^A-Z0-9]', '', d.get("Ticker","").upper()).strip()
        if tk and "no stock" not in tk.lower():
            d["Ticker"] = tk; out.append(d)
    return out[:10]

SC = {
    "Technology":"#2563eb","Communication Services":"#7c3aed","Healthcare":"#059669",
    "Financials":"#d97706","Consumer Cyclical":"#ea580c","Consumer Defensive":"#65a30d",
    "Industrials":"#4f46e5","Energy":"#dc2626","Real Estate":"#0891b2",
    "Basic Materials":"#92400e","Utilities":"#0284c7","Insurance":"#b45309"
}
def sc(s): return SC.get(s,"#64748b")

def clean_signals(raw):
    if not raw: return ""
    raw = re.sub(r'[^\x00-\x7F]', ' ', raw)
    raw = re.sub(r'\s*\|\s*', '|', raw.strip())
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    out = []
    for p in parts:
        if not p: continue
        if "Pass" in p or "PASS" in p:
            out.append('<span class="sb-pass">PASS ALL</span>')
        elif "Graham" in p and "~" not in p:
            out.append('<span class="sb-g">Graham &#10003;</span>')
        elif "Graham" in p:
            out.append('<span class="sb-gn">Graham ~</span>')
        elif "Lynch" in p and "~" not in p:
            out.append('<span class="sb-l">Lynch &#10003;</span>')
        elif "Lynch" in p:
            out.append('<span class="sb-ln">Lynch ~</span>')
        elif "Buffett" in p and "~" not in p:
            out.append('<span class="sb-b">Buffett &#10003;</span>')
        elif "Buffett" in p:
            out.append('<span class="sb-bn">Buffett ~</span>')
    return " ".join(out) if out else ""

def sig(v):
    v = v.strip()
    if v == "Candidate": return '<span class="sig sg">&#10003;</span>'
    if v == "Near Miss":  return '<span class="sig sn">~</span>'
    if v == "PASS":       return '<span class="sig sp">PASS</span>'
    if v == "FAIL":       return '<span class="sig sf">&#8212;</span>'
    return '<span class="s0">&#8212;</span>'

def mos(v):
    v = v.strip()
    return f'<span class="mos-v">{v}</span>' if v and v != "-" else '<span class="na">&#8212;</span>'

def pct(v):
    try:
        f = float(v.strip().replace("%",""))
        return f'<span class="{"pos" if f>0 else "neg"}">{f:+.1f}%</span>'
    except: return '<span class="na">&#8212;</span>'

def num(v, d=1):
    try: return f"{float(v.strip().replace('%','')):.{d}f}"
    except: return "&#8212;"

# ─────────────────────────────────────────────────────────────────────
def build_html(stocks, top10, updated_at):
    sectors   = sorted(set(s.get("Sector","").strip() for s in stocks if s.get("Sector","").strip()))
    n_total   = len(stocks)
    n_graham  = sum(1 for s in stocks if s.get("Graham Screen")=="Candidate")
    n_lynch   = sum(1 for s in stocks if s.get("Lynch Screen")=="Candidate")
    n_buffett = sum(1 for s in stocks if s.get("Buffett Screen")=="Candidate")
    n_pass    = sum(1 for s in stocks if s.get("Pass All?")=="PASS")

    # TOP 10
    t10_html = ""
    if top10:
        t = top10[0]
        tk=t.get("Ticker",""); co=t.get("Company",""); sec=t.get("Sector","")
        sigs_raw=t.get("Signals",""); score=t.get("Score",""); mos_v=t.get("Margin of Safety","—")
        c=sc(sec); sigs_html=clean_signals(sigs_raw)
        t10_html += f"""<div class="t10-featured">
  <div class="t10f-left">
    <div class="t10f-badge">&#127942; #1 This Week</div>
    <div class="t10f-ticker">{tk}</div>
    <div class="t10f-company">{co}</div>
    <div class="t10f-sec" style="background:{c}18;color:{c}">{sec}</div>
  </div>
  <div class="t10f-right">
    <div class="t10f-sigs">{sigs_html}</div>
    <div class="t10f-meta">
      <span class="t10f-score">{score}</span>
      <span class="t10f-mos">{mos_v}</span>
    </div>
  </div>
</div>"""
        t10_html += '<div class="t10-rest">'
        for i, t in enumerate(top10[1:], 2):
            tk2=re.sub(r"[^A-Z0-9]","",t.get("Ticker","").encode("ascii","ignore").decode("ascii").upper())
            co2=t.get("Company","")[:20]; sec2=t.get("Sector",""); score2=t.get("Score","")
            sigs2=clean_signals(t.get("Signals","")); c2=sc(sec2)
            blur=" t10r-locked" if i>=3 else ""
            t10_html += (
                f'<div class="t10r-row{blur}">'
                f'<span class="t10r-rank">#{i}</span>'
                f'<span class="t10r-tk">{tk2}</span>'
                f'<span class="t10r-co">{co2}</span>'
                f'<span class="t10r-sec" style="background:{c2}18;color:{c2}">{sec2}</span>'
                f'<span class="t10r-sigs">{sigs2}</span>'
                f'<span class="t10r-score">{score2}</span>'
                f'</div>'
            )
        t10_html += '</div>'

    # SECTOR PILLS
    pills = '<button class="chip on" onclick="fSec(this,\'\')" style="--cc:#374151">All</button>'
    for sec in sectors:
        c=sc(sec)
        pills += f'<button class="chip" onclick="fSec(this,\'{sec}\')" style="--cc:{c}">{sec}</button>'

    # TABLE ROWS
    rows_html = ""
    for i, s in enumerate(stocks):
        tk=s.get("Ticker",""); co=s.get("Company",""); sec=s.get("Sector","")
        pe=s.get("P/E (Live)",""); peg=s.get("PEG (Live)",""); de=s.get("Debt/Equity","")
        roic=s.get("ROIC",""); gr=s.get("Graham Screen",""); ly=s.get("Lynch Screen","")
        bu=s.get("Buffett Screen",""); pa=s.get("Pass All?",""); ms=s.get("Margin of Safety","")
        rg=s.get("Rev Gr%",""); eg=s.get("EPS Growth",""); om=s.get("Op. Margin","")
        c=sc(sec)
        dg="true" if gr=="Candidate" else "false"
        dl="true" if ly=="Candidate" else "false"
        db="true" if bu=="Candidate" else "false"
        dp="true" if pa=="PASS" else "false"
        da="true" if (gr in("Candidate","Near Miss") or ly in("Candidate","Near Miss")
                      or bu in("Candidate","Near Miss") or pa=="PASS") else "false"
        rows_html += (
            f'<tr class="sr" data-idx="{i}" data-tk="{tk.lower()}" data-co="{co.lower()}" '
            f'data-sec="{sec}" data-g="{dg}" data-l="{dl}" data-b="{db}" data-p="{dp}" data-a="{da}">'
            f'<td class="tds"><span class="stk">{tk}</span><span class="sco">{co[:24]}</span></td>'
            f'<td><span style="background:{c}15;color:{c};font-size:9px;font-weight:700;'
            f'padding:2px 5px;border-radius:2px;white-space:nowrap">{sec}</span></td>'
            f'<td class="tn">{num(pe)}</td><td class="tn">{num(peg,2)}</td>'
            f'<td class="tn">{num(de,2)}</td><td class="tn">{num(roic,1)}%</td>'
            f'<td>{sig(gr)}</td><td>{sig(ly)}</td><td>{sig(bu)}</td><td>{sig(pa)}</td>'
            f'<td>{mos(ms)}</td><td class="tn">{pct(rg)}</td>'
            f'<td class="tn">{pct(eg)}</td><td class="tn">{num(om,1)}%</td></tr>'
        )

    schema = {
        "@context":"https://schema.org","@type":"WebPage",
        "name":"S&P 500 Value Stock Screener — Graham, Lynch & Buffett | Alert Invest",
        "description":f"Screen {n_total} S&P 500 stocks using Graham, Lynch and Buffett criteria.",
        "url":f"{WP_URL}/stock-screener/","dateModified":updated_at,
        "publisher":{"@type":"Organization","name":"Alert Invest","url":WP_URL}
    }

    CSS = """*{box-sizing:border-box;margin:0;padding:0}
.entry-title,.page-title,h1.title{display:none!important}
.scr{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,sans-serif;font-size:12px;color:#111827;background:#eef0f3;min-height:100vh;padding:10px}
.scr a{color:#1d4ed8;text-decoration:none}.scr a:hover{text-decoration:underline}
.tb{background:#fff;border:1px solid #d1d5db;border-radius:5px;padding:9px 14px;margin-bottom:7px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}
.tbb{font-size:14px;font-weight:800;color:#0f172a;letter-spacing:-.4px}.tbb em{color:#2563eb;font-style:normal}
.tbst{display:flex;gap:1px;background:#e5e7eb;border-radius:4px;overflow:hidden}
.tbsi{padding:5px 14px;background:#fff;display:flex;flex-direction:column;align-items:center;gap:1px}
.tbn{font-size:15px;font-weight:800;color:#111827;line-height:1}
.tbl{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:#6b7280}
.tbn.g{color:#16a34a}.tbn.b{color:#2563eb}.tbn.p{color:#7c3aed}.tbn.y{color:#d97706}
.tbu{font-size:10px;color:#9ca3af;border:1px solid #e5e7eb;border-radius:3px;padding:3px 8px}
/* AUTH BAR */
.auth-bar{background:#fff;border:1px solid #d1d5db;border-radius:5px;padding:9px 14px;margin-bottom:7px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-height:42px}
.tier-badge{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;padding:2px 8px;border-radius:2px;white-space:nowrap}
.tier-anon{background:#f3f4f6;color:#6b7280}
.tier-google{background:#dbeafe;color:#1d4ed8}
.tier-patreon{background:#dcfce7;color:#15803d}
.auth-name{font-size:11px;color:#374151;font-weight:600}
.auth-nudge{font-size:10px;color:#6b7280}
.auth-nudge strong{color:#111827}
.auth-nudge a{color:#e85b46;font-weight:700}
.auth-actions{margin-left:auto;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.btn-google{display:inline-flex;align-items:center;gap:6px;background:#fff;color:#374151;border:1px solid #d1d5db;border-radius:3px;padding:5px 12px;font-size:11px;font-weight:600;cursor:pointer;font-family:inherit;white-space:nowrap}
.btn-google:hover{background:#f9fafb}
.btn-patreon{display:inline-flex;align-items:center;gap:6px;background:#e85b46;color:#fff;border:none;border-radius:3px;padding:5px 12px;font-size:11px;font-weight:700;cursor:pointer;font-family:inherit;white-space:nowrap}
.btn-signout{background:none;border:none;font-size:10px;color:#9ca3af;cursor:pointer;font-family:inherit;padding:2px 0}
.btn-signout:hover{color:#374151}
/* FILTERS */
.fb{background:#fff;border:1px solid #d1d5db;border-radius:5px;padding:8px 12px;margin-bottom:7px}
.fr{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.fr+.fr{margin-top:6px;padding-top:6px;border-top:1px solid #f3f4f6}
.fl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#9ca3af;min-width:60px}
.chip{display:inline-flex;align-items:center;padding:3px 9px;border-radius:3px;border:1px solid #d1d5db;background:#fff;font-size:11px;font-weight:600;color:#374151;cursor:pointer;transition:all .1s;white-space:nowrap;line-height:1.5;font-family:inherit}
.chip:hover{border-color:var(--cc,#374151);color:var(--cc,#374151)}
.chip.on{background:var(--cc,#374151);border-color:var(--cc,#374151);color:#fff}
.sw{flex:1;min-width:160px;max-width:260px;position:relative}
.si{width:100%;padding:4px 8px 4px 24px;border:1px solid #d1d5db;border-radius:3px;font-size:11px;color:#374151;outline:none;font-family:inherit}
.si:focus{border-color:#2563eb;box-shadow:0 0 0 2px #dbeafe}
.sic{position:absolute;left:7px;top:50%;transform:translateY(-50%);color:#9ca3af;pointer-events:none;font-size:11px}
.rc{font-size:11px;color:#6b7280;margin-left:auto;white-space:nowrap}
/* TOP 10 */
.t10-wrap{background:#fff;border:1px solid #d1d5db;border-radius:5px;overflow:hidden;margin-bottom:7px}
.t10-hdr{background:#0f172a;padding:7px 12px;display:flex;align-items:center;gap:10px}
.t10-hdr-t{font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:.05em}
.t10-hdr-s{font-size:10px;color:rgba(255,255,255,.4)}
.t10-featured{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:14px 16px;border-bottom:2px solid #e5e7eb;background:linear-gradient(135deg,#f8fafc,#fff)}
.t10f-left{display:flex;flex-direction:column;gap:5px}
.t10f-badge{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#d97706;background:#fef3c7;padding:2px 8px;border-radius:2px;display:inline-block;width:fit-content}
.t10f-ticker{font-size:24px;font-weight:900;color:#0f172a;letter-spacing:-.5px;line-height:1}
.t10f-company{font-size:12px;color:#6b7280;margin-top:1px}
.t10f-sec{display:inline-block;font-size:10px;font-weight:700;padding:2px 8px;border-radius:3px;margin-top:4px}
.t10f-right{display:flex;flex-direction:column;align-items:flex-end;gap:8px}
.t10f-sigs{display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end}
.t10f-meta{display:flex;align-items:center;gap:10px}
.t10f-score{font-size:13px;font-weight:800;color:#15803d;background:#f0fdf4;border:1px solid #bbf7d0;padding:3px 10px;border-radius:3px}
.t10f-mos{font-size:11px;font-weight:700;color:#2563eb}
.sb-pass{background:#dbeafe;color:#1d4ed8;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.sb-g{background:#dcfce7;color:#15803d;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.sb-gn{background:#fef9c3;color:#92400e;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.sb-l{background:#dbeafe;color:#1d4ed8;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.sb-ln{background:#fef9c3;color:#92400e;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.sb-b{background:#f3e8ff;color:#7c3aed;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.sb-bn{background:#fef9c3;color:#92400e;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.t10-rest{display:flex;flex-direction:column}
.t10r-row{display:flex;align-items:center;gap:8px;padding:6px 16px;border-bottom:1px solid #f3f4f6;transition:background .1s}
.t10r-row:last-child{border-bottom:none}
.t10r-row:hover{background:#f8fafc}
.t10r-rank{font-size:10px;font-weight:700;color:#9ca3af;min-width:24px}
.t10r-tk{font-size:12px;font-weight:800;color:#1d4ed8;min-width:50px}
.t10r-co{font-size:11px;color:#6b7280;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.t10r-sec{font-size:9px;font-weight:700;padding:1px 5px;border-radius:2px;white-space:nowrap}
.t10r-sigs{display:flex;gap:3px;flex-wrap:wrap}
.t10r-score{font-size:10px;font-weight:700;color:#15803d;margin-left:auto;white-space:nowrap}
.t10r-locked{filter:blur(4px);user-select:none;pointer-events:none;opacity:.6}
/* TABLE */
.tw{background:#fff;border:1px solid #d1d5db;border-radius:5px;overflow:hidden}
.tbar{padding:6px 12px;border-bottom:1px solid #e5e7eb;background:#f9fafb;display:flex;align-items:center;justify-content:space-between}
.tbrt{font-size:11px;font-weight:700;color:#374151}.tbrm{font-size:10px;color:#9ca3af}
.tsc{overflow-x:auto}
table.t{width:100%;border-collapse:collapse;font-size:11px}
table.t thead th{padding:5px 8px;background:#f9fafb;border-bottom:2px solid #e5e7eb;text-align:left;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;white-space:nowrap;position:sticky;top:0;z-index:2}
table.t thead th.tn{text-align:right}
table.t thead th:hover{color:#2563eb;background:#eff6ff;cursor:pointer}
table.t tbody td{padding:4px 8px;border-bottom:1px solid #f3f4f6;vertical-align:middle}
table.t tbody tr:hover td{background:#f8fafc!important}
table.t tbody tr:nth-child(even) td{background:#fafafa}
.tds{min-width:130px}.stk{font-size:11px;font-weight:800;color:#1d4ed8;display:block}.sco{font-size:10px;color:#9ca3af;display:block}
.tn{text-align:right;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:#374151}
.pos{color:#15803d;font-weight:700}.neg{color:#b91c1c;font-weight:700}.na{color:#e5e7eb}
.sig{display:inline-flex;align-items:center;font-size:10px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.sg{background:#dcfce7;color:#15803d}.sn{background:#fef9c3;color:#92400e}
.sp{background:#dbeafe;color:#1d4ed8}.sf{background:#f3f4f6;color:#d1d5db}.s0{color:#e5e7eb}
.mos-v{font-size:10px;font-weight:700;color:#2563eb}
/* PAYWALL */
.pw-row td{padding:0}
.pw-gradient{background:linear-gradient(to bottom,rgba(255,255,255,0) 0%,#fff 60%);height:50px}
.pw-box{background:#fff;padding:28px 20px;text-align:center;border-top:2px solid #e5e7eb}
.pw-icon{font-size:20px;margin-bottom:8px}
.pw-title{font-size:15px;font-weight:800;color:#0f172a;margin-bottom:6px}
.pw-sub{font-size:12px;color:#6b7280;line-height:1.6;margin-bottom:16px}
.pw-btns{display:flex;flex-direction:column;align-items:center;gap:8px}
.pw-note{font-size:10px;color:#9ca3af;margin-top:10px}
/* FAQ */
.faq{margin-top:8px;background:#fff;border:1px solid #d1d5db;border-radius:5px;overflow:hidden}
.faqh{padding:7px 12px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:10px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:.05em}
.faqi{border-bottom:1px solid #f3f4f6}.faqi:last-child{border:none}
.faqq{padding:9px 12px;font-size:12px;font-weight:600;color:#374151;cursor:pointer;display:flex;justify-content:space-between;align-items:center}
.faqq:hover{background:#f8fafc;color:#2563eb}
.faqch{font-size:9px;color:#9ca3af;transition:transform .2s}
.faqa{max-height:0;overflow:hidden;transition:max-height .25s,opacity .25s;opacity:0}
.faqa.open{opacity:1}.faqai{padding:4px 12px 10px;font-size:11px;line-height:1.75;color:#6b7280}
.disc{font-size:10px;color:#9ca3af;margin-top:8px;text-align:center;line-height:1.65;padding:6px}
@media(max-width:900px){table.t th:nth-child(n+9),table.t td:nth-child(n+9){display:none}}
@media(max-width:600px){.t10-featured{flex-direction:column;align-items:flex-start}.t10f-right{align-items:flex-start}table.t th:nth-child(n+6),table.t td:nth-child(n+6){display:none}.auth-actions{margin-left:0}}"""

    GOOGLE_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" xmlns="http://www.w3.org/2000/svg"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>'

    JS = """
// ── FIREBASE CONFIG — replace with your values ────────────────────────
var FB_CFG = {
  apiKey: "AIzaSyBnz1S5v4FYX7fYo6RF42E4ALmpvtpEu9M",
  authDomain: "saas-portfolio-6bbc8.firebaseapp.com",
  projectId: "saas-portfolio-6bbc8",
  storageBucket: "saas-portfolio-6bbc8.firebasestorage.app",
  messagingSenderId: "124296076295",
  appId: "1:124296076295:web:32ee053bb6e98fea455ea2",
  measurementId: "G-D5QC7Z17PV"
};

// ── CONSTANTS ─────────────────────────────────────────────────────────
var PATREON_CLIENT_ID = '""" + PATREON_CLIENT_ID + """';
var PATREON_REDIRECT  = '""" + PATREON_REDIRECT + """';
var PATREON_JOIN_URL  = '""" + PATREON_JOIN_URL + """';
var FREE_ROWS         = """ + str(FREE_ROWS) + """;
var GOOGLE_ROWS       = """ + str(GOOGLE_ROWS) + """;
var N_TOTAL           = """ + str(n_total) + """;
var PAGE_SIZE         = 50;

// ── STATE ─────────────────────────────────────────────────────────────
var AUTH_LEVEL  = 'anon';  // 'anon' | 'google' | 'patreon'
var FB_USER     = null;
var visibleUpTo = PAGE_SIZE;
var gP='all', gS='', gQ='';

// ── FIREBASE ──────────────────────────────────────────────────────────
function initFirebase() {
  if (typeof firebase === 'undefined') { updateAuthUI(); initTable(); return; }
  if (!firebase.apps.length) firebase.initializeApp(FB_CFG);
  var auth = firebase.auth();
  auth.onAuthStateChanged(function(user) {
    FB_USER = user;
    if (user && AUTH_LEVEL !== 'patreon') {
      AUTH_LEVEL = 'google';
      saveLocalGoogle(user);
      writeUserToFirestore(user);
    } else if (!user && AUTH_LEVEL === 'google') {
      AUTH_LEVEL = 'anon';
    }
    updateAuthUI();
    initTable();
  });
}

function googleLogin() {
  if (typeof firebase === 'undefined') return;
  var provider = new firebase.auth.GoogleAuthProvider();
  provider.addScope('email');
  firebase.auth().signInWithPopup(provider).catch(function(e) {
    console.error('Google login error:', e.message);
  });
}

function googleLogout() {
  if (typeof firebase === 'undefined') return;
  firebase.auth().signOut().then(function() {
    localStorage.removeItem('ai_gu');
    FB_USER    = null;
    AUTH_LEVEL = checkPatreonLocal() ? 'patreon' : 'anon';
    updateAuthUI();
    initTable();
  });
}

function writeUserToFirestore(user) {
  if (typeof firebase === 'undefined' || !firebase.firestore) return;
  var db = firebase.firestore();
  db.collection('screener_users').doc(user.uid).set({
    uid:       user.uid,
    email:     user.email,
    name:      user.displayName || '',
    photo:     user.photoURL    || '',
    lastSeen:  firebase.firestore.FieldValue.serverTimestamp(),
    firstSeen: firebase.firestore.FieldValue.serverTimestamp(),
    source:    'screener',
    level:     'google'
  }, { merge: true });
  // merge:true ensures firstSeen is only written on first login
  // lastSeen updates on every login — use this to track activity
}

// ── LOCAL SESSION HELPERS ─────────────────────────────────────────────
function saveLocalGoogle(user) {
  localStorage.setItem('ai_gu', JSON.stringify({
    email: user.email,
    name:  user.displayName,
    exp:   Date.now() + 8*60*60*1000
  }));
}

function checkLocalGoogle() {
  try {
    var d = JSON.parse(localStorage.getItem('ai_gu') || 'null');
    return d && Date.now() < d.exp;
  } catch(e) { return false; }
}

function saveLocalPatreon(name) {
  localStorage.setItem('ai_pm', JSON.stringify({
    name: name,
    exp:  Date.now() + 8*60*60*1000
  }));
}

function checkPatreonLocal() {
  try {
    var d = JSON.parse(localStorage.getItem('ai_pm') || 'null');
    return d && Date.now() < d.exp;
  } catch(e) { return false; }
}

function getPatreonName() {
  try { return JSON.parse(localStorage.getItem('ai_pm')).name || 'Member'; }
  catch(e) { return 'Member'; }
}

function getGoogleName() {
  try { return JSON.parse(localStorage.getItem('ai_gu')).name || 'User'; }
  catch(e) { return FB_USER ? (FB_USER.displayName || FB_USER.email) : 'User'; }
}

// ── PATREON ───────────────────────────────────────────────────────────
function patreonLogin() {
  var state = Math.random().toString(36).substring(2);
  localStorage.setItem('pt_state', state);
  window.location.href = 'https://www.patreon.com/oauth2/authorize'
    + '?response_type=code'
    + '&client_id=' + PATREON_CLIENT_ID
    + '&redirect_uri=' + encodeURIComponent(PATREON_REDIRECT)
    + '&scope=' + encodeURIComponent('identity identity[email] identity.memberships')
    + '&state=' + state;
}

function patreonLogout() {
  localStorage.removeItem('ai_pm');
  AUTH_LEVEL = FB_USER ? 'google' : (checkLocalGoogle() ? 'google' : 'anon');
  updateAuthUI();
  initTable();
}

function handleStreamlitCallback() {
  var p = new URLSearchParams(window.location.search);
  var member = p.get('member');
  if (!member) return false;
  if (member === '1') {
    AUTH_LEVEL = 'patreon';
    saveLocalPatreon(p.get('name') || 'Member');
    // Also update Firestore if Google user is signed in
    if (FB_USER) {
      if (typeof firebase !== 'undefined' && firebase.firestore) {
        firebase.firestore().collection('screener_users').doc(FB_USER.uid).set(
          { level: 'patreon', patreonUpgraded: firebase.firestore.FieldValue.serverTimestamp() },
          { merge: true }
        );
      }
    }
  } else if (member === '0') {
    showNotPatreonMember();
  }
  window.history.replaceState({}, '', PATREON_REDIRECT);
  return true;
}

function handleOAuthCallback() {
  var p = new URLSearchParams(window.location.search);
  var code = p.get('code');
  if (!code) return false;
  window.location.href = 'https://alert-invest-portfolio-tool.streamlit.app/'
    + '?screener_code=' + encodeURIComponent(code)
    + '&screener_redirect=' + encodeURIComponent(PATREON_REDIRECT)
    + '&state=' + encodeURIComponent(p.get('state') || '');
  return true;
}

// ── AUTH UI ───────────────────────────────────────────────────────────
var GSVG = '""" + GOOGLE_SVG.replace("'", "\\'") + """';

function updateAuthUI() {
  var bar = document.getElementById('auth-bar');
  if (!bar) return;
  var left='', right='';

  if (AUTH_LEVEL === 'patreon') {
    var n = getPatreonName();
    left  = '<span class="tier-badge tier-patreon">&#10003; Portfolio Builder</span>'
           +'<span class="auth-name">'+n+'</span>';
    right = '<button class="btn-signout" onclick="patreonLogout()">Sign out</button>';

  } else if (AUTH_LEVEL === 'google') {
    var n = getGoogleName();
    left  = '<span class="tier-badge tier-google">&#10003; Google</span>'
           +'<span class="auth-name">'+n+'</span>'
           +'<span style="color:#e5e7eb">|</span>'
           +'<span class="auth-nudge">Seeing <strong>'+GOOGLE_ROWS+' of '+N_TOTAL+' stocks</strong>'
           +' &mdash; <a href="'+PATREON_JOIN_URL+'" target="_blank">Unlock all with Patreon &rarr;</a></span>';
    right = '<button class="btn-patreon" onclick="patreonLogin()">&#128994; Connect Patreon</button>'
           +'<button class="btn-signout" onclick="googleLogout()">Sign out</button>';

  } else {
    left  = '<span class="tier-badge tier-anon">Free</span>'
           +'<span class="auth-nudge">Seeing <strong>'+FREE_ROWS+' of '+N_TOTAL+' stocks</strong>'
           +' &mdash; sign in for more</span>';
    right = '<button class="btn-google" onclick="googleLogin()">'+GSVG+' Sign in with Google</button>'
           +'<button class="btn-patreon" onclick="patreonLogin()">&#128994; Connect Patreon</button>';
  }

  bar.innerHTML = '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">'+left+'</div>'
                + '<div class="auth-actions">'+right+'</div>';
}

function showNotPatreonMember() {
  var bar = document.getElementById('auth-bar');
  if (!bar) return;
  bar.innerHTML = '<span style="color:#b91c1c;font-size:11px;font-weight:600">'
    +'&#10007; Patreon account is not a Portfolio Builder member.</span>'
    +' <a href="'+PATREON_JOIN_URL+'" target="_blank" style="font-size:11px;font-weight:700;color:#2563eb">Upgrade &rarr;</a>';
}

// ── TABLE ─────────────────────────────────────────────────────────────
function rowLimit() {
  if (AUTH_LEVEL === 'patreon') return Infinity;
  if (AUTH_LEVEL === 'google')  return GOOGLE_ROWS;
  return FREE_ROWS;
}

function initTable() { renderRows(); renderPaywall(); updateCount(); }

function renderRows() {
  var limit = rowLimit();
  var allRows = document.querySelectorAll('#tbody .sr');
  allRows.forEach(function(r) {
    var idx   = parseInt(r.dataset.idx);
    var authOk = idx < limit;
    var pageOk = (AUTH_LEVEL === 'patreon') ? idx < visibleUpTo : true;
    r.style.display = (authOk && pageOk) ? '' : 'none';
  });
  var btn = document.getElementById('load-more-btn');
  if (btn) {
    var total = allRows.length;
    btn.style.display = (AUTH_LEVEL === 'patreon' && visibleUpTo < total) ? '' : 'none';
    btn.textContent = 'Show next 50 ('+ Math.min(visibleUpTo+PAGE_SIZE, total) +' of '+total+' total)';
  }
}

function loadMore() { visibleUpTo += PAGE_SIZE; renderRows(); updateCount(); }

function updateCount() {
  var shown = 0;
  document.querySelectorAll('#tbody .sr').forEach(function(r){
    if (r.style.display !== 'none') shown++;
  });
  var el = document.getElementById('rcnt');
  if (el) el.textContent = shown + ' result' + (shown!==1?'s':'');
}

function renderPaywall() {
  var old = document.getElementById('inline-pw');
  if (old) old.remove();
  if (AUTH_LEVEL === 'patreon') return;

  var allRows = document.querySelectorAll('#tbody .sr');
  var last = null;
  allRows.forEach(function(r){ if (r.style.display!=='none') last=r; });
  if (!last) return;

  var isGoogle  = AUTH_LEVEL === 'google';
  var seenCount = isGoogle ? GOOGLE_ROWS : FREE_ROWS;
  var icon      = isGoogle ? '&#128274;' : '&#128270;';
  var title     = isGoogle ? 'Unlock the Full Screener' : 'See More — Free';
  var sub       = isGoogle
    ? 'You have access to <strong>'+seenCount+' of '+N_TOTAL+' stocks</strong>.<br>Join Patreon Portfolio Builder for full access.'
    : 'You\'re seeing <strong>'+seenCount+' of '+N_TOTAL+' stocks</strong>.<br>'
      +'Sign in with Google to unlock <strong>'+GOOGLE_ROWS+' stocks free</strong>, or join Patreon for everything.';

  var googleBtn = !isGoogle
    ? '<button onclick="googleLogin()" class="btn-google" style="width:260px;justify-content:center;padding:10px 0;font-size:12px">'
      +GSVG+' Sign in with Google &mdash; free</button>'
    : '';

  var pw = document.createElement('tr');
  pw.id = 'inline-pw';
  pw.className = 'pw-row';
  pw.innerHTML = '<td colspan="14">'
    +'<div class="pw-gradient"></div>'
    +'<div class="pw-box">'
    +'<div class="pw-icon">'+icon+'</div>'
    +'<div class="pw-title">'+title+'</div>'
    +'<div class="pw-sub">'+sub+'</div>'
    +'<div class="pw-btns">'
    +googleBtn
    +'<button onclick="patreonLogin()" class="btn-patreon" style="width:260px;justify-content:center;padding:10px 0;font-size:12px">'
    +'&#128994; Connect Patreon &mdash; full access</button>'
    +'</div>'
    +'<div class="pw-note">Portfolio Builder on Patreon &middot; Cancel anytime</div>'
    +'</div></td>';
  last.insertAdjacentElement('afterend', pw);
}

function apply() {
  var limit = rowLimit();
  document.querySelectorAll('#tbody .sr').forEach(function(r) {
    var idx    = parseInt(r.dataset.idx);
    var philOk = true;
    if      (gP==='g'&&r.dataset.g!=='true') philOk=false;
    else if (gP==='l'&&r.dataset.l!=='true') philOk=false;
    else if (gP==='b'&&r.dataset.b!=='true') philOk=false;
    else if (gP==='p'&&r.dataset.p!=='true') philOk=false;
    else if (gP==='a'&&r.dataset.a!=='true') philOk=false;
    var secOk  = !gS || r.dataset.sec===gS;
    var srchOk = !gQ || r.dataset.tk.indexOf(gQ)!==-1 || r.dataset.co.indexOf(gQ)!==-1;
    var authOk = idx < limit;
    var pageOk = (AUTH_LEVEL==='patreon') ? idx < visibleUpTo : true;
    var searching = gP!=='all'||gS!==''||gQ!=='';
    if (searching && AUTH_LEVEL==='patreon') pageOk=true;
    r.style.display = (philOk&&secOk&&srchOk&&authOk&&pageOk) ? '' : 'none';
  });
  updateCount();
  renderPaywall();
}

function fPhil(b,v){gP=v;document.querySelectorAll('.chip[onclick*="fPhil"]').forEach(function(x){x.classList.remove('on')});b.classList.add('on');apply();}
function fSec(b,v){gS=v;document.querySelectorAll('.chip[onclick*="fSec"]').forEach(function(x){x.classList.remove('on')});b.classList.add('on');apply();}
function fSrch(v){gQ=v.toLowerCase().trim();apply();}
function fFaq(q){var a=q.nextElementSibling,ch=q.querySelector('.faqch'),open=a.classList.contains('open');a.classList.toggle('open',!open);ch.style.transform=open?'':'rotate(180deg)';a.style.maxHeight=open?'0':(a.scrollHeight+20)+'px';}

// ── BOOT ──────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', function() {
  // 1. Handle Patreon / Streamlit callback
  var wasCallback = handleStreamlitCallback() || handleOAuthCallback();
  if (wasCallback && window.location.href !== PATREON_REDIRECT) return;

  // 2. Restore auth level from localStorage
  if (!wasCallback) {
    if      (checkPatreonLocal()) AUTH_LEVEL = 'patreon';
    else if (checkLocalGoogle())  AUTH_LEVEL = 'google';
  }

  // 3. Init Firebase — onAuthStateChanged takes over from here
  initFirebase();
});
"""

    _html_before = f"""<!-- wp:html -->
<script type="application/ld+json">{json.dumps(schema)}</script>
<style>{CSS}</style>
<!-- /wp:html -->

<!-- wp:html -->
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-auth-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-firestore-compat.js"></script>
<div class="scr">

<div class="tb">
  <div class="tbb">Alert<em>Invest</em> <span style="font-size:11px;font-weight:400;color:#6b7280">/ S&amp;P 500 Screener</span></div>
  <div class="tbst">
    <div class="tbsi"><span class="tbn">{n_total}</span><span class="tbl">Stocks</span></div>
    <div class="tbsi"><span class="tbn g">{n_graham}</span><span class="tbl">Graham</span></div>
    <div class="tbsi"><span class="tbn b">{n_lynch}</span><span class="tbl">Lynch</span></div>
    <div class="tbsi"><span class="tbn p">{n_buffett}</span><span class="tbl">Buffett</span></div>
    <div class="tbsi"><span class="tbn y">{n_pass}</span><span class="tbl">Pass All</span></div>
  </div>
  <div class="tbu">Updated {updated_at}</div>
</div>

<div class="auth-bar" id="auth-bar">
  <div style="display:flex;align-items:center;gap:8px">
    <span class="tier-badge tier-anon">Free</span>
    <span class="auth-nudge">Loading&hellip;</span>
  </div>
</div>

<div class="fb">
  <div class="fr">
    <span class="fl">Screen</span>
    <button class="chip on" onclick="fPhil(this,'all')" style="--cc:#374151">All</button>
    <button class="chip" onclick="fPhil(this,'g')" style="--cc:#16a34a">Graham</button>
    <button class="chip" onclick="fPhil(this,'l')" style="--cc:#2563eb">Lynch</button>
    <button class="chip" onclick="fPhil(this,'b')" style="--cc:#7c3aed">Buffett</button>
    <button class="chip" onclick="fPhil(this,'p')" style="--cc:#d97706">Pass All</button>
    <button class="chip" onclick="fPhil(this,'a')" style="--cc:#ea580c">Any Signal</button>
    <div class="sw"><span class="sic">&#128269;</span><input class="si" id="srch" placeholder="Search ticker or company&hellip;" oninput="fSrch(this.value)"></div>
    <span class="rc" id="rcnt">{n_total} results</span>
  </div>
  <div class="fr">
    <span class="fl">Sector</span>
    {pills}
  </div>
</div>

<div class="t10-wrap">
  <div class="t10-hdr">
    <span class="t10-hdr-t">Top 10 This Week</span>
    <span class="t10-hdr-s">Ranked by combined Graham + Lynch + Buffett score</span>
  </div>
  {t10_html}
</div>

<div class="tw">
  <div class="tbar">
    <span class="tbrt">S&amp;P 500 Value Screener &mdash; {n_total} Stocks</span>
    <span class="tbrm">P/E &middot; PEG &middot; D/E &middot; ROIC &middot; Graham &middot; Lynch &middot; Buffett &middot; MoS &middot; Rev Gr &middot; EPS Gr &middot; Op Mar</span>
  </div>
  <div class="tsc">
  <table class="t">
    <thead><tr>
      <th>Stock</th><th>Sector</th>
      <th class="tn" title="P/E TTM">P/E</th>
      <th class="tn" title="PEG Ratio">PEG</th>
      <th class="tn" title="Debt/Equity">D/E</th>
      <th class="tn" title="Return on Invested Capital">ROIC</th>
      <th title="Graham screen">Graham</th>
      <th title="Lynch GARP">Lynch</th>
      <th title="Buffett quality">Buffett</th>
      <th title="Pass All criteria">Pass All</th>
      <th title="Margin of Safety">MoS</th>
      <th class="tn" title="Revenue Growth YoY">Rev Gr</th>
      <th class="tn" title="EPS Growth">EPS Gr</th>
      <th class="tn" title="Operating Margin">Op Mar</th>
    </tr></thead>
    <tbody id="tbody">{rows_html}</tbody>
  </table>
  </div>
</div>

<div id="load-more-wrap" style="text-align:center;padding:12px;background:#fff;border:1px solid #d1d5db;border-top:none;border-radius:0 0 5px 5px;margin-top:-7px;margin-bottom:7px">
  <button id="load-more-btn" onclick="loadMore()" style="display:none;background:#f9fafb;border:1px solid #d1d5db;border-radius:3px;padding:7px 20px;font-size:11px;font-weight:600;color:#374151;cursor:pointer;font-family:inherit">Show next 50</button>
</div>

<div class="faq">
  <div class="faqh">How the Screener Works</div>
  <div class="faqi"><div class="faqq" onclick="fFaq(this)">What is the Graham screen? <span class="faqch">&#9660;</span></div><div class="faqa"><div class="faqai">Benjamin Graham&rsquo;s Graham Number: <strong>Candidate</strong> when price trades below &radic;(22.5 &times; TTM EPS &times; Book Value). <strong>Near Miss</strong> = within 10% of the Graham Number.</div></div></div>
  <div class="faqi"><div class="faqq" onclick="fFaq(this)">What is the Lynch screen? <span class="faqch">&#9660;</span></div><div class="faqa"><div class="faqai">Peter Lynch&rsquo;s GARP: <strong>Candidate</strong> requires PEG &lt; 1.0, EPS growth 10&ndash;30%, D/E &lt; 0.6.</div></div></div>
  <div class="faqi"><div class="faqq" onclick="fFaq(this)">What is the Buffett screen? <span class="faqch">&#9660;</span></div><div class="faqa"><div class="faqai">Quality moat approach: ROIC &gt; 15%, FCF Yield &gt; 5%, Revenue Growth &gt; 5%, Op Margin &gt; 15%.</div></div></div>
  <div class="faqi"><div class="faqq" onclick="fFaq(this)">How often is it updated? <span class="faqch">&#9660;</span></div><div class="faqa"><div class="faqai">Automatically Monday, Wednesday and Friday using live FMP API data. All metrics are TTM.</div></div></div>
</div>
<p class="disc">Not investment advice. Data from Financial Modeling Prep API. TTM metrics. &copy; <a href="{WP_URL}">Alert Invest</a></p>
</div>
<script>"""

    _html_after = """</script>
<!-- /wp:html -->"""

    return _html_before + JS + _html_after


# ─────────────────────────────────────────────────────────────────────
def deploy_page(html, updated_at):
    import base64
    token = None
    try:
        r = requests.post(f"{WP_URL}/wp-json/jwt-auth/v1/token",
                          json={"username":WP_USER,"password":WP_PASSWORD}, timeout=15)
        if r.status_code == 200 and r.text.strip():
            token = r.json().get("token")
    except Exception as e:
        print(f"  JWT auth error: {e}")

    if token:
        headers = {"Authorization": f"Bearer {token}"}
        print("  Auth: JWT")
    else:
        creds = base64.b64encode(f"{WP_USER}:{WP_PASSWORD}".encode()).decode()
        headers = {"Authorization": f"Basic {creds}"}
        print("  Auth: Basic (Application Password)")

    payload = {
        "title":   "S&P 500 Value Stock Screener — Graham, Lynch & Buffett | Alert Invest",
        "content": html,
        "status":  "publish",
        "slug":    WP_SLUG,
        "meta":    {"_wp_page_template": "default"}
    }
    search = requests.get(f"{WP_URL}/wp-json/wp/v2/pages",
                          params={"slug":WP_SLUG}, headers=headers, timeout=15).json()
    if search and isinstance(search, list) and len(search) > 0:
        pid = search[0]["id"]
        res = requests.post(f"{WP_URL}/wp-json/wp/v2/pages/{pid}",
                            headers=headers, json=payload, timeout=120)
        action = "Updated"
    else:
        res = requests.post(f"{WP_URL}/wp-json/wp/v2/pages",
                            headers=headers, json=payload, timeout=120)
        action = "Created"

    if res.status_code in [200, 201]:
        print(f"  ✅ {action}: {WP_URL}/{WP_SLUG}/")
        return True
    else:
        print(f"  ✗ WP error {res.status_code}: {res.text[:300]}")
        return False


# ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*60}\n  Alert Invest Screener Builder — {updated_at}\n{'='*60}\n")
    print("  Fetching Screener CSV...")
    sr = fetch_csv(SCREENER_CSV); print(f"  → {len(sr)} rows")
    print("  Fetching Top 10 CSV...")
    tr = fetch_csv(TOP10_CSV); print(f"  → {len(tr)} rows")
    stocks = parse_screener(sr)
    top10  = parse_top10(tr)
    print(f"\n  Parsed {len(stocks)} stocks, {len(top10)} top 10 entries")
    if not stocks: print("  ✗ No stocks parsed"); return
    print("  Building HTML...")
    html = build_html(stocks, top10, updated_at)
    print(f"  → {len(html):,} chars")
    if args.dry_run:
        os.makedirs("output", exist_ok=True)
        open("output/screener.html", "w", encoding="utf-8").write(html)
        print("  Saved: output/screener.html")
    else:
        print("  Deploying to WordPress...")
        deploy_page(html, updated_at)
    print(f"\n{'='*60}\n  Done.\n")

if __name__ == "__main__":
    main()
