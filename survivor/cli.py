"""python3 -m survivor data/survivor_2026.json"""

from __future__ import annotations

import argparse
import json
import sys

from . import cost as cost_mod
from .data import load
from .pipeline import build_ratings
from .plan import (next_week_options, opponent_concentration, optimize,
                   optimize_capped, team_leverage)
from .multi import build_pair, simulate_pair, sweep as pair_sweep
from .simulate import DRIFT_PER_WEEK, simulate_static

BAR = "=" * 78
RULE = "-" * 78


def pct(x: float) -> str:
    return f"{x*100:.1f}%"


def render(board, plan, options, leverage, fitted, synthetic: bool, sim=None,
           rating_notes=(), costs=None) -> str:
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
    for n in rating_notes:
        a(f" Ratings         : {n}" if n is rating_notes[0] else f"                   {n}")
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
            rel = 0.0 if surv >= best - 1e-12 else (1 - surv / best)
            cost = "" if rel <= 0 else (f"-{rel*100:.2f}%" if rel < 0.01
                                        else f"-{rel*100:.0f}%")
            a(f"  {team:<6}{matchup:<16}{pct(p):>7}{pct(surv):>9}{cost:>8}"
              f"  {pct(pop) if pop else '-'}")
        a("")
        # Among the options that cost essentially nothing, the one with the
        # highest win probability is strictly the better bet: same season, safer
        # week.  The product-maximising optimum is indifferent between them; you
        # are not, because you care about getting deep, not only about the
        # perfect-season branch.
        nearly_free = [o for o in options if o[2] >= best * 0.99]
        if len(nearly_free) > 1:
            safest = max(nearly_free, key=lambda o: o[1])
            if safest[0] != options[0][0]:
                a(f"  >> {safest[0]} costs only "
                  f"{(1-safest[2]/best)*100:.2f}% of season survival but wins "
                  f"{(safest[1]-options[0][1])*100:.1f} points more often this week.")
                a(f"     Take {safest[0]}: same season, safer week.")
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

    if costs is not None:
        wk = board.future_weeks()[0].number
        a(f" OPPORTUNITY COST  (what spending a team in week {wk} really costs)")
        a(RULE)
        a(f"  {'TEAM':<6}{'BEST WK':>8}{'IF USED NOW':>13}{'AT BEST WK':>12}{'COST':>7}   VERDICT")
        for tc in costs.cheapest_now(14):
            ec = tc.earliness_cost or 0.0
            if ec < 0.02 and tc.best_week == tc.this_week:
                verdict = "FREE - this IS its peak week"
            elif ec < 0.02:
                verdict = f"FREE - schedule covers its wk {tc.best_week} slot"
            elif ec < 0.10:
                verdict = "cheap"
            elif ec < 0.20:
                verdict = f"pricey - peaks wk {tc.best_week}"
            else:
                verdict = f"HOARD - save for wk {tc.best_week}"
            a(f"  {tc.team:<6}{tc.best_week:>8}{tc.this_survival*100:>12.3f}%"
              f"{tc.best_survival*100:>11.3f}%{ec*100:>6.0f}%   {verdict}")
        a("")
        a("  IF USED NOW  season survival with this team pinned to this week")
        a("  AT BEST WK   season survival with it pinned to its best week instead")
        a("  COST         the gap, relative. This is the opportunity cost of")
        a("               spending the team early, and it is measured by re-solving")
        a("               the whole season both ways, not estimated.")
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


