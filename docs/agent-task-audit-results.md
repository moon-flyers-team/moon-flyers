# Browser-only mission-task audit: results

**Bottom line:** the experiment found real correctness/accessibility defects, but it also caught Qwen confidently answering the wrong mission. Do not treat its conclusions as a user study, scientific validation, or an automatic score of the application.

Baseline: unchanged `53dfeff`, standalone **synthetic** mock, fresh disposable Edge session per task. Participant: `llama-local/qwen3.8-27b`, browser tools only, no source/API/terminal access. See [protocol](agent-task-audit.md), [reproduction details](experiments/README.md), and [text-only traces](experiments/traces/).

## 1. Observed outcomes

Counts are attempted inputs / total tool calls, including errors. They are not successful-action counts or comparable completion-time scores.

| Run | Inputs / calls | Outcome | Evidence quality |
| --- | ---: | --- | --- |
| S1: compare two sites for a declared stay | 6 / 13 | **Partial.** Found Settings, applied 3 days and 7 Aug, read both sites correctly. Did not retain the requested 1–10 Aug planning window: changed its start to 7 Aug and left the default end. | Correct mock metrics and recognition of synthetic data/unknown slope; confused mission-duration metrics with the long timeline. |
| S2: compare 7 Aug with 8 Aug | 6 / 11 | **Failed requested task.** Compared default 1 Aug/14 days with 7 Aug/3 days, never evaluated 8 Aug, then called that a one-day delay. | Confident invalid comparison despite copying some visible values correctly. This is an agent/scenario-reasoning failure, not evidence of date sensitivity. |
| S3: add Survey Ridge and compare | 18 / 28 | **Partial.** Created the exact name/coordinates and eventually applied 7 Aug/3 days. Did not preserve the requested planning bounds. | Useful values, but overinterpreted “better site” and the static eclipse key; struggled with date editing and some locator/wait syntax. |
| S4: propose a rover outing and assess evidence | 7 / 14 | **Correct capability boundary; no validated outing.** Explored Profiles, Map and Settings; explicitly said the app does not establish drivability. | Named possible attractions without measured distance; reused default 14-day metrics while discussing 3 days. “Closest” and rover feasibility were not established. |
| S2 after bounded repairs | 1 / 5 | **Still failed requested task.** Immediately found the new native arrival field, but changed 1 Aug to 2 Aug instead of evaluating 7/8 Aug; never set the 3-day stay or requested bounds. | The field interaction works. The answer remains wrong for the task and again mistakes monthly axis ticks for the metric window. No overall usability-success claim. |

Post-repair S2 was a fresh, uncoached session on the local integration of PRs #10–#13, not a continuation of the baseline conversation. It was exploratory, not a pre-registered causal A/B test. Fewer actions do **not** mean improved task completion when the wrong scenario was evaluated.

### Important examples

- S2 titled its answer “effect of arriving one day later (7 Aug vs 1 Aug)” and said “the 1-day delay flips the comparison”. It also changed stay duration from 14 to 3 days. This conclusion must be rejected.
- S3 copied “Earth visible · 0.8°” for Malapert while its table correctly showed 0% Earth visibility over the stay. Inspection confirmed the chart's current-visibility wording was unconditional, not a faithful rendering of its returned flag.
- Several runs interpreted the timeline's `Sep 1` / `Oct 1` tick labels as the analysis window, even though the actual default bounds were 1 Aug–31 Oct. Those ticks are not window bounds, and the table's per-stay metrics are not whole-timeline averages.
- All four baseline runs noticed the explicit mock banner. That is encouraging evidence about these runs, not proof that people will interpret every provenance distinction correctly.

## 2. Administrator cross-check: what S2 should have compared

The participant never received this reference. [Reference script/output](experiments/admin-reference.json) queries the explicitly synthetic mock at the specified bounds, 3-day stay and 6-hour candidate grid. It is an internal-consistency check, **not scientific ground truth**.

| Site / arrival UTC | Sun % | Night h | Earth % | Gap h | Modeled fit |
| --- | ---: | ---: | ---: | ---: | --- |
| Connecting Ridge, 7 Aug 06:00 | 100 | 0 | 0 | 72 | comms_short |
| Connecting Ridge, 8 Aug 06:00 | 100 | 0 | 0 | 72 | comms_short |
| Malapert massif, 7 Aug 06:00 | 100 | 0 | 0 | 72 | comms_short |
| Malapert massif, 8 Aug 06:00 | 100 | 0 | 11.11 | 64 | comms_short |

