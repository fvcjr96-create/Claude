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

## 4b. Running two entries in two leagues

With one entry you maximise P(survive). With two, in two different pools, you
maximise **P(at least one survives)** — a different objective with a different
answer.

**Shared picks are worth nothing.** Two entries on the same team live and die
together, so a shared prefix is a single point of failure you are paying for
twice. The instinct to "start safe together, diverge later" is backwards, and
measurably so:

| diverge from | shared picks | alive wk5 | wk8 | wk10 | wk12 | 17-0 |
|---|---|---|---|---|---|---|
| **week 2** | 0 | **61.2%** | **29.6%** | **17.7%** | **11.1%** | **2.35%** |
| week 4 | 2 | 51.2% | 27.6% | 16.7% | 10.4% | 2.19% |
| week 6 | 4 | 35.5% | 24.6% | 16.0% | 10.3% | 2.18% |
| week 8 | 6 | 35.8% | 20.0% | 14.0% | 9.7% | 2.10% |
| never | 17 | 35.7% | 16.5% | 9.5% | 5.7% | 1.53% |

Diverging in week 2 wins at **every** horizon, not just at the end. It nearly
doubles your equity at week 10 versus running the same plan twice.

**The constraint that matters is same team, same week.** Entry A taking Kansas
City in week 3 and entry B taking Kansas City in week 9 are two different games
with independent outcomes — there is no reason to forbid it. Banning a team
outright from the second entry leaves it with the dregs (it fell to 0.12%,
versus 0.85% when only same-week clashes are blocked), and a weak second entry
is worth very little.

**Week 2 happens to make this free.** The opportunity-cost table found *two*
teams at zero cost, so both entries can start at their optimum:

| Wk | League A | League B |
|---|---|---|
| 2 | **SF** vs MIA 86% | **TB** vs CLE 79% |
| 3 | KC @ MIA 79% | SF vs ARI 79% |
| 4 | CHI vs NYJ 77% | BAL vs TEN 84% |
| 5 | NE vs LV 75% | CIN @ MIA 74% |
| 6 | PHI vs CAR 72% | LAR vs ARI 84% |
| 7 | LAR @ LV 76% | DEN @ ARI 70% |
| 8 | CIN vs TEN 79% | DAL vs ARI 75% |
| 9 | SEA vs ARI 77% | KC vs NYJ 80% |
| 10 | IND vs MIA 75% | HOU @ CLE 73% |
| 11 | DAL vs TEN 78% | BUF vs MIA 87% |
| 12 | JAX vs TEN 78% | MIN vs ATL 72% |
| 13 | DEN vs MIA 83% | PHI @ ARI 70% |
| 14 | DET vs TEN 78% | CHI @ MIA 74% |
| 15 | GB vs MIA 78% | NYG vs CLE 70% |
| 16 | BAL vs CLE 85% | LAC @ MIA 72% |
| 17 | BUF @ MIA 81% | JAX vs WAS 65% |
| 18 | HOU vs TEN 80% | NE vs MIA 81% |

Zero shared picks. A alone 1.66%, B alone 0.84%, **at least one 2.39%** — the
second entry adds ~50%.

Note the teams recur across the two columns in different weeks (SF, KC, LAR,
BAL, CHI, JAX, NE all appear twice). That is deliberate and costs nothing.

**What this does not model:** your two pools have different fields, and being
different from *the field* is a separate axis from being different from your
own other entry. If one pool is large and chalky, run `--contrarian` on that
entry — the divergence logic still holds, it just starts from a different plan.

```bash
python3 -m survivor data/survivor_2026.json --pair          # two leagues
python3 -m survivor data/survivor_2026.json --pair 5        # share through wk4
python3 -m survivor data/survivor_2026.json --pair --pair-sweep
```

---

## 5. The 17-week plan

Steelers banked in week 1. These are the other 17.

