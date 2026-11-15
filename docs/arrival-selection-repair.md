# Selected-arrival evidence repair

A separate bounded correctness/accessibility fix, not a new planner or product decision.

## Reproduction

The API returns UTC strings ending in `Z`; the custom slider emits `Date.toISOString()` strings ending in `.000Z`. `ComparisonTable` compared strings, missed the selected candidate, then silently displayed the first candidate. Thus the horizon could move to a new time while the table still showed the start-of-window evidence. This is an analysis-result bug, not just a visual affordance issue.

Three focused SSR tests were added first and all failed on the prior implementation: equivalent UTC identity, unsampled arrival handling, and a labeled bounded time input.

## Change

- Match candidates by numeric UTC instant. No nearest/first-candidate fallback: an unsampled selected instant explicitly says “Not sampled” and has no invented metrics.
- Replace the static landing-time text with a labeled native `datetime-local` control interpreted explicitly as UTC, bounded to the loaded arrival window and the same 6-hour grid. Existing map, custom timeline and request architecture are preserved.
- Native keyboard editing supplies an alternative to the mouse-only custom timeline. Invalid/out-of-range/off-grid edits do not change selection. This is not a full accessibility certification.

## Verification

Before stacking with the provenance PR: `npm --prefix frontend test` passed **44/44**, both TypeScript checks/build passed, and isolated mock HTTP passed. The three new tests were observed failing before the fix, then passing.

Edge 157 on Windows: filled the arrival field with 7 August 2027 06:00 UTC, then used ArrowUp twice to move the day segment to 8 and 9 August. Table metrics and horizon timestamp changed together. The six initial `/api/` resource entries remained six after the keyboard change: no additional analysis request was observed. The demonstration used the default 14-day synthetic stay, not a scientific prediction or the blinded participant's 3-day task.

The participant audit ran against unchanged main in a different worktree/browser; no UI improvements were introduced into its baseline. See the separate audit report for participant outcomes and methodological limitations.
