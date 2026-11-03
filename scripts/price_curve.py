"""What has a player projected for X points cost in this league, and is it rising?

Fits log(price) = a + b * points_over_replacement + c * run_index on every
completed auction (skill positions; QBs reported separately), using both the
winning bid and the runner-up bid (the runner-up is the real 'market' price).
"""
import json, math, sys
import numpy as np

bids = json.load(open("data/guillotine_bids.json"))
proj = json.load(open("data/guillotine_auction_proj.json"))["proj"]
REPL = {"RB": 8.5, "WR": 8.5, "TE": 6.5, "QB": 13.0}
FAILED = {("Rashee Rice", "Suite Shooters"), ("Bucky Irving", "taranteen")}
rows = []
for i, run in enumerate(bids["runs"]):
    for name, a in run["auctions"].items():
        key = f"{run['date']}|{name}"
        if key not in proj:
            continue
        live = sorted((v for t, v in a["bids"].items() if (name, t) not in FAILED), reverse=True)
        top, second = live[0], (live[1] if len(live) > 1 else 0)
        serious = sum(v >= 0.5 * top for v in live)
        rows.append(dict(run=i, date=run["date"], name=name, pos=a["pos"], pts=proj[key][0],
                         edge=proj[key][0] - REPL[a["pos"]], top=top, second=second, bidders=serious))

skill = [r for r in rows if r["pos"] != "QB" and r["top"] >= 5]
X = np.array([[1.0, r["edge"], r["run"]] for r in skill])
for label, col in (("winning bid", "top"), ("runner-up bid", "second")):
    y = np.array([math.log(max(r[col], 1)) for r in skill])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    print(f"{label:13s}: log$ = {coef[0]:.2f} + {coef[1]:.3f}*edge + {coef[2]:.3f}*run   "
          f"(+1 pt over repl = x{math.exp(coef[1]):.2f}, each run = x{math.exp(coef[2]):.2f}, resid sd {resid.std():.2f})")
    if col == "top":
        fit_top = coef; sd_top = resid.std()
    else:
        fit_2nd = coef

print("\nAuction log (skill positions):")
print(f"{'date':10s} {'player':18s} pos  proj  edge   won  2nd  model-won  serious")
for r in sorted(skill, key=lambda r: (r['date'], -r['top'])):
    m = math.exp(fit_top[0] + fit_top[1] * r["edge"] + fit_top[2] * r["run"])
    print(f"{r['date']:10s} {r['name']:18s} {r['pos']:3s} {r['pts']:5.1f} {r['edge']:5.1f} {r['top']:5d} {r['second']:4d} {m:9.0f}  {r['bidders']}")

print("\nQBs:", ", ".join(f"{r['name']} {r['pts']:.1f}pts -> ${r['top']} (2nd ${r['second']})" for r in rows if r["pos"] == "QB"))

nxt = len(bids["runs"])  # next run index
print(f"\nBaseline for the NEXT run (run index {nxt}), RB/WR (replacement 8.5):")
print(" proj   expected winning bid   middle 2/3 range   expected runner-up")
for pts in (10, 12, 14, 16, 18, 20, 22):
    e = pts - 8.5
    mid = math.exp(fit_top[0] + fit_top[1] * e + fit_top[2] * nxt)
    sec = math.exp(fit_2nd[0] + fit_2nd[1] * e + fit_2nd[2] * nxt)
    print(f" {pts:4d}   ${mid:6.0f}              ${mid*math.exp(-sd_top):4.0f}-${mid*math.exp(sd_top):4.0f}        ${sec:5.0f}")

