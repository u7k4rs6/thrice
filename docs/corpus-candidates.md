# thrice corpus candidates

Date: 2026-09-02, day 2. Triage only: no plans written, no implementation, no credits spent.

Scope set by G7 in `spikes/GATES.md`: the Jaeger 2.x release series on GitHub is **2.14.0 through 2.20.0**, nine releases from 2026-01-02 to 2026-07-20. Tags below 2.14.0 do not exist as releases, so a corpus entry must have both its buggy and its fixed release inside that window.

## Method

1. Listed every closed jaeger-ui issue with `closed:2026-01-01..2026-07-20`: **146 issues**, of which 127 are `state_reason: completed` and **44 carry the `bug` label**. The 44 are the candidate pool; the rest are enhancements, refactors, dependency bumps, and not-planned closures.
2. Established ground truth for "which release contains the fix" by resolving the **jaeger-ui submodule pointer at each jaeger release tag**, rather than by comparing dates. jaeger vendors jaeger-ui as a submodule, so `GET /repos/jaegertracing/jaeger/contents/jaeger-ui?ref=<tag>` gives the exact UI commit shipped in each release:

| jaeger release | date | jaeger-ui commit |
|---|---|---|
| v2.14.0 | 2026-01-02 | `bd7ae825` |
| v2.14.1 | 2026-01-02 | `ca725430` |
| v2.15.0 | 2026-02-06 | `f6753161` |
| v2.15.1 | 2026-02-09 | `f6753161` |
| v2.16.0 | 2026-03-07 | `050fbe2a` |
| v2.17.0 | 2026-03-30 | `4e887dce` |
| v2.18.0 | 2026-05-13 | `460dd20d` |
| v2.19.0 | 2026-06-03 | `061fa3db` |
| v2.20.0 | 2026-07-20 | `05b8aedb` |

   Note that **v2.15.0 and v2.15.1 ship the identical UI commit**, so no UI fix can be distinguished between them. That pair is unusable for the corpus.
3. For each issue, took the closing commit from the issue timeline (or the merge commit of a linked merged PR), then computed the first containing release with `git merge-base --is-ancestor <fix> <submodule pointer>` against a blobless clone of jaeger-ui. This is an exact ancestry test, not a date heuristic.
4. Read every issue body and, for the survivors, the actual fix diff, because several issues that read as CSS regressions turn out to change the DOM. That distinction decides criterion 4 and it cannot be made from the issue text.

## Criteria

- **C1** reproducible from a seed of at most a few spans
- **C2** assertable with a predicate from the D4 list, no arbitrary JS
- **C3** not a performance, timing, or large-trace bug
- **C4** not a pure visual or CSS regression unless a region digest can carry it
- **C5** maps cleanly to an adjacent release pair

### A note on C4 and region digests

Nine candidates are dark-mode or contrast regressions. A `screenshot_region_digest_equals` predicate can technically separate them: pin the digest to the buggy rendering and it holds on the buggy release and fails on the fixed one. That is exactly why they are excluded rather than admitted. Between two adjacent releases many things change, so such a predicate reports "these pixels differ", not "this contrast bug is present". Every one of these entries would score **correct for the wrong reason**, and a corpus number inflated that way is worse than a smaller honest one. A region digest earns its place only when the region is small, stable, and the bug is the only plausible thing changing it. None of these nine meet that.

## Full table

