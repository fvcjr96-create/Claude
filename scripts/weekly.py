#!/usr/bin/env python3
"""The Monday routine: record last week's picks, refresh the data, replan.

    python3 scripts/weekly.py --pick-a SF --pick-b TB

One command does all of it:

  1. records the picks you actually made, into league A and league B
  2. re-fetches the schedule, which by Monday carries last week's RESULTS and
     the newly posted lines for the week ahead
  3. rebuilds the rating prior
  4. prints the fresh plan for both leagues

Injuries and news do not need handling separately: they are already in the
book's numbers, and re-fetching picks them up.  A team that lost its starting
quarterback on Sunday shows up on Monday as a moved line, which moves the fit,
which moves the plan.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> int:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=ROOT)


def record(board_path: Path, week: int, team_a: str | None, team_b: str | None) -> None:
    board = json.loads(board_path.read_text())
    for key, team in (("used", team_a), ("used_b", team_b)):
        if not team:
            continue
        used = board.setdefault(key, {})
        prev = used.get(str(week))
        if prev and prev != team:
            print(f"  ! {key} week {week} was {prev}, overwriting with {team}")
        used[str(week)] = team
    board_path.write_text(json.dumps(board, indent=2) + "\n")
    a = board.get("used", {})
    b = board.get("used_b", {})
    print(f"  league A: {', '.join(f'wk{w} {t}' for w, t in sorted(a.items(), key=lambda kv: int(kv[0]))) or '-'}")
    print(f"  league B: {', '.join(f'wk{w} {t}' for w, t in sorted(b.items(), key=lambda kv: int(kv[0]))) or '-'}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=int, help="week the picks were for (default: latest recorded + 1)")
    ap.add_argument("--pick-a", help="team you actually played in league A")
    ap.add_argument("--pick-b", help="team you actually played in league B")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--board", default="data/survivor_2026.json")
    ap.add_argument("--no-fetch", action="store_true", help="skip the data refresh")
    args = ap.parse_args()

    board_path = ROOT / args.board

    if args.pick_a or args.pick_b:
        board = json.loads(board_path.read_text())
        week = args.week or (max((int(w) for w in board.get("used", {})), default=0) + 1)
        print(f"recording week {week} picks")
        record(board_path, week, args.pick_a, args.pick_b)

    if not args.no_fetch:
        print("\n=== refreshing schedule, results and lines")
        if run([sys.executable, "scripts/fetch_grid.py",
                "--season", str(args.season), "--out", args.board]):
            print("fetch failed - replanning on the data already on disk", file=sys.stderr)
        print("\n=== rebuilding the rating prior")
        run([sys.executable, "scripts/build_prior.py", "--season", str(args.season)])

    print("\n=== new plan")
    run([sys.executable, "-m", "survivor", args.board, "--pair", "--costs"])
    print("\nIf the plan moved, it moved because the market did. "
          "Re-read the opportunity cost table before locking anything in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
