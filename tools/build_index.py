"""Generate index.html from the 'Thrice Report' design canvas.

The design was authored as a .dc.html artboard (project ae7bda03). That format
carries canvas-authoring scaffolding that cannot ship: <x-dc>/<helmet> wrappers,
{{ prop }} bindings resolved by support.js (the dc-runtime React compiler),
<sc-if> conditionals, a DCLogic state class, and <image-slot> placeholders from
image-slot.js. All of it is compiled away here:

  {{ props }}   resolved to real values measured from the artifacts
  <sc-if>       replaced by CSS-only filtering (hidden radios + :checked ~)
  DCLogic       replaced by <details>/<summary> for the diagnosis toggles
  <image-slot>  replaced by real base64 screenshots from the #4075 attempt pair

The result keeps the page script-free, which the design's interactivity would
otherwise have required.
"""

from __future__ import annotations

import base64
import glob
import html
import json
import pathlib

# ---------------------------------------------------------------- data

def load_attempts() -> dict:
    best = {}
    for f in glob.glob('artifacts/*/attempt.json'):
        d = json.load(open(f))
        if not d.get('runs'):
            continue
        k = (str(d['issue']['number']), d['app']['version'])
        if k not in best or d['started_at'] > best[k]['started_at']:
            best[k] = d
    return best

BEST = load_attempts()

ENTRIES = [
    # num, buggy, fixed, kind, diagnosis heading, diagnosis body
    ("4075", "2.19.0", "2.20.0", "correct", None, None),
    ("3571", "2.16.0", "2.17.0", "correct", None, None),
    ("3804", "2.17.0", "2.18.0", "correct", None, None),
    ("4045", "2.19.0", "2.20.0", "incorrect", "Diagnosis: false positive",
     "Resizer read absent on both releases though the screenshot shows the correct state. "
     "The bug was in thrice, not jaeger: the evaluator pinned <code>.first</code>, so "
     "<code>element_visible</code> answered the wrong question when several elements matched."),
    ("3967", "2.18.0", "2.19.0", "incorrect", "Diagnosis: false negative",
     "The view-mode pin that keeps one plan valid across a pair waits for a toggle that "
     "shipped in 2.19.0, so it cannot exist at 2.18.0."),
    ("3468", "2.16.0", "2.17.0", "inconclusive", "Why no verdict",
     "All three browsers failed identically on the buggy release: the compare route renders "
     "the same on both releases, so the plan never reached the state the bug needs and no "
     "predicate was ever evaluated. The entry is excluded from precision and recall rather "
     "than resolved by guessing."),
]

def esc(x) -> str:
    return html.escape(str(x))

def b64(path: str) -> str | None:
    p = pathlib.Path(path)
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else None

# real run window, from the attempts themselves
stamps = sorted(d['started_at'] for d in BEST.values())
DATE_RANGE = stamps[0][:10] if stamps[0][:10] == stamps[-1][:10] else f"{stamps[0][:10]} / {stamps[-1][:10]}"
ATTEMPTS = len(BEST)

# ---------------------------------------------------------------- palette / type

