"""One self-contained static HTML report per attempt, generated from attempt.json.

Constraints from docs/04-frontend-spec.md section 3, all load-bearing:
no framework, no build step, no external asset, no CDN, no JavaScript. It must
open correctly from `file://` and from GitHub Pages, which rules out anything
that needs a server. Screenshots are inlined as base64 so the page survives
being moved; the video stays a relative file because a base64 video would blow
the page size for no benefit.

The page is a document, not an app. If a section needs interactivity to be
legible, the section is wrong.
"""

from __future__ import annotations

import base64
import html
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

MAX_INLINE_PNG = 200 * 1024
FRAME_RATE = 8

CSS = """
:root{
  --bg:#fbfbfa; --fg:#191918; --muted:#6f6f6a; --line:#e3e3df; --panel:#ffffff;
  --held:#16794a; --failed:#b3261e; --amber:#a8620a;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.wrap{max-width:1400px;margin:0 auto;padding:28px 22px 64px}
h1,h2,h3{font-weight:600;margin:0}
.eyebrow{font-size:13px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);
  margin:0 0 8px}
header.hd{border-bottom:2px solid var(--fg);padding-bottom:18px;margin-bottom:22px}
.verdict{font-size:40px;line-height:1.1;letter-spacing:-.01em;margin:2px 0 10px}
.v-REPRODUCED{color:var(--failed)} .v-NOT_REPRODUCED{color:var(--held)}
.v-FLAKY{color:var(--amber)} .v-INCONCLUSIVE{color:var(--muted)}
.facts{display:flex;flex-wrap:wrap;gap:8px 26px;color:var(--muted);font-size:13px}
.facts b{color:var(--fg);font-weight:600}
a{color:inherit;text-underline-offset:2px}
section{margin:26px 0}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:3px;padding:14px 16px}
table.plan{border-collapse:collapse;width:100%;font-size:13px}
table.plan td{border-top:1px solid var(--line);padding:4px 10px 4px 0;vertical-align:top}
table.plan tr:first-child td{border-top:0}
.pill{display:inline-block;padding:1px 7px;border:1px solid var(--line);border-radius:10px;
  font-size:12px;color:var(--muted)}
.pred{display:grid;grid-template-columns:88px 1fr;gap:6px 12px;font-size:13px;margin-top:8px}
.pred .k{color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-size:12px}
.runs{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
@media (max-width:900px){.runs{grid-template-columns:1fr}}
.run{background:var(--panel);border:1px solid var(--line);border-radius:3px;padding:12px 14px}
.run h3{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
  margin-bottom:8px}
ol.steps{list-style:none;margin:0;padding:0;font-size:13px}
ol.steps li{display:grid;grid-template-columns:52px 1fr auto;gap:8px;padding:3px 0;
  border-top:1px dotted var(--line);align-items:baseline}
ol.steps li:first-child{border-top:0}
.sid{color:var(--muted)}
.ok{color:var(--held)} .bad{color:var(--failed)} .warn{color:var(--amber)}
.dur{color:var(--muted);font-size:12px;white-space:nowrap}
.shot{margin:8px 0 2px;border:1px solid var(--line);border-radius:2px;display:block;width:100%}
.shotcap{font-size:12px;color:var(--muted);margin-bottom:10px}
.pv{margin-top:10px;padding-top:8px;border-top:1px solid var(--line);font-size:13px}
.divergence{border:1px solid var(--amber);border-left-width:4px;background:#fffaf2;
  padding:10px 14px;margin:16px 0;font-size:13px}
video{width:100%;max-width:900px;border:1px solid var(--line);border-radius:3px;background:#000}
.foot{margin-top:34px;padding-top:14px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12px}
code{background:#f2f2ef;padding:1px 5px;border-radius:2px}
"""


def _esc(x: Any) -> str:
    return html.escape(str(x))


def _b64_png(p: Path) -> str | None:
    if not p.exists() or p.stat().st_size > MAX_INLINE_PNG:
        return None
    return base64.b64encode(p.read_bytes()).decode()


def _stitch(frames_dir: Path, out: Path) -> bool:
    """Frames to mp4 with ffmpeg. Absent ffmpeg is not an error, just no video."""
    ff = shutil.which("ffmpeg")
    if not ff or not frames_dir.is_dir() or not any(frames_dir.glob("*.png")):
        return False
    if out.exists():
        return True
    r = subprocess.run(
        [ff, "-y", "-loglevel", "error", "-framerate", str(FRAME_RATE),
         "-pattern_type", "glob", "-i", str(frames_dir / "*.png"),
         "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p", str(out)],
        capture_output=True)
    return r.returncode == 0 and out.exists()


