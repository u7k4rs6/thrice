# thrice day 1: feasibility gates

Date: 2026-09-02. Plan: Starter (C1). Against `docs/01-prd.md` section 9.

All Solari work in this document was executed. Nothing here is projected.

## Summary

| Gate | Question | Verdict |
|---|---|---|
| **G1** | Does this org have a preview domain configured, and can a Solari browser load it? | **holds** |
| **G5** | Sandbox egress to github.com, binaries verified against the published sha256sum.txt | **holds** |
| **G2** | snapshot, kill, create(from_snapshot); fork time; does a fork carry the seed; revert | **holds**, with one sub-result failing (`revert`) |
| **G7** | Multi-version: two release tarballs into two snapshots, fork each, both healthy | **holds**, with a hard bound on the corpus range |
| **G3** | A video path exists | **holds**, and all three options work, which was not expected |

Total spend: **$0.0037** against a $0.20 estimate. Every sandbox was killed and every browser session released.

Three results contradict either the documentation or the day-1 instructions, and are called out where they occur: the preview not-ready status is 502 rather than the documented 425; `revert` is refused on a sandbox created from a snapshot; and Playwright `record_video` works over CDP, which the instruction to demote it assumed it would not.

---

## G1. Preview domain

### What was run

`spikes/g1_preview.py`, plus two supplements written after the first pass raised questions it could not answer.

Main run: create a 1 vCPU / 2 GB sandbox from `template="base"` with an idempotency key, write a static HTML file, serve it with `python3 -m http.server` on port 8099, call `preview_url(8099)`, fetch the returned URL from the laptop, then load it in a Solari browser over `connect_over_cdp` and read `page.url` back.

`spikes/g1b_425.py`: ask for a preview URL on a port with **nothing listening**, poll, then start the server and time the transition. The main run never saw a 425 because the server was already up.

`spikes/g1c_token.py`: is the `pt_token` actually load-bearing. The g1b pass suggested an altered and a stripped token both returned 200, but that client had already made a successful request, so a session cookie could explain it. Re-run with a fresh `httpx.AsyncClient` per request, cookies disabled, and the unauthenticated cases tried **first**.

### Raw numbers

```json
{"create_seconds": 1.27, "preview_url_seconds": 0.27,
 "preview_returned_url": true, "preview_returned_token_field": true,
 "preview_has_pt_token_in_url": true,
 "status_sequence": [200], "seconds_to_200": 1.01, "body_matches": true,
 "browser_loaded": true, "browser_sees_probe": true,
 "page_url_contains_pt_token": true,
 "js_location_search_contains_token": true,
 "page_url_shape": "https://<preview-host>/?pt_token=<...>"}
```

Not-ready behaviour, g1b, nothing listening on the port:

| Poll | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Status | 502 | 502 | 502 | 502 | 502 | 502 |

Time from starting the server to the first 200: **0.53 s**.

Token authority, g1c, fresh client per request, unauthenticated cases first:

| Case | Status | Body is the app |
|---|---|---|
| no token, tried first | **401** | no |
| wrong token (`pt_token=deadbeef`) | **401** | no |
| empty token (`pt_token=`) | **401** | no |
| valid token in query | **200** | yes |
| no token, after a valid request on a fresh client | **401** | no |
| token in `x-pinetree-preview-token` header | **200** | yes |

### Findings

**Holds.** A preview domain is configured. Host shape is `<id>-<port>.preview.getsolari.com`. `preview_url()` returned in 0.27 s and the URL was fetchable in about 1 s.

**The `pt_token` is load-bearing, and it is visible in `page.url`.** 401 without it, 401 with a wrong one, 200 with a valid one in the query or the header. And from inside the browser, both `page.url` and `location.search` contain it. This closes **Q10 in the worst direction**: the redaction control in `03-security-and-access.md` is **mandatory, not defensive**. Any `url_matches` predicate, any captured network URL, and any trajectory event that records a URL will carry a live one-hour credential unless the redactor runs first.

**The preview gateway sets a session cookie.** Every response, including the 401s, carried `Set-Cookie`. That is what made the g1b reading wrong: a client that had already presented a valid token kept access without it. Two consequences. For the runner, navigation after the first authenticated load does not need the token re-appended. For security, the cookie is a second bearer credential with the same authority as the token, and `03-security-and-access.md` should say so.

**Documentation defect: the not-ready status is 502, not 425.** The sandboxes page states "Anything that reaches the sandbox but finds nothing listening yet answers 425 Too Early; poll until it turns into your app." Six consecutive polls against a port with nothing listening returned **502**. No 425 was observed in any run. The health-check loop in `02-architecture.md` section 4 must treat 502 as the not-ready signal; a loop written to the documentation would treat 502 as a hard error and abort.

---

