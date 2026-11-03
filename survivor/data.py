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
    picks_required: int = 1   # some pools demand two winners in a single week

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
    # week -> the team(s) already spent that week.  A list, because a double
    # week spends two, and a team spent in ANY week can never come back.
    used: dict[int, list[str]] = field(default_factory=dict)
    used_b: dict[int, list[str]] = field(default_factory=dict)
    entries: int = 100
    notes: list[str] = field(default_factory=list)
    # Manual overrides for news the stored price may not carry yet.  Each is
    # {week, team, win_prob, reason}.  Kept as data, with a reason attached,
    # so an override is visible in the report rather than silently baked in.
    adjustments: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        # A bare string is iterable, so {1: "PIT"} would quietly become the
        # letters P, I, T.  Normalise instead of leaving that trap open.
        self.used = {w: [t] if isinstance(t, str) else list(t)
                     for w, t in self.used.items()}
        self.used_b = {w: [t] if isinstance(t, str) else list(t)
                       for w, t in self.used_b.items()}

    @property
    def used_teams(self) -> set[str]:
        return {t for teams in self.used.values() for t in teams}

    @property
    def used_teams_b(self) -> set[str]:
        return {t for teams in self.used_b.values() for t in teams}

    def for_entry_b(self) -> "Board":
        """A view of this board from league B's point of view."""
        return Board(season=self.season, weeks=self.weeks, used=dict(self.used_b),
                     used_b={}, entries=self.entries, notes=self.notes)

    def future_weeks(self) -> list[Week]:
        start = max(self.used) if self.used else 0
        return [w for w in self.weeks if w.number > start]

    def verified_through(self) -> int:
        v = [w.number for w in self.weeks if w.verified]
        return max(v) if v else 0

    def picks_needed(self) -> int:
        return sum(w.picks_required for w in self.future_weeks())

    def teams_available(self) -> set[str]:
        return {t for w in self.future_weeks() for t in w.teams_playing()} - self.used_teams

    def warnings(self) -> list[str]:
        out = []
        need, have = self.picks_needed(), len(self.teams_available())
        if need > have:
            out.append(f"IMPOSSIBLE: {need} picks required but only {have} teams left")
        elif need > have - 8:
            out.append(f"{need} picks required from {have} teams - only {have - need} spare, "
                       "so almost every team is load-bearing")
        for w in self.future_weeks():
            avail = len(w.teams_playing() - self.used_teams)
            if avail < w.picks_required:
                out.append(f"week {w.number} needs {w.picks_required} picks but only "
                           f"{avail} available teams play")
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


def _used(raw: dict) -> dict[int, list[str]]:
    """Accept either "PIT" or ["PIT", "NYG"] for a week."""
    return {int(k): ([v] if isinstance(v, str) else list(v)) for k, v in raw.items()}


def load(path: str | Path) -> Board:
    raw = json.loads(Path(path).read_text())
    doubles = set(raw.get("double_weeks", []))
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
                picks_required=int(wk.get("picks", 2 if n in doubles else 1)),
            )
        )
    return Board(
        season=int(raw.get("season", 2026)),
        weeks=weeks,
        used=_used(raw.get("used", {})),
        used_b=_used(raw.get("used_b", {})),
        entries=int(raw.get("entries", 100)),
        notes=list(raw.get("notes", [])),
        adjustments=list(raw.get("adjustments", [])),
    )
