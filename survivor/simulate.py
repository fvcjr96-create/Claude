"""Stress-testing a survivor plan.

The product of a plan's win probabilities answers "how often does this exact
sequence survive, assuming every number is right".  Both halves of that are
worth attacking:

* You do not actually follow a fixed sequence.  Each week you re-plan with
  fresher lines, so the ADAPTIVE policy is what you really run.
* Weeks 4-18 are priced from fitted ratings, not from a market, and those
  ratings carry measured error.  If the model is wrong about a team it is wrong
  in every one of that team's games at once -- which is precisely what makes a
  plan that fades the same opponent repeatedly fragile.

So the simulation perturbs TEAM RATINGS, not individual games, and re-prices
the season from the perturbed ratings.  That makes correlated model error the
thing being measured rather than something assumed away.
"""

from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass, field

from .data import Board
from .model import MARGIN_SD, normal_cdf, spread_from_prob
from .plan import Plan, optimize, optimize_capped
from .ratings import RATING_RMSE

# A game's error is the difference of two team errors, so a per-team sigma of
# RMSE/sqrt(2) reproduces the measured per-game RMSE one week ahead.
TEAM_RATING_SD = RATING_RMSE / math.sqrt(2.0)

# Teams do not hold still.  A rating fitted in September is a worse estimate of
# a December game than of an October one -- injuries, form, and roster churn
# accumulate.  Modelled as a random walk on each team's rating error at this
# many points per week beyond the last market-priced week.
#
# THIS IS AN ASSUMPTION, NOT A MEASUREMENT.  It cannot be validated until late
# season lines exist, and the answers it drives are sensitive to it, so
# scripts/drift_sensitivity.py reports how conclusions move across the range.
# 0.35 pts/week puts a week-18 rating error near 6 points, which is the right
# order for how far a team can move across a season.
DRIFT_PER_WEEK = 0.35


@dataclass
class SimResult:
    policy: str
    sims: int
    survival_by_week: dict[int, float]      # P(still alive after this week)
    overall: float                          # P(survive every week)
    mean_weeks_survived: float
    exit_week_counts: dict[int, int] = field(default_factory=dict)

    @property
    def se(self) -> float:
        """Standard error on `overall` -- rare events need a lot of sims."""
        return math.sqrt(max(self.overall * (1 - self.overall), 1e-12) / self.sims)

    @property
    def median_exit(self) -> int:
        seen, half = 0, self.sims / 2
        for wk in sorted(self.exit_week_counts):
            seen += self.exit_week_counts[wk]
            if seen >= half:
                return wk
        return max(self.survival_by_week, default=0)


def _base_table(board: Board) -> tuple[dict, list, set, int]:
    """Precompute each game's model probability and spread once.

    Inverting a probability back to a spread is a binary search, so doing it per
    simulation dominated the runtime.  It does not depend on the draw.
    """
    probs, spreads = {}, []
    teams = set()
    last_priced = 0
    for wk in board.weeks:
        for g in wk.games:
            key = (wk.number, g.home, g.away)
            p = g.prob_for(g.home)
            probs[key] = p
            teams.add(g.home)
            teams.add(g.away)
            if g.priced:
                last_priced = max(last_priced, wk.number)
            else:
                spreads.append((key, spread_from_prob(p), g.home, g.away, wk.number))
    return probs, spreads, teams, last_priced


def _draw_truth(base: tuple[dict, list, set, int], rng: random.Random,
                model_error: bool, drift: float = DRIFT_PER_WEEK) -> dict:
    """True home-win probability per game for one simulated world.

    Market-priced games are taken at face value -- the market is the best
    estimate available, so there is nothing to perturb it toward.  Games priced
    from ratings get a shove that is CORRELATED within a team: one rating error
    moves every game that team plays.  That is what makes a plan which fades the
    same opponent repeatedly fragile, and it is the whole point of the exercise.
    """
    probs, spreads, teams, last_priced = base
    if not model_error:
        return probs
    weeks = sorted({w for _k, _s, _h, _a, w in spreads})
    # One random walk per team: the error at week w carries forward, so a team
    # the model has wrong is wrong in all of its games, and increasingly so the
    # further from the last posted line.
    err: dict[str, dict[int, float]] = {}
    for t in teams:
        e = rng.gauss(0.0, TEAM_RATING_SD)
        walk = {}
        prev = last_priced
        for w in weeks:
            if drift:
                e += rng.gauss(0.0, drift * math.sqrt(max(1, w - prev)))
            walk[w] = e
            prev = w
        err[t] = walk
    truth = dict(probs)
    for key, spread, home, away, w in spreads:
        truth[key] = normal_cdf((spread + err[home][w] - err[away][w]) / MARGIN_SD)
    return truth


