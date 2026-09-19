#!/usr/bin/env python3
"""Generate a SYNTHETIC 18-week board so the planner's output can be seen end to end.

This is NOT the real NFL schedule and must never be used to make a pick.  It
exists so the mechanics -- hoarding, opportunity cost, the full-season table --
can be demonstrated and tested without inventing real matchups.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from survivor.data import TEAMS  # noqa: E402
from survivor.model import HOME_FIELD  # noqa: E402

SEED = 2026


def main() -> int:
    rng = random.Random(SEED)
    ratings = {t: rng.gauss(0, 5.5) for t in TEAMS}
    weeks = {}
    for wk in range(1, 19):
        pool = TEAMS[:]
        rng.shuffle(pool)
        # Six teams on bye in most weeks, as in a real season.
        byes = pool[:6] if 5 <= wk <= 14 else []
        playing = [t for t in pool if t not in byes]
        games = []
        for i in range(0, len(playing) - 1, 2):
            home, away = playing[i], playing[i + 1]
            spread = ratings[home] - ratings[away] + HOME_FIELD
            games.append({"away": away, "home": home, "home_spread": round(spread, 1)})
        weeks[str(wk)] = {"verified": wk <= 4, "source": "SYNTHETIC", "games": games}

    out = Path("data/demo_synthetic.json")
    out.write_text(json.dumps({
        "season": 2026,
        "synthetic": True,
        "entries": 100,
        "used": {"1": "PIT"},
        "weeks": weeks,
        "notes": ["SYNTHETIC BOARD. Randomly generated schedule and ratings.",
                  "Demonstrates the planner's mechanics only. Never pick from it."],
    }, indent=2) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