| Issue | Title | Fix commit | Fix PR | Last release without | First release with | Seedable | Class | Excluded by |
|---|---|---|---|---|---|---|---|---|
| #3468 | TraceDiff slot B search populates slot A instead | `10f8cf1b98` | #3473 | v2.16.0 | v2.17.0 | yes | **QUALIFIES** | - |
| #3571 | Expanded span in the timeline messes up hierarchy view col | `5f360b497b` | #3572 | v2.16.0 | v2.17.0 | yes | **QUALIFIES** | - |
| #3804 | Span name and child expander in Trace Timeline cannot be a | `16d58c3745` | #3807 | v2.17.0 | v2.18.0 | yes | **QUALIFIES** | - |
| #3967 | traces selected for comparison disappear when changing sea | `cd6e0ea940` | #3968 | v2.18.0 | v2.19.0 | yes | **QUALIFIES** | - |
| #4045 | Span Detail sidepanel is not resizable when timeline is hi | `bdb1990aa6` | #4046 | v2.19.0 | v2.20.0 | yes | **QUALIFIES** | - |
| #4075 | Back-to-search arrow missing when opening trace via trace  | `68bfe1b58d` | #4080 | v2.19.0 | v2.20.0 | yes | **QUALIFIES** | - |
| #4131 | Keyboard "Previous Span" navigation skips the root span an | `782de5ffc5` | #4145 | v2.19.0 | v2.20.0 | yes | **QUALIFIES** | - |
| #2221 | Update Tooltip Arrow Configuration in Ant Design Component | `d88069dc40` | #3663 | v2.16.0 | v2.17.0 | unclear | **MARGINAL** | C2: no user-visible behaviour; at best an antd deprecation console.warn, which console_error does not match |
| #3891 | Strict OTLP schemas (Span/ResourceSpans/InstrumentationSco | `f879b46c43` | #3964 | v2.18.0 | v2.19.0 | unclear | **MARGINAL** | C1/C2: UI-observability unproven; the closing commit is a feature change (/api/v3/trace-summaries), not a targeted schema fix, so the fixed-side behaviour may differ for an unrelated reason |
| #2201 | Archive button is enabled by default | `none` | - | - | - | n/a | **EXCLUDED** | C5: no identifiable fix commit (referenced PR closed unmerged), so ground truth is unavailable |
| #3203 | Text colors unreadable (low contrast) in jaeger-ui v1.76.0 | `8a45595d87` | #3204 | - | v2.14.0 | n/a | **EXCLUDED** | C5: fix is already in v2.14.0, so no buggy release is buildable |
| #3227 | Clicking on Services dropdown's icon opens and closes it i | `483a8741cc` | #3227 | v2.20.0 | - | n/a | **EXCLUDED** | C5: fix landed after v2.20.0, so no fixed release is buildable |
| #3282 | Dark mode in v2.14.0 is unreadable | `7ea53675f9` | #3283 | v2.14.0 | v2.14.1 | n/a | **EXCLUDED** | C4: pure contrast/CSS regression |
| #3315 | On Search form the current selection in expanded dropdown  | `991e7fa5ce` | #3320 | v2.14.1 | v2.15.0 | n/a | **EXCLUDED** | C4: pure contrast/CSS regression |
| #3321 | Flame graph doesn't look right in dark theme | `7a116a3dc3` | - | v2.20.0 | - | n/a | **EXCLUDED** | C5: fix landed after v2.20.0, so no fixed release is buildable |
| #3322 | Trace Statistics view in dark mode | `173d0fde99` | #3322 | v2.20.0 | - | n/a | **EXCLUDED** | C5: fix landed after v2.20.0, so no fixed release is buildable |
| #3327 | Text visibility issue in Dark Mode for TraceDiff page | `7a82009527` | #3314 | v2.14.1 | v2.15.0 | n/a | **EXCLUDED** | C4: pure contrast/CSS regression |
| #3332 | System Architecture page does not fully support dark mode | `c2cd6cd9a2` | #3568 | v2.16.0 | v2.17.0 | n/a | **EXCLUDED** | C4: pure contrast/CSS regression |
| #3333 | Trace Graph view does not support dark mode | `f5a41347d3` | #3334 | v2.14.1 | v2.15.0 | n/a | **EXCLUDED** | C4: pure contrast/CSS regression |
| #3335 | UI issues and poor text visibility on /traces route in dar | `none` | - | - | - | n/a | **EXCLUDED** | C5: no identifiable fix commit (referenced PR closed unmerged), so ground truth is unavailable |
| #3375 | Text overlapping while resizing the screen | `e1c9d3d18d` | #3401 | v2.14.1 | v2.15.0 | n/a | **EXCLUDED** | C4 and C2: pure CSS, and requires a viewport resize, which is not in the D4 action list |
| #3444 | Increment/decrement buttons in DDG "Visible downstream hop | `4466aa03b2` | #3450 | v2.14.1 | v2.15.0 | n/a | **EXCLUDED** | C4: pure contrast/CSS regression |
| #3457 | [UX/Bug] Inaccessible Font Contrast in Header Search durin | `8b08bf7679` | #3464 | v2.14.1 | v2.15.0 | n/a | **EXCLUDED** | C4: pure contrast/CSS regression |
| #3472 | Footer X (Twitter) link points to twitter.com instead of x | `none` | - | - | - | n/a | **EXCLUDED** | C5: no identifiable fix commit (referenced PR closed unmerged), so ground truth is unavailable |
| #3477 | Uppercase trace IDs not normalizing to lowercase | `8c3447df22` | - | v2.20.0 | - | n/a | **EXCLUDED** | C5: fix landed after v2.20.0, so no fixed release is buildable |
| #3494 | Page.tsx still uses withRouteProps | `ebbdea6c09` | #3645 | v2.16.0 | v2.17.0 | n/a | **EXCLUDED** | C2: internal refactor, no user-visible behaviour to assert |
| #3499 | Dark mode warning text unreadable in System Architecture v | `none` | - | - | - | n/a | **EXCLUDED** | C5: no identifiable fix commit (referenced PR closed unmerged), so ground truth is unavailable |
| #3537 | After upgrading 2.14.1 -> 2.15.1 SPM stopped working | `efb138f63b` | #3538 | v2.15.1 | v2.16.0 | n/a | **EXCLUDED** | C1: requires an external Prometheus/SPM metrics backend, not seedable over OTLP |
| #3539 | On initial load of Monitor page the charts are half-width | `37588e7933` | - | v2.20.0 | - | n/a | **EXCLUDED** | C5: fix landed after v2.20.0, so no fixed release is buildable |
| #3559 | Base Path regression in 2.15 | `none` | - | - | - | n/a | **EXCLUDED** | C5: no identifiable fix commit (referenced PR closed unmerged), so ground truth is unavailable |
| #3566 | Dark mode is not working correctly on the Quality Metrics  | `a8368e2c27` | #3583 | v2.16.0 | v2.17.0 | n/a | **EXCLUDED** | C4: pure contrast/CSS regression |
| #3733 | Services are no longer sorted alphabetically | `d28da37209` | - | v2.20.0 | - | n/a | **EXCLUDED** | C5: fix landed after v2.20.0, so no fixed release is buildable |
| #3767 | Timeline view time scale labels are overlapping | `648dca98b6` | #3768 | v2.17.0 | v2.18.0 | n/a | **EXCLUDED** | C4: pure CSS overlap, and requires narrowing a column |
| #3794 | UiFindInput clear button is not keyboard accessible and ex | `none` | - | - | - | n/a | **EXCLUDED** | C5: no identifiable fix commit (referenced PR closed unmerged), so ground truth is unavailable |
| #3796 | ClickToCopy uses deprecated document.execCommand instead o | `none` | - | - | - | n/a | **EXCLUDED** | C5: no identifiable fix commit (referenced PR closed unmerged), so ground truth is unavailable |
| #3799 | fix: TraceId test silently passes without ever validating  | `035dfdd63e` | #3894 | v2.19.0 | v2.20.0 | n/a | **EXCLUDED** | C2: test-only defect, no runtime behaviour |
| #3805 | Missing Word Wrap on Long Span Warnings Causes Layout Brea | `none` | - | - | - | n/a | **EXCLUDED** | C5: no identifiable fix commit (referenced PR closed unmerged), so ground truth is unavailable |
| #3901 | stringSupplant silently drops formatter output when no URL | `a5640594ac` | #3902 | v2.20.0 | - | n/a | **EXCLUDED** | C5: fix landed after v2.20.0, so no fixed release is buildable |
| #3923 | Loading a trace with a deep parent-child chain crashes wit | `none` | - | - | - | n/a | **EXCLUDED** | C5: no identifiable fix commit (referenced PR closed unmerged), so ground truth is unavailable |
| #3939 | SearchForm don't allow microseconds (us) | `2b96871674` | - | v2.20.0 | - | n/a | **EXCLUDED** | C5: fix landed after v2.20.0, so no fixed release is buildable |
| #4055 | yarn start fails after fresh clone  @assistant-ui/tap not  | `none` | - | - | - | n/a | **EXCLUDED** | C5: no identifiable fix commit (referenced PR closed unmerged), so ground truth is unavailable |
| #4070 | [Bug/UI]: System Architecture edge weights are unreadable  | `aa761ecac2` | - | v2.20.0 | - | n/a | **EXCLUDED** | C5: fix landed after v2.20.0, so no fixed release is buildable |
| #4135 | Find by Trace ID field does not clear on reload | `a99551c105` | #4135 | v2.20.0 | - | n/a | **EXCLUDED** | C5: fix landed after v2.20.0, so no fixed release is buildable |
| #4243 | Start time column in search table remains highlighted | `none` | - | - | - | n/a | **EXCLUDED** | C5: no identifiable fix commit (referenced PR closed unmerged), so ground truth is unavailable |

