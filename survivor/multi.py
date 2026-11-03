"""Running two survivor entries at once.

With one entry you maximise P(survive).  With two, in two different leagues,
you maximise P(AT LEAST ONE survives) -- and that is a different objective with
a different answer.

The thing to understand up front: weeks where both entries pick the same team
contribute NOTHING.  They live together and die together, so a shared prefix is
a single point of failure that you are paying for twice.  Pure diversification
says diverge in week 2.

It is not that simple, because the good picks are scarce.  If entry B has to
skip the two free teams in week 2, it pays 15-30% of its season for the
privilege of being different, and a second entry that is much worse is not
worth much.  So the real question is WHERE divergence is cheapest, and that is
measured here rather than guessed.

Correlation is handled by simulating both entries in the SAME drawn world: one
winner per game, shared by both entries.  Two entries picking the same team are
then perfectly correlated, two picking opposite sides of one game are perfectly
anti-correlated, and everything else falls out on its own.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .data import Board
from .plan import Plan, optimize
from .simulate import DRIFT_PER_WEEK, _base_table, _draw_truth


@dataclass
class Entry:
    label: str
    plan: Plan

    @property
    def teams(self) -> set[str]:
        return {p.team for p in self.plan.picks}


@dataclass
class JointResult:
    diverge_week: int
    shared_weeks: int
    p_at_least_one: float
    p_both: float
    p_a: float
    p_b: float
    sims: int
    overlap: int                 # picks the two entries share
    either_alive: dict = None    # week -> P(at least one entry still alive)

    @property
    def se(self) -> float:
        p = self.p_at_least_one
        return (max(p * (1 - p), 1e-12) / self.sims) ** 0.5

    @property
    def lift(self) -> float:
        """How much the second entry adds over just running the first twice."""
        return self.p_at_least_one / self.p_a - 1.0 if self.p_a else 0.0


def build_pair(board: Board, diverge_week: int,
               contrarian: float = 0.0) -> tuple[Entry, Entry]:
    """Entry A optimal; entry B shares picks until `diverge_week`, then splits.

    After the split B may not make the SAME PICK IN THE SAME WEEK as A.  That
    is the constraint that actually matters: A taking Kansas City in week 3 and
    B taking Kansas City in week 10 are two different games with two independent
    outcomes, so there is no reason to forbid it.  Banning a team outright
    leaves B with the dregs and a weak second entry is worth very little.
    """
    a = optimize(board, contrarian=contrarian)

    # Once league B has its own recorded picks, it is no longer a variation on
    # A's plan -- it is its own entry with its own history.  Plan it from that.
    if board.used_b:
        b_board = board.for_entry_b()
        clash = {(p.week, p.team) for p in a.picks}
        b_own = optimize(b_board, contrarian=contrarian, block_cells=clash)
        return Entry("A", a), Entry("B", b_own)

    shared = [p for p in a.picks if p.week < diverge_week]

    # B inherits the shared prefix, then avoids everything A will use later.
    state = Board(season=board.season, weeks=board.weeks,
                  used=dict(board.used), entries=board.entries, notes=board.notes)
    for p in shared:
        state.used.setdefault(p.week, []).append(p.team)
    # Block only A's exact (week, team) cells from the divergence point on.
    clash = {(p.week, p.team) for p in a.picks if p.week >= diverge_week}

    b_tail = optimize(state, contrarian=contrarian, block_cells=clash)
    b_plan = Plan(picks=shared + b_tail.picks,
                  survival=a.survival if not shared else
                  _product(shared) * b_tail.survival,
                  blocked_weeks=b_tail.blocked_weeks)
    return Entry("A", a), Entry("B", b_plan)


def _product(picks) -> float:
    out = 1.0
    for p in picks:
        out *= p.prob
    return out


def simulate_pair(board: Board, a: Entry, b: Entry, sims: int = 60000,
                  model_error: bool = True, seed: int = 20260919,
                  drift: float = DRIFT_PER_WEEK) -> JointResult:
    """Both entries through the same simulated seasons.

    One winner is drawn per game and both entries read it, so every form of
    correlation between the two entries is represented exactly.
    """
    rng = random.Random(seed)
    base = _base_table(board)
    by_team: dict[tuple[int, str], tuple] = {}
    for wk in board.weeks:
        for g in wk.games:
            key = (wk.number, g.home, g.away)
            by_team[(wk.number, g.home)] = (key, g)
            by_team[(wk.number, g.away)] = (key, g)

    def keyed(plan):
        rows = []
        for p in plan.picks:
            key, g = by_team.get((p.week, p.team), (None, None))
            rows.append((p, key, g))
        return rows

    a_keys, b_keys = keyed(a.plan), keyed(b.plan)

    n_a = n_b = n_either = n_both = 0
    alive: dict[int, int] = {}
    for _ in range(sims):
        truth = _draw_truth(base, rng, model_error, drift)
        # One coin per game, shared by both entries.
        results: dict[tuple, bool] = {}

        def run(keyed) -> int:
            """How many weeks this entry survives before its first loss."""
            for i, (pick, key, game) in enumerate(keyed):
                if game is None:
                    return i
                if key not in results:
                    results[key] = rng.random() < truth[key]
                if (pick.team == game.home) != results[key]:
                    return i
            return len(keyed)

        ra, rb = run(a_keys), run(b_keys)
        for i in range(max(ra, rb)):
            week = a_keys[i][0].week if i < len(a_keys) else b_keys[i][0].week
            alive[week] = alive.get(week, 0) + 1
        sa, sb = ra == len(a_keys), rb == len(b_keys)
        n_a += sa
        n_b += sb
        n_either += sa or sb
        n_both += sa and sb

    overlap = len({p.week: p.team for p in a.plan.picks}.items()
                  & {p.week: p.team for p in b.plan.picks}.items())
    shared = sum(1 for x, y in zip(a.plan.picks, b.plan.picks) if x.team == y.team)
    return JointResult(
        diverge_week=min((p.week for p in b.plan.picks), default=0),
        shared_weeks=shared,
        p_at_least_one=n_either / sims,
        p_both=n_both / sims,
        p_a=n_a / sims,
        p_b=n_b / sims,
        sims=sims,
        overlap=overlap,
        either_alive={w: c / sims for w, c in sorted(alive.items())},
    )


def sweep(board: Board, weeks: list[int], sims: int = 60000,
          contrarian: float = 0.0, seed: int = 20260919) -> list[JointResult]:
    """Try every divergence week and report what each one is worth."""
    out = []
    for d in weeks:
        a, b = build_pair(board, d, contrarian=contrarian)
        res = simulate_pair(board, a, b, sims=sims, seed=seed)
        res.diverge_week = d
        out.append(res)
    return out
