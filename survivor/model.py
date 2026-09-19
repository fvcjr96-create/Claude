"""Turning point spreads or power ratings into win probabilities."""

from __future__ import annotations

import math

# Standard deviation of NFL game margin around the closing spread, in points.
# Calibrated against the 2026 Week 2 board: a 13.5-point favourite prices at
# 85%, 8.5 at 74%, 7 at 73%, 6.5 at 69%.  sigma = 13.0 reproduces all four.
MARGIN_SD = 13.0

# Home-field advantage in points, applied when building probabilities from
# power ratings rather than from a posted spread.
HOME_FIELD = 1.8


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def prob_from_spread(spread: float) -> float:
    """Win probability for a team favoured by `spread` points.

    Positive spread means favoured.  A pick'em is 50%.
    """
    return normal_cdf(spread / MARGIN_SD)


def spread_from_prob(p: float) -> float:
    """Inverse of prob_from_spread, for sanity-checking a hand-entered grid."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    lo, hi = -40.0, 40.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if prob_from_spread(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def prob_from_ratings(team_rating: float, opp_rating: float, at_home: bool) -> float:
    """Win probability from power ratings expressed in points above average."""
    edge = team_rating - opp_rating + (HOME_FIELD if at_home else -HOME_FIELD)
    return prob_from_spread(edge)
