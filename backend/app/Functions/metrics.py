"""Moon Flyers mission statistics from sampled full-disc visibility."""
import math
from .windows import extract_visibility_windows, parse_utc


def _hours(a, b):
    return (b - a).total_seconds() / 3600


def _summary(windows, start, end):
    seen = 0.0
    longest_gap = 0.0
    cursor = start
    for window in windows:
        a, b = parse_utc(window["start_utc"]), parse_utc(window["end_utc"])
        longest_gap = max(longest_gap, _hours(cursor, a))
        seen += _hours(a, b)
        cursor = b
    return seen, max(longest_gap, _hours(cursor, end))


def calculate_metrics(timestamps_utc, sun_visible, earth_visible, window_end_utc,
                      slope_deg=None, sun_clearance_margin_deg=None,
                      earth_clearance_margin_deg=None):
    """Return API.md metrics; disabled body can be None -> its two metrics null.

    If margins are passed, zero-crossings are estimated by linear interpolation.
    Requires first timestamp to equal the requested mission start. Backend
    should slice long search histories to each candidate's mission interval.
    """
    if not timestamps_utc:
        raise ValueError("Need a sample at mission start")
    start, end = parse_utc(timestamps_utc[0]), parse_utc(window_end_utc)
    total = _hours(start, end)
    if total <= 0:
        raise ValueError("Mission duration must be positive")
    if slope_deg is not None and (not math.isfinite(slope_deg) or slope_deg < 0 or slope_deg > 90):
        raise ValueError("Slope must be between 0 and 90 degrees")

    result = {
        "sun_visible_pct": None,
        "longest_darkness_hours": None,
        "earth_visible_pct": None,
        "longest_earth_blackout_hours": None,
        "slope_deg": slope_deg,
    }
    for flags, margin, pct_name, gap_name in (
        (sun_visible, sun_clearance_margin_deg, "sun_visible_pct", "longest_darkness_hours"),
        (earth_visible, earth_clearance_margin_deg, "earth_visible_pct", "longest_earth_blackout_hours"),
    ):
        if flags is None:
            if margin is not None:
                raise ValueError("Cannot supply a margin for a disabled body")
            continue
        windows = extract_visibility_windows(timestamps_utc, flags, window_end_utc, margin)
        visible_hours, max_gap = _summary(windows, start, end)
        result[pct_name] = 100 * visible_hours / total
        result[gap_name] = max_gap
    return result