CSS = """
:root{
  --paper:#EFEBE3; --ink:#171412; --mid:#55504A; --rule:#C4BCAF;
  --brass:#7A6A3F; --red:#8C1D2B;
  --sans:'Public Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
  --serif:Newsreader,Georgia,'Times New Roman',serif;
  --black:UnifrakturMaguntia,Newsreader,Georgia,serif;
  --mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
html,body{margin:0;padding:0;background:var(--paper)}
body{color:var(--ink);font-family:var(--sans);-webkit-font-smoothing:antialiased;
  font-feature-settings:"tnum" 1}
a{color:var(--ink);text-decoration:underline;text-decoration-thickness:1px;
  text-underline-offset:3px;text-decoration-color:var(--rule)}
a:hover{color:var(--red);text-decoration-color:var(--red)}
.wrap{position:relative;z-index:1;max-width:1100px;margin:0 auto;
  padding:clamp(22px,4vw,56px) clamp(15px,4vw,64px) 0}
.eyebrow{font:500 10px/1 var(--sans);letter-spacing:.18em;text-transform:uppercase;color:var(--brass)}
.cap{font:500 9px/1.2 var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--mid)}
.mono{font-family:var(--mono)}
h2{margin:0;font-family:var(--serif);font-weight:400;
  font-size:clamp(22px,3vw,30px);letter-spacing:-.01em}
.hd{display:flex;align-items:baseline;justify-content:space-between;gap:16px;
  padding-bottom:14px;border-bottom:1px solid var(--ink)}
section{padding:clamp(22px,3vw,36px) 0 0}
code{font-family:var(--mono);font-size:.86em}

/* masthead */
header.mast{display:flex;flex-direction:column;gap:clamp(8px,1.4vw,14px);
  padding-bottom:clamp(12px,1.8vw,18px);border-bottom:1px solid var(--ink)}
.wordmark{font-family:var(--black);font-weight:400;font-size:clamp(46px,8vw,86px);
  line-height:1;letter-spacing:.01em}
.lede{margin:0;font-family:var(--serif);font-size:clamp(16.5px,2.4vw,26px);
  line-height:1.35;letter-spacing:-.01em;max-width:880px;text-wrap:pretty}
.sub{margin:0;font-size:clamp(12.5px,1.4vw,14.5px);line-height:1.5;color:var(--mid);
  max-width:640px;text-wrap:pretty}

/* certificate fields */
.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));
  gap:16px clamp(18px,3vw,44px);padding:13px 0;border-bottom:1px solid var(--rule)}
.fieldpair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px clamp(18px,3vw,44px)}
.field{display:flex;flex-direction:column;justify-content:space-between;gap:6px}
.field .cap{min-height:2.4em}
.field .val{font-family:var(--mono);font-size:12px;white-space:nowrap}

/* hero */
.numrow{display:flex;flex-wrap:nowrap;gap:clamp(20px,6vw,84px);align-items:stretch;justify-content:center}
.numcell{flex:1 1 0;display:flex;flex-direction:column;align-items:center;gap:8px;min-width:0}
.num{font-family:var(--serif);font-weight:300;font-size:clamp(58px,13.5vw,152px);
  line-height:.86;letter-spacing:-.035em}
.vrule{width:1px;align-self:stretch;background:var(--rule)}
.brassrule{height:2px;background:var(--brass);margin:clamp(14px,2vw,22px) 0 clamp(12px,1.6vw,18px)}
.claim{display:flex;flex-wrap:wrap;gap:10px 40px;align-items:baseline}
.claim .big{font-family:var(--serif);font-size:clamp(20px,3.2vw,30px);line-height:1.25;
  letter-spacing:-.01em;flex:1 1 260px;max-width:560px;text-wrap:pretty}
.claim .note{flex:1 1 220px;max-width:340px;font-size:13px;line-height:1.6;color:var(--mid);text-wrap:pretty}

/* specimen */
.spec{display:flex;flex-wrap:wrap;gap:clamp(16px,2.6vw,32px);align-items:stretch;padding-top:18px}
.speccol{flex:1 1 260px;min-width:0;display:flex;flex-direction:column;gap:10px}
.specmid{flex:.55 1 168px;min-width:0;display:flex;align-items:center}
.specmid>div{width:100%;padding:16px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
.specmid p{margin:0;font-family:var(--serif);font-size:clamp(15px,1.7vw,18px);line-height:1.45;text-wrap:pretty}
.spechead{display:flex;flex-direction:column;gap:4px;padding-bottom:9px;border-bottom:1px solid var(--rule)}
.spechead .v{font-family:var(--mono);font-size:clamp(12px,1.5vw,14px)}
.specverdict{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.specverdict b{font:600 clamp(11px,1.4vw,14px)/1.2 var(--sans);letter-spacing:.07em}
.specverdict span{font-family:var(--mono);font-size:11px;color:var(--mid)}
.shot{border:1px solid var(--rule);width:100%;aspect-ratio:16/10;display:block;object-fit:cover;object-position:top}
.speccap{margin:0;font-size:12px;line-height:1.55;color:var(--mid);text-wrap:pretty}
.speccap .mono{font-size:11px;color:var(--ink)}

/* method */
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
  gap:26px clamp(20px,3vw,40px);margin-top:20px}
.step{padding-top:16px;border-top:1px solid var(--rule)}
.step .n{font-family:var(--serif);font-size:26px;line-height:1}
.step .t{font:600 11px/1 var(--sans);letter-spacing:.12em;text-transform:uppercase;margin:14px 0 8px}
.step p{margin:0;font-size:13.5px;line-height:1.6;color:var(--mid);text-wrap:pretty}

/* filters, CSS only */
.filters{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px clamp(14px,2.4vw,26px);padding:14px 0 0}
.filters input{position:absolute;opacity:0;pointer-events:none;width:0;height:0}
.filters label{border-bottom:1px solid var(--rule);padding:0 0 3px;cursor:pointer;
  font:500 9px/1 var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--mid)}
.filters label:hover{color:var(--ink)}
.count{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--mid)}
.count span{display:none}
#f-all:checked~.filters [for=f-all],#f-cor:checked~.filters [for=f-cor],
#f-inc:checked~.filters [for=f-inc],#f-non:checked~.filters [for=f-non]{
  color:var(--ink);border-bottom-color:var(--ink)}
#f-all:checked~.filters .count .c-all,#f-cor:checked~.filters .count .c-cor,
#f-inc:checked~.filters .count .c-inc,#f-non:checked~.filters .count .c-non{display:inline}
#f-cor:checked~.rows .row:not(.correct),#f-inc:checked~.rows .row:not(.incorrect),
#f-non:checked~.rows .row:not(.inconclusive){display:none}

/* table */
.rowhead,.row>.cells{display:grid;
  grid-template-columns:14px minmax(0,1.05fr) minmax(0,1fr) minmax(0,1fr) minmax(0,.66fr);
  gap:0 clamp(6px,1.4vw,18px);align-items:start}
.rowhead{padding:12px 0 10px;border-bottom:1px solid var(--ink)}
.rowhead span{font:500 9px/1.4 var(--sans);letter-spacing:.13em;text-transform:uppercase;color:var(--mid)}
.row{border-bottom:1px solid var(--rule)}
.row>.cells{padding:14px 0}
.row.inconclusive{border-bottom-color:var(--ink)}
.mark{display:block;width:7px;height:7px;margin-top:16px}
.row.incorrect .mark{background:var(--red)}
.row.inconclusive .mark{border:1px solid var(--mid)}
.idcell{display:flex;flex-direction:column;gap:5px}
.idcell .n{font-family:var(--mono);font-size:clamp(11px,1.3vw,13px)}
.idcell .p{font-family:var(--mono);font-size:clamp(9.5px,1.1vw,11px);color:var(--mid)}
.vcell{display:flex;flex-direction:column;gap:4px}
.vcell .i{font-family:var(--mono);font-size:8.5px;color:var(--mid)}
.vcell .v{font:500 clamp(9.5px,1.15vw,11.5px)/1.35 var(--sans);letter-spacing:.06em;overflow-wrap:anywhere}
.vcell .why{font-size:9.5px;line-height:1.35;color:var(--red)}
.vcell .v.bad{color:var(--red)} .vcell .v.dim{color:var(--mid)}
.rcell{display:flex;flex-direction:column;align-items:flex-start;gap:7px}
.rcell .r{font:500 clamp(9.5px,1.15vw,11.5px)/1.35 var(--sans);letter-spacing:.06em}
.row.incorrect .rcell .r{color:var(--red)} .row.inconclusive .rcell .r{color:var(--mid)}
details{margin:0}
details summary{list-style:none;border-bottom:1px solid var(--rule);padding:0 0 2px;
  cursor:pointer;font-family:var(--mono);font-size:10px;color:var(--mid);width:max-content}
details summary::-webkit-details-marker{display:none}
details summary:hover{color:var(--ink)}
details summary::before{content:"+ "}
details[open] summary::before{content:"\\2212 "}
.diag{display:grid;grid-template-columns:14px minmax(0,1fr);gap:0 clamp(6px,1.4vw,18px);padding:0 0 16px}
.diag>div{display:flex;flex-direction:column;gap:7px;max-width:640px}
.diag h4{margin:0;font:600 9px/1 var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--red)}
.row.inconclusive .diag h4{color:var(--mid)}
.diag p{margin:0;font-size:13px;line-height:1.6;color:var(--ink);text-wrap:pretty}
.legend{display:flex;flex-wrap:wrap;gap:8px 28px;padding-top:12px}
.legend span{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--mid)}
.legend i{width:7px;height:7px;display:block}

/* two wrong answers */
.wrongs{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
  gap:28px clamp(24px,4vw,48px);margin-top:28px}
.wrong{padding-top:18px;border-top:1px solid var(--rule)}
.wrong .tag{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.wrong .tag b{font:600 10px/1 var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--red)}
.wrong .tag i{width:7px;height:7px;background:var(--red);display:block}
.wrong .tag .mono{font-size:11px;color:var(--mid)}
.wrong p{margin:0;font-family:var(--serif);font-size:clamp(16px,1.9vw,19px);line-height:1.55;text-wrap:pretty}

/* corpus */
.corpus{display:flex;flex-wrap:wrap;gap:10px clamp(18px,4vw,56px);align-items:flex-start;
  padding-top:14px;border-top:1px solid var(--ink)}
.corpus .lbl{flex:0 0 auto;width:150px;font:500 10px/1.5 var(--sans);
  letter-spacing:.14em;text-transform:uppercase;color:var(--mid)}
.corpus .body{flex:1 1 420px;display:flex;flex-direction:column;gap:16px;max-width:640px}
.corpus p{margin:0;font-size:14.5px;line-height:1.65;text-wrap:pretty}

/* tolerances */
.tols{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
  gap:26px clamp(20px,3vw,40px);margin-top:28px}
.tol{padding-top:16px;border-top:1px solid var(--rule)}
.tol .t{font:500 9px/1 var(--sans);letter-spacing:.14em;text-transform:uppercase;
  color:var(--mid);margin-bottom:10px}
.tol p{margin:0;font-size:13.5px;line-height:1.6;text-wrap:pretty}

/* footer + seal */
footer{padding:clamp(28px,3.6vw,48px) 0 clamp(30px,4vw,56px)}
.sealrow{display:flex;flex-wrap:wrap;gap:clamp(28px,5vw,64px);align-items:center;
  justify-content:space-between;padding-top:22px;border-top:2px solid var(--brass)}
.seal{position:relative;flex:0 0 auto;width:min(300px,100%);aspect-ratio:1;border:1px solid var(--brass)}
.seal i{position:absolute;background:var(--brass)}
.seal .t{left:50%;top:0;width:1px;height:34px} .seal .b{left:50%;bottom:0;width:1px;height:34px}
.seal .l{top:50%;left:0;height:1px;width:34px} .seal .r{top:50%;right:0;height:1px;width:34px}
.seal .ring{position:absolute;inset:22px;border:1px solid var(--brass);border-radius:50%;background:none}
.sealtext{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:7px;padding:14%;text-align:center;color:var(--brass);font-family:var(--mono)}
.sealtext .a{font-size:8px;letter-spacing:.2em}
.sealtext .name{font-family:var(--serif);font-size:26px;line-height:1;letter-spacing:.1em}
.sealtext hr{width:64px;height:1px;background:var(--brass);border:0;margin:1px 0}
.sealtext .m{font-size:9px;font-weight:500;letter-spacing:.1em}
.sealtext .s{font-size:7.5px;letter-spacing:.12em}
.closing{flex:1 1 300px;max-width:520px;display:flex;flex-direction:column;gap:12px}
.closing p{margin:0;font-family:var(--serif);font-size:clamp(17px,2.1vw,21px);line-height:1.5;text-wrap:pretty}
.colophon{display:flex;flex-wrap:wrap;gap:6px 26px;font:500 9px/1.6 var(--sans);
  letter-spacing:.13em;text-transform:uppercase;color:var(--mid)}
@media(max-width:520px){
  .rowhead,.row>.cells{grid-template-columns:14px minmax(0,1fr);gap:8px clamp(6px,1.4vw,18px)}
  .rowhead span:nth-child(3),.rowhead span:nth-child(4),.rowhead span:nth-child(5){display:none}
  .row>.cells>*{grid-column:2}
  .row>.cells>.mark{grid-column:1;grid-row:1}
}
"""

