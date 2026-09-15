"""Optimal starting lineup and the marginal value of an add."""

from __future__ import annotations

from dataclasses import dataclass

from .config import FLEX_POSITIONS, Player

N_FLEX = 2
BASE_SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1}


@dataclass
class Lineup:
    starters: list[Player]
    points: float

    def by_slot(self) -> list[tuple[str, Player]]:
        """Label each starter with the slot it is filling, flex last."""
        remaining = dict(BASE_SLOTS)
        fixed: list[tuple[str, Player]] = []
        flex: list[tuple[str, Player]] = []
        for p in sorted(self.starters, key=lambda x: -x.proj):
            if remaining.get(p.pos, 0) > 0:
                remaining[p.pos] -= 1
                fixed.append((p.pos, p))
            else:
                flex.append(("FLEX", p))
        order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3}
        fixed.sort(key=lambda sp: (order[sp[0]], -sp[1].proj))
        return fixed + flex


def optimize(roster: list[Player]) -> Lineup:
    """Best legal lineup for QB/RB/RB/WR/WR/TE/FLEX/FLEX.

    Brute force over how the two flex spots are split between RB, WR and TE;
    within a position the best remaining projections always win, so each split
    is settled by a sort.
    """
    pool: dict[str, list[Player]] = {}
    for p in roster:
        pool.setdefault(p.pos, []).append(p)
    for plist in pool.values():
        plist.sort(key=lambda x: -x.proj)

    best: Lineup | None = None
    # (rb_flex, wr_flex, te_flex) combinations summing to N_FLEX
    for rb_x in range(N_FLEX + 1):
        for wr_x in range(N_FLEX + 1 - rb_x):
            te_x = N_FLEX - rb_x - wr_x
            want = {
                "QB": BASE_SLOTS["QB"],
                "RB": BASE_SLOTS["RB"] + rb_x,
                "WR": BASE_SLOTS["WR"] + wr_x,
                "TE": BASE_SLOTS["TE"] + te_x,
            }
            picks: list[Player] = []
            ok = True
            for pos, n in want.items():
                have = pool.get(pos, [])
                if len(have) < n:
                    ok = False
                    break
                picks.extend(have[:n])
            if not ok:
                continue
            pts = sum(p.proj for p in picks)
            if best is None or pts > best.points:
                best = Lineup(picks, pts)

    if best is None:
        # Roster cannot fill every slot (injuries, byes, a thin config).
        # Start the best available and treat empty slots as zero points.
        picks = sorted(roster, key=lambda x: -x.proj)[: sum(BASE_SLOTS.values()) + N_FLEX]
        best = Lineup(picks, sum(p.proj for p in picks))
    return best


def add_value(roster: list[Player], add: Player) -> tuple[float, Lineup, Player | None]:
    """Points the add puts in the starting lineup, plus who it benches.

    Returns (delta, new_lineup, displaced_starter).  Delta is zero for a player
    who does not crack the lineup -- in a guillotine league a bench stash scores
    nothing and cannot save you from the chop this week.
    """
    before = optimize(roster)
    after = optimize(roster + [add])
    delta = after.points - before.points
    displaced = None
    if delta > 1e-9:
        gone = {id(p) for p in after.starters}
        out = [p for p in before.starters if id(p) not in gone]
        displaced = out[0] if out else None
    return delta, after, displaced


def drop_candidates(roster: list[Player], keep: int = 3) -> list[Player]:
    """Players whose removal costs the lineup nothing, worst first."""
    lu = optimize(roster)
    starting = {id(p) for p in lu.starters}
    bench = [p for p in roster if id(p) not in starting]
    bench.sort(key=lambda p: p.proj)
    return bench[:keep]


def stack_value(roster: list[Player], adds: list[Player]) -> float:
    """Combined lineup gain from adding several players at once."""
    return optimize(roster + list(adds)).points - optimize(roster).points

