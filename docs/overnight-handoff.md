# Overnight handoff

## What is ready for review

No changes were merged or pushed to `main`, and nothing was deployed. The original working tree remains on `feat/spaceline-planner` with its existing uncommitted documentation/messages untouched. All implementation work used isolated worktrees/branches based on `origin/main` `53dfeff`.

| PR | Purpose | Review/merge order |
| --- | --- | --- |
| [#10](https://github.com/moon-flyers-team/moon-flyers/pull/10) | Repair current contract/component fixtures, disabled-date handling, isolated HTTP checks, CI deployment gates | First; hosted frontend/backend/container smoke checks are green. Deployment jobs skipped. |
| [#11](https://github.com/moon-flyers-team/moon-flyers/pull/11) | Correct data-source/terrain/slope claims and current horizon visibility labels | Based on #10; retarget to main after #10. |
| [#12](https://github.com/moon-flyers-team/moon-flyers/pull/12) | Fix wrong candidate metrics after scrubbing; native keyboard-accessible UTC arrival input | Based on #11; retarget after predecessor merges. |
| [#13](https://github.com/moon-flyers-team/moon-flyers/pull/13) | Give all seven numeric mission settings real accessible labels | Depends only on #10; independent of #11/#12. |
| This report PR | Research-informed browser-only Qwen experiment, exact traces, limitations and this handoff | Documentation/experiment artifacts only; no product-direction decision. |

Stacked PRs have local verification; the existing workflow only runs on main-targeted PRs. Retarget/rebase and require hosted checks before merging follow-ups. No automatic merges were enabled.

## Verification actually executed

A local integration of #10–#13 merged cleanly and passed:

- **46/46 frontend tests**.
- Both TypeScript checks and Vite production build.
- Real isolated mock HTTP pipeline through Vite, including custom sites and ranked-time consistency.
- Backend: **45 passed, 2 environment-gated skips**, one upstream deprecation warning.
- Focused Edge 157 checks: invalid-date draft/recovery; native UTC selection and keyboard changes; synchronized table/horizon with no new analysis request observed; numeric settings selectable by accessible name.

`pnpm` was absent locally, so scripts ran through npm without installing dependencies or changing lockfiles. Hosted PR #10 also passed its pnpm install/test/build/HTTP, backend and container/smoke jobs. No live Horizons/real-DEM scientific validation, full accessibility acceptance or production deployment is claimed.

## Most important findings

1. **Real correctness bug:** moving the time slider could leave comparison metrics on the first candidate because `Z` and `.000Z` strings did not match. Fixed separately, with failing-before/passing-after tests.
2. **Misleading current-state labels:** the horizon said Sun/Earth were visible regardless of the returned flags; its static eclipse key could be mistaken for a current event. Fixed without changing astronomy.
3. **Qwen is not a reliable mission analyst by itself:** it twice confidently compared the wrong dates/durations, including after it could operate the new date field. Do not reuse its final prose as a jury claim or scientific result.
4. Settings and custom-site creation were discoverable in these runs. Metric-duration versus timeline-extent semantics remained confusing. Map/rover-safety limitations were correctly identified in part, but “nearby” attractions were not validated.

Read [experiment results](agent-task-audit-results.md) for the distinctions between application bugs, interface friction, tool errors, capability gaps and agent reasoning failures. Four baseline scenarios and one fresh post-repair rerun were executed; this is exploratory AI evidence, not human user validation or a statistical benchmark.

## What was deliberately not done

- No recurring-service planner, automatic rover routing, eclipse-event service or new tourism MVP.
- No merging of the competing product ideas, feasibility comparison selecting a direction, or jury-answer package.
- No scientific/safety threshold changes, API redesign, new dependencies or global Pi/system configuration.
- No edits to the user's uncommitted proposal/session/coworker documents.

The team still needs to choose one problem at the morning sync. These repairs improve the existing tool and the reliability of what it demonstrates; they do not choose that problem for the team.
