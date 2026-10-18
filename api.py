"""FastAPI + Tailwind version of the dashboard.  Run:  uvicorn api:app --reload
Open http://127.0.0.1:8000  (interactive API docs at /docs)."""
from __future__ import annotations

import json
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

import analysis, config, db, logger, model, timers

app = FastAPI(title="Virtual League Analytics")
engine = db.get_engine()
db.init_db(engine)

ODDS = ["odds_1", "odds_x", "odds_2", "odds_over25", "odds_under25", "odds_gg", "odds_ng"]


class FixtureIn(BaseModel):
    home: str
    away: str
    odds_1: Optional[float] = None
    odds_x: Optional[float] = None
    odds_2: Optional[float] = None
    odds_over25: Optional[float] = None
    odds_under25: Optional[float] = None
    odds_gg: Optional[float] = None
    odds_ng: Optional[float] = None


class MatchIn(FixtureIn):
    bookmaker: str
    cycle_id: Optional[int] = None
    round_no: Optional[int] = None
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None


class PredictIn(BaseModel):
    bookmaker: str
    fixtures: list[FixtureIn]
    cycles: int = 5
    min_edge: float = config.MIN_EDGE
    strict: bool = False


class SyncIn(BaseModel):
    round_no: int = 1


def _json(df: pd.DataFrame):
    return json.loads(df.to_json(orient="records"))   # NaN -> null


def _data(bookmaker: str) -> pd.DataFrame:
    raw = db.matches_df(engine, bookmaker)
    return analysis.prepare(raw) if not raw.empty else raw


@app.get("/api/clock")
def clock():
    c, r = timers.locate()
    return dict(anchor=timers.get_anchor(), cycle_id=c, round_no=r,
                match_sec=config.MATCH_INTERVAL_SEC, cycle_sec=config.CYCLE_INTERVAL_SEC,
                rounds_per_cycle=config.ROUNDS_PER_CYCLE,
                next_match_in=timers.seconds_to_next_match(), next_cycle_in=timers.seconds_to_next_cycle())


@app.post("/api/clock/sync")
def sync(body: SyncIn):
    import time
    timers.set_anchor(time.time() - (body.round_no - 1) * config.MATCH_INTERVAL_SEC)
    return clock()


@app.post("/api/matches")
def add_match(m: MatchIn):
    d = m.model_dump()
    mid = logger.add_match(engine, d.pop("bookmaker"), d.pop("home"), d.pop("away"),
                           d.pop("cycle_id"), d.pop("round_no"), **d)
    settled = db.settle_open_bets(engine)
    analysis.save_cycle_summaries(engine)
    return {"id": mid, "settled_bets": settled}


@app.get("/api/cycles")
def cycles(bookmaker: str):
    df = _data(bookmaker)
    return [] if df.empty else _json(analysis.cycle_table(df))


@app.get("/api/rolling")
def rolling(bookmaker: str):
    df = _data(bookmaker)
    return [] if df.empty else _json(analysis.rolling_windows(df))


@app.get("/api/deviations")
def deviations(bookmaker: str):
    df = _data(bookmaker)
    return [] if df.empty else _json(analysis.deviation_report(df))


@app.get("/api/independence")
def independence(bookmaker: str):
    df = _data(bookmaker)
    return [] if df.empty else _json(analysis.independence_tests(df))


@app.get("/api/ratings")
def ratings(bookmaker: str, cycles: int = Query(5, ge=1, le=20)):
    df = _data(bookmaker)
    return [] if df.empty else _json(model.ratings_table(model.fit_strengths(df, cycles=cycles)))


@app.post("/api/predict")
def predict(body: PredictIn):
    df = _data(body.bookmaker)
    if df.empty:
        return []
    sm = model.fit_strengths(df, cycles=body.cycles)
    rows = []
    for f in body.fixtures:
        rows += model.predict_fixture(sm, f.model_dump(), body.min_edge, body.strict)
    return _json(pd.DataFrame(rows))


@app.get("/api/performance")
def performance(bookmaker: str):
    b = db.bets_df(engine, bookmaker)
    done = b[b.status != "open"] if not b.empty else b
    if done.empty:
        return []
    per = done.groupby("cycle_id").agg(bets=("id", "count"),
                                       wins=("status", lambda s: int((s == "won").sum())),
                                       pnl=("pnl", "sum")).reset_index()
    per["losses"] = per.bets - per.wins
    per["win_rate"] = per.wins / per.bets
    per["roi"] = per.pnl / per.bets
    return _json(per)


