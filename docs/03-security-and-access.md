# thrice: security and access

Status: draft, day 1. Numbering follows `01-prd.md` (D1 to D9, G1 to G7, Q1 to Q16), whose section 0 records changes C1 (Starter plan) and C2 (no posting, corpus validation).

**C2 removes an entire threat class from v1.** thrice holds no GitHub write credential and makes no write of any kind to any public tracker, so T9 (accidental posting) cannot occur. The controls for it are kept below, marked v2, because the poster is specified and will be built later, and because a control deleted when a feature is postponed tends not to come back with it.

## 1. Assets and secrets

| Secret | Scope | Storage | Rotation |
|---|---|---|---|
| `SOLARI_API_KEY` | Browsers, sandboxes, and desktops against one credit balance | `.env` only, never committed, never passed into a sandbox | Rotate in the console first, then purge. Rotation is seconds; history rewriting is an afternoon |
| `GITHUB_TOKEN` | **v1: read-only or absent.** Ingest reads public issues, needing no token beyond rate-limit headroom. The **issues: write** scope is a v2 requirement (C2) | `.env` only | Short expiry: the build week plus a few days |
| `LLM_API_KEY` (optional) | `openai_compatible` planner only. Absent by default (D3) | `.env` only | User-supplied |
| Preview URL and `pt_token` | Per sandbox, per port, valid one hour | Never written to a report, never committed | Self-expiring; fetch fresh per attempt |

The last row is easy to get wrong. `preview_url(16686)` returns a URL carrying a signed `pt_token`, and anything holding it reaches the sandbox for an hour with no API key. It is a bearer capability, so it is a secret, and it flows through parts of the system not designed to hold secrets: `page.url`, the `url_matches` predicate, captured network URLs, and any frame where the page shows its own address.

`.gitignore` covers `.env`, `artifacts/`, and `*.mp4`. CI secret-scans every push with custom rules for the `slr_live_` prefix, the GitHub fine-grained token prefix ([UNVERIFIED] against a live token), and `pt_token=`, so a contributor without hooks installed is still caught.

## 2. Threat model

| # | Threat | Vector | Impact |
|---|---|---|---|
| T1 | Prompt injection producing a malicious plan | Issue text is attacker-controlled and is the planner's input | A plan that navigates off-target, exfiltrates, or burns credits |
| T2 | Plan tampering after review | A plan file edited between `thrice plan` and `thrice run` | Same as T1, without the LLM |
| T3 | Sandbox egress abuse | The sandbox has outbound network for the tarball (G5) | The sandbox becomes a proxy or a miner |
| T4 | Browser egress to non-target hosts | A plan step or page navigating off the preview host | thrice drives a third party website, which the brief forbids |
| T5 | Seed payloads as an attack vector | OTLP JSON written into the sandbox and rendered by jaeger-ui | Oversized payloads exhaust the sandbox; crafted content renders into a posted screenshot |
| T6 | Credential leakage into sandboxes or recordings | `create(envs=...)`, or a key visible on screen | Key in a persisting snapshot, or in a public video |
| T7 | Preview token leakage | `pt_token` in report JSON, network capture, or a video frame | One hour of unauthenticated access to the sandbox |
| T8 | Credit exhaustion as denial of service | A runaway loop, or 429 retried tightly | The $3 monthly balance gone until next month |
| T9 | Accidental posting (**v2 only under C2**) | Wrong verdict, duplicate comment, or wrong repo | Spent maintainer trust, the project's scarcest asset. Cannot occur in v1: no write credential is held |
| T10 | Snapshot poisoning | A snapshot built from a tampered tarball | Every later attempt runs a compromised binary |

## 3. Controls

| Control | Threats |
|---|---|
| **Schema-validated plans, closed action enum.** `goto`, `click`, `fill`, `press`, `select`, `wait_for`, `scroll`, `assert`. An unknown action is a validation error, not a skipped step | T1, T2 |
| **No arbitrary JavaScript and no XPath from plans.** No `evaluate` action, no `by: "xpath"`. The most important control here: it is what stops a plan from being a program | T1, T2 |
| **URL allowlist.** A plan supplies a path, never a host. The base URL comes from `preview_url`, or the `env.mode: external` host under the G1 fallback. A plan containing a scheme or host fails validation | T1, T2, T4 |
| **Request interception in the browser.** The runner blocks any request whose host is not the base URL host, at the CDP level. Belt and braces over the allowlist: it also catches redirects and subresources no plan mentioned | T4 |
| **Seed size and schema limits.** At most 8 seeds, 256 KB per payload, OTLP JSON validated before writing, endpoint restricted to `/v1/traces` | T5 |
| **No secrets in the sandbox, ever.** `create(envs=...)` never carries a credential. The sandbox fetches a public tarball and serves a local port; it has no reason to hold a key and is never given one | T6, T10 |
| **Sandbox killed after every attempt.** `lifecycle={"onTimeout": "kill"}`, an explicit `kill()` in a `finally`, and an orphan sweep by `metadata.thrice_attempt` | T3, T8 |
| **Pinned tarball with SHA-256.** Both checks run: our digest on the tarball, the project's published digests on the extracted `jaeger` and `example-hotrod` | T10 |
| **Pinned SDK versions and a lockfile.** `solari-sandbox==0.2.0`, `solari-core==0.2.0`, Playwright pinned, `uv.lock` committed | T10 |
| **Preview token redaction.** Every URL passes a redactor before entering a trajectory event, report, or comment: `pt_token=[redacted]`, host replaced with `<preview-host>`. The redactor is the only public write path for artifacts, so it cannot be bypassed by forgetting to call it, and `url_matches` predicates see the redacted URL, so a plan cannot assert on the token either | T7 |
| **Screenshots are page-only.** The capture path records the viewport, not browser chrome. [UNVERIFIED], and stated rather than relied on: redaction is what holds. See Q10 | T7 |
| **Recording reviewed before publication.** Solari recording captures input values by default. thrice never types credentials, but any video reaching a public post is watched end to end first | T6, T7 |
| **Budget guard.** Per-attempt and per-day ceilings, reserved before any call, refusing rather than proceeding | T8 |
| **429 never retried.** Treated as a semaphore bug, logged, attempt aborts INCONCLUSIVE. The docs are explicit that no SDK retries a 429 and a tight loop burns quota against a wall | T8 |
| **Idempotency keys on create routes.** UUID v4 per create, so an interrupted and retried create cannot double-charge | T8 |
| **No write credential in v1 (C2).** The strongest available control, and free: thrice cannot post because it holds nothing that could. Everything below is v2 | T9 |
| **HITL approval, one comment per issue ever (v2).** `thrice post` refuses a duplicate, refuses any repo but jaegertracing/jaeger-ui, and refuses INCONCLUSIVE outright | T9 |
| **AI-assisted disclosure in every comment (v2).** Non-negotiable, and the honest framing: the plan came from a model, the run did not | T9 |
| **Token scope minimisation (v2).** Issues write only means a compromised token cannot open a PR, push a commit, or reach a private repo. This is the technical enforcement of the never-open-PRs rule, which survives C2 unchanged | T9 |