For this mock scenario, Malapert's Earth fraction/gap improve on 8 Aug, but remain below the declared 45% Earth threshold. Connecting Ridge does not change on these four metrics. **There is no modeled-fit recovery.** Neither Qwen S2 answer establishes this result.

For S3 on 7 Aug: Survey Ridge has 100% Sun, 0 h darkness, 13.89% Earth visibility and 62 h blackout; Malapert has 100%, 0 h, 0%, 72 h. Both remain `comms_short`; those numbers alone do not establish which site an operator should choose.

## 3. Findings and bounded fixes

| Finding | Classification and independent evidence | Action |
| --- | --- | --- |
| Scrubbing can leave the table on the first candidate | **Application correctness bug.** Slider emits `.000Z`, API emits `Z`; string equality misses and falls back. Focused tests were observed failing before the repair. | [PR #12](https://github.com/moon-flyers-team/moon-flyers/pull/12): numeric UTC identity; no substituted evidence for missing samples. |
| Exact arrival is hard to enter nonvisually | **Accessibility/workflow defect**, independently confirmed: static timestamp plus mouse-only custom track, no native keyboard alternative. | PR #12: labeled native UTC arrival input, bounded to loaded 6-hour samples. Existing timeline preserved. Edge keyboard changes update table/horizon together without additional analysis fetches. |
| Seven numeric settings have no accessible names | **Application accessibility defect.** Browser snapshot showed unnamed spinbuttons; Field labels had no input associations. | [PR #13](https://github.com/moon-flyers-team/moon-flyers/pull/13): unique IDs and explicit label associations; regression test and named-locator browser check. |
| Sun/Earth “visible” labels and eclipse key mislead | **Presentation correctness defect**, independently reproduced and checked against returned flags/code. | [PR #11](https://github.com/moon-flyers-team/moon-flyers/pull/11): independent current flags, eclipse intervals key, honest terrain/slope caveats; no new astronomy model. |
| Mission stay versus display extent is misunderstood | **Semantic/workflow friction plus agent error.** Repeated in several transcripts; axis ticks are not incorrect, but do not communicate the active mission context well to this participant. | Not silently redesigned. Candidate follow-up: show applied stay duration, full planning bounds, and a short explanation of metric versus timeline coverage; test that with people. |
| Rover route/safety cannot be established | **Missing capability / explicit scope boundary**, not a broken button. No route graph, vehicle limits or validated travel-time evidence was supplied. | Report only. No routing engine, product commitment or safe-route claim was implemented. |
| Wrong dates/duration and unsupported causal conclusions | **Agent reasoning/evidence failure.** S2 did not perform the requested scenario, including after the new input was discoverable. | Reject the answer. Keep scenario completion and conclusion correctness separate from clicking success. |
| Invalid locator/wait syntax, attempted image reads | **Tool/agent limitations.** Qwen is text-only; the gate returns DOM for image requests. | Do not classify as visual-design defects. Preserve failures in the traces. |

The fixes do not establish human usability, safe tourism, scientific precision, or a preferred product direction. Backend metric-aggregation differences, source/fallback uncertainty and unassessed slope/link/energy/vehicle constraints remain material limits.

## 4. What was used — and what cannot be concluded

Profiles, site selection, Settings, manual custom-site entry and Map were exercised across the four jobs. No task required every reference overlay, contour option, retry path or site-management action. **An unused feature here is not demonstrated to be useless.** Likewise, a source-blinded AI's failure does not establish that a person cannot complete the task.

The test is useful for locating unclear state, unsupported claims, missing evidence and concrete interaction barriers. A stronger next study should use repeated fresh runs and real users, record exact task-state completion, and independently verify final answers. It should not optimize the interface solely to make one local model pass.

## 5. Verification and delivery

- Protocol and scenarios were written before scored runs; four baseline tasks and one fresh post-repair rerun actually executed.
- Four administrator launch/pilot failures were excluded from app scoring; details are in the reproduction notes.
- Permission gate: **3 tests passed**. Five extracted JSON traces were parsed and reviewed; images, provider headers and system prompts are not published.
- Independent combined integration of PRs #10–#13: **46 frontend tests passed**, both TypeScript checks/build and isolated real mock HTTP passed. Backend: **45 passed, 2 environment-gated skips**.
- Hosted [PR #10](https://github.com/moon-flyers-team/moon-flyers/pull/10) frontend, backend and container/smoke checks passed; deployment jobs were correctly skipped. Stacked follow-up PRs have local verification and need main-targeted hosted checks after retargeting.
- No merge or push to main, no deployment, no new product features, no changes to the user's original uncommitted documents. The study report itself is delivered as a separate PR.
