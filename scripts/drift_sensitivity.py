#!/usr/bin/env python3
"""How much does the plan depend on the rating-drift assumption?

DRIFT_PER_WEEK is the one number in the model that cannot be validated against
data yet, so rather than hide it, this sweeps it and reports whether any
conclusion actually turns on it.

    python3 scripts/drift_sensitivity.py data/survivor_2026.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from survivor.data import load  # noqa: E402
from survivor.plan import optimize, optimize_capped  # noqa: E402
from survivor.ratings import fit, fill  # noqa: E402
from survivor.simulate import TEAM_RATING_SD, simulate_static  # noqa: E402

GRID = (0.0, 0.35, 0.7, 1.2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board", nargs="?", default="data/survivor_2026.json")
    ap.add_argument("--sims", type=int, default=50000)
    ap.add_argument("--max-vs", type=int, default=3)
    args = ap.parse_args()

    board = load(args.board)
    fill(board, fit(board))
    free = optimize(board)
    capped = optimize_capped(board, args.max_vs)
    horizon = len([w for w in board.future_weeks()])

    print(f"free plan fades: {[f'{o} x{c}' for o, c in "
          f"__import__('survivor.plan', fromlist=['x']).opponent_concentration(free)[:3]]}")
    print(f"capped (max-vs {args.max_vs}) analytic {capped.survival*100:.2f}%"
          f" vs free {free.survival*100:.2f}%\n")
    print(f"{'drift':>7}{'wk-18 err sd':>14}{'free':>21}{'capped':>21}{'winner':>10}")
    for drift in GRID:
        a = simulate_static(board, free, sims=args.sims, seed=1, drift=drift)
        c = simulate_static(board, capped, sims=args.sims, seed=1, drift=drift)
        d, sed = a.overall - c.overall, (a.se ** 2 + c.se ** 2) ** 0.5
        win = "free" if d > 2 * sed else ("capped" if -d > 2 * sed else "tie")
        err = (TEAM_RATING_SD ** 2 + drift ** 2 * horizon) ** 0.5
        print(f"{drift:>7.2f}{err:>14.1f}{a.overall*100:>14.3f}% ±{a.se*100:.3f}"
              f"{c.overall*100:>14.3f}% ±{c.se*100:.3f}{win:>10}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
