"""The board: one self-refreshing HTML page per controller, written on every tick.

Open it in Orca's browser tab (file:// URL from `runway board`) beside the loop tab.
Columns: Queued, Implementing, In review, Merged, Waiting on you.
"""

import html

from . import journal as jn

COLUMNS = (
    ('Queued', ('queued',)),
    ('Implementing', ('building', 'build-failed', 'review-failed')),
    ('In review', ('built', 'reviewing', 'review-passed')),
    ('Merged', ('merged', 'dropped')),
    ('Waiting on you', ('needs-you',)),
)
NOTE = {'build-failed': 'fix pass due', 'review-failed': 'fix pass due', 'built': 'review due',
        'review-passed': 'landing', 'dropped': 'dropped'}

STYLE = """
:root { --bg:#f7f7f5; --card:#fff; --ink:#1d1d1b; --muted:#6b6b66; --line:#e2e2dc; --accent:#2f6fde; --warn:#b5541b; }
@media (prefers-color-scheme: dark) { :root { --bg:#171716; --card:#222220; --ink:#ecece8; --muted:#9a9a93; --line:#33332f; --accent:#7aa7ff; --warn:#f0a070; } }
* { box-sizing: border-box; }
body { margin:0; padding:16px; background:var(--bg); color:var(--ink); font:14px/1.4 -apple-system, system-ui, sans-serif; }
header { display:flex; flex-wrap:wrap; gap:8px 20px; align-items:baseline; margin-bottom:14px; }
h1 { font-size:17px; margin:0; }
.meta { color:var(--muted); }
.state { font-weight:600; color:var(--accent); }
.state.paused, .state.stopped { color:var(--warn); }
.cols { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:12px; }
.col h2 { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); margin:0 0 8px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:8px 10px; margin-bottom:8px; }
.card .id { font-weight:600; }
.card .sub { color:var(--muted); font-size:12px; }
.col.you .card { border-color:var(--warn); }
"""


def render(data, beat=None):
    st = jn.states(data)
    t = data['tickets']
    merged = {x for x, s in st.items() if s['state'] in ('merged', 'dropped')}
    # Open Engine's two pauses: a worker's question (answer it in Orca, the worker resumes)
    # and a hold (only you can decide: a stuck ticket, or the chunk PR at the gate).
    asks = {e.get('ticket'): ('question: ' if e['kind'] == 'question' else 'hold: ') + e['reason']
            for e in data['events'] if e['kind'] in ('needs-you', 'question')}
    cols = []
    for label, states in COLUMNS:
        cards = []
        for tid in data['order']:
            s = st[tid]
            if s['state'] not in states and not (label == 'Waiting on you' and tid in asks and s['state'] != 'merged'):
                continue
            bits = []
            if s.get('machine') and s['state'] in ('building', 'reviewing'):
                bits.append(f'{s["machine"]} · {s.get("built_by", "")}' if s['state'] == 'building' else s['machine'])
            if s['state'] in NOTE:
                bits.append(NOTE[s['state']])
            if s['state'] == 'queued':
                waits = [b for b in t[tid]['blocked_by'] if b not in merged]
                bits.append('waits on ' + ', '.join(waits) if waits else 'ready')
            if label == 'Waiting on you':
                bits = [asks.get(tid) or s.get('reason', '')]
            cards.append(f'<div class="card"><div class="id">{html.escape(tid)}</div>'
                         f'<div>{html.escape(t[tid]["title"])}</div>'
                         f'<div class="sub">{html.escape(" · ".join(b for b in bits if b))}</div></div>')
        if label == 'Waiting on you' and None in asks:
            cards.append(f'<div class="card"><div class="id">chunk</div><div class="sub">{html.escape(asks[None])}</div></div>')
        cls = ' you' if label == 'Waiting on you' else ''
        cols.append(f'<section class="col{cls}"><h2>{label} ({len(cards)})</h2>{"".join(cards)}</section>')
    state = 'no heartbeat'
    if beat:
        state = 'paused' if beat.get('paused') else beat.get('state', '?')
    last = (beat or {}).get('last_pickup')
    pickup = f'last pickup {last["ticket"]} on {last["machine"]} at {last["at"]}' if last else 'nothing picked up yet'
    resting = ''.join(f'<span class="state paused">{html.escape(a)} resting until {html.escape(u)}</span>'
                      for a, u in ((beat or {}).get('resting') or {}).items())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="15"><title>Runway board</title><style>{STYLE}</style></head>
<body><header><h1>{html.escape(data['chunk'])}</h1>
<span class="state {html.escape(state)}">loop {html.escape(state)}</span>
<span class="meta">{html.escape(pickup)}</span>{resting}
<span class="meta">{html.escape(data['branch'])} → {html.escape(data['base'])} · risk {jn.chunk_risk(data)}</span>
<span class="meta">updated {html.escape((beat or {}).get('at', ''))}</span></header>
<div class="cols">{''.join(cols)}</div></body></html>
"""


def write(data, beat=None):
    path = jn.home() / 'board.html'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(data, beat))
    return path