## G5. Sandbox egress and checksum verification

### What was run

`spikes/g5_g2_jaeger.py`, phase 1. Inside the sandbox: `curl` the pinned Jaeger 2.20.0 tarball and its `sha256sum.txt` from github.com, extract, and run `sha256sum -c` against the published file.

### Raw numbers

```json
{"download_seconds": 1.72, "download_exit": 0, "tarball_bytes": "58367331",
 "tarball_contents": ["example-hotrod", "jaeger"],
 "sha256sum_c_output": ["jaeger-2.20.0-linux-amd64/example-hotrod: OK",
                        "jaeger-2.20.0-linux-amd64/jaeger: OK"],
 "sha256sum_exit": 0}
```

### Findings

**Holds.** Egress to github.com works and is fast: 58,367,331 bytes in **1.72 s**, which is roughly 34 MB/s and far better than the laptop would manage. The `files.write` fallback is not needed.

The doc 2 section 4 correction is confirmed in practice: the published `sha256sum.txt` verifies the **extracted binaries**, not the tarball, and `sha256sum -c` run from `/opt` after extraction passes both lines. A verification step written against the tarball digest would have failed against the published file.

---

## G2. Snapshot, fork, seed persistence, revert

### What was run

`spikes/g5_g2_jaeger.py`, phase 2: start `./jaeger` with default in-memory storage, health check 16686 and 4318, seed two spans over OTLP/HTTP JSON, snapshot, kill the build sandbox, `create(from_snapshot=...)`, and inspect the forked store. Then `revert(snapshot_id)`.

`spikes/g2b_seed_persistence.py`: a re-run of the seed-persistence question only, because the first pass got it wrong. See below.

### Raw numbers

| Measurement | Value |
|---|---|
| Seconds to healthy after starting `./jaeger` | **1.52** |
| Health before snapshot | `ui_16686=200`, `otlp_4318=200` |
| Seed POST status | 200 |
| `snapshot()` | **13.6 s** |
| `create(from_snapshot=...)` | **9.59 s** |
| Connect after fork | 10.44 s cumulative |
| Fork seconds to healthy | **2.49** |
| Health after fork | `ui_16686=200`, `otlp_4318=200` |
| `revert(snapshot_id)` | **failed**, `GatewayError: Not revertable` |

Seed persistence, g2b, with spans timestamped to now and an explicit 48 hour query range:

| | services | traces | spans |
|---|---|---|---|
| before snapshot | `["jaeger", "thrice-seeded"]` | **1** | **2** |
| after fork | `["jaeger", "thrice-seeded"]` | **1** | **2** |

### Findings

**Holds.** Snapshot and fork both work, and **Jaeger is still running after the fork without being restarted**: the snapshot captures process state, so a fork is healthy 2.5 s after connect rather than needing a fresh boot. Total fork-to-usable is about 12 s against roughly 25 s for a cold build, and the gap widens for versions with slower startup.

**UNVERIFIED item 6 is answered: a fork CARRIES the pre-snapshot seed.** Snapshots must therefore be built clean, before any seeding, exactly as D1 specifies. A snapshot taken after a debugging session would silently poison every attempt forked from it, and because the poison is data rather than a crash, it would show up as wrong verdicts rather than as errors.

**A correction, recorded because the first answer was wrong.** The initial G2 run reported `trace_count: 0` after the fork and concluded the store came up empty. That was a broken query, not an empty store: Jaeger's `/api/traces` applies a default lookback window and the seed spans were timestamped November 2023, so nothing matched **before** the snapshot either. The service list carrying `thrice-probe` across the fork was the clue. Re-run with spans timestamped to now and an explicit `start`/`end` range, both sides show 1 trace and 2 spans. The lesson for the runner: a Jaeger query without an explicit time range is not evidence of absence, and any predicate that asserts on trace counts must pin the range.

**`revert(snapshot_id)` fails: `GatewayError: Not revertable`.** Attempted on a sandbox that was itself created via `from_snapshot`. The snapshots documentation presents `revert` as the way to reset a machine between test runs, and it is the mechanism `02-architecture.md` section 4 names for the sequential-with-reset alternative for stateful targets. That alternative is therefore **not available in the form documented**, at least for a sandbox created from a snapshot. Not blocking for v1, because jaeger-ui is read-only and Model A applies, but the doc 2 claim needs qualifying and the condition under which a sandbox is revertable needs establishing before any stateful target is attempted. New open question, Q19.

---

## G7. Multi-version feasibility

### What was run

`spikes/g7_multiversion.py`. Two versions built **concurrently**, which also exercises the Starter sandbox cap of exactly 2: 2.19.0 (recent) and 2.14.0 (the oldest 2.x release publishing a linux-amd64 tarball). Each: download, verify, start, health check both ports, read `jaeger version`, snapshot, kill. Then fork from both snapshots concurrently and health check each.