# ---------------------------------------------------------------- rows

def row_html(num, vb, vf, kind, dh, db, i):
    a, b = BEST[(num, vb)], BEST[(num, vf)]
    short = {'REPRODUCED': 'REPRODUCED', 'NOT_REPRODUCED': 'NOT_REPRODUCED',
             'INCONCLUSIVE': 'INCONCLUSIVE'}
    label = {'correct': 'Correct', 'incorrect': 'Incorrect', 'inconclusive': 'Inconclusive'}[kind]
    va, vfx = a['verdict'], b['verdict']
    bad_a = kind == 'incorrect' and va == 'NOT_REPRODUCED'
    bad_f = kind == 'incorrect' and vfx == 'REPRODUCED'
    why_a = '<span class=why>Expected REPRODUCED, false negative</span>' if bad_a else ''
    why_f = '<span class=why>Expected NOT_REPRODUCED, false positive</span>' if bad_f else ''
    cls_a = ' bad' if bad_a else (' dim' if va == 'INCONCLUSIVE' else '')
    cls_f = ' bad' if bad_f else ''
    det = ''
    if dh:
        det = (f'<div class=diag><span></span><div><h4>{esc(dh)}</h4><p>{db}</p></div></div>')
        det = (f'<details><summary>{"note" if kind=="inconclusive" else "diagnosis"}</summary>'
               f'{det}</details>')
    return f"""<div class="row {kind}"><div class=cells>
<span class=mark aria-hidden=true></span>
<span class=idcell><span class=n>#{num}</span><span class=p>{vb} &rarr; {vf}</span></span>
<span class=vcell><span class=i>{i:02d}</span>
  <a class="v{cls_a}" href="artifacts/{a['attempt_id']}/report.html">{short[va]}</a>{why_a}</span>
<span class=vcell><span class=i>{i+1:02d}</span>
  <a class="v{cls_f}" href="artifacts/{b['attempt_id']}/report.html">{short[vfx]}</a>{why_f}</span>
<span class=rcell><span class=r>{label}</span>{det}</span>
</div></div>"""