def render_pair(board, args) -> str:
    """Side-by-side plans for two entries in two different leagues."""
    out: list[str] = []
    a = out.append
    a(BAR)
    a(f" TWO-ENTRY SURVIVOR PLAN - {board.season}")
    a(BAR)
    a(" Objective: P(AT LEAST ONE entry survives), not P(this entry survives).")
    a(" Picks the two entries share are a single point of failure - they live")
    a(" and die together - so shared weeks buy no diversification at all.")
    a("")

    if args.pair_sweep:
        weeks = [w.number for w in board.future_weeks()][:8]
        a(" WHERE TO DIVERGE")
        a(RULE)
        a(f"  {'FROM WK':>8}{'SHARED':>8}{'P(>=1)':>10}{'ENTRY A':>10}{'ENTRY B':>10}{'LIFT':>8}")
        for r in pair_sweep(board, weeks, sims=30000, contrarian=args.contrarian):
            a(f"  {r.diverge_week:>8}{r.shared_weeks:>8}{r.p_at_least_one*100:>9.3f}%"
              f"{r.p_a*100:>9.3f}%{r.p_b*100:>9.3f}%{r.lift*100:>7.0f}%")
        a("")

    entry_a, entry_b = build_pair(board, args.pair, contrarian=args.contrarian)
    res = simulate_pair(board, entry_a, entry_b, sims=60000, drift=args.drift)

    a(f" THE TWO PLANS  (diverging from week {args.pair})")
    a(RULE)
    a(f"  {'WK':<4}{'LEAGUE A':<24}{'LEAGUE B':<24}")
    for x, y in zip(entry_a.plan.picks, entry_b.plan.picks):
        ax = f"{x.team} {'vs' if x.home else '@'} {x.opponent} {x.prob*100:.0f}%"
        bx = f"{y.team} {'vs' if y.home else '@'} {y.opponent} {y.prob*100:.0f}%"
        same = "  <- SAME PICK" if x.team == y.team else ""
        a(f"  {x.week:<4}{ax:<24}{bx:<24}{same}")
    a(RULE)
    a(f"  Entry A alone        : {pct(res.p_a)}")
    a(f"  Entry B alone        : {pct(res.p_b)}")
    a(f"  AT LEAST ONE survives: {pct(res.p_at_least_one)}  +/- {res.se*100:.3f}")
    a(f"  Both survive         : {pct(res.p_both)}")
    a(f"  Second entry adds    : +{res.lift*100:.0f}% over running one plan twice")
    a("")
    ea = res.either_alive or {}
    a(" P(AT LEAST ONE STILL ALIVE)")
    a(RULE)
    a("  " + "   ".join(f"wk{w} {ea.get(w, 0)*100:.1f}%" for w in (5, 8, 10, 12) if w in ea))
    a("")
    a("  Most pools end long before week 18, so this matters more than the")
    a("  perfect-season number. Diverging early wins at every one of these")
    a("  horizons, not just at the end.")
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
    ap.add_argument("--discount", type=float, default=1.0,
                    help="below 1.0 front-loads certainty (e.g. 0.97) for pools "
                         "that pay for lasting longest rather than going undefeated")
    ap.add_argument("--pair", type=int, nargs="?", const=2, default=0,
                    metavar="WEEK",
                    help="plan TWO entries in two leagues, diverging from WEEK "
                         "(default 2); maximises P(at least one survives)")
    ap.add_argument("--pair-sweep", action="store_true",
                    help="with --pair, compare every divergence week")
    ap.add_argument("--costs", action="store_true",
                    help="show the opportunity cost of spending each team now")
    ap.add_argument("--prior", default=None,
                    help="rating prior JSON (default data/prior_<season>.json)")
    ap.add_argument("--win-totals", default=None,
                    help="win totals JSON (default data/win_totals_<season>.json)")
    ap.add_argument("--no-fill", action="store_true",
                    help="do not price unlined games from fitted ratings")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    board = load(args.board)
    raw = json.loads(open(args.board).read())
    synthetic = bool(raw.get("synthetic", False))

    fitted, rating_notes = None, []
    if not args.no_fill:
        prior = args.prior or f"data/prior_{board.season}.json"
        totals = args.win_totals or f"data/win_totals_{board.season}.json"
        fitted, rating_notes = build_ratings(board, prior, totals)

    if args.max_vs:
        plan = optimize_capped(board, args.max_vs, contrarian=args.contrarian)
    else:
        plan = optimize(board, contrarian=args.contrarian,
                        discount=args.discount)
    options = next_week_options(board, contrarian=args.contrarian)
    leverage = team_leverage(board, contrarian=args.contrarian) if len(board.future_weeks()) > 1 else []

    if args.pair:
        print(render_pair(board, args))
        return 0

    costs = cost_mod.build(board, contrarian=args.contrarian) if args.costs else None

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
            "rating_notes": rating_notes,
            "opportunity_cost": None if costs is None else [
                {"team": t.team, "best_week": t.best_week,
                 "best_survival": round(t.best_survival, 6),
                 "if_used_now": None if t.this_survival is None else round(t.this_survival, 6),
                 "cost_relative": None if t.earliness_cost is None else round(t.earliness_cost, 4)}
                for t in costs.teams
            ],
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
        print(render(board, plan, options, leverage, fitted, synthetic, sim,
                     rating_notes, costs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
