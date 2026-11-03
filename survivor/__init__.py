"""NFL survivor pool planner.

A survivor pool is not 17 independent weekly decisions.  You may use each team
once, so picking the safest team this week is often wrong: it spends a resource
that a later week needs more.  The planner treats the whole season as a single
assignment problem -- weeks on one side, teams on the other -- and solves it
exactly rather than greedily.
"""

__all__ = ["assign", "model", "data", "plan"]