rows = "".join(row_html(*e, i) for e, i in zip(ENTRIES, range(1, 13, 2)))

spec_b = b64('artifacts/4075-2.19.0-0302e4/run_0_st10.png')
spec_f = b64('artifacts/4075-2.20.0-1b6426/run_0_st10.png')

def img(data, alt):
    if not data:
        return '<div class=shot></div>'
    return f'<img class=shot alt="{esc(alt)}" src="data:image/png;base64,{data}">'

# ---------------------------------------------------------------- page

DOC = f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>thrice: certificate of reproduction accuracy</title>
<meta name=description content="A harness that answers whether a reported bug still reproduces, measured against known-correct answers: precision 0.80, recall 0.80 across six already-fixed jaeger-ui issues.">
<link rel=preconnect href="https://fonts.googleapis.com">
<link rel=preconnect href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,300;6..72,400;6..72,500&family=Public+Sans:wght@400;500;600&family=UnifrakturMaguntia&family=IBM+Plex+Mono:wght@400;500&display=swap" rel=stylesheet>
<style>{CSS}</style>
<div class=wrap>

<header class=mast>
  <div class=eyebrow>Certificate of reproduction accuracy</div>
  <div class=wordmark>thrice</div>
  <p class=lede>&ldquo;Does this bug still happen?&rdquo; answered by running it, three times, on both sides of the release that fixed it.</p>
  <p class=sub>Automated bug reproduction for self-hosted web apps. No model in the run loop.</p>
