"""Command line front end:  python3 -m guillotine data/week02.json"""

from __future__ import annotations

import argparse
import json
import sys

from .config import load
from .engine import build_plan, effective_reserve, remaining_cycles, season_phase
from .market import edge_over_replacement
from .rollover import write_rollover

BAR = "=" * 78
RULE = "-" * 78


def money(x: float) -> str:
    return f"${x:,.0f}"


def render(plan) -> str:
    lg = plan.league
    out: list[str] = []
    a = out.append

    phase, phase_advice = season_phase(lg)
    a(BAR)
    a(f" GUILLOTINE WAIVER PLAN - WEEK {lg.week}")
    a(f" {lg.my_team}")
    a(BAR)
    a(f" Teams left      : {lg.teams_left} of {lg.settings.teams_at_start}"
      f"   ({lg.weeks_left} weeks still to play)")
    a(f" Your FAAB       : {money(lg.my_budget)}"
      f"   (reserve floor {money(effective_reserve(lg))},"
      f" {remaining_cycles(lg)} waiver cycles left after this one)")
    a(f" Phase           : {phase} - {phase_advice}")
    a("")
    a(f" Projected score : {plan.baseline_lineup.points:.2f}"
      f"   (rank {rank_of(plan):d} of {lg.teams_left})")
    a(f" Chop risk       : {plan.baseline_chop*100:5.2f}%  this week")
    a(f" Season equity   : {plan.baseline_equity:.4f}"
      f"   |  win the league {plan.baseline.p_win*100:.1f}%"
      f"   |  expected {plan.baseline.mean_weeks_survived:.1f} more weeks alive")
    a("")

    a(" CURRENT LINEUP")
    a(RULE)
    for slot, p in plan.baseline_lineup.by_slot():
        a(f"  {slot:<5} {p.name:<20} {p.team:<4} {p.proj:6.2f}  +/- {p.sd:4.1f}")
    a(f"  {'TOTAL':<5} {'':<20} {'':<4} {plan.baseline_lineup.points:6.2f}")
    a("")

    a(" WAIVER TARGETS  (ranked by expected equity gain)")
    a(RULE)
    hdr = (f"  {'PLAYER':<19}{'POS':<5}{'+PTS':>6}{'CHOP':>7}{'MAX':>7}"
           f"{'BID':>7}{'WIN%':>6}{'50/50':>7}")
    a(hdr)
    for c in plan.candidates:
        a(f"  {c.player.name:<19}{c.player.pos:<5}{c.lineup_delta:>6.2f}"
          f"{c.p_chop_with*100:>6.2f}%{money(c.max_bid):>7}"
          f"{money(c.recommended_bid):>7}{c.p_win_at_recommended*100:>5.0f}%"
          f"{money(c.price_50):>7}")
    a("")
    a("  +PTS  points the add puts in your STARTING lineup (bench stashes score 0)")
    a("  CHOP  your chop risk this week if you land him")
    a("  MAX   most he can be worth to you before the lost budget outweighs him")
    a("  BID   the bid that maximises equity once you price in losing the auction")
    a("  50/50 what the model thinks wins him half the time")
    a("")

    a(" THE CALL")
    a(RULE)
    for i, c in enumerate(plan.candidates, 1):
        tag = "PRIMARY" if i == 1 and c.recommended_bid >= 1 else f"#{i}"
        a(f"  [{tag}] {c.player.name} ({c.player.pos}, {c.player.team})"
          f" - {c.verdict}")
        if c.recommended_bid >= 1:
            detail = (f"     bid {money(c.recommended_bid)}"
                      f" ({c.recommended_bid/lg.my_budget*100:.0f}% of budget),"
                      f" wins ~{c.p_win_at_recommended*100:.0f}% of the time;"
                      f" ceiling {money(c.max_bid)}")
            a(detail)
            if c.displaced:
                a(f"     starts over {c.displaced.name}"
                  f" (+{c.lineup_delta:.2f} pts/wk, "
                  f"{edge_over_replacement(c.player, lg.settings):.1f} over replacement)")
            if c.drop:
                a(f"     drop: {c.drop.name}")
        else:
            a(f"     no bid - {c.lineup_delta:+.2f} pts to your lineup")
    a("")

    if plan.primary:
        p = plan.primary
        spent = p.recommended_bid
        a(" CONTINGENCY")
        a(RULE)
        a(f"  Lead with {money(spent)} on {p.player.name}. Blind bids cost nothing when")
        a("  they lose, so stack fallbacks underneath at their own recommended prices -")
        a("  those numbers already assume the lead claim failed.")
        fallbacks = [c for c in plan.candidates[1:] if c.recommended_bid >= 1]
        if fallbacks:
            worst = spent + sum(c.recommended_bid for c in fallbacks)
            a(f"  Fallbacks: " + ", ".join(
                f"{c.player.name} {money(c.recommended_bid)}" for c in fallbacks))
            a(f"  If EVERY claim somehow lands you spend {money(worst)}"
              f" - cap total exposure at {money(max(0, lg.my_budget - effective_reserve(lg)))}")
            a("  by ordering the claims and letting the platform stop at your budget.")
        a("")

    if plan.warnings:
        a(" CHECK THESE INPUTS")
        a(RULE)
        for w in plan.warnings:
            a(f"  ! {w}")
        for n in lg.notes:
            a(f"  - {n}")
        a("")
    a(BAR)
    return "\n".join(out)


def rank_of(plan) -> int:
    mine = plan.baseline_lineup.points
    return 1 + sum(1 for r in plan.league.rivals if r.proj > mine)


def as_json(plan) -> str:
    return json.dumps(
        {
            "week": plan.league.week,
            "team": plan.league.my_team,
            "budget": plan.league.my_budget,
            "teams_left": plan.league.teams_left,
            "phase": season_phase(plan.league)[0],
            "projected_points": round(plan.baseline_lineup.points, 2),
            "chop_risk": round(plan.baseline_chop, 4),
            "season_equity": round(plan.baseline_equity, 4),
            "p_win_league": round(plan.baseline.p_win, 4),
            "targets": [
                {
                    "player": c.player.name,
                    "pos": c.player.pos,
                    "lineup_delta": round(c.lineup_delta, 2),
                    "chop_risk_with": round(c.p_chop_with, 4),
                    "max_bid": round(c.max_bid),
                    "recommended_bid": round(c.recommended_bid),
                    "p_win_auction": round(c.p_win_at_recommended, 3),
                    "price_50": round(c.price_50),
                    "price_75": round(c.price_75),
                    "verdict": c.verdict,
                    "drop": c.drop.name if c.drop else None,
                }
                for c in plan.candidates
            ],
            "warnings": plan.warnings,
        },
        indent=2,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Optimal FAAB bids for a guillotine league")
    ap.add_argument("config", help="path to the weekly league snapshot JSON")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--budget", type=float, help="override your FAAB budget")
    ap.add_argument("--sims", type=int, help="override Monte-Carlo simulation count")
    ap.add_argument("--rollover", metavar="PATH",
                    help="write a skeleton snapshot for next week and exit")
    ap.add_argument("--chopped", metavar="TEAM",
                    help="with --rollover, the rival to remove from next week")
    args = ap.parse_args(argv)

    lg = load(args.config)
    if args.budget is not None:
        lg.my_budget = args.budget
    if args.sims:
        lg.settings.simulations = args.sims

    if args.rollover:
        out = write_rollover(lg, args.rollover, args.chopped)
        print(f"wrote {out} - fill in this week's projections, budgets and waiver pool")
        return 0

    plan = build_plan(lg)
    print(as_json(plan) if args.json else render(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
