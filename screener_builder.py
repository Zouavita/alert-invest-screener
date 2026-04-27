#!/usr/bin/env python3
import argparse, csv, io, json, os
from datetime import datetime
import requests

WP_URL      = "https://alert-invest.com"
WP_USER     = os.environ.get("WP_USER", "")
WP_PASSWORD = os.environ.get("WP_PASSWORD", "")
WP_SLUG     = "stock-screener"
FREE_ROWS   = 20
SCREENER_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRAgh9VdS0Ox8xrDf8XYCslQwCNuKfVRwJ9329YkEE7Fn5BtW4bkLrts19MnNjjkHbnp6twVB99Z21I/pub?gid=310948557&single=true&output=csv"
TOP10_CSV    = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRAgh9VdS0Ox8xrDf8XYCslQwCNuKfVRwJ9329YkEE7Fn5BtW4bkLrts19MnNjjkHbnp6twVB99Z21I/pub?gid=1532740227&single=true&output=csv"
PATREON_URL  = "https://www.patreon.com/cw/AlertInvest/membership"

def fetch_csv(url):
    r = requests.get(url, timeout=20); r.raise_for_status()
    return list(csv.reader(io.StringIO(r.text)))

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
        tk = d.get("Ticker","").strip().replace("\U0001f195","").strip()
        if tk and "\u2014" not in tk and "no stock" not in tk.lower():
            d["Ticker"] = tk; out.append(d)
    return out[:10]

SC = {"Technology":"#2563eb","Communication Services":"#7c3aed","Healthcare":"#059669",
      "Financials":"#d97706","Consumer Cyclical":"#ea580c","Consumer Defensive":"#65a30d",
      "Industrials":"#4f46e5","Energy":"#dc2626","Real Estate":"#0891b2",
      "Basic Materials":"#92400e","Utilities":"#0284c7","Insurance":"#b45309"}
def sc(s): return SC.get(s,"#64748b")

def sig(v):
    v=v.strip()
    if v=="Candidate": return '<span class="sig sg">&#10003; Cand</span>'
    if v=="Near Miss":  return '<span class="sig sn">~ Near</span>'
    if v=="PASS":       return '<span class="sig sp">&#10003; PASS</span>'
    if v=="FAIL":       return '<span class="sig sf">FAIL</span>'
    return '<span class="s0">&#8212;</span>'

def mos(v):
    v=v.strip()
    return f'<span style="color:#1d4ed8;font-weight:700;font-size:10px">{v}</span>' if v and v!="-" else '<span style="color:#d1d5db">&#8212;</span>'

def pct(v):
    try:
        f=float(v.strip().replace("%",""))
        return f'<span class="{"pos" if f>0 else "neg"}">{f:+.1f}%</span>'
    except: return '<span style="color:#d1d5db">&#8212;</span>'

def num(v,d=1):
    try: return f"{float(v.strip().replace('%','')):.{d}f}"
    except: return "&#8212;"

