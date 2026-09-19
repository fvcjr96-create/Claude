#!/usr/bin/env python3
"""Build the full-season survivor board from ESPN's public scoreboard API.

Run this on your own machine -- it needs plain internet access:

    python3 scripts/fetch_grid.py --season 2026 --out data/survivor_2026.json

It pulls every week's schedule, attaches the posted spread wherever one exists,
and marks those weeks verified.  Games with no line are left blank; the planner
prices them from ratings fitted to the lines that do exist, and keeps flagging
them as model rather than market.

Existing "used", "entries" and "notes" in the output file are preserved, so
re-running it each week updates the board without losing your picks.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
       "?dates={season}&seasontype=2&week={week}")

# ESPN spells a few teams differently from the planner's canonical list.
ALIAS = {"WSH": "WAS", "LAR": "LAR", "LAC": "LAC", "LV": "LV", "JAX": "JAX"}


def fetch(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "survivor-planner/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def parse_spread(comp: dict, home_abbr: str) -> float | None:
    """Return the spread from the home team's point of view, or None."""
    for odds in comp.get("odds", []) or []:
        if odds.get("spread") is not None:
            # ESPN's "spread" is the home line already (negative = home favoured
            # in their convention), so flip it to "positive = home favoured".
            try:
                return -float(odds["spread"])
            except (TypeError, ValueError):
                pass
        details = odds.get("details")
        if details and details.upper() != "EVEN":
            m = re.match(r"^\s*([A-Z]{2,4})\s+([+-]?\d+(?:\.\d+)?)\s*$", details.strip())
            if m:
                team, num = m.group(1), float(m.group(2))
                team = ALIAS.get(team, team)
                # `num` is negative for the favourite.
                return -num if team == home_abbr else num
        if details and details.upper() == "EVEN":
            return 0.0
    return None


def build(season: int, weeks: int = 18) -> dict:
    out: dict[str, dict] = {}
    for wk in range(1, weeks + 1):
        try:
            payload = fetch(API.format(season=season, week=wk))
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  week {wk}: fetch failed ({e}) - skipped", file=sys.stderr)
            continue
        games, lined = [], 0
        for ev in payload.get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            home = away = None
            for c in comp.get("competitors", []):
                abbr = ALIAS.get((c.get("team") or {}).get("abbreviation", ""),
                                 (c.get("team") or {}).get("abbreviation", ""))
                if c.get("homeAway") == "home":
                    home = abbr
                else:
                    away = abbr
            if not home or not away:
                continue
            g = {"away": away, "home": home}
            sp = parse_spread(comp, home)
            if sp is not None:
                g["home_spread"] = sp
                lined += 1
            games.append(g)
        if not games:
            continue
        out[str(wk)] = {
            "verified": lined >= len(games) - 1,
            "source": f"ESPN scoreboard API, season {season} week {wk}",
            "games": games,
        }
        print(f"  week {wk}: {len(games)} games, {lined} with a posted line")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--weeks", type=int, default=18)
    ap.add_argument("--out", default="data/survivor_2026.json")
    args = ap.parse_args()

    path = Path(args.out)
    existing = json.loads(path.read_text()) if path.exists() else {}

    print(f"fetching {args.season} schedule and lines...")
    weeks = build(args.season, args.weeks)
    if not weeks:
        print("no weeks fetched - nothing written", file=sys.stderr)
        return 1

    # Keep any week the file already had verified with better data than ESPN gave.
    for num, wk in (existing.get("weeks") or {}).items():
        if wk.get("verified") and not weeks.get(num, {}).get("verified"):
            weeks[num] = wk

    payload = {
        "season": args.season,
        "entries": existing.get("entries", 100),
        "used": existing.get("used", {}),
        "weeks": weeks,
        "notes": existing.get("notes", []),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {path}: {len(weeks)} weeks")
    print(f"now run:  python3 -m survivor {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