## Counts

| Class | Count |
|---|---|
| **QUALIFIES** | **7** |
| MARGINAL | 2 |
| EXCLUDED | 35 |
| **Total bug-labelled, completed, closed in window** | **44** |

Exclusions by criterion:

| Criterion | Count | Detail |
|---|---|---|
| C5, fix landed after v2.20.0 | 10 | No buildable fixed release |
| C5, no identifiable fix commit | 11 | Referenced PR closed unmerged; ground truth unavailable |
| C5, fix already in v2.14.0 | 1 | No buildable buggy release |
| C4, pure CSS or contrast | 10 | Nine dark-mode/contrast plus one overlap-on-resize |
| C2, nothing user-observable | 2 | One refactor, one test-only defect |
| C1, needs an external backend | 1 | SPM requires Prometheus |

The single largest cause of exclusion is not the predicate criteria at all: **22 of 35 exclusions are C5**, meaning the issue is fine but the release pair is not available. That is a consequence of the seven-month window G7 established, and it is worth stating plainly because it means the corpus is bounded by release availability rather than by thrice's expressiveness.

## QUALIFIES entries: seed and predicate sketches

Predicate pairs follow D4: the run counts as reproduced only if the **actual** predicate holds and the **expected** predicate fails. All locators are role, text, testid, or CSS. No XPath, no JavaScript.

