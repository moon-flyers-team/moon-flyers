"""Runs before any test module imports `src`: keep the API tests offline on mock ephemeris.

`tests/test_ephemeris.py` covers the Horizons adapter with a fake `positions()`, plus one
opt-in live test (set MOON_FLYERS_LIVE=1).
"""

import os

os.environ["MOON_FLYERS_EPHEMERIS"] = "mock"
