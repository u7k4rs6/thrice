# Day 7: recording shot list and post drafts

## Recording, 40 seconds

Screen only. No voiceover, no music, no titles, no speed ramping. 1280x720,
terminal at a readable size.

**Nothing here is staged.** Every shot is a real artifact committed to the repo.
Where a shot shows output, it is the output that actually ran.

| Time | Shot | Source |
|---|---|---|
| 0:00 to 0:06 | GitHub issue **jaegertracing/jaeger-ui#4075**, scrolled to "Steps to reproduce". Then the linked fix PR #4080, so the viewer sees ground truth exists. | Live GitHub |
| 0:06 to 0:12 | `plans/4075-2.19.0.json` in the editor, scrolled to `actual_predicate` and `expected_predicate`. Two typed predicates, visible as data. | Repo file |
| 0:12 to 0:20 | Terminal: `uv run python -m thrice.attempt plans/4075-2.19.0.json plans/4075-2.20.0.json`. Environment lines appear: fork, seed, `seed visible: 1 trace, 2 spans`, preview 200. **Real speed.** | Live run |
| 0:20 to 0:26 | The three per-run lines land for **2.19.0**, the buggy release: `actual=True expected=False reproduced=True` three times, then `verdict REPRODUCED 3/3`. | Live run |
| 0:26 to 0:32 | The same for **2.20.0**, the fixed release: `actual=False expected=True reproduced=False`, then `verdict NOT_REPRODUCED 3/3`. The pair is the point: same plan, opposite answers, both correct. | Live run |
| 0:32 to 0:40 | `artifacts/4075-2.19.0-0302e4/report.html` in a browser. Scroll once: header with REPRODUCED 3/3 and the cost, the plan table, the three run columns with per-step timings, one screencast video playing. | Committed report page |

**Two things not to show, because they do not exist.** The three-column live
progress display specified in `04-frontend-spec.md` was never built; the runner
prints per-run lines instead, and that is what the recording shows. And no
posted comment appears anywhere, because thrice posts nothing.

If the terminal run is too slow to fit, use a real recording of a real run and
cut between phases. Do not re-time it to look faster than it is.

---

## LinkedIn draft

> Agents that "reproduce" a bug are unreliable narrators: they decide what the
> steps meant, and they decide whether the outcome matched. Both decisions are
> invisible.
>
> So I built thrice, and then measured it.
>
> It forks a Solari sandbox from a snapshot of the app at a pinned release,
> seeds state over OTLP, runs the reported steps in three browsers, and checks
> typed predicates. No model in the run loop.
>
> Validation: 6 already-fixed jaeger-ui issues, ground truth from the fix
> commits. Correct on 3 of 5 conclusive entries. Precision 0.80, recall 0.80.
> Two confident wrong answers, written up rather than dropped.
>
> And the honest bit: 63 runs, zero divergence. Running three times bought
> nothing on this corpus.
>
> Built on @Solari. Thanks @Harry Chow.

*(118 words)*

**First reply:** `https://github.com/u7k4rs6/thrice` plus one line: "Findings,
including why the preview gateway returns 502 where the docs say 425, are in
docs/findings.md."

---

## X draft

> "Does this bug still reproduce?" I built a harness that answers it, then
> checked whether the harness is right.
>
> thrice: Solari sandbox forked from a snapshot at a pinned release, state
> seeded over OTLP, steps run in 3 browsers, typed predicates. No model in the
> run loop.
>
> Measured against 6 already-fixed jaeger-ui issues where the fix commit is
> ground truth: correct on 3 of 5 conclusive entries. Precision 0.80, recall
> 0.80.
>
> 63 runs produced zero divergence, so the three-run design is unvalidated. Say
> so.
>
> @solari @harrychow

*(95 words)*

**First reply:** `https://github.com/u7k4rs6/thrice`

---

## Framing notes

The claim is **a validation study of a reproduction harness**, not "AI finds
bugs in jaeger". Every issue in the corpus was already fixed by its maintainers
before thrice ran. Nothing was reported to anyone, and nothing was posted to any
tracker.

Both drafts lead with the number including its failures, and both state the
zero-divergence result. A post that omitted either would be selling something
the repo does not support.
