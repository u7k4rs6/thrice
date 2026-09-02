# thrice: findings

What building thrice actually taught, with the evidence. Everything here was
measured on a real Solari account against real jaeger releases between
2026-09-02 and 2026-09-03. Nothing is projected.

Numbering continues the gates (G1 to G7) and hazards (H1 to H3) from
`spikes/GATES.md` and `docs/corpus-candidates.md`.

---

## F1. The preview gateway answers 502, not the documented 425, and 502 cannot be told from a real failure

**Claim.** Solari's sandboxes documentation states: "Anything that reaches the
sandbox but finds nothing listening yet answers 425 Too Early; poll until it
turns into your app." On this deployment it answers **502**.

**Evidence.** `spikes/g1b_425.py` requested a preview URL for a port with
nothing listening and polled it six times over three seconds:

| Poll | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Status | 502 | 502 | 502 | 502 | 502 | 502 |

No 425 was observed in any run, on any day. Starting the server produced a 200
in **0.53 s**.

**Why it matters more than a wrong status code.** 425 means one specific thing:
not ready yet, keep polling. 502 means an upstream failed, which is also what a
genuinely broken gateway returns. A client written to the documentation treats
502 as fatal and aborts a healthy launch; a client written to the observation
cannot distinguish "still booting" from "broken" and can only bound the wait.

thrice does the latter, and compensates by checking health **inside** the
sandbox first (`curl localhost:16686` over `commands.run`) before ever touching
the preview URL. If the app answers locally and the preview still 502s past the
deadline, the error says the gateway is at fault rather than blaming jaeger.
That ordering is the only reason a preview failure is attributable at all.

---

## F2. The 409 family (`Not snapshottable`, `Not revertable`) is transient

**Claim.** Two different 409 refusals looked like hard platform limits and both
turned out to be temporary or conditional.

**Evidence, `Not revertable` (day 1).** `revert(snapshot_id)` on a sandbox
created via `from_snapshot` returned `GatewayError: Not revertable`. The
snapshots documentation presents `revert` as the way to reset a machine between
test runs, and it is the mechanism `02-architecture.md` names for the
sequential-with-reset path for stateful targets. That path is therefore not
available in the documented form.

**Evidence, `Not snapshottable` (day 3).** `snapshot()` returned **409** four
consecutive times, including on a trivial freshly created sandbox that had just
run `echo hi` successfully. Two hypotheses were tested and both were falsified:

| Hypothesis | Test | Result |
|---|---|---|
| At the concurrent-sandbox cap | Reaped to zero live, retried | Still 409 |
| At a snapshot quota | Deleted down to two snapshots, retried | Still 409 |

Roughly twenty minutes later the identical call succeeded in 17.3 s. G7 had
performed the same call successfully earlier the same day.

**Consequence.** thrice's environment manager falls back to building jaeger in
place when snapshotting is refused, which costs about 25 s instead of 10 s per
attempt but keeps the run alive. Any client that treats a 409 here as terminal
will fail intermittently for reasons it cannot explain.

---

## F3. Release pairs diverge in ways that appear nowhere in the fix diff

**Claim.** This is the finding with the widest reach, because it constrains any
tool that tries to compare a bug across two versions, not just thrice.

Two releases of the same app can differ in ways that break a reproduction plan
while being completely absent from the commit that fixed the bug under test.

**Evidence A, the default view mode.** jaeger-ui 2.19.0 renders search results
in **List** view by default; 2.20.0 renders them in **Table**. `.ResultItemTitle`
exists only in List. A plan that clicks a search result therefore works on one
side of the #4075 pair and fails on the other, and nothing in #4075's fix diff
(`ClickToCopy.tsx`, `update-ui-find.ts`, `useServiceFilter.tsx`) mentions view
modes. Both screenshots are committed under `artifacts/`.

**Evidence B, and the sharper version: the mitigation is itself version-dependent.**
The obvious fix for A is to pin the view mode with an explicit step. That works
for the 2.19.0 to 2.20.0 pair. It fails outright for the 2.18.0 to 2.19.0 pair,
because **the List/Table toggle does not exist at 2.18.0 at all**: neither the
`Results view mode` radio group nor `TraceTable` is present in that release.
Waiting for the pin control timed out on the buggy side of #3967.