A separate read-only pass over the GitHub releases API established which 2.x releases exist at all.

### Raw numbers

| | 2.19.0 | 2.14.0 |
|---|---|---|
| Download and extract | 3.54 s | 3.49 s |
| Archive contents | `["example-hotrod", "jaeger"]` | `["example-hotrod", "jaeger"]` |
| `sha256sum -c` | OK, both binaries | OK, both binaries |
| Seconds to healthy | 1.53 | 1.53 |
| Health | `16686=200`, `4318=200` | `16686=200`, `4318=200` |
| `jaeger version` git-version | `v2.19.0` | `v2.14.0` |
| `snapshot()` | 13.3 s | 12.64 s |
| Build wall total | 22.13 s | 21.20 s |
| `create(from_snapshot=...)` | 10.77 s | 10.21 s |
| Fork seconds to healthy | 2.26 | 2.36 |
| Services after fork | `["jaeger"]` | `["jaeger"]` |

Two parallel builds wall clock: **22.64 s**. Two parallel forks: **14.74 s**.

Release availability:

| Tag | Release exists | linux-amd64 tarball |
|---|---|---|
| v2.0.0, v2.5.0, v2.13.0 | **no** | n/a |
| v2.14.0 through v2.20.0 (9 releases) | yes | yes, uniform naming |

### Findings

**Holds.** Two versions coexist as separate snapshots, both fork healthy, and the archive layout is identical across a six-month version spread: same two binaries, same directory naming, same checksum file convention, same default ports, same startup time. Nothing about pinning an older 2.x release is special.

**Two concurrent sandboxes work**, which is the Starter cap exactly. A third would be a non-retryable 429, so the semaphore of 2 in `02-architecture.md` section 7 is the right number and is now confirmed rather than assumed.

**A hard bound on the corpus, which the corpus design needs to absorb.** The Jaeger 2.x release series on GitHub is **2.14.0 through 2.20.0, nine releases, 2026-01-02 to 2026-07-20**. Tags below 2.14.0 do not exist as releases at all, so any jaeger-ui issue whose fix shipped before 2.14.0 cannot be tested by this method. Corpus entries must be drawn from issues fixed in that seven-month window. That is narrower than assumed when the corpus was specified and it directly constrains entry selection, so it is a day-1 finding rather than a day-4 surprise. It does not invalidate the design: nine releases give eight adjacent version pairs, which is more than the target of 8 entries needs.

**Clean forks are clean.** Services after forking a never-seeded snapshot is exactly `["jaeger"]`, corroborating G2b from the other direction: the seed persists only because it was seeded before the snapshot.

---

## G3. Video path

### What was run

`spikes/g3_video.py`, all three options against a page that animates a counter and cycles its background colour, so a blank capture is distinguishable from a working one. `spikes/g3b_replay.py` re-tested option 3 after the first pass could not retrieve a replay in 30 s.

Option 2 was probed for both failure modes separately: whether the existing context can be reconfigured, and whether a fresh context created over CDP records and where the file lands.

### Raw numbers

**Option 1, `Page.startScreencast`:**

```json
{"frames_captured": 45, "frames_landed_locally": 45, "total_bytes": 516631,
 "capture_seconds": 9.54, "ffmpeg_present": true, "ffmpeg_exit": 0,
 "video_bytes": 46272}
```
ffprobe on the stitched MP4: 800x600, 45 packets, 4.5 s.

**Option 2, Playwright `record_video`:**

```json
{"existing_context_present": true,
 "existing_context_has_record_video_setter": false,
 "new_context_with_record_video_dir": "accepted",
 "page_video_object": true,
 "video_path_reported": ".../g3_recordvideo/page@65fb8f...webm",
 "path_exists_locally": true,
 "save_as_ok": true, "save_as_bytes": 41612,
 "files_landed_locally": ["page@65fb8f...webm", "saved.webm"]}
```
ffprobe on `saved.webm`: `codec_name=vp8`, 640x480, **134 packets**, duration 5.36 s, 41,612 bytes. Frames extracted at n=2, 20, 40 have 3, 320 and 432 distinct colours respectively, matching the page's animation. The file is real and it shows the remote page.

**Option 3, session replay:** first pass, 10 polls at 3 s intervals, all 404. Re-run (g3b) with a page generating real DOM events: one 404, then success at **4.6 s**, 1,923 bytes, 8 NDJSON lines, first line `{"type":4,"data":{"href":"data:text/html,<title>g3b</title>...`, not a video container.

### Findings

**Holds, and all three options work.** The gate asked for one; it got three, which changes the ranking from a feasibility question into a merit question.

