"""Analyze replay JSON and output structured summary."""
import json
import sys
from collections import Counter, defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else "logs/replay/replay_seed42_1774846186.json"

with open(path) as f:
    data = json.load(f)

entries = data['entries']
num_players = data.get('num_players', 3)

# ─────── Re-derive correct round numbers ───────
# A "round" = all N players have selected a role.
# We count role selections (action_id 0-7) and increment round
# every N selections.
role_count = 0
current_round = 0
for e in entries:
    if 0 <= e['action_id'] <= 7:
        e['round'] = current_round
        role_count += 1
        if role_count >= num_players:
            # This is the last role selection of the current round.
            # Next role selection starts a new round.
            role_count = 0
            current_round += 1
    else:
        # Non-role actions belong to the round of the most recent role selection.
        # But if no role selected yet (round 0 start), keep round 0.
        e['round'] = max(0, current_round - 1) if role_count == 0 and current_round > 0 else current_round

total_rounds = entries[-1]['round']

# Group by round
rounds = defaultdict(list)
for e in entries:
    rounds[e['round']].append(e)

# ─────── Helper: classify action ─────── 
def classify(e):
    a = e['action_id']
    if 0 <= a <= 7: return 'role'
    if (8 <= a <= 14) or a == 105: return 'settler'
    if a == 15: return 'pass'
    if 16 <= a <= 38: return 'build'
    if 39 <= a <= 43: return 'trade'
    if 44 <= a <= 63: return 'captain'
    if 64 <= a <= 68: return 'store_windrose'
    if 69 <= a <= 72: return 'mayor'
    if 93 <= a <= 97: return 'craftsman'
    if 106 <= a <= 110: return 'store_warehouse'
    return 'other'

# ─────── Per-player stats ───────
player_stats = {i: {
    'roles_selected': Counter(),
    'buildings_built': [],
    'goods_traded': Counter(),
    'goods_shipped': Counter(),
    'ship_vp_events': 0,
    'value_estimates': [],
    'role_confidences': [],
    'build_confidences': [],
    'captain_confidences': [],
    'settler_actions': [],
} for i in range(3)}

for e in entries:
    p = e['player']
    cat = classify(e)
    top = e.get('top_actions', [])
    conf = top[0]['prob'] if top else None
    val = e.get('value_estimate', None)
    
    if val is not None:
        player_stats[p]['value_estimates'].append((e['round'], val))
    
    if cat == 'role':
        role = e.get('role_selected', '?')
        player_stats[p]['roles_selected'][role] += 1
        if conf: player_stats[p]['role_confidences'].append(conf)
    elif cat == 'build':
        bname = e['action'].split('Build ')[1].split(' (')[0]
        player_stats[p]['buildings_built'].append((e['round'], bname))
        if conf: player_stats[p]['build_confidences'].append(conf)
    elif cat == 'trade':
        gname = e['action'].split('Sell ')[1].split(' (')[0]
        player_stats[p]['goods_traded'][gname] += 1
    elif cat == 'captain':
        gname = e['action'].split('Load ')[1].split(' onto')[0].split(' via')[0]
        player_stats[p]['goods_shipped'][gname] += 1
        player_stats[p]['ship_vp_events'] += 1
        if conf: player_stats[p]['captain_confidences'].append(conf)
    elif cat == 'settler':
        player_stats[p]['settler_actions'].append((e['round'], e['action']))