### 1. #3468 TraceDiff slot B search populates slot A (v2.16.0 to v2.17.0)
- **Seed**: two traces, two spans each, distinct service names and fixed trace IDs `aaaa...` and `bbbb...`.
- **Steps**: goto `/trace/<A>...<B>` compare view, open slot B dropdown, select trace B.
- **actual**: `text_present` scoped to the slot A container, regex matching trace B's short ID.
- **expected**: `text_present` scoped to the slot B container, same regex.
- Fix is 4 lines in `getValidState.ts`, so the DOM difference is exactly the slot assignment.

### 2. #3571 Detail-row hierarchy guides missing for parent spans (v2.16.0 to v2.17.0)
- **Seed**: three spans, root to mid to leaf, so the mid span has children.
- **Steps**: goto the trace, click the mid span to expand its detail row.
- **actual**: `element_absent` on css `[data-testid="detail-row-self-guide"]`.
- **expected**: `element_visible` on the same locator.
- Reads as a CSS bug in the issue text; the fix diff adds a real DOM node with a `data-testid`, which is why it survives C4. Verified in the diff of `SpanTreeOffset.tsx`.

### 3. #3804 Child expander not keyboard reachable (v2.17.0 to v2.18.0)
- **Seed**: two spans, root plus one child, so the expander renders.
- **Steps**: goto the trace, locate the children-toggle switch in the timeline.
- **actual**: `element_absent` on css `[role="switch"][tabindex="0"]`.
- **expected**: `element_visible` on role `switch` with accessible name `Expand or collapse child spans`.
- The fix adds `tabIndex: 0`, `onKeyDown`, and that exact `aria-label`, so both sides are attribute-level facts rather than rendering judgements.

