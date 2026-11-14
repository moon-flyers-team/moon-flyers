"""Topocentric Sun/Earth whole-disc visibility against a periodic lunar skyline.

Body elevations must be geometric/apparent angles from the *same* local horizontal
as the terrain skyline; angular radius is supplied by the ephemeris provider.
"""
import numpy as np


def calculate_visibility_margin(
    body_azimuth_deg,
    body_elevation_deg,
    horizon_azimuth_deg,
    horizon_elevation_deg,
    body_angular_radius_deg,
    horizon_clearance_deg=0.3,
):
    """Return signed bottom-of-disc clearance (degrees), one per timestamp.

    Positive: entirely above the required skyline; negative: obstructed.
    Zero: meets the threshold exactly. Periodic horizon interpolation works at
    azimuth wrap (359 -> 0). Do not pass a DEM missing angular sectors as though
    it were a complete skyline.
    """
    # Convert lists to numeric arrays so the same formula applies to every timestamp.
    # Body arrays follow time; horizon arrays follow compass direction.
    az = np.asarray(body_azimuth_deg, dtype=float)
    el = np.asarray(body_elevation_deg, dtype=float)
    haz = np.asarray(horizon_azimuth_deg, dtype=float)
    hel = np.asarray(horizon_elevation_deg, dtype=float)
    rad = np.asarray(body_angular_radius_deg, dtype=float)
    clearance = float(horizon_clearance_deg)

    # Reject missing/misaligned data instead of silently treating it as blocked or visible.
    if az.ndim != 1 or az.size == 0 or el.shape != az.shape:
        raise ValueError("Body azimuth/elevation must be nonempty equal-length 1D arrays")
    if haz.ndim != 1 or haz.size < 2 or hel.shape != haz.shape:
        raise ValueError("Horizon arrays must have >=2 equal-length 1D samples")
    if rad.ndim > 1 or (rad.ndim == 1 and rad.shape != az.shape):
        raise ValueError("Angular radius must be scalar or have one value per sample")
    if not all(np.all(np.isfinite(x)) for x in (az, el, haz, hel, rad)):
        raise ValueError("Angles must be finite; missing DEM/ephemeris data is not visibility")
    if not np.isfinite(clearance) or clearance < 0 or np.any(rad < 0):
        raise ValueError("Angular radius and horizon clearance must be nonnegative")
    if np.any((el < -90) | (el > 90)):
        raise ValueError("Body elevations must be within [-90, 90] degrees")

    # Sort the skyline around the compass. 0° and 360° describe the same direction;
    # duplicates are allowed only when their elevations agree.
    normalized = np.mod(haz, 360)
    order = np.argsort(normalized)
    sorted_az, sorted_el = normalized[order], hel[order]
    unique_az, first = np.unique(sorted_az, return_index=True)
    if len(unique_az) < 2:
        raise ValueError("At least two distinct horizon azimuths are needed")
    for a, j in zip(unique_az, first):
        if not np.allclose(sorted_el[sorted_az == a], sorted_el[j], rtol=0, atol=1e-9):
            raise ValueError("Conflicting elevations at duplicate horizon azimuth")
    # Interpolate terrain at each body azimuth, including across north (359° → 0°).
    skyline = np.interp(np.mod(az, 360), unique_az, sorted_el[first], period=360)
    # Bottom of disc minus terrain minus safety clearance: zero is the pass boundary.
    return (el - rad - skyline - clearance).tolist()


def calculate_visibility(
    body_azimuth_deg,
    body_elevation_deg,
    horizon_azimuth_deg,
    horizon_elevation_deg,
    body_angular_radius_deg,
    horizon_clearance_deg=0.3,
):
    """Boolean full-disc visibility at samples (margin >= 0)."""
    margin = calculate_visibility_margin(
        body_azimuth_deg, body_elevation_deg,
        horizon_azimuth_deg, horizon_elevation_deg,
        body_angular_radius_deg, horizon_clearance_deg,
    )
    return [m >= 0 for m in margin]