</header>

<div class=fields>
  <div class=fieldpair>
    <div class=field><span class=cap>Report no.</span><span class=val>TR-001</span></div>
    <div class=field><span class=cap>Corpus</span><span class=val>jaeger-ui</span></div>
    <div class=field><span class=cap>Attempts</span><span class=val>{ATTEMPTS}</span></div>
    <div class=field><span class=cap>Run window</span><span class=val>{DATE_RANGE}</span></div>
  </div>
  <div class=fieldpair>
    <div class=field><span class=cap>Actions implemented</span><span class=val>4 of 8</span></div>
    <div class=field><span class=cap>Predicates implemented</span><span class=val>4 of 10</span></div>
    <div class=field><span class=cap>Model in run loop</span><span class=val>none</span></div>
  </div>
</div>

<section>
  <div class=eyebrow style="color:var(--mid);text-align:center;margin-bottom:clamp(14px,2vw,22px)">Measured against known-correct answers</div>
  <div class=numrow>
    <div class=numcell><div class=num>0.80</div><div class=cap>Precision</div></div>
    <div class=vrule></div>
    <div class=numcell><div class=num>0.80</div><div class=cap>Recall</div></div>
  </div>
  <div class=brassrule></div>
  <div class=claim>
    <div class=big>3 of 5 conclusive entries correct. One false positive, one false negative, one inconclusive.</div>
    <div class=note>Ground truth taken from the commit that fixed each issue: six already-fixed jaeger-ui issues, each run on the last buggy release and the first fixed release, twelve attempts in total.</div>
  </div>
