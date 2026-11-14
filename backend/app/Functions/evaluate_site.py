"""Evaluate one Moon Flyers landing site using precomputed ephemerides and horizon.

No network/DEM access occurs here. The backend supplies the NASA-derived data.
Angles: degrees; UTC timestamps; azimuth clockwise from north; whole-disc
visibility (lower limb must clear terrain horizon by the configured margin).
"""
from datetime import timedelta
import math

from .visibility import calculate_visibility_margin
from .windows import extract_visibility_windows, parse_utc, format_utc
from .metrics import calculate_metrics, initial_visibility_hours
from .suitability import evaluate_fit


def evaluate_site(ephemeris, horizon, landing_utc, days_on_surface=14,
                  constraints=None, slope_deg=None,
                  sun_visibility=True, earth_visibility=True):
    """Return API.md's analysis block for a single landing-time/site.

    ephemeris: {
      'timestamps_utc': [ISO-8601 UTC, ...],
      'sun_azimuth_deg': [...], 'sun_elevation_deg': [...],
      'sun_angular_radius_deg': scalar or [...],
      'earth_azimuth_deg': [...], 'earth_elevation_deg': [...],
      'earth_angular_radius_deg': scalar or [...]
    }
    horizon: {'horizon_azimuth_deg': [...], 'horizon_elevation_deg': [...]}
    Any disabled body's ephemeris fields may be omitted.

    The first timestamp MUST equal landing_utc and all samples MUST be strictly
    before landing_utc + days_on_surface. The last sample is held to mission end.
    A body whose data are disabled has null metrics; fit is null unless both
    Sun and Earth are evaluated (API v0 statuses cannot encode unknown).

    Note: For /compare timeline coverage outside this mission and for
    /landing-windows, the backend must request a longer history separately.
    """
    if not isinstance(days_on_surface, (int, float)) or isinstance(days_on_surface, bool) or not math.isfinite(days_on_surface) or days_on_surface <= 0:
        raise ValueError('days_on_surface must be a positive finite number')
    if not sun_visibility and not earth_visibility:
        raise ValueError('At least one of sun_visibility / earth_visibility must be True')
    if not isinstance(ephemeris, dict) or not isinstance(horizon, dict):
        raise ValueError('ephemeris and horizon must be dictionaries')

    landing = parse_utc(landing_utc)
    mission_end = landing + timedelta(days=days_on_surface)
    end_utc = format_utc(mission_end)
    stamps = ephemeris.get('timestamps_utc')
    if not isinstance(stamps, (list, tuple)) or not stamps:
        raise ValueError('ephemeris.timestamps_utc must be a nonempty array')
    times = [parse_utc(t) for t in stamps]
    if times[0] != landing:
        raise ValueError('First ephemeris sample must equal landing_utc')
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('Ephemeris timestamps must be strictly increasing')
    if times[-1] >= mission_end:
        raise ValueError('Ephemeris samples must precede mission end')

    haz = horizon['horizon_azimuth_deg']
    hel = horizon['horizon_elevation_deg']
    clearance = (constraints or {}).get('horizon_clearance_deg', 0.3)
    n = len(stamps)
    timeseries = [{'time_utc': format_utc(t)} for t in times]
    visibility_flags = {}
    margins = {}
    windows = {}

    for body, enabled in (('sun', sun_visibility), ('earth', earth_visibility)):
        if not enabled:
            windows[body] = []
            visibility_flags[body] = None
            margins[body] = None
            continue
        az = ephemeris[f'{body}_azimuth_deg']
        el = ephemeris[f'{body}_elevation_deg']
        rad = ephemeris[f'{body}_angular_radius_deg']
        if len(az) != n or len(el) != n:
            raise ValueError(f'{body} ephemerides must have one sample per timestamp')
        margin = calculate_visibility_margin(az, el, haz, hel, rad, clearance)
        flags = [x >= 0 for x in margin]
        windows[body] = extract_visibility_windows(stamps, flags, end_utc, margin)
        margins[body] = margin
        visibility_flags[body] = flags
        for i in range(n):
            timeseries[i][f'{body}_azimuth_deg'] = float(az[i])
            timeseries[i][f'{body}_elevation_deg'] = float(el[i])
            timeseries[i][f'{body}_visible'] = flags[i]

    metrics = calculate_metrics(
        timestamps_utc=stamps,
        sun_visible=visibility_flags['sun'],
        earth_visible=visibility_flags['earth'],
        window_end_utc=end_utc,
        slope_deg=slope_deg,
        sun_clearance_margin_deg=margins['sun'],
        earth_clearance_margin_deg=margins['earth'],
    )
    for body, metric in (('sun', 'initial_sunlight_hours'),
                         ('earth', 'initial_earth_visibility_hours')):
        if visibility_flags[body] is not None:
            metrics[metric] = initial_visibility_hours(windows[body], landing_utc)

    fit = (evaluate_fit(metrics, constraints) if sun_visibility and earth_visibility
           else None)
    return {
        'timeseries': timeseries,
        'horizon': {'horizon_azimuth_deg': list(haz),
                    'horizon_elevation_deg': list(hel)},
        'windows': windows,
        'metrics': metrics,
        'fit': fit,
    }
