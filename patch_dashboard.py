import os

DASH_FILE = "trader_dashboard_v3.py"

NEW_CODE = """    def group_positions(self, positions):
        \"\"\"
        Groups positions into spreads based on logic from nexus_spreads.py.
        Updated to support PARTIAL SPREADS and LEGGED SPREADS.
        Returns: (grouped_list, grouped_data_export, processed_ids_set)
        NOTE: V3 expects Dictionaries in grouped_display.
        \"\"\"
        from collections import defaultdict
        import copy
        import re
        import datetime
        
        # 0. Deep Copy positions to allow modification (handling remainders)
        working_positions = copy.deepcopy(positions)
        
        # 1. Map Positions by Symbol for quick lookup
        pos_map = {p.get("Symbol"): p for p in working_positions}
        grouped_display = []
        grouped_data = [] # For JSON export
        processed_syms = set() # Track symbols fully consumed

        # 2. PRIMARY PASS: Group by Timestamp (Creation Time)
        time_groups = defaultdict(list)
        for p in working_positions:
            ts = p.get("Timestamp") or p.get("DateAcquired") or p.get("Created")
            if ts:
                time_groups[ts].append(p)
        
        for ts, group in time_groups.items():
            # Filter out already processed symbols
            active_group = [p for p in group if p.get("Symbol") not in processed_syms]
            
            if len(active_group) == 2:
                p1 = active_group[0]; p2 = active_group[1]
                q1 = float(p1.get("Quantity", 0)); q2 = float(p2.get("Quantity", 0))
                
                # Check for Spread Characteristics:
                if (q1 * q2 < 0):
                    # Partial Match Logic
                    abs_q1 = abs(q1)
                    abs_q2 = abs(q2)
                    common_qty = min(abs_q1, abs_q2)
                    
                    if common_qty > 0:
                        sym1 = p1.get("Symbol"); sym2 = p2.get("Symbol")
                        short_p = p1 if q1 < 0 else p2
                        long_p = p2 if q1 < 0 else p1
                        short_sym = short_p.get("Symbol")
                        long_sym = long_p.get("Symbol")
                        
                        ratio_short = common_qty / abs(float(short_p.get("Quantity", 1)))
                        ratio_long = common_qty / abs(float(long_p.get("Quantity", 1)))
                        
                        pl_short = float(short_p.get("UnrealizedProfitLoss", 0)) * ratio_short
                        pl_long = float(long_p.get("UnrealizedProfitLoss", 0)) * ratio_long
                        val_short = float(short_p.get("MarketValue", 0)) * ratio_short
                        val_long = float(long_p.get("MarketValue", 0)) * ratio_long
                        
                        pl_net = pl_short + pl_long
                        val_net = val_short + val_long
                        
                        cost_basis = val_net - pl_net
                        pl_pct_str = "0.0%"
                        pl_pct = 0.0
                        if cost_basis != 0:
                            pl_pct = (pl_net / abs(cost_basis)) * 100
                            pl_pct_str = f"{pl_pct:+.1f}%"
                            
                        # Format Label
                        label = "SPREAD"
                        try:
                            s_tok = short_sym.strip().split()[-1]
                            l_tok = long_sym.strip().split()[-1]
                            def parse_s(tok):
                                if 'C' in tok: idx=tok.rfind('C'); typ='C'
                                elif 'P' in tok: idx=tok.rfind('P'); typ='P'
                                else: return None, None
                                return typ, float(tok[idx+1:])
                            typ_s, k_s = parse_s(s_tok)
                            typ_l, k_l = parse_s(l_tok)
                            if k_s > 10000: k_s /= 1000
                            if k_l > 10000: k_l /= 1000
                            label_prefix = "?"
                            if typ_s == 'C': 
                                if k_l < k_s: label_prefix = "DEBIT CALL"
                                else: label_prefix = "CREDIT CALL"
                            elif typ_s == 'P':
                                if k_l < k_s: label_prefix = "CREDIT PUT"
                                else: label_prefix = "DEBIT PUT"
                            label = f"{label_prefix} ({k_s:g}/{k_l:g})"
                        except: pass

                        exp_str = "-"
                        try:
                            ts_raw = short_p.get('ExpirationDate')
                            if ts_raw:
                                d = datetime.datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                                now = datetime.datetime.now(d.tzinfo); days = (d.date() - now.date()).days
                                exp_str = f"{d.strftime('%b %d')} ({days}d)"
                        except: pass

                        age_str = "?"
                        try:
                            ts_raw = short_p.get("Timestamp") or short_p.get("DateAcquired") or short_p.get("Created")
                            if ts_raw:
                                if "T" in ts_raw: dt = datetime.datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                                else: dt = datetime.datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")
                                now = datetime.datetime.now(dt.tzinfo)
                                delta = now - dt
                                if delta.days > 0: age_str = f"{delta.days}d"
                                else: age_str = f"{delta.seconds // 3600}h"
                        except: pass

                        grouped_display.append({
                            "label": label,
                            "exp": exp_str,
                            "qty": str(int(common_qty)),
                            "pl": pl_pct_str,
                            "val": f"${val_net:.2f}",
                            "key": f"AUTO|{short_sym}|{long_sym}",
                            "raw_pl": pl_net,
                            "raw_val": val_net,
                            "pl_pct": pl_pct,
                            "age": age_str
                        })
                        
                        new_q1 = abs_q1 - common_qty
                        new_q2 = abs_q2 - common_qty
                        p1['Quantity'] = new_q1 * (-1 if q1 < 0 else 1)
                        p2['Quantity'] = new_q2 * (-1 if q2 < 0 else 1)
                        
                        if new_q1 <= 0.001: processed_syms.add(sym1)
                        else: 
                            if sym1 in processed_syms: processed_syms.remove(sym1)
                        if new_q2 <= 0.001: processed_syms.add(sym2)
                        else:
                            if sym2 in processed_syms: processed_syms.remove(sym2)

        # 3. SECONDARY PASS: Loose Grouping
        orthan_map = defaultdict(list)
        for p in working_positions:
             sym = p.get("Symbol")
             if sym in processed_syms: continue
             if abs(float(p.get("Quantity",0))) < 0.001: continue
             root = sym.split()[0]
             ts_exp = p.get("ExpirationDate", "").split("T")[0]
             if root and ts_exp:
                 orthan_map[(root, ts_exp)].append(p)
                 
        for k, group in orthan_map.items():
             shorts = [p for p in group if float(p.get("Quantity",0)) < 0]
             longs = [p for p in group if float(p.get("Quantity",0)) > 0]
             shorts.sort(key=lambda x: abs(float(x.get("Quantity",0))), reverse=True)
             longs.sort(key=lambda x: abs(float(x.get("Quantity",0))), reverse=True)
             
             while shorts and longs:
                 p1 = shorts.pop(0); p2 = longs.pop(0)
                 q1 = float(p1.get("Quantity", 0)); q2 = float(p2.get("Quantity", 0))
                 common_qty = min(abs(q1), abs(q2))
                 
                 if common_qty > 0:
                        sym1 = p1.get("Symbol"); sym2 = p2.get("Symbol")
                        short_p = p1; long_p = p2
                        short_sym = short_p.get("Symbol"); long_sym = long_p.get("Symbol")

                        ratio_short = common_qty / abs(float(short_p.get("Quantity", 1)))
                        ratio_long = common_qty / abs(float(long_p.get("Quantity", 1)))
                        
                        pl_short = float(short_p.get("UnrealizedProfitLoss", 0)) * ratio_short
                        pl_long = float(long_p.get("UnrealizedProfitLoss", 0)) * ratio_long
                        val_short = float(short_p.get("MarketValue", 0)) * ratio_short
                        val_long = float(long_p.get("MarketValue", 0)) * ratio_long
                        
                        pl_net = pl_short + pl_long
                        val_net = val_short + val_long
                        
                        cost_basis = val_net - pl_net
                        pl_pct_str = "0.0%"
                        if cost_basis != 0:
                            pl_pct = (pl_net / abs(cost_basis)) * 100
                            pl_pct_str = f"{pl_pct:+.1f}%"
                        else: pl_pct=0.0

                        label = "SPREAD (LEGGED)"
                        try:
                            s_tok = short_sym.strip().split()[-1]
                            l_tok = long_sym.strip().split()[-1]
                            def parse_s(tok):
                                if 'C' in tok: idx=tok.rfind('C'); typ='C'
                                elif 'P' in tok: idx=tok.rfind('P'); typ='P'
                                else: return None, None
                                return typ, float(tok[idx+1:])
                            typ_s, k_s = parse_s(s_tok)
                            typ_l, k_l = parse_s(l_tok)
                            if k_s > 10000: k_s /= 1000
                            if k_l > 10000: k_l /= 1000
                            label_prefix = "?"
                            if typ_s == 'C': 
                                if k_l < k_s: label_prefix = "DEBIT CALL"
                                else: label_prefix = "CREDIT CALL"
                            elif typ_s == 'P':
                                if k_l < k_s: label_prefix = "CREDIT PUT"
                                else: label_prefix = "DEBIT PUT"
                            label = f"{label_prefix} ({k_s:g}/{k_l:g})"
                        except: pass

                        exp_str = "-"
                        try:
                            ts_raw = short_p.get('ExpirationDate')
                            if ts_raw:
                                d = datetime.datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                                now = datetime.datetime.now(d.tzinfo); days = (d.date() - now.date()).days
                                exp_str = f"{d.strftime('%b %d')} ({days}d)"
                        except: pass

                        age_str = "?"
                        try:
                            ts_raw = short_p.get("Timestamp") or short_p.get("DateAcquired") or short_p.get("Created")
                            if ts_raw:
                                if "T" in ts_raw: dt = datetime.datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                                else: dt = datetime.datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")
                                now = datetime.datetime.now(dt.tzinfo)
                                delta = now - dt
                                if delta.days > 0: age_str = f"{delta.days}d"
                                else: age_str = f"{delta.seconds // 3600}h"
                        except: pass

                        grouped_display.append({
                            "label": label,
                            "exp": exp_str,
                            "qty": str(int(common_qty)),
                            "pl": pl_pct_str,
                            "val": f"${val_net:.2f}",
                            "key": f"AUTO|{short_sym}|{long_sym}",
                            "raw_pl": pl_net,
                            "raw_val": val_net,
                            "pl_pct": pl_pct,
                            "age": age_str
                        })
                        
                        new_q1 = abs(q1) - common_qty
                        new_q2 = abs(q2) - common_qty
                        p1['Quantity'] = new_q1 * (-1 if q1 < 0 else 1); p2['Quantity'] = new_q2 * (-1 if q2 < 0 else 1)
                        
                        if new_q1 > 0: shorts.insert(0, p1)
                        if new_q2 > 0: longs.insert(0, p2)
                        
                        if new_q1 <= 0.001: processed_syms.add(sym1)
                        else:
                            if sym1 in processed_syms: processed_syms.remove(sym1)
                        if new_q2 <= 0.001: processed_syms.add(sym2)
                        else:
                            if sym2 in processed_syms: processed_syms.remove(sym2)

        return grouped_display, grouped_data, processed_syms
"""

with open(DASH_FILE, "r") as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if "def group_positions(self, positions):" in line:
        start_idx = i
        break

if start_idx != -1:
    # Look for return statement... but safer to find indentation break?
    # Or just look for the known return string.
    for i in range(start_idx, len(lines)):
        if "return grouped_display, grouped_data, processed_syms" in lines[i]:
            end_idx = i
            break

if start_idx != -1 and end_idx != -1:
    print(f"Replacing lines {start_idx} to {end_idx}")
    new_lines = lines[:start_idx] + [NEW_CODE] + lines[end_idx+1:]
    with open(DASH_FILE, "w") as f:
        f.writelines(new_lines)
    print("Patch applied.")
else:
    print("Could not find function bounds.")
