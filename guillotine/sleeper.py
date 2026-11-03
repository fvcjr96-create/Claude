"""Turning a Sleeper league into a guillotine board.

The transforms here are pure: they take already-fetched JSON and return the
board.  That matters because the network call cannot be exercised from every
environment, so the parsing -- which is where the bugs live -- is tested
against fixtures instead of against a live league.

Sleeper's shapes, for reference:
  /v1/league/{id}            settings.waiver_budget, roster_positions, scoring
  /v1/league/{id}/users      user_id -> display_name, metadata.team_name
  /v1/league/{id}/rosters    owner_id, players[], settings.waiver_budget_used
  /v1/league/{id}/matchups/N starters[], starters_points[], points
  /v1/players/nfl            player_id -> full_name, position, team  (~5 MB)
  /projections/nfl/{yr}/{wk} unofficial; stats.pts_ppr per player
"""

from __future__ import annotations

SKILL = ("QB", "RB", "WR", "TE")


def team_names(users: list[dict]) -> dict[str, str]:
    """user_id -> the name a human would recognise."""
    out = {}
    for u in users:
        meta = u.get("metadata") or {}
        out[u["user_id"]] = meta.get("team_name") or u.get("display_name") or u["user_id"]
    return out


def budgets(league: dict, rosters: list[dict]) -> dict[str, float]:
    """roster_id -> FAAB remaining.

    Sleeper stores what has been SPENT, not what is left, and omits the field
    entirely for a team that has never bid.
    """
    total = float((league.get("settings") or {}).get("waiver_budget", 100))
    out = {}
    for r in rosters:
        used = float((r.get("settings") or {}).get("waiver_budget_used", 0) or 0)
        out[str(r["roster_id"])] = total - used
    return out


def rostered_player_ids(rosters: list[dict]) -> set[str]:
    out: set[str] = set()
    for r in rosters:
        out.update(str(p) for p in (r.get("players") or []))
    return out


def free_agents(rosters: list[dict], players: dict, projections: dict[str, float],
                limit: int = 40) -> list[dict]:
    """Everyone not on a roster, best projection first.

    In a guillotine league the chopped team's roster lands here automatically,
    so there is no need to work out who was eliminated -- whoever is unowned IS
    the pool.
    """
    taken = rostered_player_ids(rosters)
    out = []
    for pid, meta in players.items():
        if pid in taken:
            continue
        pos = meta.get("position")
        if pos not in SKILL:
            continue
        proj = projections.get(pid)
        if proj is None:
            continue
        out.append({
            "name": meta.get("full_name") or pid,
            "pos": pos,
            "team": meta.get("team") or "FA",
            "proj": round(float(proj), 2),
            "player_id": pid,
        })
    out.sort(key=lambda p: -p["proj"])
    return out[:limit]


def roster_for(roster: dict, players: dict, projections: dict[str, float],
               starters: list[str] | None = None) -> list[dict]:
    out = []
    starting = set(starters or [])
    for pid in (roster.get("players") or []):
        pid = str(pid)
        meta = players.get(pid) or {}
        pos = meta.get("position")
        if pos not in SKILL:
            continue
        out.append({
            "name": meta.get("full_name") or pid,
            "pos": pos,
            "team": meta.get("team") or "FA",
            "proj": round(float(projections.get(pid, 0.0)), 2),
            "starter": pid in starting,
            "player_id": pid,
        })
    out.sort(key=lambda p: -p["proj"])
    return out


def projected_total(roster: dict, players: dict, projections: dict[str, float],
                    slots: tuple = ("QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX")) -> float:
    """A rival's projected score: their best legal lineup, same rules as mine."""
    from .lineup import optimize
    from .config import Player

    squad = [Player(p["name"], p["pos"], p["proj"])
             for p in roster_for(roster, players, projections)]
    return round(optimize(squad).points, 2)


def build_board(league: dict, users: list[dict], rosters: list[dict],
                players: dict, projections: dict[str, float],
                my_user_id: str, week: int,
                starters: list[str] | None = None) -> dict:
    """Assemble the board this package's engine already understands."""
    names = team_names(users)
    purse = budgets(league, rosters)
    mine = next((r for r in rosters if r.get("owner_id") == my_user_id), None)
    if mine is None:
        owners = {r.get("owner_id") for r in rosters}
        raise ValueError(f"user {my_user_id} owns no roster here; owners are {sorted(map(str, owners))}")

    rivals = []
    for r in rosters:
        if r["roster_id"] == mine["roster_id"]:
            continue
        rivals.append({
            "name": names.get(r.get("owner_id"), f"roster {r['roster_id']}"),
            "proj": projected_total(r, players, projections),
            "budget": purse[str(r["roster_id"])],
        })
    rivals.sort(key=lambda x: -x["proj"])

    return {
        "week": week,
        "my_team": names.get(my_user_id, "me"),
        "my_budget": purse[str(mine["roster_id"])],
        "default_budget": float((league.get("settings") or {}).get("waiver_budget", 100)),
        "roster": roster_for(mine, players, projections, starters),
        "rivals": rivals,
        "waivers": free_agents(rosters, players, projections),
        "notes": [
            f"Built from the Sleeper API for league {league.get('league_id')} "
            f"({league.get('name')}), week {week}.",
            "Rival projections are each roster's own best legal lineup under the "
            "same slot rules, so every team is measured the same way.",
            "The waiver pool is every unowned skill player, which in a guillotine "
            "league already includes the chopped roster.",
        ],
    }