### 4. #3967 Comparison selection lost when the search service changes (v2.18.0 to v2.19.0)
- **Seed**: two traces, one per service (`svc-a`, `svc-b`), two spans each.
- **Steps**: search `svc-a`, tick the compare checkbox on the result, switch the service to `svc-b`, search again.
- **actual**: `count_equals` on the selected-for-comparison strip items, value 0.
- **expected**: `count_equals` on the same locator, value 1.

### 5. #4045 Side panel resizer absent when the timeline is hidden (v2.19.0 to v2.20.0)
- **Seed**: two spans.
- **Steps**: goto the trace, hide the timeline column, open the span detail side panel.
- **actual**: `element_absent` on css `.VerticalResizer`.
- **expected**: `element_visible` on css `.VerticalResizer`.
- Before the fix `VerticalResizer` sat inside the `timelineBarsVisible` branch; after it, it renders on `timelineBarsVisible || sidePanelVisible`. One open detail: confirm the UI control that hides the timeline, since the steps depend on it.

### 6. #4075 Back-to-search arrow missing when opening a trace via its trace ID (v2.19.0 to v2.20.0)
- **Seed**: one trace, two spans, one service.
- **Steps**: goto `/search?service=<svc>`, click the trace ID (the copy-to-clipboard element) in the result row rather than the trace name.
- **actual**: `element_absent` on the back-to-search control.
- **expected**: `element_visible` on the back-to-search control.
- The fix is `{ replace: true, state: location.state }` in `update-ui-find.ts`: the arrow's presence is driven by preserved router state, so this is a clean presence/absence pair. The strongest entry in the set.

### 7. #4131 Previous-span navigation skips the root span (v2.19.0 to v2.20.0)
- **Seed**: four spans in a chain, root span name carrying a unique token such as `rootmatch`.
- **Steps**: goto the trace, fill the find input with the token, press the previous-span shortcut.
- **actual**: `element_visible` on the focus-highlight class scoped to the **last** span row.
- **expected**: `element_visible` on the focus-highlight class scoped to the **root** span row.
- Root cause is `!nextSpanIndex` treating a valid index 0 as not-found; the fix changes it to `nextSpanIndex === undefined`. The observable is which row carries the highlight, so the exact class name needs pinning during plan authoring.

## Practical consequences

**Snapshots needed: five, not fourteen.** The seven entries cluster on four adjacent pairs, so the corpus needs snapshots for v2.16.0, v2.17.0, v2.18.0, v2.19.0 and v2.20.0 only.

| Release pair | Entries |
|---|---|
| v2.16.0 to v2.17.0 | #3468, #3571 |
| v2.17.0 to v2.18.0 | #3804 |
| v2.18.0 to v2.19.0 | #3967 |
| v2.19.0 to v2.20.0 | #4045, #4075, #4131 |

**Cost.** 7 entries x 2 attempts = 14 attempts. At the Model A figure of $0.0129 from `docs/01-prd.md` section 8, that is **$0.18**. Five snapshot builds at the 22 s per version measured in G7 is 110 sandbox-seconds, about **$0.002**. The corpus is free in budget terms; the cost is plan-authoring time, as section 7 already argued.

**Coverage shape.** The seven span four of the eight available adjacent pairs and touch five distinct areas of the UI: trace diff, timeline hierarchy, keyboard accessibility, search state, and routing state. None is a variation on another, which matters more for a corpus of seven than breadth would.

## Go / no-go

**GO.** Seven entries qualify against a floor of five, with no MARGINAL entries promoted to reach the number.

Two things to carry into day 3. The day-7 target in `docs/01-prd.md` section 7 is 8 entries with a floor of 5 and a stretch of 12; **12 is now off the table** and 8 is only reachable by promoting a MARGINAL entry, which is what the floor exists to prevent. The realistic target is **7**, and section 7 should be corrected to say so rather than leaving a stretch figure the release window cannot support.

