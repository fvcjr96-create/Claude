"""Monte-Carlo survival model for a guillotine league.

Two questions get answered here:

1. What is the chance I am the lowest score THIS week (i.e. get chopped)?
2. How much league equity do I hold, once the rest of the season is played out
   week by week with the lowest team removed each time?

Question 2 is the one that prices waiver bids.  A player who saves you 0.4% of
survival this week but 6% of season equity is worth real money; one who only
pads a blowout week is worth close to nothing.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .config import League, Settings
from .lineup import optimize


@dataclass
class TeamState:
    name: str
    proj: float
    sd: float
    is_me: bool = False


@dataclass
class SurvivalResult:
    p_chop_this_week: float
    equity: float
    survival_curve: list[float]   # P(alive after each remaining week)
    mean_weeks_survived: float
    p_win: float


def my_team_state(lg: League, extra: list = ()) -> TeamState:
    """Projection and spread of my optimal lineup, optionally with adds."""
    lu = optimize(list(lg.roster) + list(extra))
    var = sum(p.sd ** 2 for p in lu.starters)
    return TeamState(lg.my_team, lu.points, math.sqrt(var), is_me=True)


def rival_states(lg: League) -> list[TeamState]:
    s = lg.settings
    sd = math.sqrt(s.rival_team_sd ** 2 + s.rival_proj_error_sd ** 2)
    return [TeamState(r.name, r.proj, sd) for r in lg.rivals]


def _draw(team: TeamState, rho: float, common: float, rng: random.Random) -> float:
    idio = rng.gauss(0.0, 1.0)
    shock = math.sqrt(1.0 - rho) * idio + math.sqrt(rho) * common
    return team.proj + team.sd * shock


def chop_probability(me: TeamState, rivals: list[TeamState], settings: Settings,
                     sims: int | None = None, seed: int | None = None) -> float:
    """P(my score is the lowest in the league this week)."""
    rng = random.Random(settings.seed if seed is None else seed)
    n = sims or settings.simulations
    rho = settings.correlation
    hits = 0
    for _ in range(n):
        common = rng.gauss(0.0, 1.0)
        mine = _draw(me, rho, common, rng)
        low = True
        for r in rivals:
            if _draw(r, rho, common, rng) < mine:
                low = False
                break
        if low:
            hits += 1
    return hits / n


def season_equity(me: TeamState, rivals: list[TeamState], lg: League,
                  sims: int = 4000, seed: int | None = None) -> SurvivalResult:
    """Play the rest of the season out, chopping the low team every week.

    Uses a fixed seed so that two scenarios (with an add and without) share the
    same random draws.  Common random numbers make the DIFFERENCE between two
    scenarios far more precise than either level, which is exactly what a bid
    depends on.
    """
    s = lg.settings
    rho = s.correlation
    weeks = lg.weeks_left
    rng = random.Random(s.seed if seed is None else seed)

    alive_after = [0] * weeks
    chopped_this_week = 0
    weeks_survived_total = 0
    wins = 0

    base = [(t.proj, t.sd, t.is_me) for t in [me] + rivals]

    for _ in range(sims):
        field = [[p, sd, me_flag] for (p, sd, me_flag) in base]
        alive = True
        for w in range(weeks):
            common = rng.gauss(0.0, 1.0)
            worst_i, worst_score = -1, None
            for i, (proj, sd, _me) in enumerate(field):
                idio = rng.gauss(0.0, 1.0)
                score = proj + sd * (math.sqrt(1.0 - rho) * idio + math.sqrt(rho) * common)
                if worst_score is None or score < worst_score:
                    worst_i, worst_score = i, score
            if field[worst_i][2]:
                if w == 0:
                    chopped_this_week += 1
                alive = False
                weeks_survived_total += w
                break
            field.pop(worst_i)
            alive_after[w] += 1
            if len(field) == 1:
                wins += 1
                weeks_survived_total += weeks
                alive = False
                break
            # Surviving teams pick over the chopped roster: everyone drifts up a
            # little, and the drift itself is uncertain.
            for row in field:
                row[0] += rng.gauss(s.rival_waiver_drift, s.rival_waiver_drift_sd)
        if alive:
            weeks_survived_total += weeks

    curve = [a / sims for a in alive_after]
    # Late weeks are where the money is; weight equity toward surviving deep.
    wts = [(i + 1) ** 2.0 for i in range(weeks)]
    tot = sum(wts)
    equity = sum(w * c for w, c in zip(wts, curve)) / tot
    return SurvivalResult(
        p_chop_this_week=chopped_this_week / sims,
        equity=equity,
        survival_curve=curve,
        mean_weeks_survived=weeks_survived_total / sims,
        p_win=wins / sims if wins else (curve[-1] if curve else 0.0),
    )
