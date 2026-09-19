"""Opportunity cost: what it really costs to spend a team in a given week.

A team's win probability this week is not its price.  Its price is what the
rest of the season looks like once it is gone.  Kansas City at 71% might be
cheaper than Baltimore at 77%, because the schedule has somewhere else to turn
in Baltimore's best week and nowhere to turn in Kansas City's.

Everything here is measured the same way: re-solve the whole remaining season
with the team pinned to a week, and compare to the unconstrained optimum.  That
difference is the opportunity cost, in units of season survival.
"""

from __future__ import annotations

from dataclasses import dataclass

from .data import Board
from .plan import optimize


@dataclass
class TeamCost:
    team: str
    by_week: dict[int, float]        # week -> season survival if pinned there
    best_week: int
    best_survival: float
    this_week: int | None            # the next week to pick, if the team plays
    this_survival: float | None

    @property
    def earliness_cost(self) -> float | None:
        """Relative survival lost by using the team now instead of its best week."""
        if self.this_survival is None or not self.best_survival:
            return None
        return 1.0 - self.this_survival / self.best_survival

    @property
    def weeks_early(self) -> int | None:
        if self.this_week is None:
            return None
        return self.best_week - self.this_week


@dataclass
class CostBoard:
    optimum: float
    teams: list[TeamCost]

    def by_name(self) -> dict[str, TeamCost]:
        return {t.team: t for t in self.teams}

    def cheapest_now(self, top: int = 10) -> list[TeamCost]:
        live = [t for t in self.teams if t.this_survival is not None]
        live.sort(key=lambda t: -t.this_survival)
        return live[:top]

    def most_expensive_to_burn(self, top: int = 10) -> list[TeamCost]:
        live = [t for t in self.teams if t.earliness_cost is not None]
        live.sort(key=lambda t: -(t.earliness_cost or 0))
        return live[:top]


def build(board: Board, contrarian: float = 0.0) -> CostBoard:
    """Season survival for every (team, week) pairing.

    One assignment solve per cell.  At roughly a millisecond each that is under
    a second for a full board, which is why this can be exact rather than
    approximated by a heuristic like "points above the week's replacement".
    """
    weeks = board.future_weeks()
    if not weeks:
        return CostBoard(0.0, [])
    next_week = weeks[0].number
    optimum = optimize(board, contrarian=contrarian).survival

    all_teams = sorted({t for w in weeks for t in w.teams_playing()} - board.used_teams)
    out: list[TeamCost] = []

    for team in all_teams:
        by_week: dict[int, float] = {}
        for wk in weeks:
            if team not in wk.teams_playing():
                continue                      # bye, or the game already kicked off
            by_week[wk.number] = optimize(
                board, contrarian=contrarian, force={wk.number: team}
            ).survival
        if not by_week:
            continue
        best_week = max(by_week, key=lambda w: by_week[w])
        out.append(TeamCost(
            team=team,
            by_week=by_week,
            best_week=best_week,
            best_survival=by_week[best_week],
            this_week=next_week if next_week in by_week else None,
            this_survival=by_week.get(next_week),
        ))

    out.sort(key=lambda t: -t.best_survival)
    return CostBoard(optimum, out)


def schedule_of_record(cost: CostBoard, plan_teams: dict[int, str]) -> list[tuple]:
    """For each planned pick, how its week compares to that team's best week."""
    rows = []
    idx = cost.by_name()
    for week, team in sorted(plan_teams.items()):
        tc = idx.get(team)
        if tc is None:
            continue
        surv = tc.by_week.get(week)
        rows.append((week, team, tc.best_week, surv, tc.best_survival))
    return rows
