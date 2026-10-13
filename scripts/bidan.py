import json, numpy as np, collections
D=json.load(open('data/guillotine_bids.json'))
FAILED={('Rashee Rice','Suite Shooters'),('Bucky Irving','taranteen')}
bud=collections.defaultdict(lambda:1000.0); spent=collections.defaultdict(float); wins=collections.defaultdict(list)
top=collections.defaultdict(list)   # share of budget bid on each run's top-2 marquee players
sec=collections.defaultdict(list)
rows=[]
for run in D['runs']:
    b0=dict(bud)
    # marquee = two highest winning prices that run
    au=run['auctions']; price={p:max(v for t,v in a['bids'].items() if (p,t) not in FAILED) for p,a in au.items()}
    order=sorted(price,key=price.get,reverse=True); marquee=order[:2]; second=order[2:5]
    for p,a in au.items():
        live={t:v for t,v in a['bids'].items() if (p,t) not in FAILED}
        w=max(live,key=live.get); s=sorted(live.values(),reverse=True)
        rows.append((run['date'],p,a['pos'],w,s[0],s[1] if len(s)>1 else 0,len([v for v in s if v>=0.5*s[0]])))
        spent[w]+=s[0]; bud[w]-=s[0]; wins[w].append(f"{p} ${s[0]}")
        for t,v in a['bids'].items():
            B=b0.get(t,1000.0)
            if p in marquee: top[t].append(v/B)
            elif p in second: sec[t].append(v/B)
print("== Price paid vs runner-up (overpay = winning - 2nd)")
for r in rows:
    if r[4]>=30: print(f"{r[0]} {r[1]:18s} {r[2]} won by {r[3][:22]:22s} ${r[4]:4d}  2nd ${r[5]:4d}  overpay ${r[4]-r[5]:4d}  serious bidders {r[6]}")
print("\n== Team profiles  (share = bid / that team's budget at the time)")
alive=['Kevin James\' Knockers','Scott is a lil bih ah','nobodylovesme','Chief Had A Little Sex','AdamKohl14','Jaffe\'s Nose','Nick burns had sex','Jive Turkeys','taranteen','BigdogE12','TheSoose']
for t in alive:
    tp=top.get(t,[]); sc=sec.get(t,[])
    print(f"{t[:22]:22s} spent ${spent[t]:4.0f} left ${bud[t]:4.0f} | marquee bids {len(tp)} median share {np.median(tp) if tp else 0:.2f} max {max(tp) if tp else 0:.2f} | 2nd-tier median {np.median(sc) if sc else 0:.2f} | won: {', '.join(wins[t])}")
json.dump({t:dict(top=top.get(t,[]),sec=sec.get(t,[])) for t in alive},open('profiles.json','w'))
