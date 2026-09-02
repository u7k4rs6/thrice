# thrice: frontend spec

Status: draft, day 1. Reflects `01-prd.md` section 0 changes C1 (Starter) and C2 (no posting, corpus validation). There is no web app. The developer is not a frontend person and will not compete on polish, so every surface below is finishable in hours and legible in a 40 second recording.

## 1. CLI

Six commands. Plain text on stdout, JSON on `--json`, no TUI framework, no spinner library, no colour beyond ANSI bold and three colour codes.

| Command | Does |
|---|---|
| `thrice gates` | Runs G1 to G6 against Solari and prints a pass/fail table. The only day-1 command that spends credits |
| `thrice plan <issue-url>` | `manual` provider prints the filled prompt template and the path to write the plan to, then exits. `openai_compatible` calls the endpoint and writes the plan itself |
| `thrice run <plan-file>` | Forks, seeds, runs three browsers, scores, writes the attempt |
| `thrice report <attempt-id>` | Writes `report.html` and `comment.md`, prints the path |
| `thrice corpus score` | Reads every corpus attempt's report and emits per-entry outcomes plus aggregate correct / incorrect / INCONCLUSIVE with precision and recall (C2) |
| `thrice approve <attempt-id>` | **v2, specified and unbuilt (C2).** Records a human decision. FLAKY requires `--flaky-ok` as a separate flag |
| `thrice post <attempt-id>` | **v2, specified and unbuilt (C2).** Posts the comment, refusing without an approval record. In v1 it exits 5 with "posting is disabled in v1" |

Exit codes are stable and scriptable:

| Code | Meaning |
|---|---|
| 0 | Success. For `run`, a verdict was produced (any of the three postable ones) |
| 1 | Usage or validation error: bad plan, bad flag, missing file |
| 2 | INCONCLUSIVE. The attempt ran but produced no verdict; the reason is on stderr and in the attempt JSON |
| 3 | Budget guard refused. Nothing was launched and no credit was spent |
| 4 | Solari error: 429 at cap, capacity, or auth |
| 5 | Refused for policy: no approval record, duplicate comment, wrong repo, or INCONCLUSIVE passed to `post` |
| 6 | A gate failed (`thrice gates` only) |

`thrice run` stdout, which is what the recording shows:

```
thrice 0.1.0  attempt a7f3c21e
issue    jaegertracing/jaeger-ui#2481
app      jaeger 2.20.0  (sha256 c967368b)
budget   reserved $0.10 of $0.40 remaining today

[env]  fork from jaeger-2.20.0-ready ......... ok    18.4s
[env]  health 16686 / 4318 ................... ok     3.1s
[env]  seed 2 payloads ....................... ok     1.2s
[env]  preview url ........................... ok  (425 x3, then 200)

       run 0            run 1            run 2
       ---------------  ---------------  ---------------
st1    goto        ok   goto        ok   goto        ok
st2    click       ok   click       ok   click       ok
st3    assert      ok   assert      ok   assert      ok
       actual  HELD     actual  HELD     actual  HELD
       expect  FAILED   expect  FAILED   expect  FAILED

verdict  REPRODUCED  3/3
cost     $0.0191   (352 browser-seconds, 174 sandbox-seconds)
report   artifacts/a7f3c21e/report.html
next     thrice corpus score
```

The three-run display is three fixed-width columns rewritten in place with a carriage return, one row per step id, appended as steps complete. Steps print in plan order, so columns stay aligned when one run is slower. Plain `\r` and `\n`, not a framework. If stdout is not a TTY, each row prints once on completion.

Divergence is marked inline on FLAKY with a `<` in the gutter at the first divergent step id, and repeated in the summary.

## 2. Verdict comment (v2; not sent anywhere in v1)

**C2: nothing is posted in v1.** These templates stay because the poster is a specified v2 surface, and because `thrice report` still writes `comment.md` locally as a human-readable summary of an attempt. What changes is only that no process sends it anywhere.

One template per postable verdict, each under 120 words including the disclosure. Placeholders in angle brackets.

**REPRODUCED**

```markdown
**Reproduced 3/3** on jaeger `<version>`.

Ran the steps from this issue three times in three independent browsers against a
fresh <version> instance seeded with <n> synthetic trace(s).

- Reported behaviour (`<actual_predicate_summary>`): held in 3/3 runs.
- Expected behaviour (`<expected_predicate_summary>`): failed in 3/3 runs.

Report with per-run step timelines, screenshots and video: <report_url>

<sub>Posted by a human. Reproduction plan drafted with AI assistance from the issue
text, reviewed before running; the run itself is deterministic and has no model in
the loop. Tooling: <repo_url></sub>
```

**NOT_REPRODUCED**

```markdown
**Not reproduced 0/3** on jaeger `<version>`.

Ran the steps from this issue three times against a fresh <version> instance seeded
with <n> synthetic trace(s). Every step completed in every run.

- Reported behaviour (`<actual_predicate_summary>`): did not hold in any run.
- Expected behaviour (`<expected_predicate_summary>`): held in 3/3 runs.

This may mean the bug is fixed, or that the seeded state does not match the
reporter's. The exact plan is in the report: <report_url>

<sub>Posted by a human. Plan drafted with AI assistance, reviewed before running; the
run is deterministic. Tooling: <repo_url></sub>
```

**FLAKY**

```markdown
**Flaky <k>/3** on jaeger `<version>`.

Same steps, same seeded state, three independent browsers: the reported behaviour
held in <k> of 3 runs. First divergence at step `<step_id>` (`<key>`), where run
<a> and run <b> differ.

Report with the divergence diff and all three timelines: <report_url>

<sub>Posted by a human. Plan drafted with AI assistance, reviewed before running; the
run is deterministic. Tooling: <repo_url></sub>
```

