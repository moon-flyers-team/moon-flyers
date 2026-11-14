"""Moon Flyers API v0 power/comms requirement checks (not spacecraft modelling)."""
import math

DEFAULT_CONSTRAINTS = {
    "min_sun_visible_pct": 60.0,
    "max_darkness_hours": 96.0,
    "min_earth_visible_pct": 45.0,
    "max_earth_blackout_hours": 240.0,
}


def evaluate_fit(metrics, constraints=None):
    """Return API.md fit: {status, violations}.

    Contract limitation: the four available statuses cannot represent unknown
    suitability. Reject incomplete metrics instead of claiming a pass.
    Slope is not evaluated in API v0 (by contract).
    """
    limits = {**DEFAULT_CONSTRAINTS, **(constraints or {})}
    for key, val in limits.items():
        if val is None or not isinstance(val, (int, float)) or not math.isfinite(val):
            raise ValueError(f"Invalid threshold: {key}")
        if val < 0 or (key.endswith("pct") and val > 100):
            raise ValueError(f"Threshold outside allowed range: {key}")

    rules = (
        ("sun_visible_pct", "min_sun_visible_pct", "min"),
        ("longest_darkness_hours", "max_darkness_hours", "max"),
        ("earth_visible_pct", "min_earth_visible_pct", "min"),
        ("longest_earth_blackout_hours", "max_earth_blackout_hours", "max"),
    )
    violations = []
    for metric, threshold, rule in rules:
        value = metrics.get(metric)
        if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Cannot evaluate fit without valid {metric}; skip fit if body disabled")
        passes = value >= limits[threshold] if rule == "min" else value <= limits[threshold]
        if not passes:
            violations.append(metric)
    power_failed = any(x in violations for x in ("sun_visible_pct", "longest_darkness_hours"))
    comms_failed = any(x in violations for x in ("earth_visible_pct", "longest_earth_blackout_hours"))
    status = ("neither_met" if power_failed and comms_failed else
              "power_short" if power_failed else "comms_short" if comms_failed else "both_met")
    return {"status": status, "violations": violations}
