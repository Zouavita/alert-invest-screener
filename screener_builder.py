#!/usr/bin/env python3
import argparse, csv, io, json, os, re
from datetime import datetime
import requests

WP_URL      = "https://alert-invest.com"
WP_USER     = os.environ.get("WP_USER", "")
WP_PASSWORD = os.environ.get("WP_PASSWORD", "")
WP_SLUG     = "stock-screener"
FREE_ROWS   = 5  # rows visible before paywall
PATREON_URL = "https://www.patreon.com/cw/AlertInvest/membership"

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

SC = {"Technology":"#2563eb","Communication Services":"#7c3aed","Healthcare":"#059669",
      "Financials":"#d97706","Consumer Cyclical":"#ea580c","Consumer Defensive":"#65a30d",
      "Industrials":"#4f46e5","Energy":"#dc2626","Real Estate":"#0891b2",
      "Basic Materials":"#92400e","Utilities":"#0284c7","Insurance":"#b45309"}
def sc(s): return SC.get(s,"#64748b")

def clean_signals(raw):
    """Convert Google Sheet signal string (may have emoji) to clean HTML badges."""
    if not raw: return ""
    # Normalize: remove broken encoding artifacts, normalize separators
    raw = re.sub(r'[^\x00-\x7F]', ' ', raw)  # strip non-ASCII
    raw = re.sub(r'\s*\|\s*', '|', raw.strip())
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    out = []
    for p in parts:
        if not p: continue
        if "Pass" in p or "PASS" in p:
            out.append('<span class="sb-pass">PASS ALL</span>')
        elif "Graham" in p and ("~" not in p):
            out.append('<span class="sb-g">Graham &#10003;</span>')
        elif "Graham" in p:
            out.append('<span class="sb-gn">Graham ~</span>')
        elif "Lynch" in p and ("~" not in p):
            out.append('<span class="sb-l">Lynch &#10003;</span>')
        elif "Lynch" in p:
            out.append('<span class="sb-ln">Lynch ~</span>')
        elif "Buffett" in p and ("~" not in p):
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

    # ── TOP 1 FEATURED + OTHERS COMPACT ─────────────────────────────────────
    t10_html = ""
    if top10:
        # Featured #1
        t = top10[0]
        tk = t.get("Ticker",""); co = t.get("Company",""); sec = t.get("Sector","")
        sigs_raw = t.get("Signals",""); score = t.get("Score",""); mos_v = t.get("Margin of Safety","—")
        c = sc(sec)
        sigs_html = clean_signals(sigs_raw)
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
        # Others #2-#10 compact list — #3+ blurred for free users
        t10_html += '<div class="t10-rest">'
        for i, t in enumerate(top10[1:], 2):
            tk2 = re.sub(r"[^A-Z0-9]", "", t.get("Ticker","").encode("ascii","ignore").decode("ascii").upper())
            co2 = t.get("Company","")[:20]
            sec2 = t.get("Sector",""); score2 = t.get("Score","")
            sigs2 = clean_signals(t.get("Signals",""))
            c2 = sc(sec2)
            blur = " t10r-locked" if i >= 3 else ""
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

    # ── SECTOR PILLS ─────────────────────────────────────────────────────────
    pills = '<button class="chip on" onclick="fSec(this,\'\')" style="--cc:#374151">All</button>'
    for sec in sectors:
        c = sc(sec)
        pills += f'<button class="chip" onclick="fSec(this,\'{sec}\')" style="--cc:{c}">{sec}</button>'

    # ── TABLE ROWS ───────────────────────────────────────────────────────────
    rows = ""
    for i, s in enumerate(stocks):
        tk=s.get("Ticker",""); co=s.get("Company",""); sec=s.get("Sector","")
        pe=s.get("P/E (Live)",""); peg=s.get("PEG (Live)",""); de=s.get("Debt/Equity","")
        roic=s.get("ROIC",""); gr=s.get("Graham Screen",""); ly=s.get("Lynch Screen","")
        bu=s.get("Buffett Screen",""); pa=s.get("Pass All?",""); ms=s.get("Margin of Safety","")
        rg=s.get("Rev Gr%",""); eg=s.get("EPS Growth",""); om=s.get("Op. Margin","")
        c = sc(sec)
        dg="true" if gr=="Candidate" else "false"
        dl="true" if ly=="Candidate" else "false"
        db="true" if bu=="Candidate" else "false"
        dp="true" if pa=="PASS" else "false"
        da="true" if (gr in("Candidate","Near Miss") or ly in("Candidate","Near Miss")
                      or bu in("Candidate","Near Miss") or pa=="PASS") else "false"
        # All rows included — JS controls visibility based on FREE_ROWS and auth
        rows += (
            f'<tr class="sr" data-idx="{i}" data-tk="{tk.lower()}" data-co="{co.lower()}" data-sec="{sec}" '
            f'data-g="{dg}" data-l="{dl}" data-b="{db}" data-p="{dp}" data-a="{da}">'
            f'<td class="tds"><span class="stk">{tk}</span><span class="sco">{co[:24]}</span></td>'
            f'<td><span style="background:{c}15;color:{c};font-size:9px;font-weight:700;'
            f'padding:2px 5px;border-radius:2px;white-space:nowrap">{sec}</span></td>'
            f'<td class="tn">{num(pe)}</td><td class="tn">{num(peg,2)}</td>'
            f'<td class="tn">{num(de,2)}</td><td class="tn">{num(roic,1)}%</td>'
            f'<td>{sig(gr)}</td><td>{sig(ly)}</td><td>{sig(bu)}</td><td>{sig(pa)}</td>'
            f'<td>{mos(ms)}</td><td class="tn">{pct(rg)}</td>'
            f'<td class="tn">{pct(eg)}</td><td class="tn">{num(om,1)}%</td></tr>'
        )

    schema = {"@context":"https://schema.org","@type":"WebPage",
              "name":"S&P 500 Value Stock Screener — Graham, Lynch & Buffett | Alert Invest",
              "description":f"Screen {n_total} S&P 500 stocks using Graham, Lynch and Buffett criteria. Live P/E, PEG, ROIC and Margin of Safety.",
              "url":f"{WP_URL}/stock-screener/","dateModified":updated_at,
              "publisher":{"@type":"Organization","name":"Alert Invest","url":WP_URL}}

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
/* Featured #1 */
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
/* Signal badges for Top 10 */
.sb-pass{background:#dbeafe;color:#1d4ed8;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.sb-g{background:#dcfce7;color:#15803d;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.sb-gn{background:#fef9c3;color:#92400e;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.sb-l{background:#dbeafe;color:#1d4ed8;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.sb-ln{background:#fef9c3;color:#92400e;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.sb-b{background:#f3e8ff;color:#7c3aed;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
.sb-bn{background:#fef9c3;color:#92400e;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;white-space:nowrap}
/* Rest list #2-10 */
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
/* LOCKED */
.locked td{filter:blur(5px);user-select:none;pointer-events:none;opacity:.6}
/* PAYWALL */
.pw{position:relative;margin-top:-80px;z-index:10;padding:0 12px 10px}
.pwc{background:#fff;border:1px solid #d1d5db;border-radius:10px;padding:32px 28px;text-align:center;max-width:500px;margin:0 auto;box-shadow:0 8px 40px rgba(0,0,0,.12)}
.pwl{font-size:26px;margin-bottom:10px}
.pwt{font-size:16px;font-weight:800;color:#0f172a;margin-bottom:8px}
.pws{font-size:12px;color:#6b7280;line-height:1.7;margin-bottom:16px}
.pwf{display:flex;flex-wrap:wrap;gap:5px;justify-content:center;margin-bottom:20px}
.pwf span{background:#eff6ff;color:#2563eb;font-size:10px;font-weight:700;padding:3px 10px;border-radius:2px}
.pw-btns{display:flex;flex-direction:column;align-items:center;gap:8px}
.pwb-main{display:inline-block;background:#2563eb;color:#fff;font-size:13px;font-weight:700;padding:10px 28px;border-radius:4px;text-decoration:none;width:100%;max-width:280px}
.pwb-main:hover{background:#1d4ed8;color:#fff;text-decoration:none}
.pwb-login{display:inline-block;background:#fff;color:#374151;font-size:12px;font-weight:600;padding:8px 28px;border-radius:4px;text-decoration:none;border:1px solid #d1d5db;width:100%;max-width:280px}
.pwb-login:hover{background:#f9fafb;color:#111827;text-decoration:none}
.pwn{font-size:10px;color:#9ca3af;margin-top:8px}
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
@media(max-width:600px){.t10-featured{flex-direction:column;align-items:flex-start}.t10f-right{align-items:flex-start}table.t th:nth-child(n+6),table.t td:nth-child(n+6){display:none}}"""

    JS = """
// ── PATREON OAUTH CONFIG ──────────────────────────────────────────────
var PATREON_CLIENT_ID   = '""" + PATREON_CLIENT_ID + """';
var PATREON_REDIRECT    = '""" + PATREON_REDIRECT + """';
var PATREON_CAMPAIGN_ID = '""" + PATREON_CAMPAIGN_ID + """';
var PATREON_TIER        = '""" + PATREON_TIER + """';
var PATREON_JOIN_URL    = '""" + PATREON_JOIN_URL + """';
var FREE_ROWS           = """ + str(5) + """;
var N_TOTAL             = {n_total};

var IS_MEMBER = false;
var gP='all', gS='', gQ='';

// ── OAUTH FLOW ────────────────────────────────────────────────────────
function patreonLogin() {
  var state = Math.random().toString(36).substring(2);
  localStorage.setItem('patreon_state', state);
  var scope = encodeURIComponent('identity identity[email] identity.memberships');
  var url = 'https://www.patreon.com/oauth2/authorize'
    + '?response_type=code'
    + '&client_id=' + PATREON_CLIENT_ID
    + '&redirect_uri=' + encodeURIComponent(PATREON_REDIRECT)
    + '&scope=' + scope
    + '&state=' + state;
  window.location.href = url;
}

function patreonLogout() {
  localStorage.removeItem('patreon_member');
  localStorage.removeItem('patreon_name');
  IS_MEMBER = false;
  updateAuthUI();
  initTable();
}

// ── CHECK CACHED SESSION ──────────────────────────────────────────────
function checkCachedSession() {
  var cached = localStorage.getItem('patreon_member');
  if (cached) {
    try {
      var d = JSON.parse(cached);
      // Valid for 8 hours
      if (d.expires && Date.now() < d.expires && d.isMember) {
        IS_MEMBER = true;
        return true;
      }
    } catch(e) {}
    localStorage.removeItem('patreon_member');
  }
  return false;
}

// ── HANDLE OAUTH CALLBACK (code in URL) ───────────────────────────────
function handleOAuthCallback() {
  var params = new URLSearchParams(window.location.search);
  var code  = params.get('code');
  var state = params.get('state');
  if (!code) return false;

  // Show loading state
  showAuthLoading();

  // We can't do server-side token exchange from pure JS (CORS).
  // Use the Streamlit app as a proxy — same pattern as portfolio analyzer.
  // Redirect to Streamlit with code, Streamlit verifies and redirects back with member=1
  var proxyUrl = 'https://alert-invest-portfolio-tool.streamlit.app/'
    + '?screener_code=' + encodeURIComponent(code)
    + '&screener_redirect=' + encodeURIComponent(PATREON_REDIRECT)
    + '&state=' + encodeURIComponent(state || '');
  window.location.href = proxyUrl;
  return true;
}

// ── HANDLE STREAMLIT CALLBACK (member param in URL) ───────────────────
function handleStreamlitCallback() {
  var params = new URLSearchParams(window.location.search);
  var member = params.get('member');
  var name   = params.get('name') || 'Member';
  if (member === '1') {
    IS_MEMBER = true;
    localStorage.setItem('patreon_member', JSON.stringify({
      isMember: true,
      name: name,
      expires: Date.now() + 8 * 60 * 60 * 1000
    }));
    localStorage.setItem('patreon_name', name);
    // Clean URL
    window.history.replaceState({}, '', PATREON_REDIRECT);
    return true;
  }
  if (member === '0') {
    // Logged in but not a member
    showNotMember();
    window.history.replaceState({}, '', PATREON_REDIRECT);
    return true;
  }
  return false;
}

function showAuthLoading() {
  var bar = document.getElementById('auth-bar');
  if (bar) bar.innerHTML = '<span style="color:#6b7280;font-size:11px">Verifying Patreon membership&hellip;</span>';
}

function showNotMember() {
  var bar = document.getElementById('auth-bar');
  if (bar) bar.innerHTML = '<span style="color:#b91c1c;font-size:11px;font-weight:600">&#10007; Your Patreon account is not a Portfolio Builder member.</span>'
    + ' <a href="' + PATREON_JOIN_URL + '" target="_blank" style="font-size:11px;font-weight:700;color:#2563eb">Upgrade &rarr;</a>'
    + ' <button onclick="patreonLogout()" style="margin-left:8px;font-size:10px;color:#6b7280;background:none;border:none;cursor:pointer;font-family:inherit">Sign out</button>';
}

function updateAuthUI() {
  var bar = document.getElementById('auth-bar');
  if (!bar) return;
  var name = localStorage.getItem('patreon_name') || 'Member';
  if (IS_MEMBER) {
    bar.innerHTML = '<span style="color:#15803d;font-size:11px;font-weight:700">&#10003; Portfolio Builder &mdash; ' + name + '</span>'
      + ' <button onclick="patreonLogout()" style="margin-left:8px;font-size:10px;color:#6b7280;background:none;border:none;cursor:pointer;font-family:inherit">Sign out</button>';
  } else {
    bar.innerHTML = '<button onclick="patreonLogin()" style="display:inline-flex;align-items:center;gap:6px;background:#e85b46;color:#fff;border:none;border-radius:3px;padding:5px 12px;font-size:11px;font-weight:700;cursor:pointer;font-family:inherit">&#128994; Connect with Patreon</button>'
      + ' <span style="font-size:10px;color:#9ca3af;margin-left:6px">or <a href="' + PATREON_JOIN_URL + '" target="_blank" style="color:#2563eb;font-weight:600">become a Portfolio Builder member</a></span>';
  }
}

// ── TABLE INIT ────────────────────────────────────────────────────────
function initTable() {
  var rows = document.querySelectorAll('#tbody .sr');
  rows.forEach(function(r) {
    var idx = parseInt(r.dataset.idx);
    r.style.display = (!IS_MEMBER && idx >= FREE_ROWS) ? 'none' : '';
  });
  renderPaywall();
  updateCount();
}

function updateCount() {
  var shown = 0;
  document.querySelectorAll('#tbody .sr').forEach(function(r) {
    if (r.style.display !== 'none') shown++;
  });
  var el = document.getElementById('rcnt');
  if (el) el.textContent = shown + ' result' + (shown !== 1 ? 's' : '');
}

function renderPaywall() {
  var existing = document.getElementById('inline-pw');
  if (existing) existing.remove();
  if (IS_MEMBER) return;

  var rows = document.querySelectorAll('#tbody .sr');
  var lastVisible = null;
  rows.forEach(function(r) {
    if (r.style.display !== 'none') lastVisible = r;
  });
  if (!lastVisible) return;

  var pw = document.createElement('tr');
  pw.id = 'inline-pw';
  pw.innerHTML = '<td colspan="14" style="padding:0">'
    + '<div style="background:linear-gradient(to bottom,rgba(255,255,255,0) 0%,#fff 60%);height:50px"></div>'
    + '<div style="background:#fff;padding:28px 20px;text-align:center;border-top:2px solid #e5e7eb">'
    + '<div style="font-size:20px;margin-bottom:8px">&#128274;</div>'
    + '<div style="font-size:15px;font-weight:800;color:#0f172a;margin-bottom:6px">Unlock the Full Screener</div>'
    + '<div style="font-size:12px;color:#6b7280;line-height:1.6;margin-bottom:16px">You&rsquo;re seeing <strong>' + FREE_ROWS + ' of ' + N_TOTAL + ' stocks</strong>.<br>Portfolio Builder members get full access to all results, filters and weekly updates.</div>'
    + '<div style="display:flex;flex-direction:column;align-items:center;gap:8px">'
    + '<button onclick="patreonLogin()" style="display:inline-flex;align-items:center;justify-content:center;gap:8px;background:#e85b46;color:#fff;border:none;border-radius:4px;padding:11px 28px;font-size:13px;font-weight:700;cursor:pointer;font-family:inherit;width:280px">&#128994; Connect with Patreon</button>'
    + '<a href="' + PATREON_JOIN_URL + '" target="_blank" style="display:inline-flex;align-items:center;justify-content:center;background:#fff;color:#374151;font-size:12px;font-weight:600;padding:9px 28px;border-radius:4px;text-decoration:none;border:1px solid #d1d5db;width:280px">Become a Portfolio Builder member &rarr;</a>'
    + '</div>'
    + '<div style="font-size:10px;color:#9ca3af;margin-top:10px">Portfolio Builder membership on Patreon &middot; Cancel anytime</div>'
    + '</div></td>';
  lastVisible.insertAdjacentElement('afterend', pw);
}

function apply() {
  var rows = document.querySelectorAll('#tbody .sr');
  rows.forEach(function(r) {
    var idx = parseInt(r.dataset.idx);
    var philOk = true;
    if (gP==='g'&&r.dataset.g!=='true') philOk=false;
    else if (gP==='l'&&r.dataset.l!=='true') philOk=false;
    else if (gP==='b'&&r.dataset.b!=='true') philOk=false;
    else if (gP==='p'&&r.dataset.p!=='true') philOk=false;
    else if (gP==='a'&&r.dataset.a!=='true') philOk=false;
    var secOk  = !gS || r.dataset.sec === gS;
    var srchOk = !gQ || r.dataset.tk.indexOf(gQ) !== -1 || r.dataset.co.indexOf(gQ) !== -1;
    var authOk = IS_MEMBER || idx < FREE_ROWS;
    r.style.display = (philOk && secOk && srchOk && authOk) ? '' : 'none';
  });
  updateCount();
  renderPaywall();
}

function fPhil(btn,v){gP=v;document.querySelectorAll('.chip[onclick*="fPhil"]').forEach(function(b){b.classList.remove('on')});btn.classList.add('on');apply();}
function fSec(btn,v){gS=v;document.querySelectorAll('.chip[onclick*="fSec"]').forEach(function(b){b.classList.remove('on')});btn.classList.add('on');apply();}
function fSrch(v){gQ=v.toLowerCase().trim();apply();}
function fFaq(q){var a=q.nextElementSibling,ch=q.querySelector('.faqch'),open=a.classList.contains('open');a.classList.toggle('open',!open);ch.style.transform=open?'':'rotate(180deg)';a.style.maxHeight=open?'0':(a.scrollHeight+20)+'px';}

// ── BOOT ──────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', function() {
  // Priority order: Streamlit callback > OAuth callback > cached session
  if (handleStreamlitCallback()) {
    updateAuthUI();
    initTable();
  } else if (handleOAuthCallback()) {
    // Redirecting to Streamlit proxy — do nothing
  } else {
    checkCachedSession();
    updateAuthUI();
    initTable();
  }
});
"""

    return f"""<!-- wp:html -->
<script type="application/ld+json">{json.dumps(schema)}</script>
<style>{CSS}</style>
<div class="scr">

<div class="tb">
  <div class="tbb">Alert<em>Invest</em> <span style="font-size:11px;font-weight:400;color:#6b7280">/ S&P 500 Screener</span></div>
  <div id="auth-bar" style="display:flex;align-items:center;gap:6px"></div>
  <div class="tbst">
    <div class="tbsi"><span class="tbn">{n_total}</span><span class="tbl">Stocks</span></div>
    <div class="tbsi"><span class="tbn g">{n_graham}</span><span class="tbl">Graham</span></div>
    <div class="tbsi"><span class="tbn b">{n_lynch}</span><span class="tbl">Lynch</span></div>
    <div class="tbsi"><span class="tbn p">{n_buffett}</span><span class="tbl">Buffett</span></div>
    <div class="tbsi"><span class="tbn y">{n_pass}</span><span class="tbl">Pass All</span></div>
  </div>
  <div class="tbu">Updated {updated_at}</div>
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
  <div class="t10-hdr"><span class="t10-hdr-t">Top 10 This Week</span><span class="t10-hdr-s">Ranked by combined Graham + Lynch + Buffett score</span></div>
  {t10_html}
</div>

<div class="tw">
  <div class="tbar">
    <span class="tbrt">S&P 500 Value Screener &mdash; {n_total} Stocks</span>
    <span class="tbrm">P/E &middot; PEG &middot; D/E &middot; ROIC &middot; Graham &middot; Lynch &middot; Buffett &middot; MoS &middot; Rev Gr &middot; EPS Gr &middot; Op Mar</span>
  </div>
  <div class="tsc">
  <table class="t">
    <thead><tr>
      <th>Stock</th><th>Sector</th>
      <th class="tn" title="P/E TTM">P/E</th><th class="tn" title="PEG Ratio">PEG</th>
      <th class="tn" title="Debt/Equity">D/E</th><th class="tn" title="Return on Invested Capital">ROIC</th>
      <th title="Graham screen">Graham</th><th title="Lynch GARP">Lynch</th>
      <th title="Buffett quality">Buffett</th><th title="Pass All criteria">Pass All</th>
      <th title="Margin of Safety">MoS</th>
      <th class="tn" title="Revenue Growth YoY">Rev Gr</th>
      <th class="tn" title="EPS Growth">EPS Gr</th>
      <th class="tn" title="Operating Margin">Op Mar</th>
    </tr></thead>
    <tbody id="tbody">{rows}</tbody>
  </table>
  </div>
</div>

<!-- paywall rendered inline by JS -->

<div class="faq">
  <div class="faqh">How the Screener Works</div>
  <div class="faqi"><div class="faqq" onclick="fFaq(this)">What is the Graham screen? <span class="faqch">&#9660;</span></div><div class="faqa"><div class="faqai">Benjamin Graham&rsquo;s Graham Number: <strong>Candidate</strong> when price trades below &radic;(22.5 &times; TTM EPS &times; Book Value). <strong>Near Miss</strong> = within 10% of the Graham Number.</div></div></div>
  <div class="faqi"><div class="faqq" onclick="fFaq(this)">What is the Lynch screen? <span class="faqch">&#9660;</span></div><div class="faqa"><div class="faqai">Peter Lynch&rsquo;s GARP: <strong>Candidate</strong> requires PEG &lt; 1.0, EPS growth 10&ndash;30%, D/E &lt; 0.6.</div></div></div>
  <div class="faqi"><div class="faqq" onclick="fFaq(this)">What is the Buffett screen? <span class="faqch">&#9660;</span></div><div class="faqa"><div class="faqai">Quality moat approach: ROIC &gt; 15%, FCF Yield &gt; 5%, Revenue Growth &gt; 5%, Op Margin &gt; 15%.</div></div></div>
  <div class="faqi"><div class="faqq" onclick="fFaq(this)">How often is it updated? <span class="faqch">&#9660;</span></div><div class="faqa"><div class="faqai">Automatically Monday, Wednesday and Friday using live FMP API data. All metrics are TTM.</div></div></div>
</div>
<p class="disc">Not investment advice. Data from Financial Modeling Prep API. TTM metrics. &copy; <a href="{WP_URL}">Alert Invest</a></p>
</div>
<script>{JS}</script>
<!-- /wp:html -->"""


def deploy_page(html, updated_at):
    import base64
    # Try JWT auth first, fall back to Basic Auth (Application Passwords)
    token = None
    try:
        r = requests.post(f"{WP_URL}/wp-json/jwt-auth/v1/token",
                          json={"username":WP_USER,"password":WP_PASSWORD},timeout=15)
        if r.status_code == 200 and r.text.strip():
            token = r.json().get("token")
    except Exception as e:
        print(f"  JWT auth error: {e}")

    if token:
        headers = {"Authorization": f"Bearer {token}"}
        print("  Auth: JWT")
    else:
        # Fallback: Basic Auth with Application Password
        creds = base64.b64encode(f"{WP_USER}:{WP_PASSWORD}".encode()).decode()
        headers = {"Authorization": f"Basic {creds}"}
        print("  Auth: Basic (Application Password)")
    payload = {"title":"S&P 500 Value Stock Screener — Graham, Lynch & Buffett | Alert Invest",
               "content":html,"status":"publish","slug":WP_SLUG}
    search = requests.get(f"{WP_URL}/wp-json/wp/v2/pages",params={"slug":WP_SLUG},headers=headers,timeout=15).json()
    if search and isinstance(search,list) and len(search)>0:
        pid=search[0]["id"]
        res=requests.post(f"{WP_URL}/wp-json/wp/v2/pages/{pid}",headers=headers,json=payload,timeout=120)
        action="Updated"
    else:
        res=requests.post(f"{WP_URL}/wp-json/wp/v2/pages",headers=headers,json=payload,timeout=120)
        action="Created"
    if res.status_code in[200,201]:
        print(f"  ✅ {action}: {WP_URL}/{WP_SLUG}/"); return True
    else:
        print(f"  ✗ WP error {res.status_code}: {res.text[:300]}"); return False


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    updated_at=datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*60}\n  Alert Invest Screener Builder — {updated_at}\n{'='*60}\n")
    print("  Fetching Screener CSV...")
    sr=fetch_csv(SCREENER_CSV); print(f"  → {len(sr)} rows")
    print("  Fetching Top 10 CSV...")
    tr=fetch_csv(TOP10_CSV); print(f"  → {len(tr)} rows")
    stocks=parse_screener(sr); top10=parse_top10(tr)
    print(f"\n  Parsed {len(stocks)} stocks, {len(top10)} top 10 entries")
    if not stocks: print("  ✗ No stocks parsed"); return
    print("  Building HTML...")
    html=build_html(stocks,top10,updated_at); print(f"  → {len(html):,} chars")
    if args.dry_run:
        os.makedirs("output",exist_ok=True)
        open("output/screener.html","w",encoding="utf-8").write(html)
        print("  Saved: output/screener.html")
    else:
        print("  Deploying to WordPress..."); deploy_page(html,updated_at)
    print(f"\n{'='*60}\n  Done.\n")

if __name__=="__main__":
    main()
