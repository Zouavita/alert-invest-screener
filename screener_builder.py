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
            f'<td><span class="sec-badge" style="background:{c}15;color:{c}">{sec}</span></td>'
            f'<td class="tn">{num(pe)}</td><td class="tn">{num(peg,2)}</td>'
            f'<td class="tn">{num(de,2)}</td><td class="tn">{num(roic,1)}%</td>'
            f'<td class="tc">{sig(gr)}</td><td class="tc">{sig(ly)}</td>'
            f'<td class="tc">{sig(bu)}</td><td class="tc">{sig(pa)}</td>'
            f'<td class="tn">{mos(ms)}</td><td class="tn">{pct(rg)}</td>'
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
/* TOPBAR */
.tb{background:#fff;border:1px solid #d1d5db;border-radius:5px;padding:9px 14px;margin-bottom:7px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}
.tbb{font-size:14px;font-weight:800;color:#0f172a;letter-spacing:-.4px}.tbb em{color:#2563eb;font-style:normal}
.tbst{display:flex;gap:1px;background:#e5e7eb;border-radius:4px;overflow:hidden}
.tbsi{padding:5px 14px;background:#fff;display:flex;flex-direction:column;align-items:center;gap:1px}
.tbn{font-size:15px;font-weight:800;color:#111827;line-height:1}
.tbl{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:#6b7280}
.tbn.g{color:#16a34a}.tbn.b{color:#2563eb}.tbn.p{color:#7c3aed}.tbn.y{color:#d97706}
.tbu{font-size:10px;color:#9ca3af;border:1px solid #e5e7eb;border-radius:3px;padding:3px 8px}
/* AUTH BAR */
.auth-bar{background:#fff;border:1px solid #d1d5db;border-radius:5px;padding:8px 14px;margin-bottom:7px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-height:40px}
.tier-badge{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;padding:2px 8px;border-radius:2px;white-space:nowrap}
.tier-anon{background:#f3f4f6;color:#6b7280}
.tier-google{background:#dbeafe;color:#1d4ed8}
.tier-patreon{background:#dcfce7;color:#15803d}
.auth-name{font-size:11px;color:#374151;font-weight:600}
.auth-nudge{font-size:10px;color:#6b7280}
.auth-nudge strong{color:#111827}
.auth-nudge a{color:#e85b46;font-weight:700;text-decoration:none}
.auth-actions{margin-left:auto;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.btn-google{display:inline-flex;align-items:center;gap:6px;background:#fff;color:#374151;border:1px solid #d1d5db;border-radius:3px;padding:5px 12px;font-size:11px;font-weight:600;cursor:pointer;font-family:inherit;white-space:nowrap}
.btn-google:hover{background:#f9fafb}
.btn-patreon{display:inline-flex;align-items:center;gap:6px;background:#e85b46;color:#fff;border:none;border-radius:3px;padding:5px 12px;font-size:11px;font-weight:700;cursor:pointer;font-family:inherit;white-space:nowrap}
.btn-signout{background:none;border:none;font-size:10px;color:#9ca3af;cursor:pointer;font-family:inherit;padding:2px 4px}
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
.si{width:100%;padding:4px 8px 4px 26px;border:1px solid #d1d5db;border-radius:3px;font-size:11px;color:#374151;outline:none;font-family:inherit}
.si:focus{border-color:#2563eb;box-shadow:0 0 0 2px #dbeafe}
.sic{position:absolute;left:8px;top:50%;transform:translateY(-50%);color:#9ca3af;pointer-events:none;font-size:11px}
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
table.t{width:100%;border-collapse:collapse;font-size:11px;table-layout:fixed}
table.t thead th{padding:5px 6px;background:#f9fafb;border-bottom:2px solid #e5e7eb;text-align:left;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#6b7280;white-space:nowrap;position:sticky;top:0;z-index:2;overflow:hidden;text-overflow:ellipsis}
table.t thead th.tn{text-align:right}
table.t thead th.tc{text-align:center}
table.t thead th:hover{color:#2563eb;background:#eff6ff;cursor:pointer}
table.t tbody td{padding:3px 6px;border-bottom:1px solid #f3f4f6;vertical-align:middle;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
table.t tbody tr:hover td{background:#f8fafc!important}
table.t tbody tr:nth-child(even) td{background:#fafafa}
/* column widths */
table.t th:nth-child(1),table.t td:nth-child(1){width:130px}
table.t th:nth-child(2),table.t td:nth-child(2){width:100px}
table.t th:nth-child(3),table.t td:nth-child(3){width:48px}
table.t th:nth-child(4),table.t td:nth-child(4){width:44px}
table.t th:nth-child(5),table.t td:nth-child(5){width:44px}
table.t th:nth-child(6),table.t td:nth-child(6){width:50px}
table.t th:nth-child(7),table.t td:nth-child(7){width:58px}
table.t th:nth-child(8),table.t td:nth-child(8){width:48px}
table.t th:nth-child(9),table.t td:nth-child(9){width:58px}
table.t th:nth-child(10),table.t td:nth-child(10){width:58px}
table.t th:nth-child(11),table.t td:nth-child(11){width:90px}
table.t th:nth-child(12),table.t td:nth-child(12){width:58px}
table.t th:nth-child(13),table.t td:nth-child(13){width:58px}
table.t th:nth-child(14),table.t td:nth-child(14){width:52px}
.tds{display:flex;flex-direction:column;gap:1px}
.stk{font-size:11px;font-weight:800;color:#1d4ed8;line-height:1.2}
.sco{font-size:9px;color:#9ca3af;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sec-badge{font-size:9px;font-weight:700;padding:2px 5px;border-radius:2px;white-space:nowrap;display:inline-block;max-width:100%;overflow:hidden;text-overflow:ellipsis}
.tn{text-align:right;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;color:#374151}
.tc{text-align:center}
.pos{color:#15803d;font-weight:700}.neg{color:#b91c1c;font-weight:700}.na{color:#e5e7eb}
.sig{display:inline-flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;padding:2px 5px;border-radius:2px;white-space:nowrap}
.sg{background:#dcfce7;color:#15803d}.sn{background:#fef9c3;color:#92400e}
.sp{background:#dbeafe;color:#1d4ed8}.sf{background:#f3f4f6;color:#d1d5db}.s0{color:#e5e7eb}
.mos-v{font-size:9px;font-weight:700;color:#2563eb;white-space:nowrap}
/* PAYWALL */
.pw-gradient{background:linear-gradient(to bottom,rgba(255,255,255,0) 0%,#fff 60%);height:50px}
.pw-box{background:#fff;padding:24px 20px;text-align:center;border-top:2px solid #e5e7eb}
.pw-icon{font-size:18px;margin-bottom:6px}
.pw-title{font-size:14px;font-weight:800;color:#0f172a;margin-bottom:5px}
.pw-sub{font-size:11px;color:#6b7280;line-height:1.6;margin-bottom:14px}
.pw-btns{display:flex;flex-direction:column;align-items:center;gap:7px}
.pw-note{font-size:10px;color:#9ca3af;margin-top:8px}
/* FAQ */
.faq{margin-top:8px;background:#fff;border:1px solid #d1d5db;border-radius:5px;overflow:hidden}
.faqh{padding:7px 12px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:10px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:.05em}
.faqi{border-bottom:1px solid #f3f4f6}.faqi:last-child{border:none}
.faqq{padding:9px 12px;font-size:12px;font-weight:600;color:#374151;cursor:pointer;display:flex;justify-content:space-between;align-items:center;user-select:none}
.faqq:hover{background:#f8fafc;color:#2563eb}
.faqch{font-size:9px;color:#9ca3af;transition:transform .2s;display:inline-block}
.faqa{max-height:0;overflow:hidden;transition:max-height .3s ease,opacity .3s ease;opacity:0}
.faqa.open{opacity:1}
.faqai{padding:6px 12px 12px;font-size:11px;line-height:1.75;color:#6b7280}
.disc{font-size:10px;color:#9ca3af;margin-top:8px;text-align:center;line-height:1.65;padding:6px}
@media(max-width:900px){table.t th:nth-child(n+12),table.t td:nth-child(n+12){display:none}}
@media(max-width:700px){table.t th:nth-child(n+9),table.t td:nth-child(n+9){display:none}}
@media(max-width:500px){table.t th:nth-child(n+6),table.t td:nth-child(n+6){display:none}.auth-actions{margin-left:0}.t10-featured{flex-direction:column;align-items:flex-start}.t10f-right{align-items:flex-start}}"""

    # JS — no Python string injection for SVG, defined purely in JS
    JS = (
        "\n"
        "// ── FIREBASE CONFIG — replace with your real values ─────────────\n"
        "var FB_CFG = {\n"
        "  apiKey:            'AIzaSyBnz1S5v4FYX7fYo6RF42E4ALmpvtpEu9M',\n"
        "  authDomain:        'saas-portfolio-6bbc8.firebaseapp.com',\n"
        "  projectId:         'saas-portfolio-6bbc8',\n"
        "  storageBucket:     'saas-portfolio-6bbc8.firebasestorage.app',\n"
        "  messagingSenderId: '124296076295',\n"
        "  appId:             '1:124296076295:web:32ee053bb6e98fea455ea2'\n"
        "};\n"
        "\n"
        "// ── GOOGLE SVG (no Python injection) ─────────────────────────────\n"
        "var GSVG = '<svg viewBox=\"0 0 24 24\" width=\"14\" height=\"14\" xmlns=\"http://www.w3.org/2000/svg\">'\n"
        "  + '<path d=\"M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z\" fill=\"#4285F4\"/>'\n"
        "  + '<path d=\"M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z\" fill=\"#34A853\"/>'\n"
        "  + '<path d=\"M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z\" fill=\"#FBBC05\"/>'\n"
        "  + '<path d=\"M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z\" fill=\"#EA4335\"/>'\n"
        "  + '</svg>';\n"
        "\n"
        "// ── CONSTANTS ─────────────────────────────────────────────────────\n"
        "var PATREON_CLIENT_ID = '" + PATREON_CLIENT_ID + "';\n"
        "var PATREON_REDIRECT  = '" + PATREON_REDIRECT + "';\n"
        "var PATREON_JOIN_URL  = '" + PATREON_JOIN_URL + "';\n"
        "var FREE_ROWS         = " + str(FREE_ROWS) + ";\n"
        "var GOOGLE_ROWS       = " + str(GOOGLE_ROWS) + ";\n"
        "var N_TOTAL           = " + str(n_total) + ";\n"
        "var PAGE_SIZE         = 50;\n"
        "\n"
        "// ── STATE ─────────────────────────────────────────────────────────\n"
        "var AUTH_LEVEL  = 'anon';\n"
        "var FB_USER     = null;\n"
        "var visibleUpTo = PAGE_SIZE;\n"
        "var gP='all', gS='', gQ='';\n"
        "\n"
        "// ── FIREBASE ──────────────────────────────────────────────────────\n"
        "function initFirebase() {\n"
        "  if (typeof firebase === 'undefined') {\n"
        "    updateAuthUI(); initTable(); return;\n"
        "  }\n"
        "  try {\n"
        "    if (!firebase.apps.length) firebase.initializeApp(FB_CFG);\n"
        "  } catch(e) {\n"
        "    console.warn('Firebase init failed:', e.message);\n"
        "    updateAuthUI(); initTable(); return;\n"
        "  }\n"
        "  try {\n"
        "    firebase.auth().onAuthStateChanged(function(user) {\n"
        "      FB_USER = user;\n"
        "      if (user && AUTH_LEVEL !== 'patreon') {\n"
        "        AUTH_LEVEL = 'google';\n"
        "        saveLocalGoogle(user);\n"
        "        writeUserToFirestore(user);\n"
        "      } else if (!user && AUTH_LEVEL === 'google') {\n"
        "        AUTH_LEVEL = 'anon';\n"
        "      }\n"
        "      updateAuthUI();\n"
        "      initTable();\n"
        "    });\n"
        "  } catch(e) {\n"
        "    console.warn('Firebase auth failed:', e.message);\n"
        "    updateAuthUI(); initTable();\n"
        "  }\n"
        "}\n"
        "\n"
        "function googleLogin() {\n"
        "  if (typeof firebase === 'undefined') return;\n"
        "  try {\n"
        "    var provider = new firebase.auth.GoogleAuthProvider();\n"
        "    provider.addScope('email');\n"
        "    firebase.auth().signInWithPopup(provider).catch(function(e) {\n"
        "      console.error('Google login error:', e.message);\n"
        "    });\n"
        "  } catch(e) { console.error(e); }\n"
        "}\n"
        "\n"
        "function googleLogout() {\n"
        "  if (typeof firebase === 'undefined') return;\n"
        "  firebase.auth().signOut().then(function() {\n"
        "    localStorage.removeItem('ai_gu');\n"
        "    FB_USER = null;\n"
        "    AUTH_LEVEL = checkPatreonLocal() ? 'patreon' : 'anon';\n"
        "    updateAuthUI(); initTable();\n"
        "  });\n"
        "}\n"
        "\n"
        "function writeUserToFirestore(user) {\n"
        "  try {\n"
        "    if (typeof firebase === 'undefined' || !firebase.firestore) return;\n"
        "    firebase.firestore().collection('screener_users').doc(user.uid).set({\n"
        "      uid:       user.uid,\n"
        "      email:     user.email,\n"
        "      name:      user.displayName || '',\n"
        "      photo:     user.photoURL    || '',\n"
        "      lastSeen:  firebase.firestore.FieldValue.serverTimestamp(),\n"
        "      firstSeen: firebase.firestore.FieldValue.serverTimestamp(),\n"
        "      source:    'screener',\n"
        "      level:     'google'\n"
        "    }, { merge: true });\n"
        "  } catch(e) { console.warn('Firestore write failed:', e.message); }\n"
        "}\n"
        "\n"
        "// ── LOCAL SESSION ─────────────────────────────────────────────────\n"
        "function saveLocalGoogle(user) {\n"
        "  try { localStorage.setItem('ai_gu', JSON.stringify({\n"
        "    email: user.email, name: user.displayName,\n"
        "    exp: Date.now() + 8*60*60*1000\n"
        "  })); } catch(e) {}\n"
        "}\n"
        "function checkLocalGoogle() {\n"
        "  try { var d=JSON.parse(localStorage.getItem('ai_gu')||'null');\n"
        "    return d && Date.now() < d.exp; } catch(e) { return false; }\n"
        "}\n"
        "function saveLocalPatreon(name) {\n"
        "  try { localStorage.setItem('ai_pm', JSON.stringify({\n"
        "    name: name, exp: Date.now() + 8*60*60*1000\n"
        "  })); } catch(e) {}\n"
        "}\n"
        "function checkPatreonLocal() {\n"
        "  try { var d=JSON.parse(localStorage.getItem('ai_pm')||'null');\n"
        "    return d && Date.now() < d.exp; } catch(e) { return false; }\n"
        "}\n"
        "function getPatreonName() {\n"
        "  try { return JSON.parse(localStorage.getItem('ai_pm')).name||'Member'; }\n"
        "  catch(e) { return 'Member'; }\n"
        "}\n"
        "function getGoogleName() {\n"
        "  try {\n"
        "    if (FB_USER) return FB_USER.displayName || FB_USER.email;\n"
        "    return JSON.parse(localStorage.getItem('ai_gu')).name || 'User';\n"
        "  } catch(e) { return 'User'; }\n"
        "}\n"
        "\n"
        "// ── PATREON ───────────────────────────────────────────────────────\n"
        "function patreonLogin() {\n"
        "  var state = Math.random().toString(36).substring(2);\n"
        "  try { localStorage.setItem('pt_state', state); } catch(e) {}\n"
        "  window.location.href = 'https://www.patreon.com/oauth2/authorize'\n"
        "    + '?response_type=code'\n"
        "    + '&client_id=' + PATREON_CLIENT_ID\n"
        "    + '&redirect_uri=' + encodeURIComponent(PATREON_REDIRECT)\n"
        "    + '&scope=' + encodeURIComponent('identity identity[email] identity.memberships')\n"
        "    + '&state=' + state;\n"
        "}\n"
        "function patreonLogout() {\n"
        "  try { localStorage.removeItem('ai_pm'); } catch(e) {}\n"
        "  AUTH_LEVEL = FB_USER ? 'google' : (checkLocalGoogle() ? 'google' : 'anon');\n"
        "  updateAuthUI(); initTable();\n"
        "}\n"
        "function handleStreamlitCallback() {\n"
        "  var p = new URLSearchParams(window.location.search);\n"
        "  var member = p.get('member');\n"
        "  if (!member) return false;\n"
        "  if (member === '1') {\n"
        "    AUTH_LEVEL = 'patreon';\n"
        "    saveLocalPatreon(p.get('name') || 'Member');\n"
        "    try {\n"
        "      if (FB_USER && typeof firebase !== 'undefined' && firebase.firestore) {\n"
        "        firebase.firestore().collection('screener_users').doc(FB_USER.uid).set(\n"
        "          { level: 'patreon', patreonAt: firebase.firestore.FieldValue.serverTimestamp() },\n"
        "          { merge: true }\n"
        "        );\n"
        "      }\n"
        "    } catch(e) {}\n"
        "  } else if (member === '0') {\n"
        "    showNotPatreonMember();\n"
        "  }\n"
        "  window.history.replaceState({}, '', PATREON_REDIRECT);\n"
        "  return true;\n"
        "}\n"
        "function handleOAuthCallback() {\n"
        "  var p = new URLSearchParams(window.location.search);\n"
        "  var code = p.get('code');\n"
        "  if (!code) return false;\n"
        "  window.location.href = 'https://alert-invest-portfolio-tool.streamlit.app/'\n"
        "    + '?screener_code=' + encodeURIComponent(code)\n"
        "    + '&screener_redirect=' + encodeURIComponent(PATREON_REDIRECT)\n"
        "    + '&state=' + encodeURIComponent(p.get('state') || '');\n"
        "  return true;\n"
        "}\n"
        "\n"
        "// ── AUTH UI ───────────────────────────────────────────────────────\n"
        "function updateAuthUI() {\n"
        "  var bar = document.getElementById('auth-bar');\n"
        "  if (!bar) return;\n"
        "  var left = '', right = '';\n"
        "  if (AUTH_LEVEL === 'patreon') {\n"
        "    left  = '<span class=\"tier-badge tier-patreon\">&#10003; Portfolio Builder</span>'\n"
        "           + '<span class=\"auth-name\">' + getPatreonName() + '</span>';\n"
        "    right = '<button class=\"btn-signout\" onclick=\"patreonLogout()\">Sign out</button>';\n"
        "  } else if (AUTH_LEVEL === 'google') {\n"
        "    left  = '<span class=\"tier-badge tier-google\">&#10003; Google</span>'\n"
        "           + '<span class=\"auth-name\">' + getGoogleName() + '</span>'\n"
        "           + '<span style=\"color:#e5e7eb;margin:0 2px\">|</span>'\n"
        "           + '<span class=\"auth-nudge\">Seeing <strong>' + GOOGLE_ROWS + ' of ' + N_TOTAL + ' stocks</strong>'\n"
        "           + ' &mdash; <a href=\"' + PATREON_JOIN_URL + '\" target=\"_blank\">Unlock all &rarr;</a></span>';\n"
        "    right = '<button class=\"btn-patreon\" onclick=\"patreonLogin()\">&#128994; Connect Patreon</button>'\n"
        "           + '<button class=\"btn-signout\" onclick=\"googleLogout()\">Sign out</button>';\n"
        "  } else {\n"
        "    left  = '<span class=\"tier-badge tier-anon\">Free</span>'\n"
        "           + '<span class=\"auth-nudge\">Seeing <strong>' + FREE_ROWS + ' of ' + N_TOTAL + ' stocks</strong>'\n"
        "           + ' &mdash; sign in to unlock more</span>';\n"
        "    right = '<button class=\"btn-google\" onclick=\"googleLogin()\">' + GSVG + ' Sign in with Google</button>'\n"
        "           + '<button class=\"btn-patreon\" onclick=\"patreonLogin()\">&#128994; Connect Patreon</button>';\n"
        "  }\n"
        "  bar.innerHTML = '<div style=\"display:flex;align-items:center;gap:8px;flex-wrap:wrap\">'\n"
        "    + left + '</div><div class=\"auth-actions\">' + right + '</div>';\n"
        "}\n"
        "function showNotPatreonMember() {\n"
        "  var bar = document.getElementById('auth-bar');\n"
        "  if (!bar) return;\n"
        "  bar.innerHTML = '<span style=\"color:#b91c1c;font-size:11px;font-weight:600\">'\n"
        "    + '&#10007; Not a Portfolio Builder member.</span>'\n"
        "    + ' <a href=\"' + PATREON_JOIN_URL + '\" target=\"_blank\" style=\"font-size:11px;font-weight:700;color:#2563eb\">Upgrade &rarr;</a>';\n"
        "}\n"
        "\n"
        "// ── TABLE ─────────────────────────────────────────────────────────\n"
        "function rowLimit() {\n"
        "  if (AUTH_LEVEL === 'patreon') return Infinity;\n"
        "  if (AUTH_LEVEL === 'google')  return GOOGLE_ROWS;\n"
        "  return FREE_ROWS;\n"
        "}\n"
        "function initTable() { renderRows(); renderPaywall(); updateCount(); }\n"
        "function renderRows() {\n"
        "  var limit = rowLimit();\n"
        "  var allRows = document.querySelectorAll('#tbody .sr');\n"
        "  allRows.forEach(function(r) {\n"
        "    var idx   = parseInt(r.dataset.idx);\n"
        "    var authOk = idx < limit;\n"
        "    var pageOk = (AUTH_LEVEL === 'patreon') ? idx < visibleUpTo : true;\n"
        "    r.style.display = (authOk && pageOk) ? '' : 'none';\n"
        "  });\n"
        "  var btn = document.getElementById('load-more-btn');\n"
        "  if (btn) {\n"
        "    var total = allRows.length;\n"
        "    btn.style.display = (AUTH_LEVEL === 'patreon' && visibleUpTo < total) ? '' : 'none';\n"
        "    btn.textContent = 'Show next 50 (' + Math.min(visibleUpTo+PAGE_SIZE,total) + ' of ' + total + ' total)';\n"
        "  }\n"
        "}\n"
        "function loadMore() { visibleUpTo += PAGE_SIZE; renderRows(); updateCount(); }\n"
        "function updateCount() {\n"
        "  var shown = 0;\n"
        "  document.querySelectorAll('#tbody .sr').forEach(function(r) {\n"
        "    if (r.style.display !== 'none') shown++;\n"
        "  });\n"
        "  var el = document.getElementById('rcnt');\n"
        "  if (el) el.textContent = shown + ' result' + (shown!==1?'s':'');\n"
        "}\n"
        "function renderPaywall() {\n"
        "  var old = document.getElementById('inline-pw');\n"
        "  if (old) old.remove();\n"
        "  if (AUTH_LEVEL === 'patreon') return;\n"
        "  var allRows = document.querySelectorAll('#tbody .sr');\n"
        "  var last = null;\n"
        "  allRows.forEach(function(r) { if (r.style.display !== 'none') last = r; });\n"
        "  if (!last) return;\n"
        "  var isGoogle  = AUTH_LEVEL === 'google';\n"
        "  var seenCount = isGoogle ? GOOGLE_ROWS : FREE_ROWS;\n"
        "  var googleBtn = !isGoogle\n"
        "    ? '<button onclick=\"googleLogin()\" class=\"btn-google\" style=\"width:260px;justify-content:center;padding:9px 0;font-size:12px\">'\n"
        "      + GSVG + ' Sign in with Google &mdash; free</button>'\n"
        "    : '';\n"
        "  var pw = document.createElement('tr');\n"
        "  pw.id = 'inline-pw';\n"
        "  pw.innerHTML = '<td colspan=\"14\" style=\"padding:0\">'\n"
        "    + '<div class=\"pw-gradient\"></div>'\n"
        "    + '<div class=\"pw-box\">'\n"
        "    + '<div class=\"pw-icon\">' + (isGoogle ? '&#128274;' : '&#128270;') + '</div>'\n"
        "    + '<div class=\"pw-title\">' + (isGoogle ? 'Unlock the Full Screener' : 'See More Stocks Free') + '</div>'\n"
        "    + '<div class=\"pw-sub\">Showing <strong>' + seenCount + ' of ' + N_TOTAL + ' stocks</strong>.<br>'\n"
        "    + (isGoogle\n"
        "        ? 'Join Patreon Portfolio Builder for full access to all ' + N_TOTAL + ' stocks.'\n"
        "        : 'Sign in with Google for <strong>' + GOOGLE_ROWS + ' stocks free</strong>, or join Patreon for everything.')\n"
        "    + '</div>'\n"
        "    + '<div class=\"pw-btns\">'\n"
        "    + googleBtn\n"
        "    + '<button onclick=\"patreonLogin()\" class=\"btn-patreon\" style=\"width:260px;justify-content:center;padding:9px 0;font-size:12px\">'\n"
        "    + '&#128994; Connect Patreon &mdash; full access</button>'\n"
        "    + '</div>'\n"
        "    + '<div class=\"pw-note\">Portfolio Builder on Patreon &middot; Cancel anytime</div>'\n"
        "    + '</div></td>';\n"
        "  last.insertAdjacentElement('afterend', pw);\n"
        "}\n"
        "function apply() {\n"
        "  var limit = rowLimit();\n"
        "  document.querySelectorAll('#tbody .sr').forEach(function(r) {\n"
        "    var idx = parseInt(r.dataset.idx);\n"
        "    var philOk = true;\n"
        "    if      (gP==='g'&&r.dataset.g!=='true') philOk=false;\n"
        "    else if (gP==='l'&&r.dataset.l!=='true') philOk=false;\n"
        "    else if (gP==='b'&&r.dataset.b!=='true') philOk=false;\n"
        "    else if (gP==='p'&&r.dataset.p!=='true') philOk=false;\n"
        "    else if (gP==='a'&&r.dataset.a!=='true') philOk=false;\n"
        "    var secOk  = !gS || r.dataset.sec === gS;\n"
        "    var srchOk = !gQ || r.dataset.tk.indexOf(gQ)!==-1 || r.dataset.co.indexOf(gQ)!==-1;\n"
        "    var authOk = idx < limit;\n"
        "    var pageOk = (AUTH_LEVEL==='patreon') ? idx < visibleUpTo : true;\n"
        "    var searching = gP!=='all'||gS!==''||gQ!=='';\n"
        "    if (searching && AUTH_LEVEL==='patreon') pageOk = true;\n"
        "    r.style.display = (philOk&&secOk&&srchOk&&authOk&&pageOk) ? '' : 'none';\n"
        "  });\n"
        "  updateCount(); renderPaywall();\n"
        "}\n"
        "function fPhil(b,v){gP=v;document.querySelectorAll('.chip[onclick*=\"fPhil\"]').forEach(function(x){x.classList.remove('on')});b.classList.add('on');apply();}\n"
        "function fSec(b,v){gS=v;document.querySelectorAll('.chip[onclick*=\"fSec\"]').forEach(function(x){x.classList.remove('on')});b.classList.add('on');apply();}\n"
        "function fSrch(v){gQ=v.toLowerCase().trim();apply();}\n"
        "function fFaq(q){\n"
        "  var a=q.nextElementSibling;\n"
        "  var ch=q.querySelector('.faqch');\n"
        "  var open=a.classList.contains('open');\n"
        "  a.classList.toggle('open',!open);\n"
        "  if(ch) ch.style.transform=open?'':'rotate(180deg)';\n"
        "  a.style.maxHeight=open?'0':(a.scrollHeight+20)+'px';\n"
        "}\n"
        "\n"
        "// ── BOOT ──────────────────────────────────────────────────────────\n"
        "window.addEventListener('DOMContentLoaded', function() {\n"
        "  var wasStreamlit = handleStreamlitCallback();\n"
        "  if (!wasStreamlit && handleOAuthCallback()) return;\n"
        "  if (!wasStreamlit) {\n"
        "    if      (checkPatreonLocal()) AUTH_LEVEL = 'patreon';\n"
        "    else if (checkLocalGoogle())  AUTH_LEVEL = 'google';\n"
        "  }\n"
        "  initFirebase();\n"
        "});\n"
    )

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
      <th class="tn">P/E</th><th class="tn">PEG</th>
      <th class="tn">D/E</th><th class="tn">ROIC</th>
      <th class="tc">Graham</th><th class="tc">Lynch</th>
      <th class="tc">Buffett</th><th class="tc">Pass All</th>
      <th class="tn">MoS</th>
      <th class="tn">Rev Gr</th><th class="tn">EPS Gr</th><th class="tn">Op Mar</th>
    </tr></thead>
    <tbody id="tbody">{rows_html}</tbody>
  </table>
  </div>
</div>

<div id="load-more-wrap" style="text-align:center;padding:10px;background:#fff;border:1px solid #d1d5db;border-top:none;border-radius:0 0 5px 5px;margin-top:-7px;margin-bottom:7px">
  <button id="load-more-btn" onclick="loadMore()" style="display:none;background:#f9fafb;border:1px solid #d1d5db;border-radius:3px;padding:6px 18px;font-size:11px;font-weight:600;color:#374151;cursor:pointer;font-family:inherit">Show next 50</button>
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

    _html_after = "</script>\n<!-- /wp:html -->"

    return _html_before + JS + _html_after


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
        print("  Auth: Basic")
    payload = {
        "title":   "S&P 500 Value Stock Screener — Graham, Lynch & Buffett | Alert Invest",
        "content": html, "status": "publish", "slug": WP_SLUG,
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
        print(f"  ✅ {action}: {WP_URL}/{WP_SLUG}/"); return True
    else:
        print(f"  ✗ WP error {res.status_code}: {res.text[:300]}"); return False


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
