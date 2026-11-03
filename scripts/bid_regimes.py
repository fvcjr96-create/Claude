"""Do rivals bid a share of their budget, or a raw 'going rate'?

For every premium auction (a run's top-two prices) compare how tightly the
serious bids cluster in raw dollars versus as a share of each bidder's
budget at the time.  Lower spread = the better description of behaviour.
"""
import json, math, statistics as st, collections, sys

D = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "data/guillotine_bids.json"))
FAILED = {("Rashee Rice", "Suite Shooters"), ("Bucky Irving", "taranteen")}
bud = collections.defaultdict(lambda: 1000.0)
def cv(xs): return st.pstdev(xs) / st.mean(xs)
def logsd(xs): return st.pstdev([math.log(x) for x in xs])
print(f"{'run':10s} {'player':18s} {'n':>2s} {'top':>5s} {'2nd':>5s} {'med raw':>8s} {'sd log raw':>10s} {'sd log share':>12s}  corr(budget,bid)")
for run in D["runs"]:
    b0 = dict(bud)
    au = run["auctions"]
    price = {p: max(v for t, v in a["bids"].items() if (p, t) not in FAILED) for p, a in au.items()}
    for p in sorted(price, key=price.get, reverse=True)[:2]:
        bids = au[p]["bids"]; top = price[p]
        serious = {t: v for t, v in bids.items() if v >= 0.25 * top}
        raw = list(serious.values()); share = [v / b0.get(t, 1000.0) for t, v in serious.items()]
        bs = [b0.get(t, 1000.0) for t in serious]
        if len(raw) >= 3:
            mb, mv = st.mean(bs), st.mean(raw)
            cov = sum((x - mb) * (y - mv) for x, y in zip(bs, raw)); sx = math.sqrt(sum((x - mb) ** 2 for x in bs)); sy = math.sqrt(sum((y - mv) ** 2 for y in raw))
            corr = cov / (sx * sy) if sx and sy else float('nan')
            s2 = sorted(raw)[-2]
            print(f"{run['date']:10s} {p:18s} {len(raw):2d} {top:5d} {s2:5d} {st.median(raw):8.0f} {logsd(raw):10.2f} {logsd(share):12.2f}  {corr:+.2f}")
    for p, a in au.items():
        live = {t: v for t, v in a["bids"].items() if (p, t) not in FAILED}
        w = max(live, key=live.get); bud[w] -= live[w]
print("\nBudgets now:", {t: round(v) for t, v in sorted(bud.items(), key=lambda x: -x[1])})