> You cannot pin a control that does not exist yet.

**Why static analysis cannot find this.** Triage reads issue metadata and sees
nothing. Diff reading reads the fix and sees nothing, because the divergence
lives in code the fix never touched. It surfaces only when both sides are
actually run, and even then it can hide: on 2.20.0 the search **succeeded** and
found the seeded trace, so every signal short of the step timeout said the run
was healthy.

**The rule that follows.** An entry is not proven until both sides have run.
Static derivation gets a plan to plausible, never to correct. That sets a floor
on the cost of a corpus entry which no amount of cleverness removes.

---

## F4. A harness defect can hide behind a plan that only exercises the default route

**Claim.** thrice carried a navigation bug for three days without a single
failing signal, because the only plan in existence happened to mask it.

**Evidence.** The base URL is a preview URL carrying a signed token, and the
runner joined paths by string concatenation:

```
https://host/?pt_token=XYZ  +  /trace/abc  ->  https://host/?pt_token=XYZ/trace/abc
```

The browser loads `/`, and jaeger-ui renders `/` as the Search page whatever
path was requested. #4075's first step asks for `/search`, and `/` renders
Search, so the bug produced exactly the intended page and nothing complained.
It surfaced the moment #3571 and #3804 asked for `/trace/<id>` and landed on a
search page with a spinner: four attempts, twelve runs, all failing on a
locator that was never the problem.

**Fix and generalisation.** A real URL join that preserves the token, plus a
post-navigation assertion (Q29) that the landed path matches the requested one.
The assertion is the part that matters: it closes the class rather than the
instance. Any future URL mistake, silent redirect or base-path misconfiguration
now fails with both paths in the message instead of surfacing as a confusing
locator miss several steps later.

**The general shape.** Defects hide behind uniform test inputs. A second plan
that differed in one dimension found it immediately. This is an argument for
corpus diversity over corpus size.

---

## F5. Sixty-three runs produced zero divergence: the three-run mechanism is unexercised

**Claim, stated plainly because it is the most important limitation of this
build: thrice's central design choice is untested by its own corpus.**

**Evidence.** Across every attempt that produced verdicts:

| Measure | Count |
|---|---|
| Attempts that ran | 21 |
| Total runs | 63 |
| Completed runs | 33 |
| Attempts with at least two completed runs | 11 |
| **Attempts where completed runs disagreed** | **0** |
| **FLAKY verdicts** | **0** |

Every attempt that completed did so unanimously: 3 of 3 or 0 of 3, never 2 of 3
or 1 of 3.

**What this means.** Running three times instead of once is the core of the
design. The argument for it is that a single run cannot distinguish a bug from
a race, and that flakiness is the finding maintainers most want. On this corpus
that argument is **unfalsified but also unsupported**. The three runs cost three
times the browser-seconds and bought no information on any entry.

**What it does not mean.** It is not evidence that the mechanism is worthless.
The corpus was deliberately selected for entries reproducible from a small
deterministic seed, which is close to selecting for non-flaky behaviour. Three
of the seven candidates that were excluded (large-trace scroll behaviour,
timing-sensitive rendering) are exactly where flakiness would live. The design
was validated on a corpus chosen to make it redundant.

**The honest conclusion.** The divergence differ specified in `02-architecture.md`
section 6 was not built, because there is nothing on this corpus for it to
align. Building it would have been writing code against zero examples. It stays
specified and unbuilt, and the three-run mechanism should be considered
unvalidated until a corpus exists that contains a genuinely flaky bug.

---

## F6. The published checksum covers the extracted binaries, not the archive

**Evidence.** `jaeger-2.20.0-linux-amd64.sha256sum.txt` contains two lines, for
`jaeger-2.20.0-linux-amd64/example-hotrod` and `jaeger-2.20.0-linux-amd64/jaeger`.
Verification is therefore extract-then-verify, and `sha256sum -c` must run from
the parent directory. A pipeline written to check the tarball digest against
that file fails every time. thrice pins its own digest of the archive as well,
so a silently replaced asset is caught before extraction rather than after.

