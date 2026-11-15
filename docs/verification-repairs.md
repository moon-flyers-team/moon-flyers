# Verification repairs and CI gate

Scope: approved baseline repairs, live mock verification, and CI improvements. No tourism feature or product-direction decision. Based on `origin/main` `53dfeff`, not the older proposal baseline.

## Changes

- Migrate client/mock tests from obsolete `landing_utc` inputs and top-level comparison metrics to window-based requests and `window_metrics`.
- Keep cross-endpoint consistency assertions, including every candidate in a short window, custom coordinates, exact endpoint sampling, UTC offsets, validation and synthetic provenance.
- Test the current settings dialog rather than the removed Sidebar mission form. Export its existing component for SSR tests; no component move or new interface for users.
- Suppress duplicate applied-date notices in Profiles. Guard the custom slider and timeline seeking when disabled; disable both navigation buttons. Invalid/missing/reversed applied bounds no longer crash date formatting.
- Give each Vite SSR test server its own temporary cache. Concurrent test processes otherwise raced over the shared optimizer directory (observed Windows EPERM renames); do not serialize or skip tests to hide that failure.
- Repair the real HTTP pipeline's payloads, component props and ranked-candidate lookup. Add custom-site round-trip checks.
- Add `pnpm --dir frontend test:mock:isolated`: owns a mock and a real Vite proxy on dynamically selected loopback ports, verifies the mock source header, and closes owned processes in cleanup. Existing `test:mock` remains for developer-managed servers. Port selection has a small bind race; strict bind failures fail the check, never stop another process.
- Gate container build/deployment on frontend contracts + both TypeScript checks/build + isolated mock HTTP, and backend unit/API tests. Actions are SHA-pinned, test jobs have no deployment credentials, and the privileged deployment job remains unchanged.

## Executed locally

`pnpm` was unavailable on this shell PATH; existing scripts were invoked via npm without installing dependencies or changing lockfiles.

- `npm --prefix frontend test`: **41 passed, 0 failed**.
- `npm --prefix frontend run build`: **passed**, including both TypeScript checks.
- `npm --prefix frontend run test:mock:isolated`: **passed**, real HTTP through Vite, without live NASA/Python dependencies.
- Existing project Python environment, from `backend/`: `python -m pytest -q`: **45 passed, 2 skipped** (environment-gated live/real-dataset checks), one upstream Starlette/AnyIO deprecation warning.
- Edge 157, Windows: invalid equal-date draft shows an alert, marks both inputs invalid and disables SET MISSION. Restoring a later end date clears the error and applying it returns to four scored mock sites. Draft edits intentionally retain the previous applied analysis behind the settings dialog.

Browser checks above are limited to that actual flow; SSR does not prove all request-effect/keyboard behavior. No screen-reader, full map regression, Docker deployment or live NASA acceptance is claimed. GitHub workflow execution must be reviewed on the PR; local script success is not a claim that hosted CI passed.

## Remaining boundaries

The current custom time control is not keyboard-accessible. Exact timestamp-string matching in comparison results can also fall back to the first candidate after slider selection. Those require separate focused fixes, not fixture changes that normalize the bug. Existing terrain/source claims are handled separately. This PR does not establish scientific prediction accuracy, slope compliance, route safety, or mission readiness.
