"""Assembling the rating estimate the planner runs on.

Three sources, in order of how much they know about December:

1. **Last season's closing lines** -- a full 272-game prior, recency weighted
   and regressed for the offseason.  Always available.
2. **Market season win totals** -- forward looking and injury aware, inverted
   against the real schedule so a 9.5 behind a brutal schedule rates higher
   than a 9.5 behind an easy one.  Used when nearly all 32 are supplied.
3. **This season's posted game lines** -- the sharpest signal that exists, but
   only for the two or three weeks books have priced.

The first two form the prior; the third updates it.  Held-out validation on the
2026 board (train wk1 predict wk2, train wk1-2 predict wk3) puts the combination
at 1.58 pts mean error against 3.18 for this season's lines alone.
"""

from __future__ import annotations

import json
from pathlib import Path

from .data import Board
from .ratings import PRIOR_K, Ratings, fit, fill
from .wintotals import blend, solve


def load_prior(path: str | Path) -> dict[str, float]:
    raw = json.loads(Path(path).read_text())
    return {t: float(v) for t, v in raw["ratings"].items()}


def load_totals(path: str | Path) -> tuple[dict[str, float], int]:
    raw = json.loads(Path(path).read_text())
    totals = {t: float(v) for t, v in raw.get("totals", {}).items()}
    return totals, int(raw.get("min_teams_to_use", 28))


def build_ratings(board: Board, prior_path: str | Path | None = None,
                  totals_path: str | Path | None = None,
                  totals_weight: float = 1.0) -> tuple[Ratings, list[str]]:
    """Fit ratings for `board` and price every unlined game.  Returns notes."""
    notes: list[str] = []
    prior: dict[str, float] | None = None

    if prior_path and Path(prior_path).exists():
        prior = load_prior(prior_path)
        notes.append(f"prior: {Path(prior_path).name} "
                     f"(last season's lines, regressed x{PRIOR_K})")

    if totals_path and Path(totals_path).exists():
        totals, minimum = load_totals(totals_path)
        if len(totals) >= minimum:
            fitted = solve(board, totals, seed=prior)
            prior = blend(fitted.ratings, prior or {}, weight=totals_weight)
            notes.append(f"win totals: {len(totals)} teams, inverted against the "
                         f"schedule (max error {fitted.max_error:.3f} wins)")
        elif totals:
            notes.append(f"win totals: only {len(totals)} of {minimum} needed teams "
                         f"supplied - IGNORED, using last season's prior instead")

    if prior is None:
        notes.append("no prior available - ratings come from this season's lines "
                     "alone, which is weak for late weeks")

    ratings = fit(board, prior=prior)
    filled = fill(board, ratings)
    notes.append(f"{ratings.n_games} games with posted lines; "
                 f"{filled} priced from ratings")

    for note in apply_adjustments(board):
        notes.append(note)
    return ratings, notes


def apply_adjustments(board: Board) -> list[str]:
    """Overwrite specific game prices with a hand-set number.

    Applied AFTER the fit, so an override never leaks into the ratings and
    distort every other game that team plays -- it changes exactly the one
    game it names.  Each returns a note, because a hand-set price should be
    visible in the report rather than quietly baked into the plan.
    """
    out = []
    for adj in board.adjustments:
        week, team = int(adj["week"]), adj["team"]
        wk = next((w for w in board.weeks if w.number == week), None)
        game = wk.game_for(team, include_played=True) if wk else None
        if game is None:
            out.append(f"ADJUSTMENT IGNORED: {team} has no week {week} game")
            continue
        want = float(adj["win_prob"])
        was = game.prob_for(team)
        game.home_prob = want if team == game.home else 1.0 - want
        game.home_spread = None
        reason = adj.get("reason", "manual override")
        out.append(f"OVERRIDE wk{week} {team} {was*100:.1f}% -> {want*100:.1f}% ({reason})")
    return out
