# Challenge: Lunar Landing Site Navigator (NASA Space Apps 2026)

Source: https://www.spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/

## Resources (from the challenge's Resources tab)
NASA doesn't endorse non-US-government sites. Follow each site's data-use terms.

NASA:
- **Quickmap** (Arizona State University / LRO): high-resolution lunar imagery, topography and
  other LRO datasets. Good for exploring south-pole terrain and landing sites.
  https://quickmap.lroc.im-ldi.com (a JS app, so a fetch returns no content)
- **Moon Trek** (NASA): 3D lunar visualization with topography. Helps show how terrain
  affects horizon positions. https://trek.nasa.gov/moon (a JS app)
- **JPL Horizons**: ephemeris service. Gives Sun and Earth angular positions as seen from any
  point on the Moon. It's the intended foundation for the power and comms assessment.
  https://ssd.jpl.nasa.gov/horizons (API: https://ssd.jpl.nasa.gov/api/horizons.api,
  docs: https://ssd-api.jpl.nasa.gov/doc/horizons.html,
  manual: https://ssd.jpl.nasa.gov/horizons/manual.html)

Partner agency:
- **CSA Moon Exploration portal**: Canadian lunar missions and Artemis contributions. Background
  only, no data.
  https://www.asc-csa.gc.ca/eng/astronomy/moon-exploration/

Note: none of these is a raw DEM download. For horizon masks, LOLA gridded DEMs come from the
PDS Geosciences Node (pds-geosciences.wustl.edu, LRO LOLA RDR/GDR, polar LDEM products).
That source is our addition and not listed by the challenge.

## Summary
Missions to the Moon's south pole face extreme lighting and communication constraints, and
planning them takes careful coordination between science and engineering teams. Tools for
determining Sun and Earth positions at candidate landing sites exist, but their complicated
interfaces make it difficult to evaluate critical information with efficiency. Create an
intuitive tool that lets mission planners, educators, and the public compare landing sites and
dates quickly, visualizing Sun and Earth positions relative to the horizon to assess power
generation potential and direct-to-Earth communication windows.

## Background (condensed)
- CLPS and other missions need landing sites and dates that balance science and engineering needs.
- Sun position drives power (solar arrays) and thermal conditions. Earth position drives
  direct-to-Earth comms without relays.
- South pole: water ice makes it a key target, and its geometry causes extreme variation in
  illumination and Earth visibility across lunar days and seasons. Small location or date
  changes have large effects.
- Schedules slip (hardware, launch delays), so planners must quickly re-evaluate alternative
  sites in a region or alternative dates at a site.
- Existing tools (Quickmap, Moon Trek, JPL Horizons) are built for detailed analysis, not
  rapid comparison by non-specialists.

## Objectives (all optional "may include")
- Interactive site selection and comparison: a curated list (Apollo, CLPS targets, commercial
  missions, other countries' programs) plus custom coordinates; side-by-side or sequential comparison.
- Date and time flexibility: choose landing date and time; explore changes across lunar days and seasons.
- Sun and Earth position visualization relative to the horizon; time remaining before sunset or Earthset.
- Power and comms assessment: solar elevation, sunlight duration, Earth visibility windows.
- Multiple visualization approaches: 2D maps, 3D surface, other creative forms.
- Temporal dynamics: animations or timelines over a lunar day or several days.
- Accessibility across skill levels: planners, educators, the public.
- Any format: web app, mobile app, visualization, educational game, etc.

## Potential considerations
Technical:
- Ephemeris from JPL Horizons or pre-computed datasets.
- LOLA topography for realistic surfaces and accurate horizons.
- No atmosphere, so no refraction. The horizon is local terrain plus the edge of the lunar sphere.
- Show solar elevation angle prominently.

UX:
- Prioritize rapid scenario comparison.
- Communicate time to sunset or Earthset clearly.
- Make lunar-vs-terrestrial differences apparent.
- Help users understand why small changes have large impacts.

Data and accuracy:
- Account for real topography.
- Consider Earth libration and lunar orbital variations.
- Represent steep slopes and deep craters at the south pole (extreme shadows).

Impact:
- Support coordination between science and engineering teams.
- Fast response to schedule or hardware changes.
- Education for students and the public.
