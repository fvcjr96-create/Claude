"""Modelling the pool around you, not just your own survival.

Everything else in this package answers "will my picks win".  That is the wrong
question once the field is small enough to matter.  A survivor pool pays the
last entry standing, so what you actually want is P(I outlast 8,999 other
people) -- and that depends on what THEY pick, not only on what you pick.

Two forces pull in opposite directions:

* Picking the chalk maximises your own survival, but you survive in company.
  The weeks you win, almost everyone wins, and the pool barely thins.
* Picking off-chalk lowers your survival, but the weeks it lands are weeks the
  field is being wiped out, and those are the weeks that actually win pools.

Which force dominates is an empirical question about pool size, the schedule,
and how chalky the field is.  This module answers it by simulation rather than
by slogan.

THE FIELD MODEL IS AN ASSUMPTION.  Two of them are available:

* `field_entries=0` (fast): the field is one aggregate fraction, choosing among
  the week's best options with weight proportional to win probability raised to
  `chalk`.  It has NO memory, so its entries may spend Kansas City every week.
  That flatters the field badly in a pool needing 24 picks from 30 teams.
* `field_entries=N` (default): N archetype entries are tracked individually,
  each with its own spent-team list, each scaled to represent an equal slice of
  the pool.  Entries diverge naturally as they burn different teams, which is
  what actually creates the spread of exit weeks a survivor pool produces.

Both use each week's real matchups, that week's pick requirement, and the bye
schedule.  Neither models entries that plan ahead the way the planner does --
the field is assumed to pick greedily, week by week, which is how most pools
are actually played.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .data import Board
from .plan import Plan
from .simulate import DRIFT_PER_WEEK, _base_table, _draw_truth


@dataclass
class PoolResult:
    entries: int
    sims: int
    my_survival: dict[int, float] = field(default_factory=dict)   # week -> P(I'm alive)
    field_size: dict[int, float] = field(default_factory=dict)    # week -> E[entries alive]
    p_outlast_all: float = 0.0        # I finish strictly alone
    p_empty_pool: float = 0.0         # nobody survives the season
    equity: float = 0.0               # expected share, if someone goes the distance
    exit_week: float = 0.0            # my mean exit week

    @property
    def relative_survival(self) -> dict[int, float]:
        """My survival divided by the field's, week by week.

        Above 1.0 means I am shrinking the pool faster than it shrinks me --
        which is the whole game once the money goes to whoever lasts longest.
        """
        return {w: (self.my_survival[w] / (self.field_size[w] / self.entries)
                    if self.field_size.get(w) else 0.0)
                for w in self.my_survival}
    # THE metric. You do not have to survive the season; you have to outlast
    # everyone else. This counts how many entries are still alive at the moment
    # you go out -- zero means nobody outlasted you, which is the win condition.
    # Unlike P(last standing) it is a smooth average rather than a rare event,
    # so it converges at sim counts this can actually reach.
    rivals_above: float = 0.0
    rivals_above_se: float = 0.0
    p_nobody_above: float = 0.0       # P(no entry outlasts me)
    last_standing: float = 0.0        # P(I am among the final survivors, however it ends
    # NOTE: `equity` and `last_standing` are rare-event estimators.  At any sim
    # count this module can reach in pure Python they are dominated by noise --
    # seed to seed they move by an order of magnitude and reorder the
    # strategies.  Do not report them.  `relative_survival` below converges
    # quickly and answers the same question: am I outlasting the field?


def _week_options(board: Board, week_num: int, used: set[str], k: int,
                  top: int = 8) -> list[tuple[tuple[str, ...], float]]:
    """Candidate picks for the field this week, best first."""
    from itertools import combinations

    wk = next((w for w in board.weeks if w.number == week_num), None)
    if wk is None:
        return []
    live = sorted(wk.teams_playing() - used,
                  key=lambda t: -wk.game_for(t).prob_for(t))[:6]
    out = []
    for combo in combinations(live, k):
        p = 1.0
        for t in combo:
            p *= wk.game_for(t).prob_for(t)
        out.append((combo, p))
    out.sort(key=lambda r: -r[1])
    return out[:top]


def _week_menu(board: Board, week_num: int) -> tuple[list[tuple[str, float]], int]:
    """Every pickable team this week with its win probability, best first."""
    wk = next((w for w in board.weeks if w.number == week_num), None)
    if wk is None:
        return [], 1
    teams = sorted(((t, wk.game_for(t).prob_for(t)) for t in wk.teams_playing()),
                   key=lambda r: -r[1])
    return teams, max(1, wk.picks_required)


def simulate_pool(board: Board, plan: Plan, entries: int = 9000,
                  chalk: float = 6.0, sims: int = 4000,
                  seed: int = 20260927, drift: float = DRIFT_PER_WEEK,
                  field_entries: int = 120) -> PoolResult:
    """Play the season out with a field of `entries` around you.

    `chalk` controls how tightly the field clusters on the best option: 0 spreads
    it evenly over the candidates, large values put nearly everyone on the single
    most likely pick.  Six is a field that mostly takes the obvious pick but not
    unanimously.

    `field_entries` is how many archetype entries to track individually, each
    carrying its own spent-team list.  Set it to 0 for the old memoryless
    aggregate, which is faster and markedly kinder to the field.
    """
    rng = random.Random(seed)
    base = _base_table(board)
    weeks = sorted({p.week for p in plan.picks})

    by_team: dict[tuple[int, str], tuple] = {}
    for wk in board.weeks:
        for g in wk.games:
            key = (wk.number, g.home, g.away)
            by_team[(wk.number, g.home)] = (key, g)
            by_team[(wk.number, g.away)] = (key, g)

    # The field's menu each week, fixed across sims (it does not depend on the draw).
    menus = {}
    for wk_num in weeks:
        k = next(w.picks_required for w in board.weeks if w.number == wk_num)
        opts = _week_options(board, wk_num, board.used_teams, k)
        if not opts:
            continue
        wts = [p ** chalk for _c, p in opts]
        total = sum(wts) or 1.0
        menus[wk_num] = [(c, w / total) for (c, _p), w in zip(opts, wts)]

    week_menus = {w: _week_menu(board, w) for w in weeks}
    my_alive = {w: 0 for w in weeks}
    field_alive = {w: 0.0 for w in weeks}
    outlast = empty = 0
    equity_total = last_total = 0.0
    exit_total = 0
    rivals: list[float] = []

    for _ in range(sims):
        truth = _draw_truth(base, rng, True, drift)
        results: dict[tuple, bool] = {}

        def won(week: int, team: str) -> bool:
            key, game = by_team.get((week, team), (None, None))
            if game is None:
                return False
            if key not in results:
                results[key] = rng.random() < truth[key]
            return (team == game.home) == results[key]

        if field_entries:
            rivals_state = [{"used": set(board.used_teams), "alive": True}
                            for _ in range(field_entries)]
            per_entry = entries / field_entries
        remaining = float(entries)
        alive = True
        my_exit = len(weeks)
        last_field_week, survivors_before = len(weeks), float(entries)
        field_at_exit = 0.0
        for i, wk_num in enumerate(weeks):
            prev_remaining = remaining
            if field_entries:
                menu, k = week_menus[wk_num]
                live_count = 0
                for st in rivals_state:
                    if not st["alive"]:
                        continue
                    # Greedy but not identical: sample this week's picks from
                    # the best teams this entry has NOT already spent.
                    avail = [(t, pr) for t, pr in menu if t not in st["used"]][:6]
                    if len(avail) < k:
                        st["alive"] = False
                        continue
                    picks, pool_ = [], list(avail)
                    for _ in range(k):
                        wts = [pr ** chalk for _t, pr in pool_]
                        tot = sum(wts) or 1.0
                        r = rng.random() * tot
                        acc = 0.0
                        for idx, w in enumerate(wts):
                            acc += w
                            if r <= acc:
                                break
                        picks.append(pool_.pop(idx)[0])
                    st["used"].update(picks)
                    if all(won(wk_num, t) for t in picks):
                        live_count += 1
                    else:
                        st["alive"] = False
                remaining = live_count * per_entry
            else:
                frac = 0.0
                for combo, weight in menus.get(wk_num, []):
                    if all(won(wk_num, t) for t in combo):
                        frac += weight
                remaining *= frac
            if prev_remaining >= 1.0 > remaining:
                last_field_week, survivors_before = i, prev_remaining

            if alive and not all(won(p.week, p.team)
                                 for p in plan.picks if p.week == wk_num):
                alive = False
                my_exit = i
                field_at_exit = remaining
            if alive:
                my_alive[wk_num] += 1
            field_alive[wk_num] += remaining

        # How much of the field is still alive when I go out?  If I last the
        # whole way, it is whatever is left at the end.
        above = field_at_exit if not alive else remaining
        rivals.append(max(0.0, above - (1.0 if alive else 0.0)))
        exit_total += my_exit
        # Most pools never produce an unbeaten entry -- 44% of the time here the
        # board empties -- and the money goes to whoever lasted longest.  So
        # score being among the last standing, not only going the distance.
        if alive:
            last_total += 1.0 / max(1.0, remaining)
        elif my_exit >= last_field_week:
            # I fell in the same week the field ran out: still a co-winner.
            last_total += 1.0 / max(1.0, survivors_before)
        others = max(0.0, remaining - (1.0 if alive else 0.0))
        if alive:
            equity_total += 1.0 / (1.0 + others)
            if others < 0.5:
                outlast += 1
        if remaining < 0.5:
            empty += 1

    return PoolResult(
        entries=entries,
        sims=sims,
        my_survival={w: c / sims for w, c in my_alive.items()},
        field_size={w: v / sims for w, v in field_alive.items()},
        p_outlast_all=outlast / sims,
        p_empty_pool=empty / sims,
        equity=equity_total / sims,
        exit_week=exit_total / sims,
        last_standing=last_total / sims,
        rivals_above=sum(rivals) / len(rivals),
        rivals_above_se=(
            (sum((x - sum(rivals) / len(rivals)) ** 2 for x in rivals)
             / max(1, len(rivals) - 1)) ** 0.5 / len(rivals) ** 0.5),
        p_nobody_above=sum(1 for x in rivals if x < 0.5) / len(rivals),
    )


def compare(board: Board, plans: dict[str, Plan], entries: int = 9000,
            chalk: float = 6.0, sims: int = 4000) -> dict[str, PoolResult]:
    return {name: simulate_pool(board, p, entries=entries, chalk=chalk, sims=sims)
            for name, p in plans.items()}