# ─────── Print phase-by-phase ───────
def print_phase(title, r_start, r_end):
    print(f"\n{'='*80}")
    print(f"  {title} (Rounds {r_start}-{r_end})")
    print(f"{'='*80}")
    
    for r_num in range(r_start, min(r_end + 1, total_rounds + 1)):
        if r_num not in rounds: continue
        r_entries = rounds[r_num]
        
        # Role selections
        roles = [(e['player'], e.get('role_selected','?'), e.get('top_actions',[]), e.get('value_estimate'), e.get('commentary','')) 
                 for e in r_entries if classify(e) == 'role']
        builds = [(e['player'], e['action'], e.get('top_actions',[]))
                  for e in r_entries if classify(e) == 'build']
        trades = [(e['player'], e['action'], e.get('top_actions',[]))
                  for e in r_entries if classify(e) == 'trade']
        ships = [(e['player'], e['action']) for e in r_entries if classify(e) == 'captain']
        settlers = [(e['player'], e['action'], e.get('top_actions',[]))
                    for e in r_entries if classify(e) == 'settler']
        
        if not (roles or builds or trades or ships or settlers):
            # Mayor-only or pass-only round
            role_only = [(e['player'], e.get('role_selected','?')) for e in r_entries if classify(e) == 'role']
            if role_only:
                r_str = ", ".join([f"P{p}→{r}" for p,r in role_only])
                print(f"  R{r_num:2d} [{r_str}]")
            continue
        
        # Roles
        for p, role, top, val, cmt in roles:
            conf = top[0]['prob'] if top else 0
            alts = ", ".join([f"{t['action'].replace('Select Role: ','')}({t['prob']:.0%})" for t in top[1:3]]) if len(top)>1 else ""
            val_str = f"V={val:.3f}" if val else ""
            cmt_str = f" | {cmt}" if cmt else ""
            print(f"  R{r_num:2d} P{p}→{role} (conf={conf:.0%}) {val_str}{cmt_str}")
            if alts:
                print(f"       Alternatives: {alts}")
        
        # Settlers
        for p, act, top in settlers:
            conf = top[0]['prob'] if top else 0
            short = act.replace('Settler: ','')
            alts = ", ".join([f"{t['action'].replace('Settler: ','')}({t['prob']:.0%})" for t in top[1:3]]) if len(top)>1 else ""
            print(f"       P{p} Settle: {short} (conf={conf:.0%})")
            if alts:
                print(f"         ↳ Alt: {alts}")
        
        # Builds
        for p, act, top in builds:
            conf = top[0]['prob'] if top else 0
            short = act.replace('Builder: ','')
            alts = ", ".join([f"{t['action'].replace('Builder: ','')}({t['prob']:.0%})" for t in top[1:3]]) if len(top)>1 else ""
            print(f"       P{p} Build: {short} (conf={conf:.0%})")
            if alts:
                print(f"         ↳ Alt: {alts}")
        
        # Trades
        for p, act, top in trades:
            conf = top[0]['prob'] if top else 0
            short = act.replace('Trader: ','')
            print(f"       P{p} Trade: {short} (conf={conf:.0%})")
        
        # Ships (summarize)
        if ships:
            ship_summary = Counter()
            for p, act in ships:
                gname = act.split('Load ')[1].split(' onto')[0].split(' via')[0]
                ship_summary[f"P{p}:{gname}"] += 1
            s = ", ".join([f"{k}" for k in ship_summary])
            print(f"       Captain: {s} ({len(ships)} loads)")

# Execute — dynamic phase boundaries based on actual round count
early_end = total_rounds // 3
mid_end = 2 * total_rounds // 3
print_phase("EARLY GAME — Foundation Building", 0, early_end)
print_phase("MID GAME — Production & Shipping Engine", early_end + 1, mid_end)
print_phase("LATE GAME — Scoring & Endgame", mid_end + 1, total_rounds)

# ─────── Per-player Strategic Summary ───────
print(f"\n{'='*80}")
print(f"  PER-PLAYER STRATEGIC SUMMARY")
print(f"{'='*80}")

for i in range(3):
    ps = player_stats[i]
    score = data['final_scores'][i]
    winner = " ★" if score['winner'] else ""
    print(f"\n  Player {i}{winner}: {score['vp']} VP (TB={score['tiebreaker']})")
    print(f"  {'─'*40}")
    
    # Roles
    print(f"  Roles chosen: {dict(ps['roles_selected'])} (total: {sum(ps['roles_selected'].values())})")
    if ps['role_confidences']:
        avg_rc = sum(ps['role_confidences'])/len(ps['role_confidences'])
        print(f"  Avg role confidence: {avg_rc:.1%}")
    
    # Buildings
    print(f"  Buildings ({len(ps['buildings_built'])} total):")
    for r, b in ps['buildings_built']:
        print(f"    R{r:2d}: {b}")
    
    # Trade
    if ps['goods_traded']:
        print(f"  Traded: {dict(ps['goods_traded'])}")
    
    # Shipping
    if ps['goods_shipped']:
        print(f"  Shipped: {dict(ps['goods_shipped'])} ({ps['ship_vp_events']} events)")
    
    # Value trajectory
    vals = ps['value_estimates']
    if vals:
        early_vals = [v for r,v in vals if r <= early_end]
        mid_vals = [v for r,v in vals if early_end < r <= mid_end]
        late_vals = [v for r,v in vals if r > mid_end]
        e_avg = sum(early_vals)/len(early_vals) if early_vals else 0
        m_avg = sum(mid_vals)/len(mid_vals) if mid_vals else 0
        l_avg = sum(late_vals)/len(late_vals) if late_vals else 0
        print(f"  V(s) trajectory: Early={e_avg:.3f} → Mid={m_avg:.3f} → Late={l_avg:.3f}")

# ─────── Key strategic questions ───────
print(f"\n{'='*80}")
print(f"  KEY STRATEGIC METRICS")
print(f"{'='*80}")

# Count total role selections
all_roles = Counter()
for i in range(3):
    all_roles.update(player_stats[i]['roles_selected'])
print(f"\n  Overall role frequency: {dict(all_roles)}")

# Captain phase metrics
total_ships = sum(ps['ship_vp_events'] for ps in player_stats.values())
print(f"  Total shipping events: {total_ships}")

# Mayor frequency
mayor_count = all_roles.get('Mayor', 0)
print(f"  Mayor selected: {mayor_count} times across {total_rounds} rounds")

print()
