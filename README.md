# thrice

**Does this bug still reproduce?** thrice answers that question for a
self-hosted web app by running the reported steps three times in three
independent browsers and checking typed predicates, rather than by asking a
model what it saw.

It was then measured against known answers.

## The result

thrice was validated against a corpus of **already-fixed jaeger-ui issues**,
where ground truth comes from the commit that closed each one. For every entry
we know the last release with the bug and the first release without it, so the
correct answer is known in advance: REPRODUCED on the buggy release,
NOT_REPRODUCED on the fixed one.

| | |
|---|---|
| Entries attempted | 6 |
| **Correct** | **3** |
| Incorrect | 2 |
| Inconclusive | 1 |
| **Precision** | **0.80** |
| **Recall** | **0.80** |

Per-attempt confusion matrix across the ten attempts that produced a verdict:

| | REPRODUCED | NOT_REPRODUCED |
|---|---|---|
| on a buggy release | TP 4 | FN 1 |
| on a fixed release | FP 1 | TN 5 |

Three of six entries were authored correctly on the first attempt and scored
right. **Two produced confident wrong answers.** One could not be set up at all.
That is the number, and the two failures are described below rather than
removed.

Sample report page: [`artifacts/4075-2.19.0-0302e4/report.html`](artifacts/4075-2.19.0-0302e4/report.html)
(28 report pages and 75 screencast videos are committed).

## How it works

```
issue -> plan (JSON, hand-authored, schema-validated)
      -> fork a Solari sandbox from a snapshot of jaeger at a pinned version
      -> seed backend state over OTLP/HTTP to localhost:4318
      -> run the steps in 3 Solari browsers over CDP, concurrently
      -> evaluate two typed predicates per run
      -> verdict
```

- **No model in the run loop.** An LLM can draft a plan offline; a human reviews
  it; the run itself is deterministic and holds no API key. Every plan in this
  corpus was hand-authored.
- **Two predicates, not one.** A run counts as reproduced only if the *actual*
  predicate holds **and** the *expected* predicate fails. Both are evaluated
  every run. "The buggy thing happened" and "the correct thing did not happen"
  are different claims.
- **Predicates are typed**, drawn from a closed set (`element_visible`,
  `element_absent`, `text_present`, `text_absent`, and others specified but not
  implemented). No arbitrary JavaScript and no XPath can come from a plan.
- **Four verdicts:** REPRODUCED (3 of 3), FLAKY (1 or 2 of 3),
  NOT_REPRODUCED (0 of 3 with every step completing), INCONCLUSIVE (any run did
  not complete, with a machine-readable reason). INCONCLUSIVE is never counted
  as correct.

Cost, measured: about **one cent per entry** for both sides once the plan is
written and the snapshots exist. The whole build ran for well under $1 of
Solari credits.

## The corpus, and what bounded it

Of 146 closed jaeger-ui issues in the window, 44 were labelled `bug` and
completed. **36 were excluded**, and the reason matters more than the number:

| Exclusion cause | Count |
|---|---|
| Fix landed after the newest buildable release | 10 |
| No identifiable fix commit (referenced PR closed unmerged) | 11 |
| Fix already present in the oldest buildable release | 1 |
| **Subtotal: release-pair availability** | **22** |
| Pure CSS or contrast regression | 10 |
| Nothing user-observable (refactor, test-only) | 2 |
| Needs an external backend (Prometheus) | 1 |
| Needs a large trace (virtualized scroll) | 1 |

**22 of 36 exclusions had nothing to do with what thrice can express.** The
issue was fine; the versions needed to check it against do not exist as
buildable releases. Jaeger 2.x is published on GitHub only for 2.14.0 through
2.20.0, nine releases over seven months. That bounds any tool built this way.

Ground truth was established by resolving the **jaeger-ui submodule pointer at
each jaeger release tag** and testing commit ancestry, not by comparing dates.
That immediately showed 2.15.0 and 2.15.1 ship an identical UI commit, making
that pair unusable.

## The two it got wrong

