"""Fitting team power ratings from posted point spreads.

Sportsbooks only post lines a few weeks out, but a survivor plan needs all 18.
Ratings bridge the gap: fit them to every spread that does exist, then use them
to price the games that have no line yet.  As the season goes on and more
spreads appear, the ratings sharpen and the later picks firm up.
"""

from __future__ import annotations

from dataclasses import dataclass

from .data import TEAMS, Board
from .model import HOME_FIELD, prob_from_spread

# Ridge penalty.  Early in the season there are far fewer spreads than teams,
# so the fit is underdetermined; the penalty shrinks unseen teams toward league
# average instead of inventing an extreme rating for them.
RIDGE = 1.0


@dataclass
class Ratings:
    values: dict[str, float]
    home_field: float
    n_games: int
    ridge: float

    def spread(self, home: str, away: str) -> float:
        return self.values.get(home, 0.0) - self.values.get(away, 0.0) + self.home_field

    def home_prob(self, home: str, away: str) -> float:
        return prob_from_spread(self.spread(home, away))


def _solve_linear(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            continue
        m[col], m[piv] = m[piv], m[col]
        pv = m[col][col]
        for r in range(n):
            if r == col:
                continue
            f = m[r][col] / pv
            if f:
                for c in range(col, n + 1):
                    m[r][c] -= f * m[col][c]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


def fit(board: Board, ridge: float = RIDGE, home_field: float = HOME_FIELD) -> Ratings:
    """Least-squares ratings from every game on the board that carries a spread.

    Model: home_spread = rating(home) - rating(away) + home_field.
    Ratings are points above league average and sum to zero by construction.
    """
    idx = {t: i for i, t in enumerate(TEAMS)}
    n = len(TEAMS)
    ata = [[0.0] * n for _ in range(n)]
    atb = [0.0] * n
    used = 0

    for wk in board.weeks:
        for g in wk.games:
            if g.home_spread is None and g.home_prob is None:
                continue
            if g.home_spread is not None:
                target = g.home_spread - home_field
            else:
                from .model import spread_from_prob
                target = spread_from_prob(g.home_prob) - home_field
            h, a = idx.get(g.home), idx.get(g.away)
            if h is None or a is None:
                continue
            used += 1
            ata[h][h] += 1.0
            ata[a][a] += 1.0
            ata[h][a] -= 1.0
            ata[a][h] -= 1.0
            atb[h] += target
            atb[a] -= target

    for i in range(n):
        ata[i][i] += ridge
    vals = _solve_linear(ata, atb)
    mean = sum(vals) / n
    return Ratings({t: vals[i] - mean for t, i in idx.items()}, home_field, used, ridge)


def fill(board: Board, ratings: Ratings) -> int:
    """Price every game that has no spread, using the fitted ratings.

    Returns how many games were filled.  Filled games stay on unverified weeks,
    so the report keeps flagging those picks as provisional.
    """
    filled = 0
    for wk in board.weeks:
        for g in wk.games:
            if g.home_spread is None and g.home_prob is None:
                g.home_prob = ratings.home_prob(g.home, g.away)
                filled += 1
    return filled
