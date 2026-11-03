"""Guillotine league waiver (FAAB) optimizer.

A guillotine league is not a head-to-head league: every week the team with the
LOWEST score is chopped.  You never have to win -- you have to not be last.
That single fact changes what a waiver dollar is worth, and this package prices
bids off survival probability rather than off raw projected points.
"""

__all__ = ["config", "lineup", "sim", "market", "engine"]
