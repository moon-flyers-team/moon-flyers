"""Headroom ranking (services/ranking.py)."""

from src.schemas import Constraints, Metrics, WindowMetric
from src.services.ranking import margins, rank_landings
from src.services.visibility import fit

C = Constraints()  # sun >= 60 %, darkness <= 96 h, Earth >= 45 %, blackout <= 240 h, 14 days


def m(sun, earth, dark=0.0, blackout=0.0):
    return Metrics(sun_visible_pct=sun, longest_darkness_hours=dark,
                   earth_visible_pct=earth, longest_earth_blackout_hours=blackout)


def candidate(t, metrics):
    return WindowMetric(landing_utc=t, metrics=metrics, fit=fit(metrics, C))


def test_margins_are_scaled_per_side_of_the_threshold():
    assert margins(m(100, 100), C) == (1.0, 1.0, 1.0, 1.0)
    assert margins(m(60, 45, dark=96, blackout=240), C) == (0.0, 0.0, 0.0, 0.0)
    sun, dark, earth, blackout = margins(m(30, 0, dark=336, blackout=336), C)
    assert (sun, dark, earth, blackout) == (-0.5, -1.0, -1.0, -1.0)


def test_balanced_landing_beats_one_with_a_thin_margin():
    a = candidate("2027-08-01T00:00:00Z", m(80, 50))  # Earth margin 0.09
    b = candidate("2027-08-01T06:00:00Z", m(70, 60))  # weakest margin 0.25
    ranked = rank_landings([a, b], C, 5)
    assert [r.landing_utc for r in ranked] == [b.landing_utc, a.landing_utc]
    assert min(margins(b.metrics, C)) == 0.25


def test_fit_tier_comes_first_and_smaller_miss_ranks_higher():
    met = candidate("2027-08-01T12:00:00Z", m(61, 46))
    near_miss = candidate("2027-08-01T00:00:00Z", m(59, 100))
    big_miss = candidate("2027-08-01T06:00:00Z", m(20, 100))
    ranked = rank_landings([big_miss, near_miss, met], C, 5)
    assert [r.landing_utc for r in ranked] == [met.landing_utc, near_miss.landing_utc, big_miss.landing_utc]


def test_exact_tie_prefers_power_then_earliest():
    # Same weakest and mean margin; one has the spare room on sun, the other on Earth.
    more_sun = candidate("2027-08-02T00:00:00Z", m(100, 45))
    more_earth = candidate("2027-08-01T00:00:00Z", m(60, 100))
    ranked = rank_landings([more_earth, more_sun], C, 5)
    assert ranked[0].landing_utc == more_sun.landing_utc
    same = [candidate("2027-08-03T00:00:00Z", m(80, 80)), candidate("2027-08-01T00:00:00Z", m(80, 80))]
    assert rank_landings(same, C, 1)[0].landing_utc == "2027-08-01T00:00:00Z"
