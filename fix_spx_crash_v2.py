
import os

target_file = "/root/spx_profiler_nexus.py"
print(f"Applying CRASH FIX V2 to {target_file} for WeeklyGexTable...")

old_method_sig = "def update_content(self, dates, gex_summaries):"
new_method_code = """    def update_content(self, dates, gex_summaries):
        rich_table = Table(box=box.SIMPLE, expand=True, show_header=True, header_style="bold magenta", padding=(0, 2))
        rich_table.add_column("Date", width=12); rich_table.add_column("DTE", justify="right")
        rich_table.add_column("Total GEX", justify="right"); rich_table.add_column("Spot GEX", justify="right")
        rich_table.add_column("Max Pain", justify="right"); rich_table.add_column("Vol POC", justify="right")
        rich_table.add_column("Flip Pt", justify="right")
        rich_table.add_column("Accel (R)", justify="right"); rich_table.add_column("Pin (S)", justify="right")
        rich_table.add_column("P/C (Vol)", justify="right"); rich_table.add_column("P/C (OI)", justify="right")
        
        if not gex_summaries or len(dates) != len(gex_summaries): 
            rich_table.add_row("Waiting for GEX data...")
        else:
            for i, summary in enumerate(gex_summaries):
                # SAFETY: Handle None dates
                d_val = dates[i]
                if not d_val: continue
                
                date_str = d_val.strftime('%Y-%m-%d')
                dte = (d_val - get_trading_date()).days
                
                def fmt_s(val):
                    if val is None: return "N/A"
                    if CURRENT_BASIS != 0: 
                        try: spy_val = (val - CURRENT_BASIS) / 10
                        except: spy_val = 0
                        return f"${val:.0f} ({spy_val:.1f})"
                    return f"${val:.0f}"
                
                # SAFETY: Handle formatted strings
                gex = summary.get('total_gamma'); gex_str = fmt_gex(gex); gex_style = "green" if (gex or 0) > 0 else "red"
                sgex = summary.get('spot_gamma'); sgex_str = fmt_gex(sgex); sgex_style = "green" if (sgex or 0) > 0 else "red"
                
                max_pain_str = fmt_s(summary.get('max_pain_strike'))
                pin_s = fmt_s(summary.get('short_gamma_wall_below'))
                accel_r = fmt_s(summary.get('short_gamma_wall_above'))
                
                accel_type = summary.get('short_gamma_wall_above_type', 'NEG')
                accel_style = "bold cyan" if accel_type == 'POS' else "red"
                
                poc_strike = summary.get('volume_poc_strike'); poc_str = "N/A"
                if poc_strike:
                    c_vol = summary.get('volume_poc_call_vol') or 0
                    p_vol = summary.get('volume_poc_put_vol') or 0
                    poc_sent = "C" if c_vol > p_vol else "P"
                    poc_val_str = fmt_s(poc_strike)
                    poc_str = f"{poc_val_str} ([{'green' if poc_sent == 'C' else 'red'}]{poc_sent}[/])"
                
                flip_pt = summary.get('gex_flip_point')
                flip_str = fmt_s(flip_pt) if flip_pt else "N/A"
                flip_style = "bold cyan" if flip_pt else "dim"

                # CRITICAL FIX HERE: Safe handling of P/C Ratios
                pc_vol = float(summary.get('pc_ratio_volume') or 0.0)
                pc_oi = float(summary.get('pc_ratio_oi') or 0.0)

                rich_table.add_row(
                    date_str, str(dte),
                    Text(gex_str, style=gex_style), Text(sgex_str, style=sgex_style),
                    Text(max_pain_str, style="white"), Text.from_markup(poc_str, style="white"),
                    Text(flip_str, style=flip_style),
                    Text(accel_r, style=accel_style), Text(pin_s, style="white"),
                    Text(f"{pc_vol:.2f}", style="dim"), Text(f"{pc_oi:.2f}", style="dim")
                )

        self.update(Panel(rich_table, title="[bold green]Weekly GEX Structure (ORATS)[/]", border_style="green"))
"""

lines = []
with open(target_file, 'r') as f:
    lines = f.readlines()

new_lines = []
replaced = False
state = "copy" # copy, skipping

for line in lines:
    if state == "copy":
        if line.strip().startswith("def update_content(self, dates, gex_summaries):"):
            new_lines.append(new_method_code)
            state = "skipping"
            replaced = True
            print("Found target method start. Injecting safe version...")
        else:
            new_lines.append(line)
    elif state == "skipping":
        # Skip until next class definition (InfoBox)
        if line.strip().startswith("class InfoBox"):
            new_lines.append(line)
            state = "copy"
            print("Found end of target method. Resuming copy.")

if replaced:
    with open(target_file, 'w') as f:
        f.writelines(new_lines)
    print("Success! Patched WeeklyGexTable.")
else:
    print("Error: Could not find method to replace.")
