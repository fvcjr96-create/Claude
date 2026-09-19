"""The season board: who plays whom, and how likely each side is to win."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .model import prob_from_spread

TEAMS = [
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA",
    "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB",
    "TEN", "WAS",
]


@dataclass
class Game:
    week: int
    away: str
    home: str
    home_spread: float | None = None      # positive = home favoured
    home_prob: float | None = None        # overrides the spread if given
    played: bool = False                  # already final; cannot be picked
    priced: str = ""                      # "moneyline", "spread" or "" (modelled)

    def prob_for(self, team: str) -> float:
        if self.home_prob is not None:
            hp = self.home_prob
        elif self.home_spread is not None:
            hp = prob_from_spread(self.home_spread)
        else:
            hp = 0.5
        return hp if team == self.home else 1.0 - hp

    def opponent_of(self, team: str) -> str:
        return self.away if team == self.home else self.home

    def is_home(self, team: str) -> bool:
        return team == self.home


@dataclass
class Week:
    number: int
    games: list[Game]
    verified: bool = False
    source: str = ""
    popularity: dict[str, float] = field(default_factory=dict)

    def game_for(self, team: str, include_played: bool = False) -> Game | None:
        for g in self.games:
            if team in (g.home, g.away) and (include_played or not g.played):
                return g
        return None

    def teams_playing(self) -> set[str]:
        """Teams with a game this week that has not already kicked off."""
        return {t for g in self.games if not g.played for t in (g.home, g.away)}

    def all_teams(self) -> set[str]:
        return {t for g in self.games for t in (g.home, g.away)}


@dataclass
class Board:
    season: int
    weeks: list[Week]
    used: dict[int, str] = field(default_factory=dict)   # week -> team already picked
    entries: int = 100
    notes: list[str] = field(default_factory=list)

    @property
    def used_teams(self) -> set[str]:
        return set(self.used.values())

    def future_weeks(self) -> list[Week]:
        start = max(self.used) if self.used else 0
        return [w for w in self.weeks if w.number > start]

    def verified_through(self) -> int:
        v = [w.number for w in self.weeks if w.verified]
        return max(v) if v else 0

    def warnings(self) -> list[str]:
        out = []
        unverified = [w.number for w in self.future_weeks() if not w.verified]
        if unverified:
            out.append(
                f"weeks {unverified[0]}-{unverified[-1]} are NOT verified market data; "
                "treat their picks as placeholders and re-run once real lines exist"
            )
        for w in self.future_weeks():
            playing = w.teams_playing()
            if w.verified and len(playing) % 2:
                out.append(f"week {w.number} has an odd number of teams on the board")
            byes = [t for t in TEAMS if t not in w.all_teams()]
            if len(byes) > 6:
                out.append(f"week {w.number} is missing {len(byes)} teams - is the board complete?")
            done = [g for g in w.games if g.played]
            if done:
                out.append(f"week {w.number}: {len(done)} game(s) already final and off the board")
        return out


def load(path: str | Path) -> Board:
    raw = json.loads(Path(path).read_text())
    weeks = []
    for num, wk in sorted(raw["weeks"].items(), key=lambda kv: int(kv[0])):
        n = int(num)
        games = [
            Game(
                week=n,
                away=g["away"],
                home=g["home"],
                home_spread=g.get("home_spread"),
                home_prob=g.get("home_prob"),
                played=bool(g.get("played", False)),
                priced=g.get("priced", ""),
            )
            for g in wk["games"]
        ]
        weeks.append(
            Week(
                number=n,
                games=games,
                verified=bool(wk.get("verified", False)),
                source=wk.get("source", ""),
                popularity=dict(wk.get("popularity", {})),
            )
        )
    return Board(
        season=int(raw.get("season", 2026)),
        weeks=weeks,
        used={int(k): v for k, v in raw.get("used", {}).items()},
        entries=int(raw.get("entries", 100)),
        notes=list(raw.get("notes", [])),
    )
