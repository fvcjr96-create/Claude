"""Roll a week's snapshot forward so the weekly update is a fill-in-the-blanks job."""

from __future__ import annotations

import json
from pathlib import Path

from .config import League


def rollover(lg: League, chopped: str | None = None) -> dict:
    """Skeleton for next week: roster and settings carried over, numbers blanked.

    Projections and budgets change every week and must be re-read from the app,
    so they are carried over with a marker rather than silently reused.
    """
    rivals = [r for r in lg.rivals if chopped is None or r.name != chopped]
    return {
        "week": lg.week + 1,
        "my_team": lg.my_team,
        "my_budget": lg.my_budget,
        "default_budget": lg.default_budget,
        "roster": [
            {
                "name": p.name, "pos": p.pos, "team": p.team,
                "proj": p.proj, "rostered_pct": p.rostered_pct,
                "starter": p.starter, "note": "UPDATE proj",
            }
            for p in lg.roster
        ],
        "rivals": [
            {"name": r.name, "proj": r.proj, "budget": r.budget, "estimated": True}
            for r in rivals
        ],
        "waivers": [
            {"name": "", "pos": "WR", "team": "", "proj": 0.0, "rostered_pct": 0.0}
        ],
        "settings": {"budget_alpha": lg.settings.budget_alpha},
        "notes": [
            f"Skeleton rolled over from week {lg.week}.",
            "1. CHOP tab: overwrite every rival projection and delete the chopped team.",
            "2. TEAM tab: overwrite your own projections, including the bench.",
            "3. LEAGUE tab: overwrite every budget, yours and theirs.",
            "4. PLAYERS > Available: replace the waiver list with this week's pool.",
            "Every rival is flagged estimated=True until you overwrite it.",
        ],
    }


def write_rollover(lg: League, path: str | Path, chopped: str | None = None) -> Path:
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} already exists - refusing to overwrite")
    path.write_text(json.dumps(rollover(lg, chopped), indent=2) + "\n")
    return path