The predicate summaries are generated from the predicate type and args, never free text from the planner, so a comment cannot contain model prose.

## 3. Report page

One self-contained static HTML file per attempt, generated from `attempt.json`. No framework, no build step, no external asset, no font download, no CDN. Inline `<style>`, inline base64 for screenshots under 200 KB, a relative path for the video. It must open correctly from `file://` and from GitHub Pages.

Layout, top to bottom:

1. **Header.** Issue repo and number as a link, app version and tarball digest, the verdict as a single large word, run count, attempt cost in dollars and in browser-seconds and sandbox-seconds, and the UTC timestamp.
2. **Plan summary.** The seeds (count and endpoint), the step list, and both predicates rendered from their typed form.
3. **Three run columns.** A CSS grid, three equal columns on wide screens, stacking to one column under 900 px. Each column is a vertical step timeline: step id, action, which locator index resolved, duration, and the step outcome. Assertion steps show their screenshot inline.
4. **Divergence marker.** On FLAKY only, a horizontal rule across all three columns at the first divergent step id, with the comparison key and the three values.
5. **Video.** A single `<video controls>` below the columns, or the screencast frame sequence if no video path won G3.
6. **Raw JSON.** A link to `attempt.json` in the same directory. Nothing in the page is the only copy of anything.

Typography and colour: `ui-monospace, SFMono-Regular, Menlo, monospace` throughout, because a report of measurements should look like one and monospace aligns the three columns for free. Body 14px, header 13px uppercase with letter-spacing. Four colours: near-black on near-white, one green for held, one red for failed, one amber for divergence.

What not to build: no dark mode, no charts, no tabs, no accordions, no filtering, no sorting, no JavaScript at all. If a section needs interactivity to be legible, the section is wrong.

## 4. READMEs

**thrice repo.** Title and one sentence. A "what you see" block showing the `thrice run` output above. The verdict taxonomy table from `01-prd.md` section 6, because it is what a maintainer must understand first and what is most likely to be misread. What thrice does not do, in five lines: no PRs, no third-party sites, no hosted service, no LLM in the run loop, one repo in v1. Install and quickstart with `uv`. A gates section with the day-1 G1 to G6 results filled in. Cost per attempt with the arithmetic. Links to the four docs. Responsible posting policy, quoted, not summarised.

**Cookbook example** (`examples/thrice-jaeger/` in the solari-cookbook fork). Matches the existing examples: short README, a `requirements.txt` pinning `solari-sandbox` and `solari-browser`, and one `main.py` that is genuinely runnable and self-contained, not a stub pointing elsewhere. It does the smallest interesting thing: fork a sandbox from a snapshot, `preview_url(16686)`, open it in a Solari browser, assert one predicate, kill. Under 120 lines, linking to the thrice repo for the full pipeline rather than duplicating it.

## 5. The post

**Recording, 30 to 45 seconds, no voiceover, no music, no titles.** Screen only, 1280x720, terminal at a readable font size.

| Time | Shot |
|---|---|
| 0:00 to 0:05 | The GitHub issue, scrolled to the reproduction steps |
| 0:05 to 0:10 | `thrice run plans/2481.json`, entered |
| 0:10 to 0:22 | The env lines appearing, then the three columns filling in together. This is the shot that carries the whole thing, so it runs at real speed, not sped up |
| 0:22 to 0:28 | `verdict REPRODUCED 3/3` and the cost line |
| 0:28 to 0:38 | The report page: header, three columns, one screenshot, the video playing |
| 0:38 to 0:45 | `thrice corpus score`: the corpus table, correct / incorrect / inconclusive, precision and recall |

> *Defect record, C2.* The final shot was "The posted comment on the issue, disclosure line visible", conditional on Q2 and the day-4 kill criterion. Nothing is posted, so the recording ends on the measurement instead, which is a stronger ending: a number with a known correct answer beats a comment nobody asked for.

**LinkedIn**, under 120 words:

> Maintainers can't tell from an issue whether a bug still reproduces, whether it's flaky, or which version it's on. So I built thrice.
>
> Give it a GitHub issue. It forks a Solari sandbox from a snapshot of the app at a pinned version, seeds known backend state, runs the reported steps in three browsers, and checks typed predicates against the DOM, console and network. Verdict: reproduced 3/3, flaky n/3 with a first-divergence diff, not reproduced, or inconclusive.
>
> Then I measured it. Against <n> already-fixed jaeger-ui issues, where the fixing commit tells you the right answer, thrice was correct on <k>. Precision <p>, recall <r>.
>
> No model in the run loop. Built on @Solari.

**X**, shorter, same first reply:

> "Does this bug still reproduce?" is a question maintainers can't cheaply answer.
>
> thrice: issue in, Solari sandbox forked from a snapshot, state seeded, steps run in 3 browsers, typed predicates checked. Out: reproduced 3/3, flaky n/3 with a divergence diff, not reproduced, or inconclusive.
>
> Measured against <n> already-fixed issues where ground truth is known: correct on <k>.
>
> No LLM in the run loop.
>
> @solari @<founder>

First reply on both, posted immediately: the repo link, the four docs, and one line noting the whole week ran for under $3.00 of Solari credits.

## 6. Non-goals

No dashboard. No leaderboard. No authentication. No hosted UI. No dark mode. No design system, no component library, no CSS framework, no icon set. The report page is a document, the CLI is a tool, and neither is a product surface.

## [UNVERIFIED] items in this document

1. **Resolved by C2.** The recording ends on `thrice corpus score` rather than a posted comment. Nothing is posted in v1, so the question is withdrawn rather than answered. Section 5.
