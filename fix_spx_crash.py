
import os

target_file = "/root/spx_profiler_nexus.py"
print(f"Applying CRASH FIX to {target_file} for NoneType formatting...")

# We will completely replace the format_flow_row function with a safe version
old_func_sig = "def format_flow_row(r):"
new_func_code = """def format_flow_row(r):
    # SAFETY DEFAULTS for 14-Day History (prevent NoneType crashes)
    edge_val = r.get('edge') or 0.0
    stk_val = float(r.get('stk') or 0.0)
    be_val = float(r.get('be') or 0.0)
    z_val = float(r.get('z_score') or 0.0)
    mkt_val = float(r.get('mkt') or 0.0)
    win_val = float(r.get('win') or 0.0)
    prem_val = float(r.get('prem') or 0.0)
    vol_val = float(r.get('vol') or 0.0)
    oi_val = float(r.get('oi') or 0.0)
    
    style_base = "bold " if r.get('is_golden') else "dim "
    
    edge_txt = Text(f"{edge_val:+.1f}%", style="bold green" if edge_val>1.5 else ("bold red" if edge_val<-1.5 else "dim white"))
    
    conf_raw = r.get('conf') or ""
    conf_clean = conf_raw.replace('STRONG ','').replace('CAUTION ','')
    if r.get('is_golden'): conf_clean = "★ " + conf_clean
    conf_style = "bold green" if "BULL" in conf_raw else ("bold red" if "BEAR" in conf_raw else "dim white")
    
    if CURRENT_BASIS != 0: 
        spy_equiv = (stk_val - CURRENT_BASIS) / 10
        stk_str = f"${stk_val:.0f} ({spy_equiv:.1f}) {r.get('type','?')}"
    else: 
        spy_equiv = stk_val / 10
        stk_str = f"${stk_val:.0f} ({spy_equiv:.0f}) {r.get('type','?')}"
        
    contract_class = "green" if r.get('type')=='C' else "red"
    contract_txt = Text(stk_str + "   ", style=style_base + contract_class)
    
    side_tag = r.get('side_tag') or "?"
    side_color = "green" if side_tag == "(BOT)" else ("red" if side_tag == "(SOLD)" else "white")
    side_txt = Text(f" {side_tag} ", style=f"bold {side_color}")
    
    try: 
        d_obj = datetime.datetime.strptime(r.get('exp',''), '%Y-%m-%d')
        date_short = d_obj.strftime('%b %d')
    except: 
        date_short = str(r.get('exp','?'))
        
    edge_padded = Text(f" {edge_val:+.1f}% ", style="bold green" if edge_val>1.5 else ("bold red" if edge_val<-1.5 else "dim white"))
    conf_padded = Text(f" {conf_clean} ", style=conf_style)
    be_padded = f" ${be_val:.2f} "
    
    z_style = "bold white on red" if r.get('is_whale') else ("bold yellow" if abs(z_val) > 2.0 else "dim white")
    z_txt = Text(f"{z_val:.1f}σ", style=z_style)
    
    vol_oi_ratio = vol_val/oi_val if oi_val>0 else 100.0
    vo_txt = Text(f"{vol_oi_ratio:.1f}x" if oi_val>0 else "NEW", style="bold yellow" if (oi_val>0 and vol_oi_ratio>5) else "white")
    
    row=(date_short, str(r.get('dte','?')), contract_txt, side_txt, fmt_num(prem_val), vo_txt, f"${mkt_val:.2f}", edge_padded, conf_padded, be_padded, Text(f"{win_val:.0f}%", style="green" if win_val>60 else ("red" if win_val<40 else "white")), z_txt)
    return row

def _OLD_format_flow_row_placeholder(r):
"""

lines = []
with open(target_file, 'r') as f:
    lines = f.readlines()

new_lines = []
replaced = False
state = "copy" # copy, skipping

for line in lines:
    if state == "copy":
        if line.strip().startswith("def format_flow_row(r):"):
            new_lines.append(new_func_code)
            new_lines.append("    pass # Replaced by safe version\n")
            state = "skipping"
            replaced = True
            print("Found target function start. Injecting safe version...")
        else:
            new_lines.append(line)
    elif state == "skipping":
        # Skip until end of function (heuristic: look for next def or class or dedent specific to this file struct)
        # In this file, the next thing is `return row` indented, then empty line, then `class AlertBox`
        if line.strip().startswith("class ") or (line.strip().startswith("def ") and "format_flow_row" not in line):
            new_lines.append(line)
            state = "copy"
            print("Found end of target function. Resuming copy.")

if replaced:
    with open(target_file, 'w') as f:
        f.writelines(new_lines)
    print("Success! Patched format_flow_row.")
else:
    print("Error: Could not find function definition to replace.")