def build_html(stocks, top10, updated_at):
    sectors   = sorted(set(s.get("Sector","").strip() for s in stocks if s.get("Sector","").strip()))
    n_total   = len(stocks)
    n_graham  = sum(1 for s in stocks if s.get("Graham Screen")=="Candidate")
    n_lynch   = sum(1 for s in stocks if s.get("Lynch Screen")=="Candidate")
    n_buffett = sum(1 for s in stocks if s.get("Buffett Screen")=="Candidate")
    n_pass    = sum(1 for s in stocks if s.get("Pass All?")=="PASS")

    t10=""
    for i,t in enumerate(top10):
        rk=i+1; tk=t.get("Ticker",""); co=t.get("Company","")[:26]
        sec=t.get("Sector",""); sigs=t.get("Signals",""); score=t.get("Score","")
        c=sc(sec); rc="#f59e0b" if rk==1 else("#94a3b8" if rk==2 else("#cd7f32" if rk==3 else"#6b7280"))
        t10+=(f'<div class="t10c"><div class="t10t"><span class="t10r" style="color:{rc}">#{rk}</span>'
              f'<span class="t10k">{tk}</span></div><div class="t10n">{co}</div>'
              f'<div class="t10s" style="background:{c}18;color:{c}">{sec}</div>'
              f'<div class="t10g">{sigs}</div><div class="t10sc">{score}</div></div>')

    pills='<button class="chip on" onclick="fSec(this,\'\')" style="--cc:#374151">All</button>'
    for sec in sectors:
        c=sc(sec); pills+=f'<button class="chip" onclick="fSec(this,\'{sec}\')" style="--cc:{c}">{sec}</button>'

    rows=""
    for i,s in enumerate(stocks):
        tk=s.get("Ticker",""); co=s.get("Company",""); sec=s.get("Sector","")
        pe=s.get("P/E (Live)",""); peg=s.get("PEG (Live)",""); de=s.get("Debt/Equity","")
        roic=s.get("ROIC",""); gr=s.get("Graham Screen",""); ly=s.get("Lynch Screen","")
        bu=s.get("Buffett Screen",""); pa=s.get("Pass All?",""); ms=s.get("Margin of Safety","")
        rg=s.get("Rev Gr%",""); eg=s.get("EPS Growth",""); om=s.get("Op. Margin","")
        c=sc(sec)
        dg="true" if gr=="Candidate" else"false"; dl="true" if ly=="Candidate" else"false"
        db="true" if bu=="Candidate" else"false"; dp="true" if pa=="PASS" else"false"
        da="true" if(gr in("Candidate","Near Miss") or ly in("Candidate","Near Miss") or bu in("Candidate","Near Miss") or pa=="PASS")else"false"
        lk=" locked" if i>=FREE_ROWS else""
        rows+=(f'<tr class="sr{lk}" data-tk="{tk.lower()}" data-co="{co.lower()}" data-sec="{sec}" '
               f'data-g="{dg}" data-l="{dl}" data-b="{db}" data-p="{dp}" data-a="{da}">'
               f'<td class="tds"><span class="stk">{tk}</span><span class="sco">{co[:24]}</span></td>'
               f'<td><span style="background:{c}15;color:{c};font-size:9px;font-weight:700;padding:2px 5px;border-radius:2px;white-space:nowrap">{sec}</span></td>'
               f'<td class="tn">{num(pe)}</td><td class="tn">{num(peg,2)}</td><td class="tn">{num(de,2)}</td>'
               f'<td class="tn">{num(roic,1)}%</td><td>{sig(gr)}</td><td>{sig(ly)}</td><td>{sig(bu)}</td>'
               f'<td>{sig(pa)}</td><td>{mos(ms)}</td><td class="tn">{pct(rg)}</td>'
               f'<td class="tn">{pct(eg)}</td><td class="tn">{num(om,1)}%</td></tr>')

    schema={"@context":"https://schema.org","@type":"WebPage",
            "name":"S&P 500 Value Stock Screener — Graham, Lynch & Buffett | Alert Invest",
            "description":f"Screen {n_total} S&P 500 stocks using Graham, Lynch and Buffett criteria.",
            "url":f"{WP_URL}/stock-screener/","dateModified":updated_at,
            "publisher":{"@type":"Organization","name":"Alert Invest","url":WP_URL}}

    CSS="""*{box-sizing:border-box;margin:0;padding:0}
.entry-title,.page-title,h1.title{display:none!important}
.scr{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,sans-serif;font-size:12px;color:#111827;background:#eef0f3;min-height:100vh;padding:10px}
.scr a{color:#1d4ed8;text-decoration:none}.scr a:hover{text-decoration:underline}
.tb{background:#fff;border:1px solid #d1d5db;border-radius:5px;padding:9px 14px;margin-bottom:7px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}
.tbb{font-size:14px;font-weight:800;color:#0f172a;letter-spacing:-.4px}.tbb em{color:#2563eb;font-style:normal}
.tbst{display:flex;gap:1px;background:#e5e7eb;border-radius:4px;overflow:hidden}
.tbsi{padding:5px 12px;background:#fff;display:flex;flex-direction:column;align-items:center;gap:1px}
.tbn{font-size:14px;font-weight:800;color:#111827;line-height:1}.tbl{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:#6b7280}
.tbn.g{color:#16a34a}.tbn.b{color:#2563eb}.tbn.p{color:#7c3aed}.tbn.y{color:#d97706}
.tbu{font-size:10px;color:#9ca3af;border:1px solid #e5e7eb;border-radius:3px;padding:3px 8px}
.fb{background:#fff;border:1px solid #d1d5db;border-radius:5px;padding:8px 12px;margin-bottom:7px}
.fr{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.fr+.fr{margin-top:6px;padding-top:6px;border-top:1px solid #f3f4f6}
.fl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#9ca3af;min-width:60px}
.chip{display:inline-flex;align-items:center;padding:3px 9px;border-radius:3px;border:1px solid #d1d5db;background:#fff;font-size:11px;font-weight:600;color:#374151;cursor:pointer;transition:all .1s;white-space:nowrap;line-height:1.5;font-family:inherit}
.chip:hover{border-color:var(--cc,#2563eb);color:var(--cc,#2563eb)}
.chip.on{background:var(--cc,#374151);border-color:var(--cc,#374151);color:#fff}
.sw{flex:1;min-width:160px;max-width:260px;position:relative}
.si{width:100%;padding:4px 8px 4px 24px;border:1px solid #d1d5db;border-radius:3px;font-size:11px;color:#374151;outline:none;font-family:inherit}
.si:focus{border-color:#2563eb;box-shadow:0 0 0 2px #dbeafe}
.sic{position:absolute;left:7px;top:50%;transform:translateY(-50%);color:#9ca3af;font-size:11px;pointer-events:none}
.rc{font-size:11px;color:#6b7280;margin-left:auto;white-space:nowrap}
.t10{background:#fff;border:1px solid #d1d5db;border-radius:5px;overflow:hidden;margin-bottom:7px}
.t10h{background:#0f172a;padding:7px 12px;display:flex;align-items:center;gap:10px}
.t10ht{font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:.05em}
.t10hs{font-size:10px;color:rgba(255,255,255,.4)}
.t10g{display:grid;grid-template-columns:repeat(5,1fr)}
.t10c{padding:7px 10px;border-right:1px solid #e5e7eb;border-bottom:1px solid #e5e7eb}
.t10c:hover{background:#f8fafc}.t10c:nth-child(5n){border-right:none}.t10c:nth-child(n+6){border-bottom:none}
.t10t{display:flex;align-items:baseline;gap:5px;margin-bottom:1px}
.t10r{font-size:10px;font-weight:700}.t10k{font-size:12px;font-weight:800;color:#1d4ed8}
.t10n{font-size:10px;color:#6b7280;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.t10s{display:inline-block;font-size:9px;font-weight:700;padding:1px 5px;border-radius:2px;margin-bottom:3px}
.t10g-txt{font-size:9px;color:#2563eb;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.t10sc{font-size:9px;font-weight:700;color:#15803d;margin-top:1px}
.tw{background:#fff;border:1px solid #d1d5db;border-radius:5px;overflow:hidden}
.tbar{padding:6px 12px;border-bottom:1px solid #e5e7eb;background:#f9fafb;display:flex;align-items:center;justify-content:space-between}
.tbrt{font-size:11px;font-weight:700;color:#374151}.tbrm{font-size:10px;color:#9ca3af}
.tsc{overflow-x:auto}
table.t{width:100%;border-collapse:collapse;font-size:11px}
table.t thead th{padding:5px 8px;background:#f9fafb;border-bottom:2px solid #e5e7eb;text-align:left;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;white-space:nowrap;cursor:pointer;position:sticky;top:0;z-index:2}
table.t thead th.tn{text-align:right}
table.t thead th:hover{color:#2563eb;background:#eff6ff}
table.t tbody td{padding:4px 8px;border-bottom:1px solid #f3f4f6;vertical-align:middle}
table.t tbody tr:hover td{background:#f8fafc!important}
table.t tbody tr:nth-child(even) td{background:#fafafa}
.tds{min-width:130px}.stk{font-size:11px;font-weight:800;color:#1d4ed8;display:block}.sco{font-size:10px;color:#9ca3af;display:block}
.tn{text-align:right;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:#374151}
.pos{color:#15803d;font-weight:700}.neg{color:#b91c1c;font-weight:700}
.sig{display:inline-flex;align-items:center;font-size:9px;font-weight:700;padding:2px 5px;border-radius:2px;white-space:nowrap}
.sg{background:#dcfce7;color:#15803d}.sn{background:#fef9c3;color:#92400e}.sp{background:#dbeafe;color:#1d4ed8}.sf{background:#f3f4f6;color:#9ca3af}.s0{color:#e5e7eb;font-size:10px}
.locked td{filter:blur(5px);user-select:none;pointer-events:none;opacity:.7}
.pw{position:relative;margin-top:-90px;z-index:10;padding:0 12px 10px}
.pwc{background:#fff;border:1px solid #d1d5db;border-radius:8px;padding:28px 24px;text-align:center;max-width:460px;margin:0 auto;box-shadow:0 8px 30px rgba(0,0,0,.10)}
.pwl{font-size:22px;margin-bottom:8px}.pwt{font-size:15px;font-weight:800;color:#0f172a;margin-bottom:6px}
.pws{font-size:12px;color:#6b7280;line-height:1.65;margin-bottom:14px}
.pwf{display:flex;flex-wrap:wrap;gap:4px;justify-content:center;margin-bottom:16px}
.pwf span{background:#eff6ff;color:#2563eb;font-size:10px;font-weight:700;padding:2px 8px;border-radius:2px}
.pwb{display:inline-block;background:#2563eb;color:#fff;font-size:13px;font-weight:700;padding:9px 22px;border-radius:4px;text-decoration:none}
.pwb:hover{background:#1d4ed8;color:#fff;text-decoration:none}
.pwn{font-size:10px;color:#9ca3af;margin-top:8px}
.faq{margin-top:8px;background:#fff;border:1px solid #d1d5db;border-radius:5px;overflow:hidden}
.faqh{padding:7px 12px;background:#f9fafb;border-bottom:1px solid #e5e7eb;font-size:10px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:.05em}
.faqi{border-bottom:1px solid #f3f4f6}.faqi:last-child{border:none}
.faqq{padding:9px 12px;font-size:12px;font-weight:600;color:#374151;cursor:pointer;display:flex;justify-content:space-between;align-items:center}
.faqq:hover{background:#f8fafc;color:#2563eb}
.faqch{font-size:9px;color:#9ca3af;transition:transform .2s}
.faqa{max-height:0;overflow:hidden;transition:max-height .25s,opacity .25s;opacity:0}
.faqa.open{opacity:1}.faqai{padding:4px 12px 10px;font-size:11px;line-height:1.75;color:#6b7280}
.disc{font-size:10px;color:#9ca3af;margin-top:8px;text-align:center;line-height:1.65;padding:6px}
@media(max-width:900px){.t10g{grid-template-columns:repeat(2,1fr)}table.t th:nth-child(n+9),table.t td:nth-child(n+9){display:none}}
@media(max-width:600px){.t10g{grid-template-columns:1fr 1fr}table.t th:nth-child(n+6),table.t td:nth-child(n+6){display:none}}"""

    JS="""var gP='all',gS='',gQ='';
function apply(){
  var rows=document.querySelectorAll('#tbody .sr'),shown=0;
  rows.forEach(function(r){
    var ok=true;
    if(gP==='g'&&r.dataset.g!=='true')ok=false;
    else if(gP==='l'&&r.dataset.l!=='true')ok=false;
    else if(gP==='b'&&r.dataset.b!=='true')ok=false;
    else if(gP==='p'&&r.dataset.p!=='true')ok=false;
    else if(gP==='a'&&r.dataset.a!=='true')ok=false;
    if(gS&&r.dataset.sec!==gS)ok=false;
    if(gQ&&r.dataset.tk.indexOf(gQ)===-1&&r.dataset.co.indexOf(gQ)===-1)ok=false;
    r.style.display=ok?'':'none';if(ok)shown++;
  });
  var el=document.getElementById('rcnt');
  if(el)el.textContent=shown+' result'+(shown!==1?'s':'');
}
function fPhil(btn,v){
  gP=v;document.querySelectorAll('.chip[onclick*="fPhil"]').forEach(function(b){b.classList.remove('on')});
  btn.classList.add('on');apply();
}
function fSec(btn,v){
  gS=v;document.querySelectorAll('.chip[onclick*="fSec"]').forEach(function(b){b.classList.remove('on')});
  btn.classList.add('on');apply();
}
function fSrch(v){gQ=v.toLowerCase().trim();apply();}
function fFaq(q){
  var a=q.nextElementSibling,ch=q.querySelector('.faqch'),open=a.classList.contains('open');
  a.classList.toggle('open',!open);ch.style.transform=open?'':'rotate(180deg)';
  a.style.maxHeight=open?'0':(a.scrollHeight+20)+'px';
}"""

    return f"""<!-- wp:html -->
<script type="application/ld+json">{json.dumps(schema)}</script>
<style>{CSS}</style>
<div class="scr">
<div class="tb">
  <div class="tbb">Alert<em>Invest</em> <span style="font-size:11px;font-weight:400;color:#6b7280">/ S&P 500 Screener</span></div>
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
<div class="t10">
  <div class="t10h"><span class="t10ht">Top 10 This Week</span><span class="t10hs">Ranked by combined Graham + Lynch + Buffett score</span></div>
  <div class="t10g">{t10}</div>
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
      <th class="tn" title="P/E TTM">P/E</th><th class="tn" title="PEG">PEG</th>
      <th class="tn" title="Debt/Equity">D/E</th><th class="tn" title="ROIC">ROIC</th>
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
<div class="pw">
  <div class="pwc">
    <div class="pwl">&#128274;</div>
    <div class="pwt">Unlock the Full Screener</div>
    <div class="pws">You&rsquo;re seeing <strong>{FREE_ROWS} of {n_total} stocks</strong>. Upgrade to access all results and weekly updates.</div>
    <div class="pwf">
      <span>&#10003; {n_total} S&P 500 stocks</span><span>&#10003; Graham / Lynch / Buffett</span>
      <span>&#10003; Margin of Safety</span><span>&#10003; Mon &middot; Wed &middot; Fri</span>
    </div>
    <a href="{PATREON_URL}" class="pwb">Unlock with Patreon</a>
    <div class="pwn">Cancel anytime &middot; Instant access</div>
  </div>
</div>
<div class="faq">
  <div class="faqh">How the Screener Works</div>
  <div class="faqi"><div class="faqq" onclick="fFaq(this)">What is the Graham screen? <span class="faqch">&#9660;</span></div><div class="faqa"><div class="faqai">Benjamin Graham&rsquo;s Graham Number: <strong>Candidate</strong> when price trades below &radic;(22.5 &times; TTM EPS &times; Book Value). <strong>Near Miss</strong> = within 10%.</div></div></div>
  <div class="faqi"><div class="faqq" onclick="fFaq(this)">What is the Lynch screen? <span class="faqch">&#9660;</span></div><div class="faqa"><div class="faqai">Peter Lynch&rsquo;s GARP: <strong>Candidate</strong> requires PEG &lt; 1.0, EPS growth 10&ndash;30%, D/E &lt; 0.6.</div></div></div>
  <div class="faqi"><div class="faqq" onclick="fFaq(this)">What is the Buffett screen? <span class="faqch">&#9660;</span></div><div class="faqa"><div class="faqai">Quality moat approach: ROIC &gt; 15%, FCF Yield &gt; 5%, Revenue Growth &gt; 5%, Op Margin &gt; 15%.</div></div></div>
  <div class="faqi"><div class="faqq" onclick="fFaq(this)">How often is it updated? <span class="faqch">&#9660;</span></div><div class="faqa"><div class="faqai">Automatically Monday, Wednesday and Friday using live FMP API data. All metrics are TTM.</div></div></div>
</div>
<p class="disc">Not investment advice. Data from Financial Modeling Prep API. TTM metrics. &copy; <a href="{WP_URL}">Alert Invest</a></p>
</div>
<script>{JS}</script>
<!-- /wp:html -->"""

def deploy_page(html, updated_at):
    auth = requests.post(f"{WP_URL}/wp-json/jwt-auth/v1/token",
                         json={"username":WP_USER,"password":WP_PASSWORD},timeout=15).json()
    token = auth.get("token")
    if not token:
        print(f"  ✗ WP auth failed: {auth}"); return False
    headers = {"Authorization":f"Bearer {token}"}
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
