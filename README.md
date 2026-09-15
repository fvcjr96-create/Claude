# Claude — Guillotine waiver optimizer

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