@app.get("/api/export/{table}.csv")
def export(table: str, bookmaker: str | None = None):
    df = db.bets_df(engine, bookmaker) if table == "bets" else db.matches_df(engine, bookmaker)
    return Response(df.to_csv(index=False), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={table}.csv"})


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Virtual League Analytics</title>
<script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-slate-950 text-slate-200 min-h-screen">
<div class="max-w-6xl mx-auto p-4 space-y-6">
 <header class="flex flex-wrap items-center justify-between gap-3">
  <h1 class="text-xl font-bold">Virtual League Analytics</h1>
  <div class="flex gap-2 items-center text-sm">
   <select id="bk" class="bg-slate-800 rounded px-2 py-1"><option>SportyBet</option><option>Betika</option><option>DEMO</option></select>
   <select id="sync" class="bg-slate-800 rounded px-2 py-1"></select>
   <button onclick="syncClock()" class="bg-slate-700 hover:bg-slate-600 rounded px-2 py-1">Sync clock</button>
  </div></header>

 <section class="grid md:grid-cols-2 gap-4">
  <div class="rounded-xl bg-slate-900 p-4"><div class="text-xs opacity-60">NEXT ROUND (3-MIN)</div><div id="tm" class="text-5xl font-bold">--:--</div></div>
  <div class="rounded-xl bg-slate-800 p-4"><div class="text-xs opacity-60">MACRO CYCLE RESET (30-MIN)</div><div id="tc" class="text-5xl font-bold">--:--</div><div id="rn" class="text-xs opacity-60"></div></div>
 </section>

 <section class="rounded-xl bg-slate-900 p-4 space-y-3">
  <div class="flex justify-between items-center"><h2 class="font-semibold">Upcoming fixtures and live odds</h2>
   <div class="flex gap-2 text-sm">
    <button onclick="addRow()" class="bg-slate-700 rounded px-2 py-1">+ Row</button>
    <label class="flex items-center gap-1"><input id="strict" type="checkbox"> strict (EV &gt; margin)</label>
    <button onclick="predict()" class="bg-emerald-600 hover:bg-emerald-500 rounded px-3 py-1">Predict</button></div></div>
  <div class="overflow-x-auto"><table class="text-sm w-full"><thead class="opacity-60 text-left"><tr>
   <th>Home</th><th>Away</th><th>1</th><th>X</th><th>2</th><th>O2.5</th><th>U2.5</th><th>GG</th><th>NG</th></tr></thead>
   <tbody id="fx"></tbody></table></div>
  <div class="overflow-x-auto"><table class="text-sm w-full"><thead class="opacity-60 text-left"><tr>
   <th>Match</th><th>Sel</th><th>Model %</th><th>Model odds</th><th>Book</th><th>Edge</th><th>EV</th><th>Margin</th><th>Data cover</th></tr></thead>
   <tbody id="out"></tbody></table></div>
  <p class="text-xs opacity-60">Data cover = how much recent data backs both teams, not a win probability. Highlighted rows are flagged value; virtual results are RNG-driven, so verify with the backtest before trusting any flag.</p>
 </section>

 <section class="grid md:grid-cols-2 gap-4">
  <div class="rounded-xl bg-slate-900 p-4"><h2 class="font-semibold mb-2">Rolling windows (1 / 3 / 5 cycles)</h2><div id="roll" class="text-sm overflow-x-auto"></div></div>
  <div class="rounded-xl bg-slate-900 p-4"><h2 class="font-semibold mb-2">Win/loss per 30-min session (paper bets)</h2><div id="perf" class="text-sm overflow-x-auto"></div>
   <div class="mt-3 text-sm flex gap-3"><a id="eb" class="underline">bets.csv</a><a id="em" class="underline">matches.csv</a></div></div>
  <div class="rounded-xl bg-slate-900 p-4"><h2 class="font-semibold mb-2">Team ratings</h2><div id="rate" class="text-sm overflow-x-auto"></div></div>
  <div class="rounded-xl bg-slate-900 p-4"><h2 class="font-semibold mb-2">Does the data show resets / "overdue"?</h2><div id="ind" class="text-sm overflow-x-auto"></div></div>
 </section>
</div>
<script>
const $=id=>document.getElementById(id), bk=()=>$('bk').value;
const pad=n=>String(n).padStart(2,'0'), fmt=ms=>{const s=Math.ceil(ms/1000);return pad(Math.floor(s/60))+':'+pad(s%60)};
let clk=null;
async function j(u,o){const r=await fetch(u,o);return r.json()}
async function loadClock(){clk=await j('/api/clock');
 $('sync').innerHTML=Array.from({length:clk.rounds_per_cycle},(_,i)=>`<option value="${i+1}">now = round ${i+1}</option>`).join('')}
function tick(){if(!clk)return;const A=clk.anchor*1000,M=clk.match_sec*1000,C=clk.cycle_sec*1000,off=Date.now()-A;
 const mm=((off%M)+M)%M,cc=((off%C)+C)%C;$('tm').textContent=fmt(M-mm);$('tc').textContent=fmt(C-cc);
 $('rn').textContent='Round '+(Math.floor(cc/M)+1)+' of '+clk.rounds_per_cycle+' in this block'}
async function syncClock(){await j('/api/clock/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({round_no:+$('sync').value})});await loadClock()}
function table(rows,fmts={}){if(!rows.length)return '<span class="opacity-60">No data yet.</span>';const ks=Object.keys(rows[0]);
 return '<table class="w-full"><thead class="opacity-60 text-left"><tr>'+ks.map(k=>`<th class="pr-3">${k}</th>`).join('')+'</tr></thead><tbody>'+
 rows.map(r=>'<tr>'+ks.map(k=>{let v=r[k];if(typeof v==='number')v=fmts[k]?fmts[k](v):(Number.isInteger(v)?v:v.toFixed(3));return `<td class="pr-3">${v??''}</td>`}).join('')+'</tr>').join('')+'</tbody></table>'}
const pct=v=>(v*100).toFixed(1)+'%';
function addRow(){const tr=document.createElement('tr');
 tr.innerHTML='<td><input class="bg-slate-800 rounded px-1 w-28" placeholder="Home"></td><td><input class="bg-slate-800 rounded px-1 w-28" placeholder="Away"></td>'+
 Array.from({length:7},()=>'<td><input type="number" step="0.01" class="bg-slate-800 rounded px-1 w-16"></td>').join('');$('fx').appendChild(tr)}
async function predict(){const keys=['odds_1','odds_x','odds_2','odds_over25','odds_under25','odds_gg','odds_ng'];
 const fixtures=[...$('fx').children].map(tr=>{const i=tr.querySelectorAll('input'),o={home:i[0].value.trim(),away:i[1].value.trim()};
  keys.forEach((k,n)=>o[k]=i[n+2].value?+i[n+2].value:null);return o}).filter(f=>f.home&&f.away);
 const res=await j('/api/predict',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bookmaker:bk(),fixtures,strict:$('strict').checked})});
 const f=v=>v==null?'':pct(v);
 $('out').innerHTML=res.length?res.sort((a,b)=>(b.ev??-9)-(a.ev??-9)).map(r=>`<tr class="${r.value?'bg-emerald-900/40':''}"><td>${r.home} v ${r.away}</td><td>${r.selection}</td><td>${pct(r.model_prob)}</td><td>${r.model_odds.toFixed(2)}</td><td>${r.book_odds??''}</td><td>${f(r.edge_pp)}</td><td>${f(r.ev)}</td><td>${f(r.margin)}</td><td>${pct(r.confidence)}</td></tr>`).join(''):'<tr><td colspan=9 class="opacity-60">Log completed matches first.</td></tr>'}
async function refresh(){const b=encodeURIComponent(bk());
 $('roll').innerHTML=table(await j('/api/rolling?bookmaker='+b),{avg_goals:v=>v.toFixed(2),home_win_pct:pct,draw_pct:pct,away_win_pct:pct,over25_pct:pct,btts_pct:pct});
 $('perf').innerHTML=table(await j('/api/performance?bookmaker='+b),{win_rate:pct,roi:pct,pnl:v=>v.toFixed(2)});
 $('rate').innerHTML=table((await j('/api/ratings?bookmaker='+b)).slice(0,20));
 $('ind').innerHTML=table(await j('/api/independence?bookmaker='+b),{p_value:v=>v.toFixed(3)});
 $('eb').href='/api/export/bets.csv?bookmaker='+b;$('em').href='/api/export/matches.csv?bookmaker='+b}
$('bk').onchange=refresh;addRow();addRow();loadClock().then(()=>{tick();setInterval(tick,250)});refresh();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE
