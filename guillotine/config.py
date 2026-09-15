"""Loading and validating the weekly league snapshot."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Which roster slots each position may fill.
SLOTS = ("QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX")
FLEX_POSITIONS = ("RB", "WR", "TE")

# Weekly standard deviation of a player's score, as a linear function of their
# projection: sd = slope * proj + floor.  Projections are a central estimate;
# the spread around them is what actually decides who finishes last.
POSITION_VARIANCE = {
    "QB": (0.30, 2.5),
    "RB": (0.55, 2.0),
    "WR": (0.60, 2.0),
    "TE": (0.62, 1.8),
    "K": (0.45, 2.0),
    "DST": (0.70, 2.0),
}


@dataclass
class Player:
    name: str
    pos: str
    proj: float
    team: str = ""
    rostered_pct: float = 0.0
    starter: bool = False
    note: str = ""

    @property
    def sd(self) -> float:
        slope, floor = POSITION_VARIANCE.get(self.pos, (0.60, 2.0))
        return slope * self.proj + floor

    @classmethod
    def from_dict(cls, d: dict) -> "Player":
        return cls(
            name=d["name"],
            pos=d["pos"].upper(),
            proj=float(d["proj"]),
            team=d.get("team", ""),
            rostered_pct=float(d.get("rostered_pct", 0.0)),
            starter=bool(d.get("starter", False)),
            note=d.get("note", ""),
        )


@dataclass
class Rival:
    name: str
    proj: float
    budget: float
    estimated: bool = False  # True when the projection was inferred, not read off the app

    @classmethod
    def from_dict(cls, d: dict, default_budget: float) -> "Rival":
        return cls(
            name=d["name"],
            proj=float(d["proj"]),
            budget=float(d.get("budget", default_budget)),
            estimated=bool(d.get("estimated", False)),
        )


@dataclass
class Settings:
    """Knobs for the survival model.  Every one of these is a modelling choice,
    so they live in the config file rather than being buried in the code."""

    # Season shape
    total_weeks: int = 17          # last week the league plays
    teams_at_start: int = 16

    # Noise the projections do not capture, in points, for a whole lineup.
    rival_proj_error_sd: float = 8.0   # rivals stream/start different players than projected
    rival_team_sd: float = 26.0        # week-to-week spread of a rival's actual score
    correlation: float = 0.10          # shared week-wide scoring environment

    # Rivals improve too.  Expected points a surviving rival adds per week via
    # their own waiver claims, and the spread of that improvement.
    rival_waiver_drift: float = 0.8
    rival_waiver_drift_sd: float = 2.5

    # Budget-to-equity curve.  Future survival equity is modelled as
    # V(B) = (B / B_reference) ** budget_alpha.  alpha < 1 means the first
    # dollars matter more than the last; alpha near 0 means budget barely
    # matters and you should spend freely.
    budget_alpha: float = 0.35
    min_reserve: float = 25.0      # never bid your budget to literally zero

    # Rival bidding market
    market_aggression: float = 0.55      # a must-have player costs ~55% of a budget
    market_dispersion: float = 0.55      # lognormal sigma of rival bids
    contenders_per_player: float = 0.55  # share of rivals who bid at all on a top target
    market_half_point: float = 12.0      # points over replacement that earn half the max bid
    replacement_level: dict = field(default_factory=lambda: {
        "QB": 13.0, "RB": 8.5, "WR": 8.5, "TE": 6.5, "K": 7.0, "DST": 6.0})

    simulations: int = 20000
    seed: int = 20260915

    @classmethod
    def from_dict(cls, d: dict) -> "Settings":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"unknown settings keys: {sorted(unknown)}")
        return cls(**d)


@dataclass
class League:
    week: int
    my_team: str
    my_budget: float
    default_budget: float
    roster: list[Player] = field(default_factory=list)
    rivals: list[Rival] = field(default_factory=list)
    waivers: list[Player] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)
    notes: list[str] = field(default_factory=list)

    @property
    def teams_left(self) -> int:
        return len(self.rivals) + 1

    @property
    def weeks_left(self) -> int:
        """Weeks still to be played, including this one."""
        return max(1, self.settings.total_weeks - self.week + 1)

    def validate(self) -> list[str]:
        """Return a list of human-readable warnings (never raises on soft problems)."""
        warn = []
        if self.teams_left < 2:
            raise ValueError("need at least 2 teams left to model a chop")
        starters = [p for p in self.roster if p.starter]
        if len(starters) and len(starters) != len(SLOTS):
            warn.append(
                f"{len(starters)} players flagged as starters but the lineup has "
                f"{len(SLOTS)} slots -- lineup will be re-optimised from the full roster"
            )
        bench = [p for p in self.roster if not p.starter]
        if not bench:
            warn.append(
                "no bench players in the config: drop candidates and bye-week cover "
                "cannot be evaluated, so adds are priced as if a roster spot is free"
            )
        est = [r.name for r in self.rivals if r.estimated]
        if est:
            warn.append(
                f"{len(est)} rival projection(s) are estimates, not read from the app: "
                + ", ".join(est)
            )
        expected = self.settings.teams_at_start - (self.week - 1)
        if self.teams_left != expected:
            warn.append(
                f"{self.teams_left} teams in config but a 16-team league in week "
                f"{self.week} should have {expected}; check for missing rivals"
            )
        return warn


def load(path: str | Path) -> League:
    raw = json.loads(Path(path).read_text())
    default_budget = float(raw.get("default_budget", 1000))
    lg = League(
        week=int(raw["week"]),
        my_team=raw["my_team"],
        my_budget=float(raw.get("my_budget", default_budget)),
        default_budget=default_budget,
        roster=[Player.from_dict(p) for p in raw.get("roster", [])],
        rivals=[Rival.from_dict(r, default_budget) for r in raw.get("rivals", [])],
        waivers=[Player.from_dict(p) for p in raw.get("waivers", [])],
        settings=Settings.from_dict(raw.get("settings", {})),
        notes=list(raw.get("notes", [])),
    )
    return lg