def _wins(pick_team: str, game, truth: dict, week: int, rng: random.Random) -> bool:
    p_home = truth[(week, game.home, game.away)]
    p = p_home if pick_team == game.home else 1.0 - p_home
    return rng.random() < p


def simulate_static(board: Board, plan: Plan, sims: int = 4000,
                    model_error: bool = True, seed: int = 20260919,
                    drift: float = DRIFT_PER_WEEK) -> SimResult:
    """Follow the precomputed plan week by week and see how far it gets."""
    rng = random.Random(seed)
    base = _base_table(board)
    weeks = sorted({p.week for p in plan.picks})
    alive_after = {w: 0 for w in weeks}
    exits: dict[int, int] = {}
    total_weeks = 0
    by_week = {w.number: w for w in board.weeks}
    games = {(p.week, p.team): by_week[p.week].game_for(p.team) for p in plan.picks}

    for _ in range(sims):
        truth = _draw_truth(base, rng, model_error, drift)
        survived_weeks, dead = 0, False
        for wk_num in weeks:
            for pick in [p for p in plan.picks if p.week == wk_num]:
                g = games[(pick.week, pick.team)]
                if g is None or not _wins(pick.team, g, truth, pick.week, rng):
                    exits[wk_num] = exits.get(wk_num, 0) + 1
                    dead = True
                    break
            if dead:
                break
            # A double week only counts once, and only once BOTH picks land.
            alive_after[wk_num] += 1
            survived_weeks += 1
        total_weeks += survived_weeks

    return SimResult(
        policy="static",
        sims=sims,
        survival_by_week={w: alive_after[w] / sims for w in weeks},
        overall=alive_after[weeks[-1]] / sims if weeks else 0.0,
        mean_weeks_survived=total_weeks / sims,
        exit_week_counts=exits,
    )


def simulate_adaptive(board: Board, sims: int = 1200, model_error: bool = True,
                      max_vs: int | None = None, contrarian: float = 0.0,
                      seed: int = 20260919, drift: float = DRIFT_PER_WEEK) -> SimResult:
    """Re-optimise every week, which is what you actually do in a real pool.

    The planner only ever sees the board's own (model) probabilities; the
    simulated world is drawn separately.  So this measures a policy that is
    confidently wrong in the same ways the real one will be.
    """
    rng = random.Random(seed)
    base = _base_table(board)
    weeks = [w.number for w in board.future_weeks()]
    alive_after = {w: 0 for w in weeks}
    exits: dict[int, int] = {}
    total_weeks = 0

    for _ in range(sims):
        truth = _draw_truth(base, rng, model_error, drift)
        state = copy.deepcopy(board)
        survived = 0
        for wk_num in weeks:
            plan = (optimize_capped(state, max_vs, contrarian=contrarian)
                    if max_vs else optimize(state, contrarian=contrarian))
            if not plan.picks:
                break
            this_week = [p for p in plan.picks if p.week == wk_num]
            if not this_week:
                break
            wk = next(w for w in state.weeks if w.number == wk_num)
            lost = False
            for pick in this_week:
                g = wk.game_for(pick.team)
                if g is None or not _wins(pick.team, g, truth, wk_num, rng):
                    exits[wk_num] = exits.get(wk_num, 0) + 1
                    lost = True
                    break
            if lost:
                break
            alive_after[wk_num] += 1
            survived += 1
            state.used[wk_num] = [p.team for p in this_week]
        total_weeks += survived

    return SimResult(
        policy=f"adaptive{f' (max-vs {max_vs})' if max_vs else ''}",
        sims=sims,
        survival_by_week={w: alive_after[w] / sims for w in weeks},
        overall=alive_after[weeks[-1]] / sims if weeks else 0.0,
        mean_weeks_survived=total_weeks / sims,
        exit_week_counts=exits,
    )
