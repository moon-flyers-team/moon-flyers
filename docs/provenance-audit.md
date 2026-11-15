# Backend claims and horizon presentation audit

Scope: approved task 2. No endpoint, scientific algorithm, dependency or product-direction change. This branch builds on the verification repair.

## Verified against implementation

- `backend/src/services/ephemeris.py`: live Horizons by default, deterministic positions with `MOON_FLYERS_EPHEMERIS=mock`; the data-source header identifies ephemerides only.
- `backend/src/services/horizon.py`: synthetic hills without `LOLA_DEM_DIR`, DEM skyline with a mounted dataset, flat fallback with a warning on uncovered coordinates/runtime DEM errors.
- `backend/src/main.py`: validates an optional DEM at startup. It does not return per-site terrain mode or fallback metadata.
- `backend/src/services/visibility.py`: slope remains null and fit checks only the four Sun/Earth metrics. A mounted DEM does not make the slope threshold effective.
- Current settings moved to App's dialog; best-times client/endpoint remain but no best-times UI component is mounted. The comparison lookup's timestamp-string fallback is documented as a limitation, not described as nearest-candidate matching.

Root API docs, backend API docs and AGENTS now distinguish these facts. Example wire shapes and science behavior are unchanged. Ephemeris and terrain sources are independent; a mock ephemeris header does not establish that the horizon is synthetic either.

## Confirmed chart claims repaired

A browser inspection of the current application showed “Sun visible” at a negative elevation even though the first sample's visibility flag was false. The chart labels had become unconditional in main; tests had been changed to accept this. Both current Sun/Earth labels now use their respective returned flags (not an elevation heuristic). The static eclipse color key says “Eclipse intervals”, not an apparent current eclipse announcement. The footer no longer universally claims a flat horizon and explicitly says terrain source is unreported and slope unassessed.

## Qwen delegation and review

`llama-local/qwen3.8-27b` completed a bounded client-contract inspection and a documentation-only worker task. Its doc patch was reviewed against actual code. Review added missing flat-fallback details, corrected remaining slope/standalone-mock ambiguity, and clarified independent source modes. This demonstrates why worker output is reviewed rather than accepted as scientific authority.

## Verification

A focused SSR test covers both flat and nonflat profiles and requires source/slope caveats. Existing current-sample visibility assertions are corrected rather than weakened. Full combined test/build results are recorded on the PR after rebasing onto the verification repair. No live Horizons/real-DEM accuracy validation, terrain fallback API redesign or operational certification is claimed.

## Remaining discrepancies / follow-ups

- Root and backend API docs still duplicate substantial material; root remains the wire-contract source of truth.
- Backend and standalone mock metric aggregation differ (sample fractions versus integrated intervals); exact cross-backend scientific equivalence is not established by mock consistency tests.
- Mock allows equal window endpoints; frontend deliberately blocks equal mission dates. Mock-only cross-endpoint tests use that implemented boundary to isolate one stay; this is not a new frontend input rule.
- No per-analysis terrain provenance is returned. Reporting unknown honestly is not implementation of richer provenance.
- Eclipse overlap is a sampled angular-disc model, not a validated event-observation service or visibility guarantee.
- Route/vehicle/thermal/energy/link/safety validation remains outside these visibility checks.
