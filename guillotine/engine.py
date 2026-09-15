"""Turning survival probabilities into dollars."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import League, Player
from .lineup import Lineup, add_value, drop_candidates, optimize
from .market import demand, edge_over_replacement, market_for
from .sim import (SurvivalResult, TeamState, chop_probability, my_team_state,
                  rival_states, season_equity)

SEASON_SIMS = 8000


def budget_value(budget: float, reference: float, alpha: float) -> float:
    """Relative future value of the FAAB you keep.

    V(B) = (B / B_ref) ** alpha.  With alpha < 1 the first dollars are worth
    more than the last: going from $1000 to $700 costs you much less equity
    than going from $300 to $0.  alpha is the single most important knob in
    this model and lives in the config.
    """
    if budget <= 0:
        return 0.0
    return (budget / max(1.0, reference)) ** alpha


def remaining_cycles(lg: League) -> int:
    """Waiver cycles AFTER this one that your leftover budget could still buy.

    The season ends when one team is left or the schedule runs out, whichever
    comes first, so a 3-team league in week 15 has almost no future to save for.
    """
    chops_to_come = min(lg.weeks_left, lg.teams_left - 1)
    return max(0, chops_to_come - 1)


def effective_alpha(lg: League) -> float:
    """Budget curvature, faded out as the season runs out of waiver cycles.

    Dollars are only worth holding if there is a week left to spend them in.
    With no cycles after this one, alpha is 0: budget has no future value and
    hoarding it is a pure loss.
    """
    return lg.settings.budget_alpha * min(1.0, remaining_cycles(lg) / 4.0)


def effective_reserve(lg: League) -> float:
    return lg.settings.min_reserve if remaining_cycles(lg) > 0 else 0.0


@dataclass
class Candidate:
    player: Player
    lineup_delta: float
    displaced: Player | None
    p_chop_with: float
    equity_with: float
    max_bid: float
    recommended_bid: float
    p_win_at_recommended: float
    price_50: float
    price_75: float
    ev_gain: float
    verdict: str
    drop: Player | None = None


@dataclass
class WeekPlan:
    league: League
    baseline_lineup: Lineup
    baseline_chop: float
    baseline_equity: float
    baseline: SurvivalResult
    candidates: list[Candidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def primary(self) -> Candidate | None:
        live = [c for c in self.candidates if c.recommended_bid >= 1]
        return live[0] if live else None


def _equity(lg: League, extra: list[Player]) -> tuple[SurvivalResult, TeamState]:
    me = my_team_state(lg, extra)
    rivals = rival_states(lg)
    # Same seed for every scenario: common random numbers, so the difference
    # between "with the add" and "without" is not drowned in Monte-Carlo noise.
    res = season_equity(me, rivals, lg, sims=SEASON_SIMS, seed=lg.settings.seed)
    return res, me


def _max_bid(equity_with: float, equity_without: float, budget: float, lg: League) -> float:
    """Largest bid that still leaves you better off than passing.

    Indifference:  E_with * V(B - b) == E_without * V(B)
                   (1 - b/B) ** alpha == E_without / E_with
    """
    alpha = effective_alpha(lg)
    spendable = max(0.0, budget - effective_reserve(lg))
    if alpha <= 0:
        # Nothing left to save for: anything that helps is worth the whole pile.
        return spendable if equity_with > equity_without else 0.0
    if equity_with <= equity_without or equity_without <= 0:
        return 0.0 if equity_with <= equity_without else spendable
    ratio = equity_without / equity_with
    frac = 1.0 - ratio ** (1.0 / alpha)
    return max(0.0, min(spendable, frac * budget))


def _best_bid(market, equity_with: float, equity_without: float,
              budget: float, cap: float, lg: League) -> tuple[float, float, float]:
    """Grid-search the bid that maximises expected equity.

    Losing a blind bid costs nothing, so the trade-off is purely: a higher bid
    wins more often but leaves less budget for the weeks that follow.
    """
    alpha = effective_alpha(lg)
    ref = budget
    best = (0.0, 0.0, equity_without)
    steps = 400
    hi = min(cap, max(0.0, budget - effective_reserve(lg)))
    if hi <= 0:
        return 0.0, 0.0, equity_without
    for i in range(steps + 1):
        b = hi * i / steps
        pw = market.p_win(b)
        ev = pw * equity_with * budget_value(budget - b, ref, alpha) + (1 - pw) * equity_without
        if ev > best[2]:
            best = (b, pw, ev)
    return best


def _verdict(c_delta: float, max_bid: float, rec: float, p_win: float, budget: float) -> str:
    if c_delta <= 0.05:
        return "PASS - does not crack your starting lineup"
    if rec < 1:
        return "PASS - market price exceeds what the upgrade is worth to you"
    share = rec / max(1.0, budget)
    if share >= 0.45:
        return "MAX BID - a season-defining upgrade; win it"
    if share >= 0.20:
        return "AGGRESSIVE - real starter upgrade, worth a serious chunk"
    if share >= 0.06:
        return "VALUE BID - bid it, but do not chase"
    return "LOTTERY TICKET - throw a small bid, walk away if outbid"


def build_plan(lg: League) -> WeekPlan:
    warnings = lg.validate()
    base_res, base_me = _equity(lg, [])
    base_lineup = optimize(lg.roster)
    precise_chop = chop_probability(base_me, rival_states(lg), lg.settings)

    plan = WeekPlan(
        league=lg,
        baseline_lineup=base_lineup,
        baseline_chop=precise_chop,
        baseline_equity=base_res.equity,
        baseline=base_res,
        warnings=warnings,
    )

    drops = drop_candidates(lg.roster, keep=1)
    for p in lg.waivers:
        delta, _new_lineup, displaced = add_value(lg.roster, p)
        res, me = _equity(lg, [p])
        chop_with = chop_probability(me, rival_states(lg), lg.settings)
        mx = _max_bid(res.equity, base_res.equity, lg.my_budget, lg)
        mkt = market_for(p, lg)
        rec, pw, ev = _best_bid(mkt, res.equity, base_res.equity, lg.my_budget, mx, lg)
        plan.candidates.append(
            Candidate(
                player=p,
                lineup_delta=delta,
                displaced=displaced,
                p_chop_with=chop_with,
                equity_with=res.equity,
                max_bid=mx,
                recommended_bid=rec,
                p_win_at_recommended=pw,
                price_50=mkt.price_for(0.50, lg.my_budget),
                price_75=mkt.price_for(0.75, lg.my_budget),
                ev_gain=(ev - base_res.equity) / max(1e-9, base_res.equity),
                verdict=_verdict(delta, mx, rec, pw, lg.my_budget),
                drop=drops[0] if drops else None,
            )
        )

    plan.candidates.sort(key=lambda c: (-c.ev_gain, -c.lineup_delta))
    return plan


def season_phase(lg: League) -> tuple[str, str]:
    """Where the season is, and the spending rule that goes with it."""
    left = lg.teams_left
    start = lg.settings.teams_at_start
    frac = left / start
    if frac > 0.75:
        return ("LAND GRAB", "Field is wide and the chop line is soft. Buy only "
                             "league-winning talent; let others burn budget on depth.")
    if frac > 0.45:
        return ("SQUEEZE", "The bottom is thinning out and every roster is decent. "
                           "This is where budget converts into weekly points most efficiently.")
    if left > 4:
        return ("KNIFE FIGHT", "Any bad week ends you. Points now are worth more than "
                               "dollars later - spend down toward your reserve.")
    return ("ENDGAME", "Budget has almost no future left. Convert everything into "
                       "this week's ceiling; leaving money unspent is a loss.")
