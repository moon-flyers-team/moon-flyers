import json
import urllib.parse
import urllib.request
from datetime import datetime

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
MOON_ID = "301"
SUN_ID = "10"
EARTH_ID = "399"


def _query_azel(target, lon_deg, lat_deg, alt_km, start, stop, step):
    """Query Horizons for az/el of `target` from a lunar surface site.
    Returns (list of datetime, list of az_deg, list of el_deg)."""
    params = {
        "format": "json",
        "COMMAND": f"'{target}'",
        "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": f"'coord@{MOON_ID}'",
        "COORD_TYPE": "'GEODETIC'",
        "SITE_COORD": f"'{lon_deg},{lat_deg},{alt_km}'",  # E-lon, lat, alt (km)
        "START_TIME": f"'{start:%Y-%m-%d %H:%M:%S}'",
        "STOP_TIME": f"'{stop:%Y-%m-%d %H:%M:%S}'",
        "STEP_SIZE": f"'{step}'",
        "QUANTITIES": "'4'",  # 4 = apparent azimuth & elevation
        "TIME_DIGITS": "'SECONDS'",
        "CSV_FORMAT": "'YES'",
        "ANG_FORMAT": "'DEG'",
        "APPARENT": "'AIRLESS'",
    }
    url = HORIZONS_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if "error" in data:
        raise RuntimeError(f"Horizons error: {data['error']}")
    text = data.get("result", "")
    print(text)
    if "$$SOE" not in text:
        raise RuntimeError(f"Horizons returned no ephemeris table:\n{text[-1500:]}")

    table = text.split("$$SOE")[1].split("$$EOE")[0].strip().splitlines()
    times, az, el = [], [], []
    for row in table:
        fields = [f.strip() for f in row.split(",")]
        # Row looks like: "2027-Mar-01 12:00:00, , , 123.4567, -12.3456,"
        # (the blank/flag columns are sun/moon presence flags)
        nums = [f for f in fields[1:] if f]
        times.append(datetime.strptime(fields[0], "%Y-%b-%d %H:%M:%S"))
        az.append(float(nums[-2]))
        el.append(float(nums[-1]))
    return times, az, el


def positions(latitude_deg, longitude_deg, window_start_utc, window_end_utc,
              timestep_seconds, altitude_m=0.0):
    """Sun and Earth azimuth/elevation from a lunar surface site, via JPL Horizons.

    Returns dict of equal-length lists:
      time_utc, sun_azimuth_deg, sun_elevation_deg,
      earth_azimuth_deg, earth_elevation_deg
    """
    start = datetime.fromisoformat(window_start_utc)
    stop = datetime.fromisoformat(window_end_utc)
    span = (stop - start).total_seconds()
    if span <= 0:
        raise ValueError("window_end_utc must be after window_start_utc")
    if timestep_seconds <= 0:
        raise ValueError("timestep_seconds must be positive")

    # Horizons: whole-minute steps use 'Nm'; anything else uses the unitless
    # "split the window into N even steps" mode.
    if timestep_seconds % 60 == 0:
        step = f"{timestep_seconds // 60} m"
    else:
        if span % timestep_seconds != 0:
            raise ValueError(
                "Window length must be an exact multiple of timestep_seconds "
                "when the timestep is not a whole number of minutes"
            )
        step = str(int(span // timestep_seconds))

    lon = longitude_deg % 360.0  # Horizons: east-positive, 0..360
    alt_km = altitude_m / 1000.0
    args = (lon, latitude_deg, alt_km, start, stop, step)

    t_sun, sun_az, sun_el = _query_azel(SUN_ID, *args)
    t_earth, earth_az, earth_el = _query_azel(EARTH_ID, *args)
    if t_sun != t_earth:
        raise RuntimeError("Sun and Earth time grids from Horizons do not match")

    return {
        "time_utc": [t.strftime("%Y-%m-%dT%H:%M:%S") for t in t_sun],
        "sun_azimuth_deg": sun_az,
        "sun_elevation_deg": sun_el,
        "earth_azimuth_deg": earth_az,
        "earth_elevation_deg": earth_el,
    }


if __name__ == "__main__":
    out = positions(-89.5, 0.0, "2027-03-01T00:00:00", "2027-03-01T06:00:00", 3600, 0)
    for i, t in enumerate(out["time_utc"]):
        print(t, out["sun_azimuth_deg"][i], out["sun_elevation_deg"][i],
              out["earth_azimuth_deg"][i], out["earth_elevation_deg"][i])