**Screencast is first, now for a positive reason.** thrice needs individually addressable frames regardless, because D6 requires a screenshot hash and an assertion-region digest per step. Screencast makes one mechanism serve both the trajectory and the video, with full control of format, quality and dimensions, riding the CDP session the run already holds.

**`record_video` works over `connect_over_cdp`, contrary to the day-1 instruction to demote it.** The instruction gave two grounds. The first is half right: the **existing** context genuinely cannot be reconfigured (`record_video` is not a settable attribute on it), but `new_context(record_video_dir=...)` on a CDP-connected browser is accepted and does record. The second ground, that the `.webm` is written on the browser host with no retrieval channel, is **wrong for `connect_over_cdp`**: Playwright's driver runs locally, Chromium video recording is implemented in that driver by consuming screencast frames and muxing them, so the bytes never live on the Solari VM at all. Mechanically, option 2 is option 1 with Playwright doing the collection and muxing. It ranks second only because the artifact is opaque: one webm per context lifetime, no per-step addressability.

No claim is made about a standing upstream feature request, because none was verified.

**Session replay is third and retrievable.** rrweb NDJSON in under 5 s after release, which is excellent evidence and cheap to keep, but it is not a video container and cannot go into a static report page as a `<video>` without a player, which conflicts with the no-framework rule. thrice takes option 1 and keeps option 3 as a second, independent record. The first pass's 30 s of 404s did not reproduce and is not treated as a result; the likely cause is that a `data:` URL page with no DOM activity produced nothing worth uploading.

---

## Credits spent against estimate

Client-measured seconds from create to kill, per gate:

| Gate | Sandbox s | Browser s | USD |
|---|---|---|---|
| G1 | 10.0 | 6.1 | $0.00033 |
| G1b (425 probe) | 8.8 | 0.0 | $0.00014 |
| G1c (token authority) | 9.8 | 0.0 | $0.00016 |
| G5 + G2 | 43.7 | 0.0 | $0.00069 |
| G2b (seed persistence) | 25.3 | 0.0 | $0.00040 |
| G7 | 50.4 | 0.0 | $0.00080 |
| G3 | 0.0 | 28.4 | $0.00079 |
| G3b (replay retry) | 0.0 | 15.7 | $0.00044 |
| **Total** | **148.0** | **50.2** | **$0.00374** |

Arithmetic at Starter rates: sandbox 148.0 x $0.00001583 = $0.00234; browser 50.2 x $0.00002778 = $0.00139; total **$0.00374**.

Estimate in `docs/01-prd.md` section 8 was "about $0.20" for day-1 gates. Actual is **$0.0037, about 1.9% of estimate**, because the estimate assumed sandbox lifetimes in minutes and every gate finished in tens of seconds. The estimate should be revised down, though it is so far inside the ceiling that it changes nothing operationally.

Two caveats on the figure. It is measured client-side from create to kill, so it excludes any provisioning time Solari bills before `create()` returns and any rounding the gateway applies per session; the true number is at or slightly above this. And it counts wall time on the two G7 sandboxes that ran concurrently as two separate clocks, which is correct for billing.

Hygiene: every sandbox was killed in a `finally` block and every browser session released via `release_and_wait`. Every `create` call carried an `Idempotency-Key`. No orphans were left; the two G7 forks were the last resources alive and both were killed.

---

## Consequences for the docs

| Finding | Document change |
|---|---|
| Not-ready preview status is 502, not the documented 425 | `02-architecture.md` section 4 health loop must poll on 502 |
| `pt_token` appears in `page.url` and `location.search` | `03-security-and-access.md` redaction becomes mandatory; Q10 closed in the worst direction |
| Preview gateway sets a session cookie granting continued access | New credential to document in `03-security-and-access.md` section 1 |
| `revert` refused on a from-snapshot sandbox | `02-architecture.md` section 4's sequential-with-reset alternative needs qualifying; Q19 |
| Jaeger 2.x releases exist only for 2.14.0 to 2.20.0 | Corpus entry selection is bounded to that window; `01-prd.md` section 7 |
| A fork carries the pre-snapshot seed | Confirms D1's clean-snapshot rule and raises its importance |
| `record_video` works over CDP | `02-architecture.md` section 8 corrected; Q9 closed opposite to expectation |
| Day-1 gate cost is 1.9% of estimate | `01-prd.md` section 8 estimate revised down |

## New open questions

- **Q19** Under what conditions is a sandbox revertable? `revert` returned `Not revertable` on a sandbox created via `from_snapshot`. Needed before any stateful target.
- **Q20** Is the preview session cookie scoped per sandbox and does it expire with the token, or outlive it?
- **Q21** Which jaeger-ui issues were fixed in releases between 2.14.0 and 2.20.0? This is now the corpus selection query, and G7 bounds it.