def _predicate_line(p: dict[str, Any]) -> str:
    a = p.get("args", {})
    if "locator" in a:
        loc = a["locator"]
        detail = f"{loc.get('by')}={loc.get('value')}"
        if loc.get("nth") is not None:
            detail += f" [nth={loc['nth']}]"
    elif "re" in a:
        detail = f"/{a['re']}/"
        if a.get("scope"):
            detail += f" within {a['scope'].get('by')}={a['scope'].get('value')}"
    else:
        detail = json.dumps(a)
    return f"<code>{_esc(p.get('type'))}</code> {_esc(detail)}"


def render(attempt_dir: Path) -> Path:
    d = json.loads((attempt_dir / "attempt.json").read_text())
    verdict = d.get("verdict", "INCONCLUSIVE")
    issue = d.get("issue", {})
    app = d.get("app", {})
    cost = d.get("cost", {})
    runs = d.get("runs", [])
    plan_path = Path(d.get("plan_file", ""))
    plan = json.loads(plan_path.read_text()) if plan_path.exists() else {}

    parts: list[str] = []
    parts.append(f"<!doctype html><html lang=en><meta charset=utf-8>"
                 f"<meta name=viewport content='width=device-width,initial-scale=1'>"
                 f"<title>thrice {_esc(issue.get('number'))} {_esc(app.get('version'))} "
                 f"{_esc(verdict)}</title><style>{CSS}</style><div class=wrap>")

    # ---- header ----
    n_rep, n_tot = d.get("runs_reproduced"), d.get("runs_total") or len(runs)
    ratio = f"{n_rep}/{n_tot}" if n_rep is not None else f"{len([r for r in runs if r.get('completed')])}/{n_tot} completed"
    parts.append(
        f"<header class=hd><p class=eyebrow>thrice attempt {_esc(d.get('attempt_id'))}</p>"
        f"<h1 class='verdict v-{_esc(verdict)}'>{_esc(verdict)} {_esc(ratio)}</h1>"
        f"<div class=facts>"
        f"<span><b><a href='{_esc(issue.get('url'))}'>"
        f"{_esc(issue.get('repo'))}#{_esc(issue.get('number'))}</a></b> "
        f"{_esc(issue.get('title',''))}</span></div>"
        f"<div class=facts style='margin-top:8px'>"
        f"<span>jaeger <b>{_esc(app.get('version'))}</b></span>"
        f"<span>fix <b>{_esc(issue.get('fix_commit'))}</b> "
        f"(#{_esc(issue.get('fix_pr'))})</span>"
        f"<span>pair <b>{_esc(issue.get('last_release_without'))}</b> to "
        f"<b>{_esc(issue.get('first_release_with'))}</b></span>"
        f"<span>cost <b>${cost.get('usd', 0):.5f}</b></span>"
        f"<span>{cost.get('sandbox_seconds',0)} sandbox-s, "
        f"{cost.get('browser_seconds',0)} browser-s</span>"
        f"<span>{_esc(d.get('started_at',''))}</span></div></header>")

    if d.get("reason") or d.get("error"):
        parts.append(f"<div class=divergence><b>Reason:</b> {_esc(d.get('reason') or '')} "
                     f"{_esc(d.get('error') or '')}</div>")

    # ---- plan ----
    seeds = plan.get("seeds", [])
    steps = plan.get("steps", [])
    rows = "".join(
        f"<tr><td class=sid>{_esc(s['id'])}</td><td><span class=pill>{_esc(s['action'])}</span></td>"
        f"<td>{_esc(s.get('args',{}).get('path') or (s.get('locators') or [{}])[0].get('value','') or (str(s.get('args',{}).get('ms','')) + ' ms' if s.get('args',{}).get('ms') else ''))}</td></tr>"
        for s in steps)
    env = d.get("env", {})
    parts.append(
        "<section><p class=eyebrow>Plan</p><div class=panel>"
        f"<div class=facts><span>{len(seeds)} seed(s) to <b>{_esc(seeds[0]['endpoint']) if seeds else 'n/a'}</b>"
        f"</span><span>{len(steps)} steps</span>"
        f"<span>environment <b>{_esc(env.get('path','?'))}</b></span>"
        f"<span>seed visible: <b>{_esc((d.get('seed_visible') or {}).get('traces'))} trace(s), "
        f"{_esc((d.get('seed_visible') or {}).get('spans'))} span(s)</b></span></div>"
        f"<table class=plan>{rows}</table>"
        "<div class=pred>"
        f"<span class=k>actual</span><span>{_predicate_line(plan.get('actual_predicate',{}))}"
        f"<br><span style='color:var(--muted)'>{_esc(plan.get('actual_predicate',{}).get('summary',''))}</span></span>"
        f"<span class=k>expected</span><span>{_predicate_line(plan.get('expected_predicate',{}))}"
        f"<br><span style='color:var(--muted)'>{_esc(plan.get('expected_predicate',{}).get('summary',''))}</span></span>"
        "</div>"
        "<p style='color:var(--muted);font-size:12px;margin:10px 0 0'>"
        "A run counts as reproduced only if the actual predicate holds and the expected "
        "predicate fails. Both are evaluated on every run.</p></div></section>")

    # ---- three run columns ----
    cols = []
    for r in runs:
        idx = r["run_index"]
        li = []
        for e in r.get("events", []):
            out = e.get("outcome", "")
            cls = "ok" if out == "ok" else "bad"
            mark = "ok" if out == "ok" else _esc(out)
            extra = ""
            if e.get("locator_index"):
                extra = f" <span class=dur>fb{e['locator_index']}</span>"
            li.append(f"<li><span class=sid>{_esc(e['step_id'])}</span>"
                      f"<span>{_esc(e.get('action',''))}{extra}</span>"
                      f"<span class='{cls}'>{mark}"
                      f"<span class=dur> {e.get('t_ms','')}{'ms' if e.get('t_ms') else ''}</span>"
                      f"</span></li>")
        shots = ""
        for sid in plan.get("assertion_step_ids", []):
            b64 = _b64_png(attempt_dir / f"run_{idx}_{sid}.png")
            if b64:
                shots += (f"<img class=shot alt='run {idx} at {_esc(sid)}' "
                          f"src='data:image/png;base64,{b64}'>"
                          f"<div class=shotcap>assertion step {_esc(sid)}</div>")
        a, ex = r.get("actual_predicate_held"), r.get("expected_predicate_held")
        def _mk(v):
            if v is None:
                return "<span class=warn>not evaluated</span>"
            return "<span class=ok>HELD</span>" if v else "<span class=bad>FAILED</span>"
        pv = (f"<div class=pv>actual {_mk(a)} &nbsp; expected {_mk(ex)}<br>"
              f"<span class=dur>{_esc(r.get('actual_detail',''))} | "
              f"{_esc(r.get('expected_detail',''))}</span></div>")
        if not r.get("completed"):
            pv = (f"<div class=pv><span class=bad>incomplete: "
                  f"{_esc(r.get('incomplete_reason'))}</span><br>"
                  f"<span class=dur>{_esc(r.get('incomplete_detail',''))}</span></div>")
        cols.append(f"<div class=run><h3>run {idx} &middot; {r.get('frames',0)} frames &middot; "
                    f"{r.get('browser_seconds',0)}s</h3><ol class=steps>{''.join(li)}</ol>"
                    f"{pv}{shots}</div>")
    parts.append(f"<section><p class=eyebrow>Three runs</p><div class=runs>{''.join(cols)}</div></section>")

    if verdict == "FLAKY":
        parts.append("<div class=divergence><b>First divergence:</b> the runs disagree. "
                     "The divergence differ is specified but not built; see docs/findings.md.</div>")

    # ---- video ----
    vids = []
    for r in runs:
        idx = r["run_index"]
        mp4 = attempt_dir / f"run_{idx}.mp4"
        if _stitch(attempt_dir / f"run_{idx}_frames", mp4):
            vids.append(f"<div><div class=shotcap>run {idx}</div>"
                        f"<video controls preload=metadata src='{mp4.name}'></video></div>")
    if vids:
        parts.append("<section><p class=eyebrow>Screencast</p>"
                     f"<div class=runs>{''.join(vids)}</div></section>")

    parts.append(f"<p class=foot>Raw data: <a href='attempt.json'>attempt.json</a> &middot; "
                 f"plan: <a href='{_esc(plan_path.name)}'>{_esc(plan_path.name)}</a> &middot; "
                 f"generated by thrice. Preview URLs and API keys are redacted on write.</p>")
    parts.append("</div></html>")

    out = attempt_dir / "report.html"
    out.write_text("".join(parts))
    # Keep the plan beside the report so the page is self-contained when published.
    if plan_path.exists():
        (attempt_dir / plan_path.name).write_text(plan_path.read_text())
    return out
