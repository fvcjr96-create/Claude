"""Turning market season win totals into power ratings.

A win total is the market's forward-looking view of a team over a full season,
and it moves on injury news in a way that three weeks of game lines cannot
capture for December.  It is not a rating, though -- 9.5 wins means something
very different behind an easy schedule than a brutal one.

So invert it against the real schedule: find the rating for each team whose
expected wins, summed over that team's actual opponents, equals its posted
total.  Every team's answer depends on every other team's rating, so this is a
fixed point, solved by damped iteration.
"""

from __future__ import annotations

from dataclasses import dataclass

from .data import Board
from .model import HOME_FIELD, prob_from_spread

MAX_ITERS = 500
TOLERANCE = 1e-4
STEP = 2.5          # points of rating per win of error; damped for stability


@dataclass
class TotalsFit:
    ratings: dict[str, float]
    iterations: int
    max_error: float        # largest |expected wins - posted total| at convergence
    teams_fitted: int


def expected_wins(board: Board, ratings: dict[str, float],
                  home_field: float = HOME_FIELD) -> dict[str, float]:
    """Expected regular season wins for each team under these ratings."""
    out: dict[str, float] = {}
    for wk in board.weeks:
        for g in wk.games:
            edge = ratings.get(g.home, 0.0) - ratings.get(g.away, 0.0) + home_field
            ph = prob_from_spread(edge)
            out[g.home] = out.get(g.home, 0.0) + ph
            out[g.away] = out.get(g.away, 0.0) + (1.0 - ph)
    return out


def solve(board: Board, totals: dict[str, float], seed: dict[str, float] | None = None,
          home_field: float = HOME_FIELD) -> TotalsFit:
    """Ratings whose expected wins reproduce the posted win totals.

    Teams without a posted total keep their seed rating and still contribute as
    opponents, so a partial set of totals is usable -- it just constrains less.
    """
    teams = sorted({t for w in board.weeks for g in w.games for t in (g.home, g.away)})
    ratings = {t: (seed or {}).get(t, 0.0) for t in teams}
    fitted = [t for t in teams if t in totals]

    it, err = 0, float("inf")
    for it in range(1, MAX_ITERS + 1):
        exp = expected_wins(board, ratings, home_field)
        err = 0.0
        for t in fitted:
            diff = totals[t] - exp.get(t, 0.0)
            err = max(err, abs(diff))
            ratings[t] += STEP * diff
        if err < TOLERANCE:
            break
    # Centre on zero so the scale matches the line-fitted ratings.
    mean = sum(ratings.values()) / len(ratings)
    return TotalsFit({t: v - mean for t, v in ratings.items()}, it, err, len(fitted))


def blend(primary: dict[str, float], fallback: dict[str, float],
          weight: float = 1.0) -> dict[str, float]:
    """Per-team blend: use `primary` where it exists, `fallback` elsewhere.

    `weight` is how much of `primary` to take where both are available, so 1.0
    trusts the win totals completely and 0.5 splits the difference with last
    season's ratings.
    """
    teams = set(primary) | set(fallback)
    out = {}
    for t in teams:
        if t in primary and t in fallback:
            out[t] = weight * primary[t] + (1 - weight) * fallback[t]
        else:
            out[t] = primary.get(t, fallback.get(t, 0.0))
    mean = sum(out.values()) / len(out) if out else 0.0
    return {t: v - mean for t, v in out.items()}


def implied_totals(board: Board, ratings: dict[str, float]) -> dict[str, float]:
    """Round-trip helper: what win totals do these ratings imply?"""
    return {t: round(v, 2) for t, v in expected_wins(board, ratings).items()}

