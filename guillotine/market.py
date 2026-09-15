"""Model of what the other 14 managers will bid.

Knowing a player is worth $300 to you is only half the problem: a blind FAAB
bid that loses costs you nothing but the player.  So every recommendation needs
a second number -- the price that actually wins the auction often enough.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import League, Player, Settings


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def edge_over_replacement(p: Player, settings: Settings) -> float:
    repl = settings.replacement_level.get(p.pos, 8.5)
    return max(0.0, p.proj - repl)


def demand(p: Player, settings: Settings) -> float:
    """0-1 squash of a player's edge: how close to a must-have they are."""
    e = edge_over_replacement(p, settings)
    return e / (e + settings.market_half_point)


@dataclass
class BidMarket:
    """Independent lognormal bids from each rival, with a participation gate."""

    budgets: list[float]
    median_share: float        # median bid as a share of a rival's budget
    participation: float       # P(a given rival bids at all)
    sigma: float

    def p_win(self, bid: float) -> float:
        """P(my bid is the highest).  Ties are scored as losses (conservative)."""
        if bid <= 0:
            return 0.0
        p = 1.0
        for b in self.budgets:
            cap = max(1.0, b)
            median = max(1.0, self.median_share * cap)
            if bid >= cap:
                p_rival_beats = 0.0   # they cannot bid more than they have
            else:
                z = (math.log(bid) - math.log(median)) / self.sigma
                p_rival_beats = 1.0 - _norm_cdf(z)
            p *= 1.0 - self.participation * p_rival_beats
        return p

    def price_for(self, target_win_prob: float, cap: float) -> float:
        """Smallest bid that wins with at least the target probability."""
        lo, hi = 0.0, cap
        if self.p_win(cap) < target_win_prob:
            return cap
        for _ in range(60):
            mid = (lo + hi) / 2
            if self.p_win(mid) >= target_win_prob:
                hi = mid
            else:
                lo = mid
        return hi


def market_for(p: Player, lg: League) -> BidMarket:
    s = lg.settings
    d = demand(p, s)
    # Scarcity kicker: a player almost everyone rosters elsewhere is a player
    # every guillotine survivor recognises the moment they hit the pool.
    hype = 0.85 + 0.30 * (p.rostered_pct / 100.0)
    return BidMarket(
        budgets=[r.budget for r in lg.rivals],
        median_share=min(0.95, s.market_aggression * d * hype),
        participation=min(0.95, s.contenders_per_player * (0.40 + 0.60 * d)),
        sigma=s.market_dispersion,
    )
