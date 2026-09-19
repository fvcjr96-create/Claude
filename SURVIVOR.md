# NFL Survivor Plan — 2026

Week 1: **Steelers — won** (ATL 13 @ PIT 20). 31 teams left, 17 weeks to cover.

Full 2026 schedule loaded: all 272 games, weeks 1–3 priced from live markets.

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

Real board, de-vigged from two-way moneylines:

| Team | Matchup | Win% | Season survival | Cost |
|---|---|---|---|---|
| **SF** | vs MIA | **86.3%** | 1.2% | — |
| **TB** | vs CLE | 78.7% | 1.2% | **−2%** |
| PHI | @ TEN | 73.4% | 1.1% | −9% |
| LAC | vs LV | 72.6% | 1.1% | −10% |
| BAL | vs NO | 76.6% | 1.0% | **−18%** |
| KC | vs IND | 71.0% | 1.0% | −18% |

**Take San Francisco.** 86.3% is the biggest edge on the board and, unusually,
it costs nothing — SF is not load-bearing anywhere later.

**Tampa Bay is the near-free alternative.** 7.6 points less win probability for
only 2% of season survival, because Week 2 is TB's schedule peak. If your pool
is large and SF is heavily picked, TB is the differentiator that barely costs
anything.

**Do not use Baltimore.** At 76.6% they look like the third-best pick and they
are the fifth-best *decision*: −18%, worse than teams with lower win
probability. BAL has premium spots later and sits on the hoard list. This is
the model independently reproducing what the survivor writeups said — that the
Ravens are expensive to spend now — and it is exactly the trap a
highest-win-probability heuristic walks into.

Buffalo already played (beat Detroit by 10 on Thursday) and is off the board.

## 5. Weekly process

```bash
# 1. refresh the board (one request, whole season)
python3 scripts/fetch_grid.py --season 2026 --out data/survivor_2026.json

# 2. record last week's pick in data/survivor_2026.json
#    "used": {"1": "PIT", "2": "SF"}

# 3. plan
python3 -m survivor data/survivor_2026.json --max-vs 3

# big pool? price in the chalk
python3 -m survivor data/survivor_2026.json --max-vs 3 --contrarian 1.0
```

Read the output in this order: the `COST` column (is the obvious pick actually
cheap?), then the hoard list (am I about to burn something load-bearing?), then
the full plan (does the back half still work?).

---

## 6. The data

**The full schedule is in.** All 272 games of the 2026 regular season, from the
[nflverse](https://github.com/nflverse/nfldata) `games.csv` dataset. It passes
structural validation in the test suite: every team plays exactly 17 games, no
team is double-booked in a week, and the Week 1 result (ATL 13 @ PIT 20) matches
your winning Steelers pick.

**Pricing, best source first:**

1. **De-vigged two-way moneylines** — weeks 1–3, where books have posted. This
   is the market's own estimate with the overround removed.
2. **Fitted power ratings** — weeks 4–18, where no market exists yet. Ridge
   regression on every posted line. These picks are flagged `model`, not
   `market`, in the report.

**The ridge penalty is validated, not guessed.** Fitting on weeks 1–2 and
predicting week 3's actual lines:

| ridge | out-of-sample MAE | league spread |
|---|---|---|
| 0.01 | 2.54 pts | 16.0 |
| **0.25** | **1.84 pts** | 12.6 |
| 1.0 | 2.30 pts | 8.5 |
| 5.0 | 3.41 pts | 4.0 |

Home-field-only baseline: 4.23 pts. So the ratings predict next week's market
line to within about 1.8 points. `scripts/tune_ridge.py` re-runs this as the
season adds weeks, and two tests fail if the default stops beating both the
baseline and the neighbouring settings.

Modelled games carry that residual uncertainty explicitly: their margin
distribution is widened by the fit's RMSE in quadrature, so a modelled 80% is
correctly reported a little closer to 50% than a market 80%.

### Concentration risk — read this before trusting the back half

Left alone, the optimiser produced a plan that **faded Miami in 9 of 17 weeks**.
That is mathematically optimal and strategically fragile: it is one view of one
team, not nine independent edges. If the ratings are wrong about Miami, several
weeks fail together.

`--max-vs 3` caps how often you may fade the same opponent. It costs very little
(season survival 1.2% → 0.9%) and spreads the risk across four opponents instead
of concentrating it in one. **Use it.** The report warns whenever any opponent
appears four or more times.

### What is still soft

Weeks 4–18 are model estimates, and a model built on three weeks of lines cannot
know about November injuries. Treat the back half as a *map of where the value
probably is*, not a commitment. Re-run weekly: as books post lines, weeks flip
from `model` to `market` and the plan firms up from the front.

Popularity is not in the dataset — add a per-week `popularity` map from your own
pool to use `--contrarian`.

Your pool is described as 17 games; this board covers 18 weeks. Delete week 18
from the JSON if your pool ends at 17.

## Sources

- [ESPN — Week 2 odds, lines and totals](https://www.espn.com/espn/betting/story/_/id/49940340/2026-nfl-week-2-schedule-odds-betting-point-spreads-totals)
- [ESPN — survivor power rankings, Week 2](https://www.espn.com/fantasy/football/story/_/id/49961884/espn-nfl-survivor-week-2-survivor-pool-strategy-advice-picks-predictions)
- [FantasyLabs — Week 2 survivor picks, EV and future value](https://www.fantasylabs.com/articles/nfl-survivor-week-2-picks-2026-best-picks-ev-and-future-value/)
- [RotoWire — Week 2 grid, odds and strategy](https://www.rotowire.com/football/article/nfl-survivor-pool-picks-2026-grid-odds-strategy-126290)
- [FTN — why similar odds can mean different value](https://ftnfantasy.com/nfl-survivor-week-2-picks-2026-why-similar-odds-can-mean-very-different-value)
- [FOX Sports — Week 2 lines and spreads](https://www.foxsports.com/stories/nfl/2026-nfl-odds-week-2-lines-spreads-results-all-16-games)
- [Covers — Week 2 opening lines](https://www.covers.com/nfl/week-2-odds-opening-lines-2026)