Second, three of the seven come from the same v2.19.0 to v2.20.0 pair. If that pair turns out to have an unrelated problem, such as a UI change that breaks all three plans at once, the corpus loses three entries together rather than one. Worth authoring #4075 first, since it is both the cleanest and a canary for that pair.

## Open questions

- **Q22** How is the timeline column hidden in the UI, for #4045's steps?
- **Q23** What is the exact focus-highlight class on a span row, for #4131's predicates?
- **Q24** Does the v2.15.0 / v2.15.1 shared UI commit mean any other release pair also shares a pointer? Checked for these nine and it does not, but worth re-checking if the window ever widens.
- **Q25** What makes a sandbox "Not snapshottable"? `snapshot()` returned 409 on four consecutive attempts on day 3, including on a trivial freshly created sandbox with zero other sandboxes live and only two snapshots stored, then succeeded normally twenty minutes later. Ruled out: concurrent-sandbox state and a snapshot quota. Same 409 family as day 1's `Not revertable`. Treated as transient, and the environment manager now falls back to building in place.
- **Q26** How does a plan make jaeger-ui actually run a search? `/search?service=<svc>&lookback=1h&limit=20` applies lookback and limit but leaves the service unselected and "Find Traces" disabled, so no search executes. Likely the services list loads asynchronously and the query param is applied before the option exists. Blocks #4075 and every other entry whose steps start from search results, which is most of them.

---

## Day 3 addendum: #4075 predicate pair corrected, and the entry is not yet proven

The day-2 sketch for #4075 above (section "6.") proposed
`element_absent` / `element_visible` on the back-to-search control. **That pair
is wrong and would have scored the entry incorrect.**

Reading the fix diff on day 3 shows the maintainers did not implement the
behaviour the issue asked for. The issue says "The back-to-search button should
appear in both cases." The fix instead adds `e.preventDefault()` to
`ClickToCopy.whenClicked`, so on v2.20.0 clicking the trace ID copies it and
**does not navigate at all**. The back arrow is therefore absent on both
releases after that click: on v2.19.0 because router state was lost, on v2.20.0
because you never left the search page. The sketched `element_absent` predicate
would hold on both, returning REPRODUCED twice and marking the entry incorrect
for a reason that has nothing to do with thrice.

The corrected pair keys on the observable that actually separates the releases,
which is whether the click navigated at all:

- **actual**: `element_visible` on `.TracePageHeader` (the click navigated to a trace page)
- **expected**: `element_visible` on `.SearchResults` (the click copied and left search in place)

Mechanism, confirmed in the source at both pinned commits: `TracePageHeader`
renders the back `Link` only when `toSearch` is truthy, and
`toSearch = location.state.fromSearch`. On v2.19.0 `stopPropagation()` prevents
react-router's handler from running but the native anchor default still fires,
so the browser does a full page load and `location.state` is lost.

**Status: not yet proven.** The first end-to-end run returned INCONCLUSIVE with
reason `locator_miss` on both versions, because navigating to
`/search?service=<svc>&lookback=1h&limit=20` renders the search form with the
service left unselected and "Find Traces" disabled, so no search runs and no
result row exists to click. That is a defect in the plan's steps, not in the
predicates, and it is recorded rather than tuned away. See Q26.

> *Defect record, day 3.* The superseded sketch: "**actual**: `element_absent`
> on the back-to-search control. **expected**: `element_visible` on the
> back-to-search control. The fix is `{ replace: true, state: location.state }`
> in `update-ui-find.ts` ... The strongest entry in the set." The
> `update-ui-find.ts` change is real but it is not what makes this click
> behave differently; the `preventDefault()` in `ClickToCopy.tsx` is.

**This is worth generalising before the other six plans are authored.** The
day-2 triage read issue text and fix diffs, but it inferred the *expected*
behaviour from the issue rather than from the fix. Where a maintainer fixes a
bug differently from how the reporter framed it, a predicate pair derived from
the issue will be wrong. Every remaining entry needs its expected predicate
derived from the fix diff, not from the issue's "Expected behavior" section.