</section>

<section>
  <div class=hd>
    <div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap">
      <span style="font:600 10px/1 var(--sans);letter-spacing:.18em;text-transform:uppercase">Specimen</span>
      <span class=mono style="font-size:12px;color:var(--mid)">#4075</span>
    </div>
    <span class=cap>One attempt pair in full</span>
  </div>
  <div class=spec>
    <div class=speccol>
      <div class=spechead><span class=cap>Last buggy release</span><span class=v>jaeger-ui 2.19.0</span></div>
      <div class=specverdict><b>REPRODUCED</b><span>3 of 3</span></div>
      {img(spec_b, 'Assertion screenshot, 2.19.0 run')}
      <p class=speccap><span class=mono>[element_visible]</span> checked against seeded backend state. All three browsers read the reported fault.</p>
    </div>
    <div class=specmid><div><p>Ground truth: the commit that fixed this issue landed in 2.20.0. thrice agreed.</p></div></div>
    <div class=speccol>
      <div class=spechead><span class=cap>First fixed release</span><span class=v>jaeger-ui 2.20.0</span></div>
      <div class=specverdict><b>NOT_REPRODUCED</b><span>3 of 3</span></div>
      {img(spec_f, 'Assertion screenshot, 2.20.0 run')}
      <p class=speccap><span class=mono>[element_visible]</span> checked against the same seeded state. The fault is absent in all three.</p>
    </div>
  </div>
</section>

<section>
  <div class=hd><h2>Method of measurement</h2><span class=cap>Four steps</span></div>
  <div class=steps>
    <div class=step><div class=n>01</div><div class=t>Fork snapshot</div><p>A cloud sandbox is forked from a snapshot of the app at a pinned version. The release under test is fixed before the run starts.</p></div>
    <div class=step><div class=n>02</div><div class=t>Seed known state</div><p>Backend state is written directly over OTLP, so every run begins from facts the checker already holds and can assert against.</p></div>
    <div class=step><div class=n>03</div><div class=t>Three parallel browsers</div><p>The reported steps are carried out three times at once, in three separate cloud browsers, from the same seeded state.</p></div>
    <div class=step><div class=n>04</div><div class=t>Check predicates</div><p>Concrete predicates are checked against backend state. The verdict comes from those checks, not from a model&rsquo;s account of what it saw.</p></div>
  </div>
</section>

<section>
  <div class=hd><h2>Record of attempts</h2><span class=cap>Six issues &middot; twelve attempts</span></div>
  <input type=radio name=f id=f-all checked><input type=radio name=f id=f-cor>
  <input type=radio name=f id=f-inc><input type=radio name=f id=f-non>
  <div class=filters>
    <span class=cap>Show</span>
    <label for=f-all>All twelve</label><label for=f-cor>Correct only</label>
    <label for=f-inc>Wrong only</label><label for=f-non>Inconclusive</label>
    <span class=count><span class=c-all>12 of 12 attempts shown</span><span class=c-cor>6 of 12 attempts shown</span><span class=c-inc>4 of 12 attempts shown</span><span class=c-non>2 of 12 attempts shown</span></span>
  </div>
  <div class=rows>
    <div class=rowhead><span></span><span>Issue / release pair</span><span>Buggy release</span><span>Fixed release</span><span>Result</span></div>
    {rows}
  </div>
  <div class=legend>
    <span><i style="background:var(--red)"></i>Wrong answer, diagnosed inline</span>
    <span><i style="border:1px solid var(--mid)"></i>No verdict reached</span>
  </div>
</section>

<section>
  <div class=hd><h2>The two wrong answers</h2><span class=cap>Published in full</span></div>
  <div class=wrongs>
    <div class=wrong><div class=tag><i></i><b>False positive</b><span class=mono>#4045</span></div>
      <p>Resizer read absent on both releases though the screenshot shows the correct state. The bug was in thrice, not jaeger: the evaluator pinned <code>.first</code>, so <code>element_visible</code> answered the wrong question when several elements matched.</p></div>
    <div class=wrong><div class=tag><i></i><b>False negative</b><span class=mono>#3967</span></div>
      <p>The view-mode pin that keeps one plan valid across a pair waits for a toggle that shipped in 2.19.0, so it cannot exist at 2.18.0.</p></div>
  </div>
