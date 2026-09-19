"""Season-long survivor optimisation."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .assign import BLOCKED, solve
from .data import Board, Week

# Probability floor: a team with no game (bye) or already used is unusable.
MIN_PROB = 1e-4


@dataclass
class Pick:
    week: int
    team: str
    opponent: str
    home: bool
    prob: float
    popularity: float = 0.0
    verified: bool = False

    @property
    def label(self) -> str:
        return f"{self.team} {'vs' if self.home else '@'} {self.opponent}"


@dataclass
class Plan:
    picks: list[Pick]
    survival: float                # P(every pick wins)
    blocked_weeks: list[int]       # weeks with no legal team left

    def survival_curve(self) -> list[tuple[int, float]]:
        out, running = [], 1.0
        for p in self.picks:
            running *= p.prob
            out.append((p.week, running))
        return out


def _cost_matrix(board: Board, weeks: list[Week], teams: list[str],
                 contrarian: float = 0.0, discount: float = 1.0) -> list[list[float]]:
    """-log(win probability) per week/team, with illegal cells blocked.

    `contrarian` adds a penalty proportional to how much of the pool is on the
    same team.  At 0 the planner maximises pure survival; above 0 it starts
    paying for differentiation, which is what wins a big pool rather than just
    outlasting the field.

    `discount` below 1.0 weights early weeks more heavily.  At 1.0 the objective
    is P(survive all 17), which is indifferent between two plans with the same
    product even if one is far safer in the weeks you are actually about to
    play.  Below 1.0 it front-loads certainty, which is what you want if your
    pool pays for lasting longest rather than for going undefeated.
    """
    matrix = []
    for i, wk in enumerate(weeks):
        row = []
        for t in teams:
            g = wk.game_for(t)
            if g is None:                      # bye week, or board incomplete
                row.append(BLOCKED)
                continue
            p = max(MIN_PROB, min(1.0 - MIN_PROB, g.prob_for(t)))
            cost = -math.log(p) * (discount ** i)
            if contrarian:
                cost += contrarian * wk.popularity.get(t, 0.0)
            row.append(cost)
        matrix.append(row)
    return matrix


def optimize(board: Board, contrarian: float = 0.0,
             force: dict[int, str] | None = None,
             ban: set[str] | None = None,
             block_cells: set[tuple[int, str]] | None = None,
             discount: float = 1.0) -> Plan:
    """Best remaining season plan.

    `force` pins a team to a week (used to price alternatives); `ban` removes
    teams from consideration entirely (used to measure how much a team is
    worth to the rest of the schedule); `block_cells` rules out individual
    (week, team) pairs, which is how the concentration cap is enforced.
    """
    force = force or {}
    ban = set(ban or ())
    weeks = board.future_weeks()
    teams = [t for t in sorted({t for w in weeks for t in w.teams_playing()})
             if t not in board.used_teams and t not in ban]

    # A force may override a ban, but never the used-once rule: re-picking a
    # team you have already spent is illegal, so refuse rather than return a
    # plan that cannot be entered.
    for wk_num, t in force.items():
        if t in board.used_teams:
            raise ValueError(
                f"cannot force {t} in week {wk_num}: already used in week "
                f"{[w for w, u in board.used.items() if u == t][0]}"
            )
        if t not in teams:
            teams.append(t)
    teams.sort()

    if len(teams) < len(weeks):
        # Not enough distinct teams for every week; pad with dummy columns so
        # the matching still solves and the shortfall shows up as blocked weeks.
        teams = teams + [f"__none{i}" for i in range(len(weeks) - len(teams))]

    matrix = _cost_matrix(board, weeks, teams, contrarian, discount)
    for (bw, bt) in (block_cells or ()):
        for i, wk in enumerate(weeks):
            if wk.number == bw and bt in teams:
                matrix[i][teams.index(bt)] = BLOCKED
    for i, wk in enumerate(weeks):
        pinned = force.get(wk.number)
        if pinned is None:
            continue
        for j, t in enumerate(teams):
            if t != pinned:
                matrix[i][j] = BLOCKED

    assignment = solve(matrix)

    picks, blocked = [], []
    survival = 1.0
    for i, wk in enumerate(weeks):
        j = assignment[i]
        team = teams[j] if j >= 0 else "__none"
        g = wk.game_for(team)
        if g is None:
            blocked.append(wk.number)
            continue
        p = g.prob_for(team)
        survival *= p
        picks.append(
            Pick(
                week=wk.number,
                team=team,
                opponent=g.opponent_of(team),
                home=g.is_home(team),
                prob=p,
                popularity=wk.popularity.get(team, 0.0),
                verified=wk.verified,
            )
        )
    return Plan(picks=picks, survival=survival, blocked_weeks=blocked)


def next_week_options(board: Board, contrarian: float = 0.0,
                      top: int = 8) -> list[tuple[str, float, float, Plan]]:
    """Price every legal pick for the next week by its whole-season cost.

    For each candidate, the rest of the season is re-optimised around that
    choice.  The difference in season survival is the true cost of the pick --
    which is how a 70% team can beat a 78% team whose later weeks are needed.
    """
    weeks = board.future_weeks()
    if not weeks:
        return []
    wk = weeks[0]
    out = []
    for team in sorted(wk.teams_playing() - board.used_teams):
        g = wk.game_for(team)
        if g is None:
            continue
        plan = optimize(board, contrarian=contrarian, force={wk.number: team})
        out.append((team, g.prob_for(team), plan.survival, plan))
    out.sort(key=lambda r: -r[2])
    return out[:top]


def team_leverage(board: Board, contrarian: float = 0.0) -> list[tuple[str, float]]:
    """How much season survival drops if a team is unavailable all year.

    High leverage means the schedule depends on that team having a soft spot
    later -- those are the teams to hoard rather than burn early.
    """
    base = optimize(board, contrarian=contrarian).survival
    rows = []
    teams = {t for w in board.future_weeks() for t in w.teams_playing()} - board.used_teams
    for t in sorted(teams):
        alt = optimize(board, contrarian=contrarian, ban={t}).survival
        rows.append((t, base - alt))
    rows.sort(key=lambda r: -r[1])
    return rows


def optimize_capped(board: Board, max_vs: int, contrarian: float = 0.0,
                    max_rounds: int = 60) -> Plan:
    """Best plan that never fades the same opponent more than `max_vs` times.

    A plan can be mathematically optimal and still be one bad team's bounce-back
    away from collapsing -- fading the same opponent nine times is one bet, not
    nine.  A hard count cap is not expressible in an assignment problem, so this
    solves, finds the weakest pick against the most over-used opponent, blocks
    that single cell, and re-solves until the cap holds.  Each round is exactly
    optimal subject to the blocks, and the loop is monotone, so the result is a
    good plan under the constraint rather than a proven optimum.
    """
    from collections import Counter

    blocked: set[tuple[int, str]] = set()
    plan = optimize(board, contrarian=contrarian)
    for _ in range(max_rounds):
        counts = Counter(p.opponent for p in plan.picks)
        over = [(opp, c) for opp, c in counts.items() if c > max_vs]
        if not over:
            return plan
        opp = max(over, key=lambda oc: oc[1])[0]
        weakest = min((p for p in plan.picks if p.opponent == opp), key=lambda p: p.prob)
        blocked.add((weakest.week, weakest.team))
        plan = optimize(board, contrarian=contrarian, block_cells=blocked)
    return plan


def opponent_concentration(plan: Plan) -> list[tuple[str, int]]:
    """How many times the plan bets against each opponent, most first."""
    from collections import Counter

    return Counter(p.opponent for p in plan.picks).most_common()
