#!/usr/bin/env python3
"""Choose the ridge penalty by held-out validation instead of by feel.

Fits power ratings on the earliest market-priced weeks, then predicts the spread
in the last priced week and reports the error.  Re-run it as the season adds
weeks -- the best ridge drifts down as more real lines arrive.

    python3 scripts/tune_ridge.py data/survivor_2026.json
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from survivor.data import load  # noqa: E402
from survivor.model import HOME_FIELD, spread_from_prob  # noqa: E402
from survivor.ratings import fit  # noqa: E402

GRID = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)


def priced_spread(game) -> float | None:
    if game.home_prob is not None:
        return spread_from_prob(game.home_prob)
    return game.home_spread


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board", nargs="?", default="data/survivor_2026.json")
    args = ap.parse_args()

    board = load(args.board)
    priced = [w.number for w in board.weeks
              if any(priced_spread(g) is not None for g in w.games)]
    if len(priced) < 2:
        print("need at least two market-priced weeks to validate", file=sys.stderr)
        return 1
    holdout = priced[-1]
    train_weeks = priced[:-1]

    truth = [(g.home, g.away, priced_spread(g))
             for w in board.weeks if w.number == holdout
             for g in w.games if priced_spread(g) is not None]

    train = copy.deepcopy(board)
    for w in train.weeks:
        if w.number not in train_weeks:
            for g in w.games:
                g.home_spread = g.home_prob = None

    print(f"train: weeks {train_weeks}   holdout: week {holdout} ({len(truth)} games)\n")
    print(f"{'ridge':>7}{'MAE':>9}{'RMSE':>8}{'spread':>9}")
    best = None
    for ridge in GRID:
        r = fit(train, ridge=ridge)
        errs = [r.spread(h, a) - s for h, a, s in truth]
        mae = sum(abs(e) for e in errs) / len(errs)
        rmse = (sum(e * e for e in errs) / len(errs)) ** 0.5
        width = max(r.values.values()) - min(r.values.values())
        print(f"{ridge:>7}{mae:>9.2f}{rmse:>8.2f}{width:>9.1f}")
        if best is None or mae < best[1]:
            best = (ridge, mae, rmse)

    base = [HOME_FIELD - s for _h, _a, s in truth]
    base_mae = sum(abs(e) for e in base) / len(base)
    print(f"\nbest ridge {best[0]}: MAE {best[1]:.2f} pts, RMSE {best[2]:.2f}")
    print(f"home-field-only baseline: MAE {base_mae:.2f} pts")
    print("\nset RIDGE and RATING_RMSE in survivor/ratings.py from this.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