| Wk | Pick | Matchup | Win% | Running |
|---|---|---|---|---|
| 2 | **SF** | vs MIA | 86.3% | 86.3% |
| 3 | **KC** | @ MIA | 78.7% | 67.9% |
| 4 | **CHI** | vs NYJ | 77.1% | 52.3% |
| 5 | **NE** | vs LV | 75.1% | 39.3% |
| 6 | **PHI** | vs CAR | 71.9% | 28.3% |
| 7 | **LAR** | @ LV | 75.7% | 21.4% |
| 8 | **CIN** | vs TEN | 79.2% | 16.9% |
| 9 | **SEA** | vs ARI | 77.2% | 13.1% |
| 10 | **IND** | vs MIA | 74.7% | 9.8% |
| 11 | **DAL** | vs TEN | 77.8% | 7.6% |
| 12 | **JAX** | vs TEN | 78.1% | 5.9% |
| 13 | **DEN** | vs MIA | 83.5% | 5.0% |
| 14 | **DET** | vs TEN | 78.5% | 3.9% |
| 15 | **GB** | vs MIA | 77.7% | 3.0% |
| 16 | **BAL** | vs CLE | 84.7% | 2.6% |
| 17 | **BUF** | @ MIA | 80.7% | 2.1% |
| 18 | **HOU** | vs TEN | 80.2% | 1.7% |

Survive all 17: **1.66%**. Simulated with correlated rating error: 1.57% ± 0.04,
mean 3.6 weeks, median exit week 5.

Held in reserve and never needed: ARI, ATL, CAR, CLE, LAC, LV, MIA, MIN, NO,
NYG, NYJ, TB, TEN, WAS. That is the slack the plan re-routes into when a week
goes wrong — and it is why losing a pick is survivable, but burning an
expensive team early is not.

---

## 6. Opportunity cost — the real price of a pick

This is the number that decides everything. A team's win probability is not its
price; its price is what the rest of the season looks like once it is gone.
Each row below is measured by re-solving the entire remaining season twice —
once with the team pinned to week 2, once pinned to its best week — not
estimated by a heuristic.

| Team | Best wk | If used wk 2 | At best wk | Cost | |
|---|---|---|---|---|---|
| **TB** | 2 | 1.656% | 1.656% | **0%** | this IS its peak |
| **SF** | 7 | 1.656% | 1.656% | **0.01%** | schedule covers the gap |
| PHI | 6 | 1.544% | 1.656% | 7% | cheap |
| LAC | 11 | 1.528% | 1.620% | 6% | cheap |
| BAL | 16 | 1.376% | 1.656% | **17%** | hoard |
| CHI | 4 | 1.372% | 1.656% | 17% | hoard |
| KC | 3 | 1.362% | 1.656% | 18% | hoard |
| DAL | 11 | 1.340% | 1.656% | 19% | hoard |
| LAR | 6 | 1.312% | 1.656% | 21% | hoard |
| SEA | 9 | 1.304% | 1.656% | 21% | hoard |
| NE | 5 | 1.259% | 1.656% | 24% | hoard |
| GB | 15 | 1.183% | 1.656% | 29% | hoard |
| HOU | 18 | 1.090% | 1.656% | 34% | hoard |

Read it as: **using Houston in week 2 costs you a third of your season.** Not
because Houston is bad this week, but because week 18 has almost nothing else
and Houston is the only team that covers it.

Three things fall out of this table:

**Win probability and price are barely related.** Baltimore is the third-best
team on the board this week at 76.6% and the fifth-most expensive decision.
Chicago is only 65.8% this week and still costs 17%, because week 4 needs them.

**Almost everything is expensive.** Eleven of the thirteen teams listed cost
15–34%. Only two are genuinely free. In week 2 of a survivor pool you have
exactly two correct answers, and roughly thirty wrong ones that all look fine.

**"Free" has two different meanings.** Tampa Bay is free because week 2 *is*
their best week — spend them at their peak and you lose nothing by definition.
San Francisco is free for the opposite reason: their best week is 7, but the
schedule has someone else for week 7, so the swap costs nothing. Both are
correct picks; only one of them is a coincidence.

