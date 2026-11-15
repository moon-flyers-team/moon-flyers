# UX copy removal shortlist (pending approval)

No existing UI copy has been removed. These are recommendations, not implementation tasks yet.

## Remove from the main view

1. **Map subtitle:** “80°S–90°S · Polar stereographic · East-positive longitude”
   (`frontend/src/MapPanel.tsx`). Keep the cap extent if useful; projection and longitude
   conventions belong in map information, not a permanent subtitle.
2. **Map:** “Basemap hidden. Clear heatmaps to restore it.”
   (`frontend/src/MapPanel.tsx`). Narrates a visible state; place on the Layers control if needed.
3. **Map:** “LOLA elevation · 500 m contours · Reference radius: 1,737.4 km”
   (`frontend/src/MapPanel.tsx`). The radius is implementation detail; the legend can own source/contour spacing.
4. **Site entry:** “Latitude −90…90°, longitude −180…180°.”
   (`frontend/src/Sidebar.tsx`). Show coordinate bounds on validation failure instead of always.
5. **Profiles loading popup:** “Fetching comparison and visibility data. This can take 10–30 seconds.”
   (`frontend/src/MainPanel.tsx`). “Loading site profiles…” already communicates the task.
   Keep one slow-request cue, not both this paragraph and “Comparing sites. This can take 10–30 seconds…”.

## Shorten or move into contextual help, rather than delete the meaning

6. **Map:** “Click map to add a site · Sun/Earth: reference averages · Other heatmaps: mission analysis”
   (`frontend/src/MapPanel.tsx`). Mixes an action with dataset semantics. Keep a short click hint;
   move dataset distinctions to the relevant controls/legends.
7. **Map navigation:** “Pinch/wheel: zoom · Two-finger scroll/right-drag: pan · Shift+scroll: pan”
   (`frontend/src/MapPanel.tsx`). Put under a Help control, preserving the Shift-pan fallback.
8. **Comparison:** “Double-click a site to choose landing · keyboard: Shift+Enter”
   (`frontend/src/ComparisonTable.tsx`). A visible “Choose landing” action would eliminate this
   instruction and make the feature discoverable without prose. Do not simply remove the only hint.
9. **Route Planner:** “Click the map to add up to 98 waypoints. Drag stops to reorder, or use ↑/↓.
   Right-drag to pan; wheel to zoom.” (`frontend/src/TouristRoutePanel.tsx`). Keep “Click map to add
   stops”; put gesture help in Help and show the limit as a compact counter.
10. **Map reference overlay:** “LOLA averages (~18.6 years), unaffected by mission settings.
    Any-disc visibility; mission scoring uses whole-disc clearance. Layers blend; view individually
    to read their scales.” (`frontend/src/MapPanel.tsx`). Keep “Long-term average, not mission-specific”
    visible; move disc/scale details to the legend's information panel.
11. **Route elevation:** “Elevation change: approximate endpoint difference from LOLA (~792 m grid),
    not cumulative ascent.” (`frontend/src/TouristRoutePanel.tsx`). Move to the Elevation change
    column help, preserving approximation and net-versus-total distinction.

12. **Every horizon chart:** “Backend horizon · terrain source not reported · slope not assessed”
    (`frontend/src/HorizonChart.tsx`). Repeating the same sentence under every site is noisy.
    Consolidate into one shared comparison note or information panel; keep the uncertainty explicit.

## Keep

- Mock/synthetic labels, offline states, errors and retry actions.
- A visible distinction between long-term reference maps and mission predictions.
- Approximate POI distances versus driving-route distances.
- Null/unevaluated slope and scientific limitations; relocate details, don't imply verified safety.
