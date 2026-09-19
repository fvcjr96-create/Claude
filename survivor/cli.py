"""python3 -m survivor data/survivor_2026.json"""

from __future__ import annotations

import argparse
import json
import sys

from . import ratings as ratings_mod
from .data import load
from .plan import (next_week_options, opponent_concentration, optimize,
                   optimize_capped, team_leverage)
from .simulate import DRIFT_PER_WEEK, simulate_static

BAR = "=" * 78
RULE = "-" * 78


def pct(x: float) -> str:
    return f"{x*100:.1f}%"


def render(board, plan, options, leverage, fitted, synthetic: bool, sim=None) -> str:
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
            cost = "" if surv >= best - 1e-12 else f"-{(1-surv/best)*100:.0f}%"
            a(f"  {team:<6}{matchup:<16}{pct(p):>7}{pct(surv):>9}{cost:>8}"
              f"  {pct(pop) if pop else '-'}")
        a("")
        a("  WIN%   this week's win probability")
        a("  SEASON P(surviving every remaining week) if you take this team now")
        a("  COST   how much of that season survival you give up versus the best")
        a("         choice, relative -- \"-20%\" means a fifth worse, not 20 points")
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

    conc = [(o, c) for o, c in opponent_concentration(plan) if c > 1]
    if conc:
        a(" OPPONENT CONCENTRATION")
        a(RULE)
        a("  " + ",  ".join(f"fade {o} x{c}" for o, c in conc[:6]))
        top = conc[0]
        if top[1] >= 4:
            a(f"  {top[1]} of {len(plan.picks)} picks bet against {top[0]}. That looks like")
            a("  concentration risk, and --simulate says it is not: survival is a")
            a("  PRODUCT, so errors that move together help it slightly rather than")
            a("  hurt. Capping it with --max-vs costs real survival. Measure before")
            a("  you diversify.")
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

    if sim is not None:
        a(" SIMULATION  " + f"({sim.sims:,} seasons, correlated rating error)")
        a(RULE)
        a(f"  Survive all {len(plan.picks)} weeks : {pct(sim.overall)}"
          f"  +/- {sim.se*100:.3f}")
        a(f"  Weeks survived      : {sim.mean_weeks_survived:.2f} mean,"
          f" median exit week {sim.median_exit}")
        a(f"  Analytic (no error) : {pct(plan.survival)}")
        gap = (1 - sim.overall / plan.survival) * 100 if plan.survival else 0
        a(f"  Cost of model error : {gap:+.0f}% relative")
        a("")
        a("  Rating error is drawn per TEAM and carried as a random walk, so a")
        a("  team the model has wrong is wrong in every game it plays, and more")
        a("  so the further past the last posted line.")
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
    ap.add_argument("--max-vs", type=int, default=None,
                    help="never fade the same opponent more than N times; "
                         "spreads the plan's risk across more teams")
    ap.add_argument("--simulate", type=int, nargs="?", const=100000, default=0,
                    metavar="N",
                    help="stress-test the plan with N simulated seasons "
                         "(default 100000) under correlated rating error")
    ap.add_argument("--drift", type=float, default=DRIFT_PER_WEEK,
                    help="assumed rating drift in points per week beyond the "
                         "last posted line; higher = less trust in late weeks")
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

    if args.max_vs:
        plan = optimize_capped(board, args.max_vs, contrarian=args.contrarian)
    else:
        plan = optimize(board, contrarian=args.contrarian)
    options = next_week_options(board, contrarian=args.contrarian)
    leverage = team_leverage(board, contrarian=args.contrarian) if len(board.future_weeks()) > 1 else []

    sim = None
    if args.simulate:
        sim = simulate_static(board, plan, sims=args.simulate, drift=args.drift)

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
            "simulation": None if sim is None else {
                "sims": sim.sims,
                "survive_all": round(sim.overall, 6),
                "standard_error": round(sim.se, 6),
                "mean_weeks_survived": round(sim.mean_weeks_survived, 3),
                "median_exit_week": sim.median_exit,
                "drift_per_week": args.drift,
            },
        }, indent=2))
    else:
        print(render(board, plan, options, leverage, fitted, synthetic, sim))
    return 0


if __name__ == "__main__":
    sys.exit(main())
