#!/usr/bin/env python3
"""Build the preseason rating prior for a season from the previous one.

    python3 scripts/build_prior.py --season 2026 --out data/prior_2026.json

Three weeks of game lines are a thin basis for pricing week 15.  A full prior
season of closing lines is not -- teams carry over.  This fits ratings to last
season's 272 closing spreads with recency weighting (a week-18 line says more
about next September than a week-1 line), then regresses them toward league
average for offseason churn.

Both constants were chosen by held-out validation on the current season's own
lines; see scripts/tune_ridge.py --prior.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from survivor.ratings import HALF_LIFE, PRIOR_K, fit_from_games  # noqa: E402

SOURCE = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
ALIAS = {"LA": "LAR"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=2026, help="season the prior is FOR")
    ap.add_argument("--out", default=None)
    ap.add_argument("--half-life", type=float, default=HALF_LIFE)
    ap.add_argument("--regress", type=float, default=PRIOR_K,
                    help="offseason carry-over factor; 1.0 = no regression")
    args = ap.parse_args()

    prev = args.season - 1
    out = Path(args.out or f"data/prior_{args.season}.json")

    print(f"fetching {SOURCE}")
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "survivor-planner/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = list(csv.DictReader(io.StringIO(r.read().decode())))

    games = [
        (ALIAS.get(r["home_team"], r["home_team"]),
         ALIAS.get(r["away_team"], r["away_team"]),
         float(r["spread_line"]), int(r["week"]))
        for r in rows
        if r.get("season") == str(prev) and r.get("game_type") == "REG"
        and (r.get("spread_line") or "NA") not in ("", "NA")
    ]
    if not games:
        print(f"no {prev} games with spreads found", file=sys.stderr)
        return 1

    end = fit_from_games(games, half_life=args.half_life)
    ratings = {t: round(args.regress * v, 4) for t, v in end.items()}

    out.write_text(json.dumps({
        "for_season": args.season,
        "from_season": prev,
        "games_used": len(games),
        "half_life_weeks": args.half_life,
        "regression": args.regress,
        "source": SOURCE,
        "ratings": dict(sorted(ratings.items(), key=lambda kv: -kv[1])),
    }, indent=2) + "\n")

    rank = sorted(ratings.items(), key=lambda kv: -kv[1])
    print(f"{len(games)} games from {prev}, half-life {args.half_life}w, "
          f"regressed x{args.regress}")
    print("  top:", ", ".join(f"{t}{v:+.1f}" for t, v in rank[:5]))
    print("  bottom:", ", ".join(f"{t}{v:+.1f}" for t, v in rank[-5:]))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
