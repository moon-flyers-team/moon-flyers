"""Convert visibility histories into UTC windows.

Optional signed-clearance margins allow linear interpolation of threshold
crossings. This is a numerical approximation, not an ephemeris recomputation.
"""
from datetime import datetime, timezone, timedelta
import math


def parse_utc(value):
    """Parse a timezone-qualified ISO timestamp and normalize it to UTC."""
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO 8601 string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp: {value}") from exc
    if dt.tzinfo is None:
        raise ValueError("Timestamp needs timezone (Z or offset)")
    return dt.astimezone(timezone.utc)


def format_utc(value):
    # Keep sub-second crossing times if present; do not shift crossings by rounding.
    """Serialize a datetime as UTC, keeping fractional seconds when needed."""
    dt = value.astimezone(timezone.utc)
    return dt.isoformat(timespec="microseconds" if dt.microsecond else "seconds").replace("+00:00", "Z")


def _segments(timestamps_utc, flags, window_end_utc, clearance_margin_deg=None):
    """Build ordered (start, end, visible) pieces before merging visible runs."""
    stamps = [parse_utc(t) for t in timestamps_utc]
    end = parse_utc(window_end_utc)
    values = list(flags) if flags is not None else []
    if not stamps or len(stamps) != len(values):
        raise ValueError("Nonempty timestamps and flags must be equal length")
    if any(type(v) is not bool for v in values):
        raise ValueError("Visibility flags must be Python booleans")
    if any(b <= a for a, b in zip(stamps, stamps[1:])) or end <= stamps[-1]:
        raise ValueError("Timestamps must increase strictly and end before window_end_utc")

    # Without margins, assume each flag remains true/false until the next sample.
    if clearance_margin_deg is None:
        return [(stamps[i], stamps[i + 1] if i + 1 < len(stamps) else end, flag)
                for i, flag in enumerate(values)]

    # Margins locate crossings more precisely; their signs must match the flags.
    margins = list(clearance_margin_deg)
    if len(margins) != len(stamps) or not all(math.isfinite(float(x)) for x in margins):
        raise ValueError("Finite margin required for each timestamp")
    if values != [float(m) >= 0 for m in margins]:
        raise ValueError("Visibility flags must agree with signed clearance margins")

    segments = []
    for i in range(len(stamps) - 1):
        a, b = stamps[i], stamps[i + 1]
        m0, m1 = float(margins[i]), float(margins[i + 1])
        if (m0 < 0 < m1) or (m1 < 0 < m0):
            # Opposite signs mean a crossing: estimate where the margin reaches zero
            # assuming it changes linearly between these two observations.
            frac = -m0 / (m1 - m0)
            crossing = a + (b - a) * frac
            segments.extend([(a, crossing, m0 > 0), (crossing, b, m1 > 0)])
        else:
            # A zero endpoint is a point event; do not invent a nonzero window.
            segments.append((a, b, (m0 + m1) / 2 >= 0))
    # No right-hand sample beyond the last timestamp: retain its final state.
    segments.append((stamps[-1], end, values[-1]))
    return segments


def extract_visibility_windows(timestamps_utc, visibility_flags, window_end_utc,
                               clearance_margin_deg=None):
    """Return [{start_utc,end_utc}] visible intervals.

    Without margins: sample-and-hold visibility on [sample_i, sample_(i+1)).
    With margins: linearly interpolate zero crossings between samples; the
    last sample is still held to window_end_utc. Sub-step events can be missed.
    """
    segments = _segments(timestamps_utc, visibility_flags, window_end_utc,
                         clearance_margin_deg)
    # Join adjacent visible segments into a single interval. The end is exclusive:
    # [start, end) includes the start instant but does not add time at the end.
    windows = []
    start = stop = None
    for a, b, on in segments:
        if b <= a:
            continue
        if on:
            if start is None:
                start = a
            stop = b
        elif start is not None:
            windows.append({"start_utc": format_utc(start), "end_utc": format_utc(stop)})
            start = stop = None
    # Flush a visible run that reaches the end of the supplied history.
    if start is not None:
        windows.append({"start_utc": format_utc(start), "end_utc": format_utc(stop)})
    return windows