---

## F7. A fork carries the pre-snapshot state, so snapshots must be built clean

**Evidence.** Seeded two spans, snapshotted, killed, forked. Queried with an
explicit 48-hour range on both sides:

| | services | traces | spans |
|---|---|---|---|
| before snapshot | `["jaeger", "thrice-seeded"]` | 1 | 2 |
| after fork | `["jaeger", "thrice-seeded"]` | 1 | 2 |

**Why it is worth publishing.** A snapshot taken after a debugging session
silently poisons every attempt forked from it, and because the poison is data
rather than a crash it shows up as **wrong verdicts** rather than as errors.
thrice builds snapshots before any seeding and re-verifies after every fork
that the seed it just wrote is queryable.

**A correction worth recording.** The first measurement of this reported the
opposite, that the forked store was empty. It was a broken query: Jaeger's
`/api/traces` applies a default lookback window and the seed spans were
timestamped in the past, so nothing matched **before** the snapshot either. A
query without an explicit time range is not evidence of absence.

---

## F8. Playwright `record_video` works over CDP, contrary to expectation

**Evidence.** `new_context(record_video_dir=...)` on a `connect_over_cdp`
browser was accepted, `save_as()` wrote 41,612 bytes locally, and ffprobe
confirms a valid VP8 webm, 640x480, 134 packets, 5.36 s, whose extracted frames
show the remote page animating.

**Why.** Playwright's driver runs **locally** when you connect over CDP, and
Chromium video recording is implemented in that driver by consuming screencast
frames and muxing them. The bytes never live on the browser host. The widely
assumed blocker, that the file is written on the remote machine with no
retrieval channel, does not apply to `connect_over_cdp`.

thrice still uses raw `Page.startScreencast` because it needs individually
addressable frames for per-step screenshots anyway, so one mechanism serves both
the trajectory and the video.

---

## F9. The preview token is a real credential and it reaches `page.url`

**Evidence.** With a fresh HTTP client per request and the unauthenticated cases
tried first: no token 401, wrong token 401, valid token in the query 200, valid
token in the `x-pinetree-preview-token` header 200. From inside the browser,
both `page.url` and `location.search` contain the token.

**Consequence.** Artifact redaction is mandatory rather than defensive. Any
`url_matches` predicate, any captured network URL and any trajectory event that
records a URL carries a live one-hour credential unless the redactor runs first.
The gateway also sets a **session cookie** on success, which is a second bearer
credential with the same authority: a client that has presented a valid token
once keeps access without it.

**A near miss worth recording.** An earlier measurement concluded the token was
not load-bearing, because a stripped-token request returned 200. That client had
already made an authenticated request and was reusing the session cookie. The
correct result only appeared with a fresh client and the unauthenticated cases
ordered first.

---

## F10. The corpus is bounded by release availability, not by tool capability

**Evidence.** Of 44 candidate issues, 36 were excluded. **22 of those 36 failed
on release-pair availability alone**: 10 fixes landed after 2.20.0, 11 had no
identifiable fix commit because the referenced PR was closed unmerged, and 1 was
already fixed by 2.14.0. The jaeger 2.x series exists on GitHub only for 2.14.0
through 2.20.0, nine releases spanning seven months.

For roughly two thirds of the excluded issues thrice could have produced a
verdict, and the obstacle was that the versions needed to check it against do
not exist as buildable releases. That bounds any tool built this way.

---

## Specified and deliberately not built

| Component | Why not |
|---|---|
| Divergence differ | Zero divergent runs exist to align. See F5. Writing it would be coding against no examples. |
| Poster and HITL approval | Nothing is posted in v1. Kept as a v2 surface so the policy is written before the code exists. |
| Planner (`openai_compatible`) | The manual provider costs zero and every plan this build used was hand-authored. |
| `revert`-based sequential reset | Refused by the gateway. See F2. |