</section>

<section>
  <div class=corpus>
    <div class=lbl>Corpus and<br>ground truth</div>
    <div class=body>
      <p>Every entry is a jaeger-ui issue that has already been fixed, so the correct answer is known from the commit that fixed it. For each issue two releases are pinned: the last release that carried the bug and the first that carried the fix.</p>
      <p style="color:var(--mid)">A correct instrument reads <code style="color:var(--ink)">REPRODUCED</code> on the buggy release and <code style="color:var(--ink)">NOT_REPRODUCED</code> on the fixed one. Each release is attempted once, twelve attempts across six issues, and each verdict comes from predicates checked against seeded backend state.</p>
    </div>
  </div>
</section>

<section>
  <div class=hd><h2>Stated tolerances</h2><span class=cap>Read with the number</span></div>
  <div class=tols>
    <div class=tol><div class=t>Sample size</div><p>Five conclusive entries. One verdict moves precision or recall by roughly 0.20, so both figures should be read as a first calibration, not a rate.</p></div>
    <div class=tol><div class=t>Scope</div><p>One application, one class of bug report, one set of hand-written predicates. Nothing here shows how the method transfers to another app.</p></div>
    <div class=tol><div class=t>Instrument error</div><p>One of the two wrong answers came from the evaluator, not from the app under test. The evaluator is part of what is being measured.</p></div>
    <div class=tol><div class=t>Three runs, unvalidated</div><p>63 runs produced zero divergence and no FLAKY verdict. Running three times bought nothing here: the corpus was selected for small deterministic seeds, which is close to selecting for non-flakiness.</p></div>
  </div>
</section>

<section>
  <div class=hd><h2>Read further</h2><span class=cap>Source and evidence</span></div>
  <div class=steps>
    <div class=step><div class=t style="margin-top:0"><a href="https://github.com/u7k4rs6/thrice">Repository</a></div><p>Plans, runner, predicates, and every attempt artifact.</p></div>
    <div class=step><div class=t style="margin-top:0"><a href="https://github.com/u7k4rs6/thrice/blob/main/docs/findings.md">Findings</a></div><p>Ten findings with evidence, several about the platform rather than about thrice.</p></div>
    <div class=step><div class=t style="margin-top:0"><a href="artifacts/4075-2.19.0-0302e4/report.html">Sample report</a></div><p>One attempt in full: plan, three run columns, screenshots, screencast.</p></div>
  </div>
</section>

<footer>
  <div class=sealrow>
    <div class=seal>
      <i class=t></i><i class=b></i><i class=l></i><i class=r></i><span class=ring></span>
      <div class=sealtext>
        <span class=a>CALIBRATION STANDARD</span>
        <span class=a style="letter-spacing:.14em">CERTIFICATE NO. TR-001</span>
        <hr>
        <span class=name>THRICE</span>
        <span class=a style="letter-spacing:.18em">REPRODUCIBILITY CORPUS</span>
        <span class=m>{ATTEMPTS} ATTEMPTS / 5 CONCLUSIVE</span>
        <span class=a style="letter-spacing:.1em">0.80 PRECISION &middot; 0.80 RECALL</span>
        <hr>
        <span class=s>RANGE: {DATE_RANGE}</span>
        <span class=s style="letter-spacing:.14em">DETERMINISTIC VERIFICATION</span>
      </div>
    </div>
    <div class=closing>
      <p>The two failures are published because the number depends on them. Precision 0.80 and recall 0.80 mean nothing without the entries that produced them.</p>
      <div class=colophon><span>Report TR-001</span><span>Corpus jaeger-ui</span><span>Six issues &middot; twelve attempts</span></div>
    </div>
  </div>
</footer>
</div>
</html>"""

pathlib.Path('index.html').write_text(DOC)
print(f"index.html written: {len(DOC)/1024:.0f} KB")
print(f"run window resolved to: {DATE_RANGE}; attempts: {ATTEMPTS}")
