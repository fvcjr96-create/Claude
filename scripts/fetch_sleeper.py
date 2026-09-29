#!/usr/bin/env python3
"""Build the guillotine board straight from Sleeper. Run this on your machine.

    python3 scripts/fetch_sleeper.py --league 1397060630510362624 --user fclara1 \
        --week 4 --out data/guillotine_week04.json

Everything the board needs is in Sleeper's public read-only API: rosters, FAAB
remaining, the free-agent pool, and weekly projections. No screenshots, no
hand-typed numbers, no stale week-3 figures standing in for week 4.

The player file is ~5 MB, so it is cached under the scratch directory and
re-used until --refresh-players is passed.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guillotine.sleeper import build_board  # noqa: E402

API = "https://api.sleeper.app"
CACHE = Path(".cache")


def get(path: str, timeout: int = 60):
    url = path if path.startswith("http") else f"{API}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "guillotine-planner/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def players(refresh: bool) -> dict:
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / "sleeper_players.json"
    if cached.exists() and not refresh:
        return json.loads(cached.read_text())
    print("  fetching player list (~5 MB, cached after this)...")
    data = get("/v1/players/nfl")
    cached.write_text(json.dumps(data))
    return data


def projections(season: int, week: int) -> dict[str, float]:
    """Weekly PPR projections. This endpoint is undocumented; tolerate failure."""
    qs = urllib.parse.urlencode(
        [("season_type", "regular"), ("order_by", "pts_ppr")]
        + [("position[]", p) for p in ("QB", "RB", "WR", "TE")])
    try:
        rows = get(f"{API}/projections/nfl/{season}/{week}?{qs}")
    except Exception as e:                      # noqa: BLE001 - undocumented endpoint
        print(f"  projections unavailable ({e}); every proj will be 0", file=sys.stderr)
        return {}
    out = {}
    for row in rows or []:
        pid = str(row.get("player_id"))
        pts = (row.get("stats") or {}).get("pts_ppr")
        if pid and pts is not None:
            out[pid] = float(pts)
    print(f"  projections for {len(out)} players")
    return out


def resolve_user(users: list[dict], who: str) -> str:
    """Accept a user_id, a @handle, or a team name."""
    who_l = who.lstrip("@").lower()
    for u in users:
        meta = u.get("metadata") or {}
        if who_l in {str(u.get("user_id")).lower(),
                     str(u.get("display_name", "")).lower(),
                     str(meta.get("team_name", "")).lower()}:
            return u["user_id"]
    known = ", ".join(sorted(str(u.get("display_name")) for u in users))
    raise SystemExit(f"no user matching {who!r}. This league has: {known}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--league", required=True)
    ap.add_argument("--user", required=True, help="your @handle, team name, or user_id")
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--out", default=None)
    ap.add_argument("--refresh-players", action="store_true")
    args = ap.parse_args()

    print(f"league {args.league}, week {args.week}")
    try:
        league = get(f"/v1/league/{args.league}")
        users = get(f"/v1/league/{args.league}/users")
        rosters = get(f"/v1/league/{args.league}/rosters")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Sleeper returned {e.code} for the league. Check the id.")
    print(f"  {league.get('name')}: {len(rosters)} rosters, {len(users)} managers")

    me = resolve_user(users, args.user)
    pl = players(args.refresh_players)
    proj = projections(args.season, args.week)

    starters = None
    try:
        matchups = get(f"/v1/league/{args.league}/matchups/{args.week}")
        mine = next((m for m in matchups
                     if str(m.get("roster_id")) == str(
                         next(r["roster_id"] for r in rosters if r.get("owner_id") == me))), None)
        starters = [str(s) for s in (mine or {}).get("starters", []) if s and s != "0"]
    except Exception:                            # noqa: BLE001 - lineup not set yet
        pass

    board = build_board(league, users, rosters, pl, proj, me, args.week, starters)
    out = Path(args.out or f"data/guillotine_week{args.week:02d}.json")
    out.write_text(json.dumps(board, indent=2) + "\n")

    print(f"\n  you: {board['my_team']}  ${board['my_budget']:.0f} FAAB")
    print(f"  your projected lineup vs {len(board['rivals'])} rivals")
    rich = [r for r in board["rivals"] if r["budget"] >= board["my_budget"]]
    print(f"  {len(rich)} rivals hold at least as much FAAB as you")
    print(f"  top of the pool: " + ", ".join(
        f"{w['name']} {w['proj']}" for w in board["waivers"][:4]))
    print(f"\nwrote {out}\nnow run:  python3 -m guillotine {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