### Why SF over TB

The optimiser returns TB, because maximising P(survive all 17) is indifferent
between them — TB costs 0.000%, SF costs 0.011%. You should not be indifferent.
SF wins **7.6 points more often this week** for eleven thousandths of a percent
of season survival. Same season, much safer week.

That gap exists because the product objective only scores the perfect-season
branch, and you actually care about getting deep. The report now flags this
automatically, and `--discount 0.97` makes the optimiser care about it too, for
pools that pay for lasting longest rather than going undefeated.

## 6. The data

**The full schedule is in.** All 272 games of the 2026 regular season, from the
[nflverse](https://github.com/nflverse/nfldata) `games.csv` dataset. It passes
structural validation in the test suite: every team plays exactly 17 games, no
team is double-booked in a week, and the Week 1 result (ATL 13 @ PIT 20) matches
your winning Steelers pick.

**Ratings are built from three sources**, in order of how much each knows
about December:

1. **Last season's 272 closing lines** — recency weighted (half-life 6 weeks;
   a week-18 line says more about next September than a week-1 line) and
   regressed x0.9 for offseason churn. Always available.
2. **Market season win totals** — forward looking and injury aware, inverted
   against the real schedule so a 9.5 behind a brutal schedule rates higher
   than a 9.5 behind an easy one. Supply at least 28 of 32 in
   `data/win_totals_2026.json` and the planner uses them automatically; the
   seven I could verify are in there now, which is below the threshold, so they
   are currently ignored rather than half-applied.
3. **This season's posted game lines** — the sharpest signal that exists, but
   only for weeks 1–3.

The first two form a prior; the third updates it. Held out on two weeks of the
real board:

| model | train wk1 → predict wk2 | train wk1-2 → predict wk3 | mean |
|---|---|---|---|
| home field only | 4.23 | 4.23 | 4.23 |
| 2026 lines only | 4.53 | 1.84 | 3.18 |
| + prior k=0.7 | 2.21 | 1.20 | 1.70 |
| **+ prior k=0.9** | **2.10** | **1.07** | **1.58** |
| + prior k=1.0 | 2.23 | 1.02 | 1.63 |

**A 50% cut in error**, and k=0.9 is an interior optimum rather than an edge of
the grid. One week of lines with no prior (4.53) is barely better than assuming
every team is average — which is exactly the position the planner was in before,
for weeks 4–18.

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

### Concentration: I was wrong about this

The optimiser fades **Miami in 9 of 17 weeks**. Last week I called that fragile
and told you to cap it with `--max-vs 3`. Then I simulated it, and the
simulation says the opposite.

| rating drift | implied wk-18 error | free plan | capped at 3 |
|---|---|---|---|
| 0.0 (no drift) | 1.7 pts | **1.176%** | 0.840% |
| 0.35 (default) | 2.2 pts | **1.164%** | 0.894% |
| 0.7 | 3.2 pts | **1.064%** | 0.820% |
| 1.2 (pessimistic) | 5.0 pts | **1.048%** | 0.680% |

The uncapped plan wins at every level of model uncertainty, including one where
a week-18 rating is off by five points. Capping costs roughly a quarter of your
survival and buys nothing measurable.

**Why the intuition fails:** survival is a *product* of probabilities. When the
same error moves nine terms together, `E[Π p]` is convex in that error — the
worlds where Miami is worse than modelled gain more than the worlds where Miami
is better lose. Correlated error is mildly *good* for a product, not bad.
Diversification is right when you are averaging and wrong when you are
multiplying, and survivor multiplies.

Note the scope: this is the right answer for maximising P(survive all 17 weeks).
If your pool pays out for lasting longest rather than going undefeated, the
variance you are choosing matters differently, and that is not what this
measures.

`--max-vs` still exists, and `scripts/drift_sensitivity.py` re-runs the sweep on
your own board. Just don't reach for it on instinct.

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