## 4. Data handling

All seeded data is synthetic: OTLP JSON describing spans that never existed in any real system, so no report page, screenshot, or video contains anyone's production trace data.

Reports identify an issue by number and URL only. Author names, avatars, and comment text never appear. The plan stores `title_sha256` rather than the title, so an attempt can be matched to an issue without republishing its text.

Artifacts live under `artifacts/<attempt_id>/`, gitignored by default. Under C2 the promotion rule changes: **every corpus attempt's report page is published**, because the corpus result is the deliverable and publishing only the flattering half would make precision and recall meaningless. Entry selection happens before running, never after seeing a result. Videos are downloaded immediately after session release; C1 raises replay retention from 1 day to 7, relaxing the deadline without changing the practice.

> *Defect record, C2.* Previously: "Only artifacts for posted verdicts are promoted into the public repo, and promotion is a deliberate copy." 

## 5. Access model for the stretch GitHub Action

Not v1, but the shape is fixed now so v1 does not foreclose it: the user supplies their own `SOLARI_API_KEY` as a repository secret, the Action runs on their runner, and the key never leaves it. thrice never operates a hosted service, never proxies a run, and never holds another organisation's credentials. There is no thrice server to compromise because there is no thrice server.

The Action needs the same posting discipline: its own fine-grained token, issues write only, one comment per issue, and human approval, which in an Action means a workflow that opens a review rather than commenting directly.

## 6. Responsible posting policy (v2; nothing is posted in v1)

**C2: no posting, and no maintainer contact.** In v1 this whole section specifies a surface that is not built. It is kept in full because the poster is a v2 component, and because writing the policy after building the poster is how policies end up shaped by whatever the code already does.

**Which repos.** jaegertracing/jaeger-ui only, enforced in code, and only with the maintainer's agreement.

> *Defect record, C2.* This clause previously continued: "and only after the lead maintainer has been asked and agreed (`01-prd.md` section 9). If he declines or does not answer by end of day 4, nothing is posted and the report pages stand as the evidence." The day-4 kill criterion is deleted and no maintainer is contacted at all in v1.

**Which verdicts.** REPRODUCED and NOT_REPRODUCED after human approval. FLAKY only with an explicit per-attempt decision, because it is the most useful verdict and the easiest to misread. INCONCLUSIVE never, so a harness failure is never dressed up as a finding.

**Wording.** Under 120 words: verdict, version, run count, evidence links. Do not diagnose the bug, propose a fix, speculate about a cause, or tag anyone. A verdict comment reports a measurement; it does not have an opinion.

**Withdrawal.** If a verdict is wrong, edit the comment to say so in the first line, keep the original below a horizontal rule so the record is intact, and note the correction in the repo. Do not delete: a silently vanished automated comment is worse than a wrong one, because it makes every other comment less trustworthy. If a maintainer asks thrice to stop, stop immediately and say so in the README.

## 7. Open questions

- **Q10** Can the `pt_token` reach a screenshot or video frame? The capture path suggests not, and the redactor makes it moot for text, but this is checked on day 1 rather than assumed.
- **Q15** Redact the preview host as well as the token? Redacting it makes report pages harder to debug; leaving it publishes an address that is useless after an hour but is still an address.
- **Q16** *Reframed by C2.* Corpus attempt artifacts are published and kept indefinitely, since they are the evidence. The question now applies only to development reruns: leaning 30 days, then delete.
- **Q18 (new)** Does publishing report pages for already-fixed issues warrant any notice to the jaeger-ui project, given that nothing is posted to their tracker and the pages reference public issues by number? Leaning no, but worth deciding deliberately rather than by omission.
- **Q17** What to do when an issue's text contains an obvious injection attempt? Leaning: refuse to plan it, record the refusal, and write it up as a finding, which is more interesting than a quiet skip.

## [UNVERIFIED] items in this document

1. [UNVERIFIED] That CDP screencast frames and Playwright screenshots never include browser chrome on a Solari-hosted browser. Believed true of the capture path, tested on day 1 (Q10). Section 3.
2. [UNVERIFIED] The GitHub fine-grained token prefix used in the secret-scanning rule, taken from GitHub's documented format and not checked against a live token. Section 1.