**#4045, a false positive.** REPRODUCED on both releases. The plan reaches the
right state (the committed screenshot shows the side panel open and the timeline
hidden, exactly the issue's configuration), and the fix moves the resizer's
render condition, so it should appear on the fixed release and not the buggy
one. It read absent on both, twice, including after a genuine bug in the
predicate evaluator was fixed. The likely remaining cause is that the internal
`sidePanelVisible` flag is not satisfied by the state the plan produces. Not
chased further: the entry was at its cutoff of two runs.

**#3967, a false negative.** NOT_REPRODUCED on both. The reported bug did not
manifest under the plan's steps on the buggy release. Its two releases have
materially different search UIs: the List/Table view toggle does not exist at
all in the older one.

**#3468, inconclusive.** The compare route renders identically on both releases,
so the URL-driven approach cannot reach the state the bug needs. Reproducing it
requires building the comparison set through the search flow, which is a
different plan in kind.

## The three-run mechanism is unvalidated

Running three times instead of once is the core of the design. On this corpus it
bought nothing:

| Measure | Count |
|---|---|
| Attempts that ran | 21 |
| Total runs | 63 |
| Completed runs | 33 |
| Attempts with at least two completed runs | 11 |
| **Attempts where completed runs disagreed** | **0** |
| **FLAKY verdicts** | **0** |

Every attempt that completed did so unanimously. The argument for three runs is
that one cannot distinguish a bug from a race, and that flakiness is the finding
maintainers most want. On this corpus that argument is **unfalsified but also
unsupported**.

It is not evidence the mechanism is worthless. The corpus was selected for
entries reproducible from a small deterministic seed, which is close to
selecting for non-flaky behaviour, and the excluded candidates include exactly
the timing-sensitive cases where flakiness would live. But the design was
validated on a corpus chosen to make it redundant, and the divergence differ is
left specified and unbuilt because there is nothing here for it to align.

## What thrice does not do

- **It posts nothing.** No comment reaches any issue tracker. It holds no
  GitHub write credential, so this is a property of the build rather than a
  promise. The poster and human approval flow are specified and unbuilt.
- No pull requests, ever.
- No third-party websites. Every target is a local or Solari-hosted app.
- No hosted service. If this ever runs for someone else, it runs on their
  runner with their key.
- One app in v1: jaeger-ui on the Jaeger 2.x all-in-one binary.

## Findings

Ten findings with evidence are in [`docs/findings.md`](docs/findings.md),
including several that are about the platform rather than about thrice:

- The preview gateway answers **502**, not the documented 425, when nothing is
  listening yet, and 502 cannot be told from a genuinely broken gateway.
- `409 Not snapshottable` and `Not revertable` are **transient**, and were
  observed to clear on their own after twenty minutes.
- **Release pairs diverge in ways absent from the fix diff**, and the obvious
  mitigation is itself version-dependent: you cannot pin a control that does not
  exist yet.
- A harness defect can hide behind a plan that only exercises the default route.
  One did, for three days.
- Playwright `record_video` **does** work over `connect_over_cdp`, contrary to
  the common assumption, because the driver is local.

## Run it

```bash
uv sync
cp .env.example .env      # SOLARI_API_KEY
uv run python -m thrice.attempt plans/4075-2.19.0.json plans/4075-2.20.0.json
uv run python -m thrice.report artifacts/<attempt-id>
```

## Docs

| | |
|---|---|
| [`docs/01-prd.md`](docs/01-prd.md) | Problem, scope, verdict taxonomy, budget model |
| [`docs/02-architecture.md`](docs/02-architecture.md) | Components, data model, environment manager, runner |
| [`docs/03-security-and-access.md`](docs/03-security-and-access.md) | Threat model and controls |
| [`docs/04-frontend-spec.md`](docs/04-frontend-spec.md) | CLI, report page, comment templates |
| [`docs/corpus-candidates.md`](docs/corpus-candidates.md) | All 44 candidates, triage, hazard classes, results |
| [`docs/findings.md`](docs/findings.md) | What this build learned, with evidence |
| [`spikes/GATES.md`](spikes/GATES.md) | Day-1 feasibility gates against live Solari |

Built on [Solari](https://getsolari.com). Seven days, one developer.
