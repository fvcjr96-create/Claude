#!/usr/bin/env python3
"""Build the survivor board from the nflverse schedule dataset.

    python3 scripts/fetch_grid.py --season 2026 --out data/survivor_2026.json

nflverse publishes the full NFL schedule as a CSV on GitHub, including posted
spreads and moneylines for the weeks books have priced, and results for games
already played.  It is one request for the whole season.

Pricing, best source first:
  1. de-vigged two-way moneyline  (the market's own estimate)
  2. posted spread through the normal margin model
  3. nothing -- left blank for the planner to price from fitted ratings

Your "used" picks, "entries" and "notes" survive a re-run, so this is safe to
run every week.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SOURCE = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"

# nflverse spells the Rams "LA"; the planner uses "LAR".
ALIAS = {"LA": "LAR"}


def norm(team: str) -> str:
    return ALIAS.get(team, team)


def fetch_csv(url: str, timeout: int = 60) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "survivor-planner/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode())))


def num(row: dict, key: str) -> float | None:
    v = (row.get(key) or "").strip()
    if v in ("", "NA", "NULL"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def build(rows: list[dict], season: int) -> dict:
    from survivor.model import devig

    weeks: dict[str, dict] = {}
    priced = {"moneyline": 0, "spread": 0, "none": 0}
    played = 0

    for r in rows:
        if r.get("season") != str(season) or r.get("game_type") != "REG":
            continue
        wk = str(int(r["week"]))
        game = {"away": norm(r["away_team"]), "home": norm(r["home_team"])}

        if num(r, "result") is not None:
            game["played"] = True
            game["home_won"] = num(r, "result") > 0
            played += 1

        hml, aml = num(r, "home_moneyline"), num(r, "away_moneyline")
        spread = num(r, "spread_line")
        if hml is not None and aml is not None:
            game["home_prob"] = round(devig(hml, aml), 4)
            game["priced"] = "moneyline"
            priced["moneyline"] += 1
        elif spread is not None:
            game["home_spread"] = spread
            game["priced"] = "spread"
            priced["spread"] += 1
        else:
            priced["none"] += 1

        w = weeks.setdefault(wk, {"games": [], "source": f"nflverse games.csv, {season}"})
        w["games"].append(game)

    for wk in weeks.values():
        # A week counts as verified only if the market has priced all of it.
        wk["verified"] = all(g.get("priced") for g in wk["games"])

    print(f"  {sum(len(w['games']) for w in weeks.values())} games over {len(weeks)} weeks")
    print(f"  priced by moneyline: {priced['moneyline']}, by spread: {priced['spread']},"
          f" unpriced: {priced['none']}")
    print(f"  already played: {played}")
    return weeks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--out", default="data/survivor_2026.json")
    ap.add_argument("--source", default=SOURCE)
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    path = Path(args.out)
    existing = json.loads(path.read_text()) if path.exists() else {}

    print(f"fetching {args.source}")
    try:
        rows = fetch_csv(args.source)
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"fetch failed: {e}", file=sys.stderr)
        return 1

    weeks = build(rows, args.season)
    if not weeks:
        print(f"no {args.season} regular season games found - nothing written", file=sys.stderr)
        return 1

    payload = {
        "season": args.season,
        "entries": existing.get("entries", 100),
        "used": existing.get("used", {}),
        "weeks": dict(sorted(weeks.items(), key=lambda kv: int(kv[0]))),
        "notes": existing.get("notes", []),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {path}")
    print(f"now run:  python3 -m survivor {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
