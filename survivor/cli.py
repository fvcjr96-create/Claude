"""python3 -m survivor data/survivor_2026.json"""

from __future__ import annotations

import argparse
import json
import sys

from . import ratings as ratings_mod
from .data import load
from .plan import next_week_options, optimize, team_leverage

BAR = "=" * 78
RULE = "-" * 78


def pct(x: float) -> str:
    return f"{x*100:.1f}%"


def render(board, plan, options, leverage, fitted, synthetic: bool) -> str:
    out: list[str] = []
    a = out.append

    a(BAR)
    a(f" NFL SURVIVOR PLAN - {board.season} SEASON")
    a(BAR)
    if synthetic:
        a(" *** SYNTHETIC BOARD - THIS IS NOT THE REAL SCHEDULE ***")
        a(" *** For shape and mechanics only. Never pick from it. ***")
        a("")

    if board.used:
        used = ", ".join(f"wk{w} {t}" for w, t in sorted(board.used.items()))
        a(f" Already used    : {used}")
    a(f" Weeks to plan   : {len(board.future_weeks())}"
      f"   |  teams burned: {len(board.used_teams)}")
    a(f" Verified through: week {board.verified_through() or '-'}")
    if fitted:
        a(f" Ratings fit     : {fitted.n_games} games with real lines, "
          f"ridge {fitted.ridge}, HFA {fitted.home_field} pts")
    a("")

    if options:
        wk = board.future_weeks()[0].number
        best = options[0][2]
        a(f" WEEK {wk} DECISION  (season survival if you pick this team)")
        a(RULE)
        a(f"  {'TEAM':<6}{'MATCHUP':<16}{'WIN%':>7}{'SEASON':>9}{'COST':>8}  POP")
        for team, p, surv, _pl in options:
            g = board.future_weeks()[0].game_for(team)
            matchup = f"{'vs' if g.is_home(team) else '@'} {g.opponent_of(team)}"
            pop = board.future_weeks()[0].popularity.get(team)
            cost = "" if surv >= best - 1e-12 else f"-{pct(best-surv)}"
            a(f"  {team:<6}{matchup:<16}{pct(p):>7}{pct(surv):>9}{cost:>8}"
              f"  {pct(pop) if pop else '-'}")
        a("")
        a("  WIN%   this week's win probability")
        a("  SEASON P(surviving every remaining week) if you take this team now")
        a("  COST   season survival given up versus the best available choice")
        a("")

    a(" FULL PLAN")
    a(RULE)
    a(f"  {'WK':<4}{'PICK':<6}{'MATCHUP':<16}{'WIN%':>7}{'RUNNING':>9}   SOURCE")
    for p, (_w, running) in zip(plan.picks, plan.survival_curve()):
        src = "market" if p.verified else "model"
        a(f"  {p.week:<4}{p.team:<6}{p.label.split(' ', 1)[1]:<16}"
          f"{pct(p.prob):>7}{pct(running):>9}   {src}")
    if plan.blocked_weeks:
        a(f"  !! no legal team available in weeks: {plan.blocked_weeks}")
    a(RULE)
    a(f"  Survive all {len(plan.picks)} remaining weeks: {pct(plan.survival)}")
    a("")

    if leverage:
        a(" HOARD LIST  (season survival lost if this team were unavailable)")
        a(RULE)
        for t, v in leverage[:8]:
            a(f"  {t:<6} -{pct(v)}")
        a("")
        a("  These teams carry the plan. Burning one early on a week you could")
        a("  have covered with someone else is the most common way to lose a pool.")
        a("")

    warns = board.warnings()
    if warns or board.notes:
        a(" DATA QUALITY")
        a(RULE)
        for w in warns:
            a(f"  ! {w}")
        for n in board.notes:
            a(f"  - {n}")
        a("")
    a(BAR)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Optimal NFL survivor pool plan")
    ap.add_argument("board", help="path to the season board JSON")
    ap.add_argument("--contrarian", type=float, default=0.0,
                    help="penalty on pick popularity; 0 = pure survival, "
                         "0.5-1.5 = differentiate in a big pool")
    ap.add_argument("--no-fill", action="store_true",
                    help="do not price unlined games from fitted ratings")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    board = load(args.board)
    raw = json.loads(open(args.board).read())
    synthetic = bool(raw.get("synthetic", False))

    fitted = None
    if not args.no_fill:
        fitted = ratings_mod.fit(board)
        ratings_mod.fill(board, fitted)

    plan = optimize(board, contrarian=args.contrarian)
    options = next_week_options(board, contrarian=args.contrarian)
    leverage = team_leverage(board, contrarian=args.contrarian) if len(board.future_weeks()) > 1 else []

    if args.json:
        print(json.dumps({
            "season": board.season,
            "used": board.used,
            "survival": round(plan.survival, 6),
            "synthetic": synthetic,
            "picks": [
                {"week": p.week, "team": p.team, "opponent": p.opponent,
                 "home": p.home, "win_prob": round(p.prob, 4),
                 "verified": p.verified}
                for p in plan.picks
            ],
            "next_week": [
                {"team": t, "win_prob": round(p, 4), "season_survival": round(s, 6)}
                for t, p, s, _ in options
            ],
            "hoard": [{"team": t, "leverage": round(v, 6)} for t, v in leverage[:10]],
            "warnings": board.warnings(),
        }, indent=2))
    else:
        print(render(board, plan, options, leverage, fitted, synthetic))
    return 0


if __name__ == "__main__":
    sys.exit(main())
