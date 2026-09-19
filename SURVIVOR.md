# NFL Survivor Plan — 2026

Week 1: **Steelers — won.** 31 teams left, 17 weeks of board to cover.

---

## 1. Why a weekly pick is the wrong unit

Survivor looks like 17 independent decisions. It is one decision with 17 parts,
because using a team spends it forever. The safest team this week is often the
wrong pick — not because it might lose, but because a later week has nothing
else to cover it with.

This is a **maximum-weight bipartite matching**: weeks on one side, teams on the
other, maximising the product of win probabilities. `survivor/assign.py` solves
it exactly with the Hungarian algorithm, verified against brute force.

You can watch the logic bite in the demo board:

```
  TEAM  MATCHUP            WIN%   SEASON    COST
  MIA   @ IND             74.8%    15.1%
  LAR   @ SEA             97.5%    14.0%   -1.1%
```

LAR is a 97.5% lock and it is still the wrong pick — spending them here costs
more later than the 22 points of win probability gains now. **No greedy
strategy finds that.** Picking the weekly favourite every time is the single
most common way pools are lost, and it is the one thing this planner fixes.

---

## 2. The three quantities that decide every pick

**Win probability** — what the market says. Converted from the closing spread
with a normal model, `p = Φ(spread / 13.0)`. That σ is calibrated against this
week's real board: SF −13.5 prices at 85%, BAL −8.5 at 74%, LAC −6.5 at 69%,
all of which the model reproduces.

**Future cost** — how much season survival you give up by spending the team
now. This is the `COST` column, and it is computed by re-optimising the entire
remaining season around each candidate. A team whose best matchup is *this*
week costs nothing to use. A team with three soft spots in December is expensive.

**Popularity** — how much of your pool is on the same team. Irrelevant to
survival, decisive to *winning*. Surviving alongside 60% of the field is worth
far less than surviving alongside 5%. `--contrarian` prices this in.

The first two are in the tool. The third needs your pool's numbers.

---

## 3. Season framework

| Phase | Weeks | Posture |
|---|---|---|
| **Bank the easy ones** | 2–5 | Spend teams whose schedule peaks *now*. Lines are sharp, byes haven't started, the board is at its widest. |
| **Bye-week squeeze** | 6–14 | Six teams vanish from the board each week. This is where hoarded teams get used and where thin plans break. |
| **Rest-risk zone** | 15–18 | Playoff-clinched teams bench starters. Market lines lag this. Apply a haircut to any locked-in favourite in weeks 17–18. |

### Standing rules

1. **Never pick on win probability alone.** Always read the `COST` column.
2. **Spend teams at their schedule peak.** A team whose best remaining matchup
   is this week is free to use — that is the cheapest survival you will ever buy.
3. **Hoard the leverage list.** The planner prints the teams whose absence hurts
   the plan most. Those are load-bearing; do not burn them on a week you could
   cover another way.
4. **Re-optimise every week.** Lines move, teams get hurt, your plan changes.
   The plan past next week is a map, not a commitment.
5. **Discount weeks 17–18 favourites.** Resting starters is not in the line.
6. **Take the sure thing when the field is thin.** Late in a small pool,
   survival beats differentiation. Early in a big pool, the reverse.

---

## 4. The Week 2 call

Verified board, from real posted lines:

| Team | Matchup | Win% | Popularity |
|---|---|---|---|
| **SF** | vs MIA (−13.5) | **85.0%** | ~31% |
| BAL | vs NO (−8.5) | 74.3% | ~9% |
| TB | vs CLE | 74.0% | ~30% |
| LAR | vs NYG (−7.5) | 71.8% | — |
| PHI | @ TEN (−7) | 70.5% | — |
| KC | vs IND (−6.5) | 69.1% | — |
| LAC | vs LV (−6.5) | 69.1% | — |

**Small pool (under ~50 entries): take San Francisco.** 85% is the largest edge
on the board by a distance — a 13.5-point line is the biggest of the young
season — and in a small pool raw survival is what matters.

**Large pool: Baltimore is the better play.** At ~9% popularity versus SF's
~31%, the weeks where SF loses are the weeks you gain enormous ground. The
survivor writeups price BAL's EV above TB's for exactly this reason.

**On Tampa Bay:** reporting notes Week 2 is TB's single best matchup of the
entire season, so using them here costs zero future value. That makes TB a
legitimate third option — but at ~30% popularity you get the cost saving
without the differentiation.

⚠️ **One caveat I can't resolve from here.** Four Week 2 games are missing from
my board — ARI, ATL, CAR, CHI, DAL, MIN, SEA and WAS are unaccounted for. If
one of those is a double-digit favourite it belongs in this table. Run the
fetch script before you lock the pick.

---

## 5. Weekly process

```bash
# 1. refresh the board (run on your machine - needs internet)
python3 scripts/fetch_grid.py --season 2026 --out data/survivor_2026.json

# 2. record last week's pick in data/survivor_2026.json
#    "used": {"1": "PIT", "2": "SF"}

# 3. plan
python3 -m survivor data/survivor_2026.json

# big pool? price in the chalk
python3 -m survivor data/survivor_2026.json --contrarian 1.0
```

Read the output in this order: the `COST` column (is the obvious pick actually
cheap?), then the hoard list (am I about to burn something load-bearing?), then
the full plan (does the back half still work?).

---

## 6. Status of the data — read this

I could not reach the schedule sources from this environment; the egress proxy
blocks ESPN, NFL.com, Pro-Football-Reference and survivorgrid. So:

- **Week 2 is real.** Nine posted spreads plus one quoted win probability,
  sourced below, and the model is calibrated against them.
- **Weeks 3–18 are not on the board at all.** I did not fabricate them. A
  made-up schedule would produce confident, wrong picks and cost you the pool.
- `scripts/fetch_grid.py` closes the gap in one command from your machine. It
  pulls all 18 weeks from ESPN's public API, attaches every posted line, and
  preserves your `used` picks across re-runs.
- Games with no posted line are priced from power ratings fitted by ridge
  regression to every line that *does* exist, and stay flagged `model` rather
  than `market` in the output.
- `data/demo_synthetic.json` is a randomly generated board for seeing the
  mechanics. The CLI prints a warning banner on it. Never pick from it.

Your pool is described as 17 games; the planner covers whatever weeks are on the
board, so drop week 18 from the JSON if your pool ends at 17.

## Sources

- [ESPN — Week 2 odds, lines and totals](https://www.espn.com/espn/betting/story/_/id/49940340/2026-nfl-week-2-schedule-odds-betting-point-spreads-totals)
- [ESPN — survivor power rankings, Week 2](https://www.espn.com/fantasy/football/story/_/id/49961884/espn-nfl-survivor-week-2-survivor-pool-strategy-advice-picks-predictions)
- [FantasyLabs — Week 2 survivor picks, EV and future value](https://www.fantasylabs.com/articles/nfl-survivor-week-2-picks-2026-best-picks-ev-and-future-value/)
- [RotoWire — Week 2 grid, odds and strategy](https://www.rotowire.com/football/article/nfl-survivor-pool-picks-2026-grid-odds-strategy-126290)
- [FTN — why similar odds can mean different value](https://ftnfantasy.com/nfl-survivor-week-2-picks-2026-why-similar-odds-can-mean-very-different-value)
- [FOX Sports — Week 2 lines and spreads](https://www.foxsports.com/stories/nfl/2026-nfl-odds-week-2-lines-spreads-results-all-16-games)
- [Covers — Week 2 opening lines](https://www.covers.com/nfl/week-2-odds-opening-lines-2026)
