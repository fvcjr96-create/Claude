# Guillotine FAAB Strategy — 16 teams, $1,000 budget

The whole season reduces to one sentence: **you do not have to win, you have to
not be last.** Every rule below falls out of that, and the model in `guillotine/`
prices bids off survival probability rather than off projected points.

---

## 1. The four things that make this different from normal FAAB

**Bench players score zero.** In a redraft league a stashed breakout is an
asset. Here, a player who does not crack your eight starters contributes
literally nothing to the only thing that matters — your weekly total versus the
league minimum. The model gives a $0 bid to anyone who does not start. That is
why Jared Goff is a pass in week 2: he projects 16.3 and Baker Mayfield projects
17.68, so Goff adds exactly nothing.

**Supply spikes every single week.** A whole roster hits waivers each time
somebody gets chopped. This is why the week-2 pool has Puka Nacua in it. There
will be another pool like it next week, and the week after. Never bid as if this
is your last chance at talent — bid as if a comparable player arrives in seven
days, because one will.

**Budget has an expiry date.** FAAB you are holding when you get chopped is
worth exactly nothing. The model values leftover budget as `V(B) = (B/1000)^α`
with α ≈ 0.35, and fades α to zero as the season runs out of waiver cycles. In
the final weeks, holding money is a pure loss.

**The chop line rises all year.** The weakest team is removed every week, so the
score that survives climbs. A lineup that is comfortably mid-pack in week 2 is
last place in week 11. Standing still is losing.

---

## 2. The season in four phases

The tool prints which phase you are in. Ceilings below are what the model
computes for your current roster in a $1,000-budget field.

| Phase | Teams left | Chop risk/wk | What to buy | Ceiling on a +10 pt add |
|---|---|---|---|---|
| **LAND GRAB** | 16 → 12 | 4–7% | League-winning talent only | ~$600–650 |
| **SQUEEZE** | 11 → 8 | 8–11% | Genuine starter upgrades | ~$630–660 |
| **KNIFE FIGHT** | 7 → 5 | 15–22% | Anything that raises your floor | ~$630–735 |
| **ENDGAME** | 4 → 2 | 37–55% | Ceiling, at any price | $970 → your whole budget |

### LAND GRAB (weeks 1–4)
You are 4th of 15 with a 4.6% chop risk. You are not in danger, so **do not buy
safety — buy equity.** The only correct reason to spend big here is a player who
upgrades your starting lineup for the entire season. Depth, handcuffs and
bye-week patches are a waste of money at this stage; the six teams below you will
spend their budgets on exactly that and be broke by week 8.

Rule of thumb: **one big swing, then nothing.** Spend up to ~50% of budget on a
top-12-at-his-position add, and otherwise bid under $25.

### SQUEEZE (weeks 5–9)
The soft teams are gone and the chop line is climbing fast. This is where a
dollar converts into weekly points most efficiently, because you can still find
real starters and the field's budgets are thinning. Target the 2–4 point weekly
upgrades that cost $100–250 — the ones nobody wants to pay for.

Bye weeks bite here. A week where you cannot fill eight slots is a near-certain
chop, so this is the one phase where a bench body is genuinely worth money.

### KNIFE FIGHT (weeks 10–13)
15–22% chop risk per week. Variance is now your enemy, not your friend: raise
your floor. Prefer a reliable 12-point starter over a boom-bust 14-point one —
the model rewards this automatically, because chop probability depends on the
downside tail, not the mean.

Spend down toward your reserve. Budget held past week 13 rarely gets used well.

### ENDGAME (final 4 teams)
`remaining_cycles` hits zero and the model's α goes to zero with it: **bid your
entire budget on anything that helps.** With two teams left you are in a
one-week shootout where you need the higher score, so the variance logic
inverts — now you want ceiling, not floor. Leaving $300 unspent in the final
week is strictly dominated.

---

## 3. The weekly process

1. **After the chop posts**, screenshot CHOP, TEAM, PLAYERS > Available, and the
   budgets on LEAGUE.
2. `python3 -m guillotine data/weekNN.json --rollover data/weekNN+1.json --chopped "<team>"`
3. Fill in the skeleton: every rival projection, every budget (yours *and*
   theirs — the model bids differently against a broke field), your own roster
   including the bench, and the new waiver pool.
4. `python3 -m guillotine data/weekNN+1.json`
5. Enter the **BID** column, in the order the tool prints, as conditional claims.

### Reading the output
- **MAX** is the ceiling: past this, the budget you burn costs more equity than
  the player adds. Never exceed it, however tempting the player is.
- **BID** is the recommendation: it already prices in that a losing blind bid
  costs nothing, so it sits below MAX when the market is expensive and at MAX
  when the player is worth more to you than to the field.
- **WIN%** is deliberately allowed to be low. A 27% shot at Nacua for $465 beats
  a 70% shot for $750 — you keep the budget in the 73% of worlds you lose.

### Bidding mechanics that actually matter
- Bids are blind and losing is free, so **always stack fallbacks**. The tool's
  fallback prices already assume your lead claim failed.
- Cap total exposure at budget minus reserve and order claims so the platform
  stops when the money runs out.
- Bid odd numbers ($465, not $450). Ties are common at round numbers and the
  tiebreaker will not be kind.

---

## 4. Standing rules

1. **Never bid on a player who does not start.** Zero exceptions before the
   ENDGAME phase.
2. **Never bid above MAX**, even for a name you like.
3. **Do not buy insurance in LAND GRAB.** Your 4.6% chop risk is not worth
   paying down; it is cheaper to be chopped in week 3 with a full budget than to
   reach week 10 broke.
4. **Update every rival's budget weekly.** Bid prices fall hard once the field
   is spent — the same player who costs $583 against a rich field costs a
   fraction of it against a broke one.
5. **Re-read your own bench before bidding.** The model prices adds as if a
   roster spot is free until you tell it otherwise.
6. **Spend it all by the end.** Leftover FAAB has never won a guillotine league.

---

## 5. The week 2 call

Projected 111.38, 4th of 15, 4.57% chop risk, full $1,000.

**Primary: Puka Nacua — bid $465.** He replaces Rome Odunze in the flex for
+10.02 points a week, which drops your chop risk from 4.57% to 2.71% *and* holds
that edge for the rest of the season. Ceiling is $596; the model takes the lower
number because losing costs nothing. This is the one big swing LAND GRAB allows.

**Fallbacks, in order:** Rashee Rice $316, Tetairoa McMillan $267, Tucker Kraft
$233. Each assumes the claim above it failed. Do not let more than one land —
their values are computed against the same flex slot and stacking them buys the
same points twice.

**Jared Goff: no bid.** Mayfield already projects higher.

The numbers assume ranks 10–15 on the CHOP tab (scrolled off your screenshot)
and everyone's budget at $1,000. Fill in the real values and re-run before you
submit.
