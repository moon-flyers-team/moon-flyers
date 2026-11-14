"""Search and rank landing opportunities from a *single* visibility history.

Uses the visibility data you've already calculated to determine the best times to land.

This is geometry-based screening, not spacecraft power or RF link analysis.
The ephemerides / horizon data must cover [window_start, window_end + duration].
Candidate landing timestamps include window_start and any step-aligned time <= window_end.

Exmaple usage:
Imagine the user specifies:
- Possible landing dates: 1–31 August 2027.
- Mission duration: 14 days.
- Minimum Sun visibility: 60%.
- Maximum uninterrupted darkness: 48 hours.
- Minimum Earth visibility: 45%.
- Maximum communication blackout: 24 hours.
Your application needs to answer:

If we could land at any time during August, which landing dates would best satisfy these requirements?
"""
from datetime import timedelta
import math

from .windows import extract_visibility_windows, parse_utc, format_utc
from .metrics import _summary, initial_visibility_hours
from .suitability import evaluate_fit


def _clip_windows(windows, start, end):
    """ Selecting the relevant mission interval
    Intersect a precomputed ordered set of UTC visibility windows with [start,end].
    Suppose the Sun is continuously visible from August 5 until August 20. But you're evaluating a mission that begins on August 10 and ends on August 17.
    The function returns only August 10–17.
    """
    clipped = []
    for w in windows:
        a, b = parse_utc(w['start_utc']), parse_utc(w['end_utc'])
        # Keep only the overlap with this mission; intervals outside it contribute nothing.
        left, right = max(a, start), min(b, end)
        if left < right:
            clipped.append({'start_utc': format_utc(left), 'end_utc': format_utc(right)})
    return clipped


def rank_landing_windows(candidates, limit=5):
    """Return API-shaped best candidates, fitting missions first.

    Contract v0 order: satisfies all requirements first, then Sun visibility %,
    then Earth visibility %. Other failing status classes have equal priority.
    Tie breaker is earlier landing timestamp for deterministic output.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError('limit must be a positive integer')
    # Python sorts ascending: negative values put successful fits and larger
    # visibility percentages first. Timestamp resolves otherwise equal candidates.
    ordered = sorted(candidates, key=lambda c: (
        -(c['fit']['status'] == 'both_met'),
        -c['metrics']['sun_visible_pct'],
        -c['metrics']['earth_visible_pct'],
        parse_utc(c['landing_utc']),
    ))
    return [{**c, 'rank': idx} for idx, c in enumerate(ordered[:limit], start=1)]


def find_landing_windows(
    timestamps_utc,
    sun_visible,
    earth_visible,
    data_end_utc,
    window_start_utc,
    window_end_utc,
    days_on_surface=14,
    candidate_step_hours=6,
    constraints=None,
    limit=5,
    sun_clearance_margin_deg=None,
    earth_clearance_margin_deg=None,
    slope_deg=None,
):
    """Find landing times for one site, returning the API /landing-windows list.

    Input time series should be from Physicist 1; margins optional, but recommended
    for interpolated crossings. Both bodies required because fit needs both.
    The data series starts no later than window_start and runs to data_end_utc.
    Samples need not be aligned to candidate times: windows are precomputed once
    then clipped precisely to each candidate [landing, landing+duration).
    """
    for label, value in [('days_on_surface', days_on_surface), ('candidate_step_hours', candidate_step_hours)]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{label} must be a finite positive number')
    if sun_visible is None or earth_visible is None:
        raise ValueError('Both Sun and Earth histories are required to evaluate suitability')
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError('limit must be a positive integer')

    # Search bounds describe possible touchdown times, not the end of the data.
    # The last candidate still needs a complete surface stay beyond the search end.
    start, stop = parse_utc(window_start_utc), parse_utc(window_end_utc)
    data_end = parse_utc(data_end_utc)
    if stop < start:
        raise ValueError('Landing window end must not precede start')
    duration = timedelta(days=days_on_surface)
    step = timedelta(hours=candidate_step_hours)
    if not timestamps_utc or parse_utc(timestamps_utc[0]) > start or data_end < stop + duration:
        raise ValueError('Visibility data must cover the complete candidate search and surface stays')

    # Extract once; don't recompute ephemerides for every landing time.
    sun_windows = extract_visibility_windows(
        timestamps_utc, sun_visible, data_end_utc, sun_clearance_margin_deg)
    earth_windows = extract_visibility_windows(
        timestamps_utc, earth_visible, data_end_utc, earth_clearance_margin_deg)
    
    # Reuse the same history for every candidate. Clipping supports touchdown
    # between observation times without snapping it to the nearest sample.
    candidates = []
    landing = start
    while landing <= stop:
        mission_end = landing + duration
        sw = _clip_windows(sun_windows, landing, mission_end)
        ew = _clip_windows(earth_windows, landing, mission_end)
        # Score just this candidate’s stay, including gaps at either mission boundary.
        sun_hours, longest_dark = _summary(sw, landing, mission_end)
        earth_hours, longest_blackout = _summary(ew, landing, mission_end)
        total = duration.total_seconds() / 3600
        metrics = {
            'sun_visible_pct': 100 * sun_hours / total,
            'longest_darkness_hours': longest_dark,
            'earth_visible_pct': 100 * earth_hours / total,
            'longest_earth_blackout_hours': longest_blackout,
            'slope_deg': slope_deg,
        }
        # Opt-in extension to API v0; add only when initial-stay rules requested.
        if constraints and 'min_initial_sunlight_hours' in constraints:
            metrics['initial_sunlight_hours'] = initial_visibility_hours(sw, landing)
        if constraints and 'min_initial_earth_visibility_hours' in constraints:
            metrics['initial_earth_visibility_hours'] = initial_visibility_hours(ew, landing)
        candidates.append({
            'landing_utc': format_utc(landing),
            'metrics': metrics,
            'fit': evaluate_fit(metrics, constraints),
        })
        landing += step
    return rank_landing_windows(candidates, limit=limit)
