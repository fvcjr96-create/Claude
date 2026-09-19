# Claude — fantasy football planners

Two planners, both stdlib-only Python 3.11.

- **[Guillotine waiver optimizer](#guillotine-waiver-optimizer)** — FAAB bids priced off survival probability
- **[NFL survivor planner](#nfl-survivor-planner)** — whole-season pick allocation, solved exactly

---

# Guillotine waiver optimizer

Optimal FAAB bids for a 16-team guillotine league, where the lowest score each
week is chopped. Bids are priced off **survival probability**, not projected
points: the model simulates the rest of the season week by week, removing the
low team each time, and asks what a given add is worth to your chance of still
being alive at the end.

No third-party dependencies — Python 3.11 standard library only.

## Use it

```bash
# this week's plan
python3 -m guillotine data/week02.json

# machine-readable
python3 -m guillotine data/week02.json --json

# start next week's snapshot
python3 -m guillotine data/week02.json --rollover data/week03.json --chopped "Team X"

python3 -m unittest discover -s tests -t .
```

`STRATEGY.md` is the season-long plan: what to buy in each phase, when to spend,
and the standing rules.

## What comes out

```
 Projected score : 111.38   (rank 4 of 15)
 Chop risk       :  4.57%  this week
 Season equity   : 0.2301   |  win the league 9.3%   |  expected 8.1 more weeks alive

  PLAYER             POS    +PTS   CHOP    MAX    BID  WIN%  50/50
  Puka Nacua         WR    10.02  2.71%   $596   $465   27%   $583
  Rashee Rice        WR     5.02  3.44%   $413   $316   27%   $402
  ...
  Jared Goff         QB     0.00  4.57%     $0     $0    0%   $218
```

- **+PTS** — points the add puts in your *starting* lineup. A bench stash scores
  zero and cannot save you from the chop, so it gets a $0 bid.
- **MAX** — the ceiling. Past this, the equity lost with the budget outweighs the
  player.
- **BID** — the recommendation, after pricing in that a losing blind bid is free.
- **50/50** — what the model thinks wins the auction half the time.

## How it prices a bid

1. **Lineup** (`lineup.py`) — best legal QB/RB/RB/WR/WR/TE/FLEX/FLEX, brute-forced
   over how the two flex spots split across RB/WR/TE.
2. **Survival** (`sim.py`) — each team's weekly score is its projection plus
   noise, with a shared week-wide component. The season is played out; the low
   team is chopped; survivors drift up as they pick over the chopped roster.
   Equity weights surviving deep more heavily than surviving one more week.
   Scenarios share random draws (common random numbers), so the *difference*
   an add makes is measured far more precisely than either level.
3. **Market** (`market.py`) — rivals bid a lognormal share of their own budget,
   scaled by the player's edge over replacement and gated by a participation
   probability. This gives `P(win | bid)` and is why every rival's budget needs
   to be in the config: a broke field is cheap to outbid.
4. **Price** (`engine.py`) — leftover budget is worth `V(B) = (B/B₀)^α`. The
   ceiling solves `E_with · V(B−b) = E_without · V(B)`; the recommendation
   maximises `P(win)·E_with·V(B−b) + (1−P(win))·E_without`. α fades to zero as
   waiver cycles run out, so the endgame correctly says *spend everything*.

## Weekly update

Everything the model needs is in one JSON file per week (`data/weekNN.json`):
your roster with projections, every rival's projection **and budget**, and the
waiver pool. `--rollover` writes next week's skeleton with the roster carried
over and every rival flagged `estimated` until you overwrite it.

The knobs live in `settings` in that file — `budget_alpha` (how much holding
budget is worth), `market_aggression`, `min_reserve`, and the per-position
variance assumptions. `config.py` documents each one.

## Known gaps in the current snapshot

`data/week02.json` is built from screenshots and the tool warns about both:
ranks 10–15 on the CHOP tab were scrolled off and are straight-line estimates,
and the bench is not in the roster, so adds are priced as if a roster spot is
free. Fill both in for real numbers.


---

# NFL survivor planner

One pick a week, each team usable once. That makes it a **season-long
assignment problem**, not 17 weekly ones — and greedily picking the weekly
favourite is how pools get lost. `survivor/assign.py` solves it exactly with the
Hungarian algorithm (verified against brute force), maximising the product of
win probabilities across every remaining week.

```bash
# whole 2026 season in one request
python3 scripts/fetch_grid.py --season 2026 --out data/survivor_2026.json

python3 scripts/build_prior.py --season 2026        # ratings prior from last season
python3 -m survivor data/survivor_2026.json --costs --simulate
python3 -m survivor data/survivor_2026.json --contrarian 1.0   # big pool
python3 scripts/tune_ridge.py data/survivor_2026.json          # re-validate ridge
python3 scripts/drift_sensitivity.py data/survivor_2026.json   # assumption sweep
```

`SURVIVOR.md` is the season plan and the Week 2 call.

## What it tells you

```
  TEAM  MATCHUP            WIN%   SEASON    COST
  MIA   @ IND             74.8%    15.1%
  LAR   @ SEA             97.5%    14.0%   -1.1%
```

A 97.5% lock is the *wrong* pick here: spending LAR now costs more later than
it gains today. `COST` is computed by re-optimising the whole remaining season
around each candidate, so it is the true price of a pick, not a heuristic.

The report also prints a **hoard list** — the teams whose absence would hurt the
plan most, i.e. the ones not to burn early.

## How the numbers are made

- **Schedule**: all 272 games of 2026 from
  [nflverse](https://github.com/nflverse/nfldata). Validated in tests — every
  team plays exactly 17 games, nobody is double-booked.
- **Opportunity cost** (`--costs`): for every team, season survival with that
  team pinned to each week. The gap between using it now and using it in its
  best week is the true price of the pick, computed by re-solving the season
  both ways rather than estimated. Win probability turns out to be a poor guide
  to it — a 76.6% team can cost 17% of your season while a 65.8% team costs the
  same, and only two teams on a typical week are genuinely free.
- **Ratings prior**: last season's 272 closing lines, recency weighted and
  regressed, optionally combined with market win totals inverted against the
  real schedule. Held out on two weeks, this cuts prediction error roughly in
  half versus using this season's lines alone (1.58 vs 3.18 pts).
- **Priced games**: de-vigged two-way moneylines where books have posted
  (weeks 1–3). Sharper than converting the spread.
- **Unpriced games**: ridge-regression power ratings fitted to every posted
  line. The penalty is chosen by held-out validation — fitting on weeks 1–2 and
  predicting week 3, ridge 0.25 gives 1.84 pts MAE against a 4.23 baseline —
  and two tests fail if the default stops beating its neighbours. Those picks
  stay flagged `model`, with their margin distribution widened by the fit's
  RMSE so a modelled 80% is not trusted like a market 80%.
- **Simulation**: `--simulate` runs the plan through 100k seasons with rating
  error drawn per *team* and carried as a random walk, so a team the model has
  wrong is wrong in all of its games, and more so further from the last posted
  line. That is the honest way to price how much of the plan is real.
- **Tiebreak**: when two picks cost the same season survival, the product
  objective is indifferent and you are not — the report flags the one that
  survives *this* week more often, and `--discount` makes the optimiser prefer
  it too.
- **Concentration**: `--max-vs N` caps how often the plan fades one opponent.
  Uncapped it fades Miami 9 times in 17 weeks, which looks reckless — but the
  simulation says capping costs a quarter of your survival and buys nothing,
  at every drift assumption tested. Survival is a *product*, so correlated
  error is mildly good for it. Measure before diversifying.
- **Popularity**: `--contrarian` penalises chalk, because surviving alongside
  60% of your pool is worth far less than surviving alongside 5%.

## Data honesty

The schedule is real and complete. Weeks 1–3 are priced from live markets;
weeks 4–18 are model estimates and are labelled as such in every report, because
a model built on three weeks of lines cannot know about November injuries. Treat
the back half as a map of where the value probably is, and re-run weekly as
books post more lines. `data/demo_synthetic.json` is a randomly generated board
for demonstration only; the CLI banners it as such.
