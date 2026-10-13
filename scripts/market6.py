import json, numpy as np
P=json.load(open('profiles.json')); ME="Chief Had A Little Sex"
BUD={"Kevin James' Knockers":912,"Scott is a lil bih ah":699,"nobodylovesme":736,"AdamKohl14":650,"Jaffe's Nose":454,"Nick burns had sex":660,"Jive Turkeys":683,"taranteen":570,"BigdogE12":351,"TheSoose":1000}
MARQ_AUCTIONS=8
# extra participation for teams whose lineup gains most (from the week-6 marginal-gain table)
NEED={"AdamKohl14":0.35,"Nick burns had sex":0.0,"Kevin James' Knockers":0.05,"taranteen":0.1}
rng=np.random.default_rng(7); N=60000
def rival_max(tier, kind):
    mx=np.zeros(N)
    for t,B in BUD.items():
        shares=np.array(P[t]['top' if kind=='top' else 'sec'] or [0.0])
        part=min(1.0,len(P[t]['top'])/MARQ_AUCTIONS+NEED.get(t,0)) if kind=='top' else 0.6
        s=rng.choice(shares,N)*np.exp(rng.normal(0,0.25,N))*tier
        bid=np.minimum(s*B,B)*(rng.random(N)<part)
        mx=np.maximum(mx,bid)
    return mx
def qb_max():   # QB/TE history: $0-28; Nick has no healthy QB this week
    nick=np.exp(rng.normal(np.log(45),0.6,N))
    others=np.exp(rng.normal(np.log(12),0.7,(N,4))).max(1)
    return np.maximum(nick,others)
def te_max(): return np.exp(rng.normal(np.log(4),0.9,N))*(rng.random(N)<0.5)
mk={'Kenneth Walker':rival_max(1.0,'top'),'Chase Brown':rival_max(0.8,'top'),
    'Rashee Rice':rival_max(1.0,'sec'),'Carnell Tate':rival_max(1.0,'sec'),
    'Jordan Love':qb_max(),'Hunter Henry':te_max()}
VALUE={'Kenneth Walker':400,'Chase Brown (no Walker)':313,'Chase Brown (with Walker)':112,'Jordan Love':40,'Hunter Henry':30,'Carnell Tate (with Walker)':60,'Rashee Rice (with Walker)':62}
for name,m in mk.items():
    q=np.percentile(m,[25,50,75,90])
    print(f"{name:15s} top rival bid: 25%={q[0]:.0f} median={q[1]:.0f} 75%={q[2]:.0f} 90%={q[3]:.0f}")
print()
for label,val in VALUE.items():
    m=mk[label.split(' (')[0]]
    bids=np.arange(1,int(val)+1)
    pw=np.array([(m<b).mean() for b in bids]); ev=pw*(val-bids)
    b=bids[ev.argmax()]
    pts=[x for x in (25,50,113,150,200,250,305,340,377,400) if x<=val]
    print(f"{label:28s} value ${val:3d} -> best bid ${b:3d} (wins {pw[b-1]*100:.0f}%) | "+' '.join(f"${x}:{(m<x).mean()*100:.0f}%" for x in pts))
